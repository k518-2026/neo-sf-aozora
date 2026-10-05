import unittest
from pathlib import Path

from src.config import SMTPConfig
from src.post_formatter import format_post_content, parse_markdown_with_frontmatter
from src.mail_sender import WordPressMailSender
from src.history_manager import HistoryManager
from src.story_generator import StoryGenerator
from src.x_poster import XPoster, build_x_post_text, calc_x_weight, build_oauth1_header

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
            use_jetpack_shortcodes=True,
            blogger_post_email="testuser.secret@blogger.com"
        )

    def test_story_file_exists(self):
        self.assertTrue(self.story_path.exists(), "Story file should exist in content/story.md")

    def test_parse_frontmatter(self):
        meta, body = parse_markdown_with_frontmatter(str(self.story_path))
        self.assertIn("title", meta)
        self.assertTrue("十八時の音楽浴" in meta["title"])
        self.assertIn("categories", meta)
        self.assertTrue(len(body) > 1000, "Body should have substantial length")

    def test_history_manager_and_catalog(self):
        mgr = HistoryManager()
        self.assertTrue(len(mgr.catalog) >= 10, "Catalog should have at least 10 works")
        next_work = mgr.select_next_work()
        self.assertIsNotNone(next_work, "Should find next unposted work")
        posted_ids = mgr.get_posted_ids()
        # Verify that the selected work has NOT yet been posted
        self.assertNotIn(next_work["id"], posted_ids, "Selected work must not be in already-posted history")
        # Verify specific lookup
        specific_work = mgr.select_next_work(work_id="unno-18-music")
        self.assertEqual(specific_work["id"], "unno-18-music", "Specific work lookup should return correct work")

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

    def test_dry_run_send_and_blogger_clean_format(self):
        formatted = format_post_content(str(self.story_path))
        # WordPress version has Jetpack shortcodes
        self.assertIn("[status publish]", formatted.content_html)
        # Blogger clean version omits Jetpack shortcodes so Blogger doesn't print them literally
        self.assertNotIn("[status publish]", formatted.content_html_clean)
        self.assertNotIn("[category ", formatted.content_html_clean)
        self.assertNotIn("[tags ", formatted.content_html_clean)

        sender = WordPressMailSender(self.config)
        wp_msg = sender.create_mime_message(formatted, for_blogger=False)
        blogger_msg = sender.create_mime_message(formatted, for_blogger=True)
        self.assertEqual(wp_msg["To"], "secret_post@post.wordpress.com")
        self.assertEqual(blogger_msg["To"], "testuser.secret@blogger.com")

        result = sender.send_post(formatted, dry_run=True)
        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["to"], "secret_post@post.wordpress.com")
        self.assertEqual(result["blogger_to"], ["testuser.secret@blogger.com"])

    def test_links_stripped_and_plain_doi_preserved(self):
        import re
        formatted = format_post_content(str(self.story_path))
        links = re.findall(r'<a\b[^>]*>', formatted.content_html)
        self.assertEqual(len(links), 0, "All <a href='...'> tags should be stripped for anti-spam safety")
        self.assertNotIn("http://", formatted.content_html)
        self.assertNotIn("https://", formatted.content_html)
        self.assertNotIn("http://", formatted.content_plain)
        self.assertNotIn("https://", formatted.content_plain)
        self.assertIn("DOI: 10.1038/s41467-022-28205-y", formatted.content_html)
        self.assertIn("DOI: 10.1038/s41467-022-28205-y", formatted.content_plain)

    def test_x_post_formatting_all_catalog_works(self):
        mgr = HistoryManager()
        for work in mgr.catalog:
            reboot_title = f"{work['title']}――現代先端科学によるハードSFリブート"
            for url in ("", "https://example.wordpress.com"):
                post_text = build_x_post_text(work, reboot_title=reboot_title, site_url=url)
                weight = calc_x_weight(post_text)
                self.assertLessEqual(weight, 280, f"X post weight exceeded 280 for {work['id']}: {weight}")
                self.assertIn(f"📖原典：{work['author']}『{work['title']}』", post_text)
                self.assertIn("🔬SFリブートの視点：", post_text)

    def test_x_poster_dry_run_and_oauth_header(self):
        mgr = HistoryManager()
        work = mgr.catalog[0]
        poster = XPoster(self.config)
        res = poster.post_update(work=work, reboot_title="十八時の音楽浴――ソノジェネティクス・シンフォニー", dry_run=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertLessEqual(res["weight"], 280)

        header = build_oauth1_header(
            method="POST",
            url="https://api.x.com/2/tweets",
            api_key="key123",
            api_secret="sec456",
            access_token="tok789",
            access_token_secret="toksec012",
            nonce="fixednonce",
            timestamp="1700000000"
        )
        self.assertTrue(header.startswith("OAuth "))
        self.assertIn('oauth_consumer_key="key123"', header)
        self.assertIn('oauth_signature=', header)

    def test_stock_file_detection_and_unstocked_selection(self):
        mgr = HistoryManager()
        # 'unno-18-music' has content/story.md
        stock_1 = mgr.find_stock_file_for_work("unno-18-music")
        self.assertIsNotNone(stock_1)
        self.assertTrue(stock_1.exists())
        # Verify unstocked works returns a list of dicts
        unstocked = mgr.select_unstocked_works(count=2)
        self.assertIsInstance(unstocked, list)
        for w in unstocked:
            self.assertNotIn(w["id"], mgr.get_posted_ids())

    def test_image_attachment_in_mime_message(self):
        import tempfile
        import base64
        # 1x1 valid transparent PNG
        tiny_png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test_story.md"
            png_path = Path(tmpdir) / "test_story.png"
            md_path.write_text("---\ntitle: \"テストSF作品\"\n---\n本文テスト", encoding="utf-8")
            png_path.write_bytes(tiny_png)

            formatted = format_post_content(str(md_path))
            self.assertEqual(formatted.image_path, str(png_path))

            sender = WordPressMailSender(self.config)
            wp_msg = sender.create_mime_message(formatted, for_blogger=False)
            blogger_msg = sender.create_mime_message(formatted, for_blogger=True)

            self.assertEqual(wp_msg.get_content_Type() if hasattr(wp_msg, "get_content_Type") else wp_msg.get_content_type(), "multipart/mixed")
            self.assertEqual(blogger_msg.get_content_type(), "multipart/mixed")
            payloads = wp_msg.get_payload()
            self.assertEqual(len(payloads), 2)
            self.assertEqual(payloads[1].get_content_type(), "image/png")

if __name__ == "__main__":
    unittest.main()
