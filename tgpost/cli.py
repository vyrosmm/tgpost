"""Command line interface for tgpost."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
import time
from pathlib import Path

from . import config as cfg
from .api import Bot, TelegramError, message_link
from .markdown import split_message, to_telegram_html

__all__ = ["main"]

_MEDIA_SUFFIXES = {
    ".jpg": "photo", ".jpeg": "photo", ".png": "photo", ".webp": "photo",
    ".mp4": "video", ".mov": "video", ".m4v": "video",
}


def _resolve_token(args: argparse.Namespace) -> str:
    token = cfg.resolve("token", args.token) or cfg.resolve("bot_token")
    if not token:
        raise SystemExit(
            "No bot token. Pass --token, set TGPOST_TOKEN, or put it in .tgpost.toml.\n"
            "Create a bot with @BotFather to get one."
        )
    return token


def _resolve_chats(args: argparse.Namespace) -> list[str]:
    """One or more target chats. Repeat --chat, or comma-separate them."""
    given = getattr(args, "chat", None)
    raw: list[str] = []
    for value in (given if isinstance(given, list) else [given]):
        if value:
            raw.extend(str(value).split(","))
    if not raw:
        raw = cfg.resolve("chat").split(",")
    chats = [c.strip() for c in raw if c and c.strip()]
    if not chats:
        raise SystemExit(
            "No target chat. Pass --chat @yourchannel, set TGPOST_CHAT, or add it to\n"
            ".tgpost.toml. Remember to add the bot to the channel as an administrator."
        )
    return chats


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


def _send_document(bot: Bot, chat: str, text: str, *, preview: bool, silent: bool,
                   media: list[str], dry_run: bool, album: bool = False) -> list[dict]:
    html = to_telegram_html(text)
    chunks = split_message(html)
    if not chunks and not media:
        raise SystemExit("Nothing to send: the document is empty.")

    if dry_run:
        mode = "album" if album and len(media) > 1 else "separate"
        print(f"--- dry run [{chat}]: {len(chunks)} message(s), "
              f"{len(media)} attachment(s), {mode} ---")
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
    if album and 2 <= len(media) <= 10:
        results.extend(bot.send_media_group(chat, media, caption, silent=silent))
        return results

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
    chats = _resolve_chats(args)
    text = _read_source(args.source)
    failures = 0
    for index, chat in enumerate(chats):
        try:
            results = _send_document(bot, chat, text, preview=not args.no_preview,
                                     silent=args.silent, media=args.media or [],
                                     dry_run=args.dry_run,
                                     album=getattr(args, "album", False))
            _report(bot, chat, results)
        except TelegramError as exc:
            # One bad channel must not stop the rest.
            failures += 1
            print(f"{chat}: {exc}", file=sys.stderr)
        if index + 1 < len(chats):
            time.sleep(2)
    return 1 if failures == len(chats) else 0


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
    try:
        chats = _resolve_chats(args)
    except SystemExit:
        print("chat       (not set — pass --chat to verify posting rights)")
        return 0
    for chat_id in chats:
        try:
            chat = bot.get_chat(chat_id)
        except TelegramError as exc:
            print(f"chat       {chat_id}: {exc}")
            continue
        username = chat.get("username")
        where = f"https://t.me/{username}" if username else "(private chat)"
        print(f"chat       {chat.get('title')}  ({chat.get('type')})  {where}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tgpost",
        description="Post Markdown files to a Telegram channel. No dependencies.",
    )
    parser.add_argument("--token", help="bot token (default: $TGPOST_TOKEN)")
    parser.add_argument("--chat", action="append",
                        help="@channel or numeric id; repeat or comma-separate for several "
                             "(default: $TGPOST_CHAT or .tgpost.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    send = sub.add_parser("send", help="send a Markdown file now")
    send.add_argument("source", help="path to a .md file, or - for stdin")
    send.add_argument("--media", action="append", metavar="FILE",
                      help="attach a photo/video/document (repeatable)")
    send.add_argument("--silent", action="store_true", help="send without a notification")
    send.add_argument("--no-preview", action="store_true", help="disable link previews")
    send.add_argument("--album", action="store_true",
                      help="send 2-10 attachments as one album instead of separately")
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
    schedule.add_argument("--album", action="store_true")
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
