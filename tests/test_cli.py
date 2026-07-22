"""Tests for argument/config resolution and the send flow."""

import argparse
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tgpost import config as cfg
from tgpost.cli import _resolve_chats, _resolve_token, build_parser


def args(**kw):
    return argparse.Namespace(**kw)


class ResolveTests(unittest.TestCase):
    def setUp(self):
        for key in ("TGPOST_TOKEN", "TGPOST_CHAT", "TELEGRAM_TOKEN", "TELEGRAM_CHAT"):
            os.environ.pop(key, None)
        # keep the developer's real ~/.tgpost.toml out of the tests
        self._patch = mock.patch.object(cfg, "load_file", return_value={})
        self._patch.start()

    def tearDown(self):
        self._patch.stop()

    def test_flag_wins_over_environment(self):
        os.environ["TGPOST_TOKEN"] = "from-env"
        self.assertEqual(_resolve_token(args(token="from-flag")), "from-flag")

    def test_environment_used_when_no_flag(self):
        os.environ["TGPOST_TOKEN"] = "from-env"
        self.assertEqual(_resolve_token(args(token=None)), "from-env")

    def test_missing_token_is_a_clear_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _resolve_token(args(token=None))
        self.assertIn("BotFather", str(ctx.exception))

    def test_single_chat(self):
        self.assertEqual(_resolve_chats(args(chat=["@one"])), ["@one"])

    def test_repeated_chat_flags(self):
        self.assertEqual(_resolve_chats(args(chat=["@one", "@two"])), ["@one", "@two"])

    def test_comma_separated_chats(self):
        self.assertEqual(_resolve_chats(args(chat=["@one, @two ,@three"])),
                         ["@one", "@two", "@three"])

    def test_chats_from_environment(self):
        os.environ["TGPOST_CHAT"] = "@a,@b"
        self.assertEqual(_resolve_chats(args(chat=None)), ["@a", "@b"])

    def test_missing_chat_is_a_clear_error(self):
        with self.assertRaises(SystemExit) as ctx:
            _resolve_chats(args(chat=None))
        self.assertIn("administrator", str(ctx.exception))


class ConfigFileTests(unittest.TestCase):
    def test_config_file_is_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / cfg.FILENAME
            path.write_text('[tgpost]\ntoken = "abc"\nchat = ["@x", "@y"]\n',
                            encoding="utf-8")
            with mock.patch.object(cfg.Path, "cwd", return_value=Path(tmp)):
                data = cfg.load_file()
        self.assertEqual(data.get("token"), "abc")
        self.assertEqual(data.get("chat"), ["@x", "@y"])

    def test_broken_config_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / cfg.FILENAME).write_text("this is not toml {{{", encoding="utf-8")
            with mock.patch.object(cfg.Path, "cwd", return_value=Path(tmp)):
                self.assertEqual(cfg.load_file(), {})

    def test_missing_config_file_is_fine(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(cfg.Path, "cwd", return_value=Path(tmp)), \
                 mock.patch.object(cfg.Path, "home", return_value=Path(tmp)):
                self.assertEqual(cfg.load_file(), {})


class ParserTests(unittest.TestCase):
    def test_send_accepts_repeated_chat_and_album(self):
        parsed = build_parser().parse_args(
            ["--chat", "@a", "--chat", "@b", "send", "post.md", "--album"])
        self.assertEqual(parsed.chat, ["@a", "@b"])
        self.assertTrue(parsed.album)

    def test_schedule_requires_at(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(["schedule", "post.md"])

    def test_check_subcommand_exists(self):
        self.assertEqual(build_parser().parse_args(["check"]).command, "check")


if __name__ == "__main__":
    unittest.main()
