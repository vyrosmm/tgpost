"""Markdown -> Telegram HTML.

Telegram's Bot API accepts a *very* small HTML subset — no headings, no lists,
no tables. Everything else has to be folded into the tags it does understand:

    <b> <i> <u> <s> <a href> <code> <pre> <blockquote> <tg-spoiler>

So this module renders headings as bold lines, list items as bulleted lines, and
leaves the rest as plain text. It is deliberately small and dependency-free.
"""

from __future__ import annotations

import html
import re

__all__ = ["to_telegram_html", "split_message"]

# Telegram rejects messages over 4096 characters.
MAX_MESSAGE = 4096

_BULLET = "•"

_LINK_RE = re.compile(r"\[([^\]]+)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?[^)]*\)")
_BOLD_RE = re.compile(r"(?<!\*)\*\*(?!\s)(.+?)(?<!\s)\*\*(?!\*)", re.S)
_ITALIC_RE = re.compile(r"(?<![\*\w])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\*\w])")
_STRIKE_RE = re.compile(r"~~(?!\s)(.+?)(?<!\s)~~", re.S)
_CODE_RE = re.compile(r"`([^`\n]+)`")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_LIST_RE = re.compile(r"^\s*[-*+]\s+(.*\S)\s*$")
_ORDERED_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*\S)\s*$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


def _placeholders(text: str) -> tuple[str, list[str]]:
    """Pull fenced code blocks out before anything else touches them."""
    blocks: list[str] = []

    def stash(match: re.Match[str]) -> str:
        body = match.group(2)
        lang = (match.group(1) or "").strip()
        rendered = html.escape(body.strip("\n"))
        if lang:
            rendered = f'<code class="language-{html.escape(lang)}">{rendered}</code>'
        blocks.append(f"<pre>{rendered}</pre>")
        return f"\x00{len(blocks) - 1}\x00"

    return re.sub(r"```([^\n]*)\n(.*?)```", stash, text, flags=re.S), blocks


def _inline(text: str) -> str:
    """Escape the line, then re-introduce the inline tags Telegram allows."""
    text = _IMAGE_RE.sub(lambda m: m.group(1) or "", text)

    links: list[tuple[str, str]] = []

    def stash_link(match: re.Match[str]) -> str:
        links.append((match.group(1), match.group(2)))
        return f"\x01{len(links) - 1}\x01"

    text = _LINK_RE.sub(stash_link, text)

    codes: list[str] = []

    def stash_code(match: re.Match[str]) -> str:
        codes.append(match.group(1))
        return f"\x02{len(codes) - 1}\x02"

    text = _CODE_RE.sub(stash_code, text)
    text = html.escape(text)
    text = _BOLD_RE.sub(r"<b>\1</b>", text)
    text = _STRIKE_RE.sub(r"<s>\1</s>", text)
    text = _ITALIC_RE.sub(r"<i>\1</i>", text)

    def restore_code(match: re.Match[str]) -> str:
        return f"<code>{html.escape(codes[int(match.group(1))])}</code>"

    text = re.sub(r"\x02(\d+)\x02", restore_code, text)

    def restore_link(match: re.Match[str]) -> str:
        label, url = links[int(match.group(1))]
        return f'<a href="{html.escape(url, quote=True)}">{_inline(label)}</a>'

    return re.sub(r"\x01(\d+)\x01", restore_link, text)


def to_telegram_html(markdown_text: str) -> str:
    """Convert a Markdown document to the HTML subset Telegram understands."""
    text, blocks = _placeholders(markdown_text or "")
    out: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            out.append("")
            continue

        stashed = re.fullmatch(r"\x00(\d+)\x00", line.strip())
        if stashed:
            out.append(blocks[int(stashed.group(1))])
            continue

        if _RULE_RE.match(line):
            out.append("—" * 12)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            out.append(f"<b>{_inline(heading.group(2))}</b>")
            continue

        quote = _QUOTE_RE.match(line)
        if quote:
            out.append(f"<blockquote>{_inline(quote.group(1))}</blockquote>")
            continue

        bullet = _LIST_RE.match(line)
        if bullet:
            out.append(f"{_BULLET} {_inline(bullet.group(1))}")
            continue

        ordered = _ORDERED_RE.match(line)
        if ordered:
            out.append(f"{ordered.group(1)}. {_inline(ordered.group(2))}")
            continue

        out.append(_inline(line))

    # Collapse the runs of blank lines Markdown leaves behind.
    rendered = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return rendered.strip()


def split_message(text: str, limit: int = MAX_MESSAGE) -> list[str]:
    """Split rendered text into Telegram-sized chunks on paragraph boundaries.

    Splitting never happens inside a line, so an open tag can't be cut in half.
    """
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            cut = paragraph.rfind("\n", 0, limit)
            if cut <= 0:
                cut = limit
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks
