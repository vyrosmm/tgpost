"""A very small Telegram Bot API client built on the standard library.

Only the handful of methods `tgpost` needs are implemented. There are no third
party dependencies on purpose: the whole point of this tool is that you can drop
it onto a server and run it without a virtualenv.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

__all__ = ["TelegramError", "Bot"]

API_ROOT = "https://api.telegram.org"


class TelegramError(RuntimeError):
    """Raised when Telegram rejects a request or the network fails."""

    def __init__(self, message: str, *, code: int | None = None,
                 retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


def _multipart(fields: dict[str, Any],
               files: list[tuple[str, str, bytes]]) -> tuple[str, bytes]:
    boundary = "----tgpost" + uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        if value is None:
            continue
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()
    for name, filename, payload in files:
        ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        body += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n"
        ).encode()
        body += payload + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return f"multipart/form-data; boundary={boundary}", body


class Bot:
    """Thin wrapper around the Bot API.

    >>> bot = Bot(token)                     # doctest: +SKIP
    >>> bot.get_me()["username"]             # doctest: +SKIP
    'example_bot'
    """

    def __init__(self, token: str, *, timeout: int = 60, retries: int = 2) -> None:
        token = (token or "").strip()
        if not token:
            raise TelegramError("A bot token is required (get one from @BotFather).")
        self.token = token
        self.timeout = timeout
        self.retries = max(0, retries)

    # -- plumbing ---------------------------------------------------------
    def _request(self, method: str, request: urllib.request.Request) -> Any:
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as exc:
                raw = exc.read().decode("utf-8", "replace")
                try:
                    payload = json.loads(raw)
                except ValueError:
                    raise TelegramError(f"{method}: HTTP {exc.code}: {raw[:200]}",
                                        code=exc.code) from None
                retry_after = (payload.get("parameters") or {}).get("retry_after")
                description = payload.get("description", raw[:200])
                # 429 means we are being rate limited; Telegram tells us how long to wait.
                if exc.code == 429 and retry_after and attempt < self.retries:
                    time.sleep(int(retry_after) + 1)
                    attempt += 1
                    continue
                raise TelegramError(f"{method}: {description}", code=exc.code,
                                    retry_after=retry_after) from None
            except (urllib.error.URLError, TimeoutError) as exc:
                # Network-level failure: the request never reached Telegram, so a
                # retry cannot duplicate a message.
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
                    attempt += 1
                    continue
                raise TelegramError(f"{method}: connection failed: {exc}") from None

        if not payload.get("ok"):
            raise TelegramError(f"{method}: {payload.get('description', 'unknown error')}")
        return payload.get("result")

    def call(self, method: str, **fields: Any) -> Any:
        """Call a Bot API method with url-encoded fields."""
        data = urllib.parse.urlencode(
            {k: v for k, v in fields.items() if v is not None}
        ).encode()
        request = urllib.request.Request(
            f"{API_ROOT}/bot{self.token}/{method}",
            data=data,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._request(method, request)

    def upload(self, method: str, field: str, path: str | os.PathLike[str],
               **fields: Any) -> Any:
        """Call a Bot API method that carries a file."""
        file_path = Path(path)
        if not file_path.exists():
            raise TelegramError(f"File not found: {file_path}")
        size = file_path.stat().st_size
        if size > 50 * 1024 * 1024:
            raise TelegramError(
                f"{file_path.name} is {size / 1024 / 1024:.0f} MB; the Bot API "
                "limit for uploads is 50 MB."
            )
        ctype, body = _multipart(
            {k: v for k, v in fields.items() if v is not None},
            [(field, file_path.name, file_path.read_bytes())],
        )
        request = urllib.request.Request(
            f"{API_ROOT}/bot{self.token}/{method}",
            data=body,
            method="POST",
            headers={"Content-Type": ctype},
        )
        return self._request(method, request)

    # -- the handful of methods we actually use ---------------------------
    def get_me(self) -> dict[str, Any]:
        return self.call("getMe")

    def get_chat(self, chat: str) -> dict[str, Any]:
        return self.call("getChat", chat_id=chat)

    def send_message(self, chat: str, text: str, *, preview: bool = True,
                     silent: bool = False, reply_to: int | None = None) -> dict[str, Any]:
        return self.call(
            "sendMessage",
            chat_id=chat,
            text=text,
            parse_mode="HTML",
            link_preview_options=json.dumps({"is_disabled": not preview}),
            disable_notification="true" if silent else None,
            reply_to_message_id=reply_to,
        )

    def send_photo(self, chat: str, path: str | os.PathLike[str], caption: str = "",
                   *, silent: bool = False) -> dict[str, Any]:
        return self.upload("sendPhoto", "photo", path, chat_id=chat,
                           caption=caption or None, parse_mode="HTML",
                           disable_notification="true" if silent else None)

    def send_video(self, chat: str, path: str | os.PathLike[str], caption: str = "",
                   *, silent: bool = False) -> dict[str, Any]:
        return self.upload("sendVideo", "video", path, chat_id=chat,
                           caption=caption or None, parse_mode="HTML",
                           supports_streaming="true",
                           disable_notification="true" if silent else None)

    def send_document(self, chat: str, path: str | os.PathLike[str], caption: str = "",
                      *, silent: bool = False) -> dict[str, Any]:
        return self.upload("sendDocument", "document", path, chat_id=chat,
                           caption=caption or None, parse_mode="HTML",
                           disable_notification="true" if silent else None)


def message_link(chat: dict[str, Any], message_id: int) -> str:
    """Public t.me link for a message, when the chat has a username."""
    username = chat.get("username")
    if not username:
        return ""
    return f"https://t.me/{username}/{message_id}"
