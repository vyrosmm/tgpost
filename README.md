# tgpost

Post Markdown files to a Telegram channel from the command line.

No dependencies — just Python 3.9+ and the standard library. Copy the folder onto a
server and it runs; there is no virtualenv to build and nothing to `pip install`.

```bash
tgpost send announcement.md
```

## Why this exists

Writing channel posts directly in Telegram is fine until you want to keep them in
git, review them before they go out, or send the same post to several channels.
Telegram's own API only accepts a small HTML subset — no headings, no lists — so
pasting Markdown into `sendMessage` produces a mess.

`tgpost` renders Markdown into exactly the tags Telegram accepts, splits anything
over the 4096-character limit on paragraph boundaries, and sends it.

## Install

```bash
git clone https://github.com/vyrosmm/tgpost.git
cd tgpost
python -m tgpost --help
```

Or install it so `tgpost` is on your PATH:

```bash
pip install .
```

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
2. Add the bot to your channel **as an administrator** with permission to post.
3. Export the token and the channel:

```bash
export TGPOST_TOKEN="123456:ABC-DEF..."
export TGPOST_CHAT="@yourchannel"
```

Check that both work before you send anything real:

```bash
tgpost check
# bot        @your_bot  (id 123456)
# chat       Your Channel  (channel)
# public at  https://t.me/yourchannel
```

## Usage

```bash
# send now
tgpost send post.md

# see exactly what would be sent, without sending
tgpost send post.md --dry-run

# attach media (repeat --media for more than one)
tgpost send post.md --media cover.jpg --media clip.mp4

# no notification sound, no link preview
tgpost send post.md --silent --no-preview

# send later — absolute, clock time, or relative
tgpost schedule post.md --at "2026-07-23 09:00"
tgpost schedule post.md --at "09:00"
tgpost schedule post.md --at "+30m"

# read from stdin
cat post.md | tgpost send -
```

`schedule` stays in the foreground and sleeps until the given time, so pair it with
cron, systemd or a terminal multiplexer if it needs to survive a reboot.

## What Markdown maps to

Telegram supports very little HTML, so the renderer folds everything into what it
does accept:

| Markdown | Telegram |
| --- | --- |
| `# Heading` (any level) | bold line |
| `**bold**` / `*italic*` / `~~strike~~` | `<b>` / `<i>` / `<s>` |
| `` `code` `` and fenced blocks | `<code>` / `<pre>` |
| `- item`, `1. item` | `•  item`, `1.  item` |
| `[text](url)` | `<a href="url">text</a>` |
| `> quote` | `<blockquote>` |
| `![alt](image.png)` | the alt text (Telegram can't inline images in text) |
| `---` | a horizontal line of dashes |

Anything else is escaped and sent as plain text, so a stray `<script>` in your
document can never reach the API as markup.

## Use it as a library

```python
from tgpost import Bot, to_telegram_html

bot = Bot("123456:ABC-DEF...")
bot.send_message("@yourchannel", to_telegram_html("# Hello\n\nFrom **Python**."))
```

## Notes and limits

- Uploads are capped at 50 MB — that is the Bot API's limit, not this tool's.
- On HTTP 429 the client waits for the `retry_after` Telegram returns, then retries.
- Network failures are retried; API errors are not, because a create call that
  already reached Telegram must never be sent twice.
- Messages longer than 4096 characters are split between paragraphs, so a formatting
  tag is never cut in half.

## Tests

```bash
python -m unittest discover -s tests
```

## Who made this

Built and maintained by the team behind [VyroSMM](https://vyrosmm.net/en/), which
makes tools for growing Telegram channels. `tgpost` is the small piece we use to
publish our own posts, released on its own because it is useful without the rest.

## License

MIT — see [LICENSE](LICENSE).
