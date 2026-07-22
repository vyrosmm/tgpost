"""Command line interface for tgpost."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
import time
from pathlib import Path

from .api import Bot, TelegramError, message_link
from .markdown import split_message, to_telegram_html

__all__ = ["main"]

_MEDIA_SUFFIXES = {
    ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".webp": "photo",
    ".mp4": "video", ".mov": "video", ".m4v": "video",
}


def _env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _resolve_token(args: argparse.Namespace) -> str:
    token = args.token or _env("TGPOST_TOKEN", "TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "No bot token. Pass --token or set TGPOST_TOKEN.\n"
            "Create a bot with @BotFather to get one."
        )
    return token


def _resolve_chat(args: argparse.Namespace) -> str:
    chat = args.chat or _env("TGPOST_CHAT", "TELEGRAM_CHAT_ID")
    if not chat:
        raise SystemExit(
            "No target chat. Pass --chat @yourchannel or set TGPOST_CHAT.\n"
            "Remember to add the bot to the channel as an administrator."
        )
    return chat


def _read_source(source: str) -> str:
    if source == "-":
        return sys.stdin.read()
    path = Path(source)
    if not path.exists():
        raise SystemExit(f"No such file: {path}")
    return path.read_text(encoding="utf-8")


def _parse_when(value: str) -> dt.datetime:
    """Accept 'YYYY-MM-DD HH:MM', 'HH:MM' (today or tomorrow) or '+30m' / '+2h'."""
    value = value.strip()
    relative = re.fullmatch(r"\+(\d+)\s*([mh])", value, re.I)
    if relative:
        amount = int(relative.group(1))
        delta = dt.timedelta(minutes=amount) if relative.group(2).lower() == "m" \
            else dt.timedelta(hours=amount)
        return dt.datetime.now() + delta
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%d.%m.%Y %H:%M"):
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        clock = dt.datetime.strptime(value, "%H:%M").time()
    except ValueError:
        raise SystemExit(
            f"Could not read a time from {value!r}. "
            "Try '2026-07-23 09:00', '09:00' or '+30m'."
        ) from None
    today = dt.datetime.combine(dt.date.today(), clock)
    return today if today > dt.datetime.now() else today + dt.timedelta(days=1)


def _send_document(bot: Bot, chat: str, text: str, *, preview: bool,
                   silent: bool, media: list[str], dry_run: bool) -> list[dict]:
    html = to_telegram_html(text)
    chunks = split_message(html)
    if not chunks and not media:
        raise SystemExit("Nothing to send: the document is empty.")

    if dry_run:
        print(f"--- dry run: {len(chunks)} message(s), {len(media)} attachment(s) ---")
        for index, chunk in enumerate(chunks, 1):
            print(f"\n[message {index}, {len(chunk)} chars]\n{chunk}")
        for item in media:
            print(f"\n[attachment] {item}")
        return []

    results = []
    for index, chunk in enumerate(chunks):
        result = bot.send_message(chat, chunk, preview=preview, silent=silent)
        results.append(result)
        if index + 1 < len(chunks):
            time.sleep(1)  # stay well inside Telegram's per-chat rate limit

    caption = "" if chunks else to_telegram_html(text)[:1024]
    for item in media:
        suffix = Path(item).suffix.lower()
        kind = _MEDIA_SUFFIXES.get(suffix, "document")
        sender = {"photo": bot.send_photo, "video": bot.send_video}.get(
            kind, bot.send_document)
        results.append(sender(chat, item, caption, silent=silent))
        caption = ""
        time.sleep(1)
    return results


def _report(bot: Bot, chat_id: str, results: list[dict]) -> None:
    if not results:
        return
    try:
        chat = bot.get_chat(chat_id)
    except TelegramError:
        chat = {}
    for result in results:
        link = message_link(chat, result.get("message_id", 0))
        print(f"sent message {result.get('message_id')}" + (f"  {link}" if link else ""))


def _cmd_send(args: argparse.Namespace) -> int:
    bot = Bot(_resolve_token(args))
    chat = _resolve_chat(args)
    text = _read_source(args.source)
    results = _send_document(bot, chat, text, preview=not args.no_preview,
                             silent=args.silent, media=args.media or [],
                             dry_run=args.dry_run)
    _report(bot, chat, results)
    return 0


def _cmd_schedule(args: argparse.Namespace) -> int:
    when = _parse_when(args.at)
    delay = (when - dt.datetime.now()).total_seconds()
    if delay < 0:
        raise SystemExit(f"{when:%Y-%m-%d %H:%M} is in the past.")
    print(f"waiting until {when:%Y-%m-%d %H:%M} ({delay / 60:.0f} min)…")
    # A deliberately simple approach: tgpost stays in the foreground. Pair it with
    # cron/systemd if you want it to survive a reboot.
    try:
        time.sleep(delay)
    except KeyboardInterrupt:
        print("\ncancelled before sending")
        return 130
    return _cmd_send(args)


def _cmd_check(args: argparse.Namespace) -> int:
    bot = Bot(_resolve_token(args))
    me = bot.get_me()
    print(f"bot        @{me.get('username')}  (id {me.get('id')})")
    chat_id = args.chat or _env("TGPOST_CHAT", "TELEGRAM_CHAT_ID")
    if not chat_id:
        print("chat       (not set — pass --chat to verify posting rights)")
        return 0
    chat = bot.get_chat(chat_id)
    print(f"chat       {chat.get('title')}  ({chat.get('type')})")
    username = chat.get("username")
    print(f"public at  https://t.me/{username}" if username else "public at  (private chat)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tgpost",
        description="Post Markdown files to a Telegram channel. No dependencies.",
    )
    parser.add_argument("--token", help="bot token (default: $TGPOST_TOKEN)")
    parser.add_argument("--chat", help="@channel or numeric id (default: $TGPOST_CHAT)")
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send", help="send a Markdown file now")
    send.add_argument("source", help="path to a .md file, or - for stdin")
    send.add_argument("--media", action="append", metavar="FILE",
                      help="attach a photo/video/document (repeatable)")
    send.add_argument("--silent", action="store_true", help="send without a notification")
    send.add_argument("--no-preview", action="store_true", help="disable link previews")
    send.add_argument("--dry-run", action="store_true",
                      help="render and print, without sending")
    send.set_defaults(func=_cmd_send)

    schedule = sub.add_parser("schedule", help="send later, e.g. --at '09:00'")
    schedule.add_argument("source", help="path to a .md file, or - for stdin")
    schedule.add_argument("--at", required=True,
                          metavar="WHEN", help="'2026-07-23 09:00', '09:00' or '+30m'")
    schedule.add_argument("--media", action="append", metavar="FILE")
    schedule.add_argument("--silent", action="store_true")
    schedule.add_argument("--no-preview", action="store_true")
    schedule.add_argument("--dry-run", action="store_true")
    schedule.set_defaults(func=_cmd_schedule)

    check = sub.add_parser("check", help="verify the token and channel access")
    check.set_defaults(func=_cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TelegramError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
