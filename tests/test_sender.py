import unittest
from pathlib import Path

from src.config import SMTPConfig
from src.post_formatter import format_post_content, parse_markdown_with_frontmatter
from src.mail_sender import WordPressMailSender
from src.history_manager import HistoryManager
from src.story_generator import StoryGenerator

class TestNeoAozoraSystem(unittest.TestCase):
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

    def test_history_manager_and_catalog(self):
        mgr = HistoryManager()
        self.assertTrue(len(mgr.catalog) >= 10, "Catalog should have at least 10 works")
        next_work = mgr.select_next_work()
        self.assertIsNotNone(next_work, "Should find next unposted work")
        self.assertNotEqual(next_work["id"], "unno-18-music", "unno-18-music was already posted")
        self.assertEqual(next_work["id"], "unno-fly-man", "Second work should be fly-man")

    def test_model_fallback_candidates(self):
        gen = StoryGenerator(model_name="gemini-2.5-flash")
        candidates = gen._get_model_candidates()
        self.assertEqual(candidates[0], "gemini-2.5-flash")
        # Ensure 3.5, 3.6, 3.7, 3.8 are included
        has_35 = any("3.5" in c for c in candidates)
        has_36 = any("3.6" in c for c in candidates)
        has_37 = any("3.7" in c for c in candidates)
        has_38 = any("3.8" in c for c in candidates)
        self.assertTrue(has_35, "Should include 3.5 fallback")
        self.assertTrue(has_36, "Should include 3.6 fallback")
        self.assertTrue(has_37, "Should include 3.7 fallback")
        self.assertTrue(has_38, "Should include 3.8 fallback")

    def test_dry_run_send(self):
        formatted = format_post_content(str(self.story_path))
        sender = WordPressMailSender(self.config)
        result = sender.send_post(formatted, dry_run=True)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["to"], "secret_post@post.wordpress.com")

if __name__ == "__main__":
    unittest.main()
