# Changelog

## 0.2.0

- Post to several channels in one run — repeat `--chat` or comma-separate them. A failure
  on one channel no longer stops the others.
- New `--album` flag sends 2-10 attachments as a single Telegram album via `sendMediaGroup`.
- Optional `.tgpost.toml` config file (project folder or home directory), so the token and
  channels no longer have to be environment variables. Precedence: flag > env > file.
- `tgpost check` now verifies every configured channel, not just the first.
- 14 more tests (33 total).

## 0.1.0

- First release: `send`, `schedule` and `check`.
- Markdown rendered into the HTML subset the Bot API accepts; over-long messages split on
  paragraph boundaries.
- Photo, video and document attachments. No dependencies.
