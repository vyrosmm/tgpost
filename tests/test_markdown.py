"""Tests for the Markdown -> Telegram HTML renderer."""

import unittest

from tgpost.markdown import MAX_MESSAGE, split_message, to_telegram_html


class RenderTests(unittest.TestCase):
    def test_headings_become_bold(self):
        self.assertEqual(to_telegram_html("# Title"), "<b>Title</b>")
        self.assertEqual(to_telegram_html("### Deep"), "<b>Deep</b>")

    def test_inline_styles(self):
        self.assertEqual(to_telegram_html("**bold**"), "<b>bold</b>")
        self.assertEqual(to_telegram_html("*italic*"), "<i>italic</i>")
        self.assertEqual(to_telegram_html("~~gone~~"), "<s>gone</s>")

    def test_bullets_and_numbers(self):
        self.assertEqual(to_telegram_html("- one\n- two"), "• one\n• two")
        self.assertEqual(to_telegram_html("1. first"), "1. first")

    def test_links(self):
        self.assertEqual(
            to_telegram_html("[site](https://example.com)"),
            '<a href="https://example.com">site</a>',
        )

    def test_link_label_keeps_formatting(self):
        self.assertEqual(
            to_telegram_html("[**bold** link](https://example.com)"),
            '<a href="https://example.com"><b>bold</b> link</a>',
        )

    def test_images_reduce_to_alt_text(self):
        # Telegram cannot render inline images inside a text message.
        self.assertEqual(to_telegram_html("![a cat](cat.png)"), "a cat")

    def test_html_is_escaped(self):
        self.assertEqual(to_telegram_html("5 < 6 & 7 > 2"), "5 &lt; 6 &amp; 7 &gt; 2")

    def test_script_tags_cannot_survive(self):
        rendered = to_telegram_html("<script>alert(1)</script>")
        self.assertNotIn("<script>", rendered)
        self.assertIn("&lt;script&gt;", rendered)

    def test_url_with_ampersand_is_escaped(self):
        rendered = to_telegram_html("[x](https://e.com/?a=1&b=2)")
        self.assertIn("a=1&amp;b=2", rendered)

    def test_inline_code(self):
        self.assertEqual(to_telegram_html("run `ls -la`"), "run <code>ls -la</code>")

    def test_code_block_is_not_reformatted(self):
        rendered = to_telegram_html("```python\nx = **not bold**\n```")
        self.assertIn("<pre>", rendered)
        self.assertIn("**not bold**", rendered)
        self.assertNotIn("<b>", rendered)

    def test_blockquote(self):
        self.assertEqual(to_telegram_html("> quoted"), "<blockquote>quoted</blockquote>")

    def test_blank_line_runs_collapse(self):
        self.assertEqual(to_telegram_html("a\n\n\n\nb"), "a\n\nb")

    def test_asterisk_in_prose_is_left_alone(self):
        self.assertEqual(to_telegram_html("2 * 3 * 4"), "2 * 3 * 4")


class SplitTests(unittest.TestCase):
    def test_short_text_is_one_chunk(self):
        self.assertEqual(split_message("hello"), ["hello"])

    def test_empty_text_yields_nothing(self):
        self.assertEqual(split_message(""), [])

    def test_long_text_is_split_within_the_limit(self):
        text = "\n\n".join(f"paragraph {i} " + "x" * 300 for i in range(40))
        chunks = split_message(text)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_MESSAGE)

    def test_nothing_is_lost_when_splitting(self):
        text = "\n\n".join(f"line {i}" for i in range(2000))
        joined = " ".join(split_message(text))
        self.assertIn("line 0", joined)
        self.assertIn("line 1999", joined)

    def test_single_giant_paragraph_still_splits(self):
        chunks = split_message("y" * (MAX_MESSAGE * 2))
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), MAX_MESSAGE)


if __name__ == "__main__":
    unittest.main()
