import unittest
import os
from pathlib import Path

from src.config import SMTPConfig
from src.post_formatter import format_post_content, parse_markdown_with_frontmatter
from src.mail_sender import WordPressMailSender

class TestWordPressPostEmail(unittest.TestCase):
    def setUp(self):
        self.story_path = Path("content/story.md")
        self.config = SMTPConfig(
            host="smtp.example.com",
            port=587,
            user="author@example.com",
            password="secretpassword",
            use_tls=True,
            use_ssl=False,
            from_name="SF Test Publisher",
            wp_post_email="secret_post@post.wordpress.com",
            default_status="publish",
            use_jetpack_shortcodes=True
        )

    def test_story_file_exists(self):
        self.assertTrue(self.story_path.exists(), "Story file should exist in content/story.md")

    def test_parse_frontmatter(self):
        meta, body = parse_markdown_with_frontmatter(str(self.story_path))
        self.assertIn("title", meta)
        self.assertTrue("十八時の音響変調" in meta["title"])
        self.assertIn("categories", meta)
        self.assertTrue(len(body) > 1000, "Body should have substantial length")

    def test_post_formatter(self):
        formatted = format_post_content(
            str(self.story_path),
            status_override="draft",
            include_jetpack_shortcodes=True
        )
        self.assertEqual(formatted.status, "draft")
        self.assertIn("[status draft]", formatted.content_plain)
        self.assertIn("Martorell", formatted.content_html)
        self.assertIn("sf-story-container", formatted.content_html)

    def test_dry_run_send(self):
        formatted = format_post_content(str(self.story_path))
        sender = WordPressMailSender(self.config)
        result = sender.send_post(formatted, dry_run=True)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["to"], "secret_post@post.wordpress.com")

if __name__ == "__main__":
    unittest.main()
