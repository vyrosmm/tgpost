"""tgpost — post Markdown files to a Telegram channel, with no dependencies."""

from .api import Bot, TelegramError
from .markdown import split_message, to_telegram_html

__version__ = "0.1.0"
__all__ = ["Bot", "TelegramError", "to_telegram_html", "split_message", "__version__"]
