import argparse
import sys
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config import get_config
from src.history_manager import HistoryManager
from src.story_generator import StoryGenerator
from src.post_formatter import format_post_content
from src.mail_sender import WordPressMailSender

JST = timezone(timedelta(hours=9))

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

def main():
    parser = argparse.ArgumentParser(
        description="Daily Aozora Bunko Sci-Fi Reboot & WordPress Mail Auto-Poster"
    )
    parser.add_argument(
        "--file", "-f",
        default=None,
        help="Optional: Path to a specific markdown file to publish directly"
    )
    parser.add_argument(
        "--work-id",
        default=None,
        help="Optional: Specific Aozora work ID from catalog to generate and publish"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force generation even if the work has already been published"
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the email to WordPress (if omitted, runs in dry-run mode)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly run in dry-run mode (no email sent, history not updated)"
    )
    parser.add_argument(
        "--preview-html",
        action="store_true",
        help="Export rendered HTML to preview_output.html"
    )
    parser.add_argument(
        "--status",
        choices=["publish", "draft"],
        default=None,
        help="Override post status (publish or draft)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)
    logger = logging.getLogger("wp-autoposter")

    config = get_config()
    history_mgr = HistoryManager()

    is_dry_run = True
    if args.send and not args.dry_run:
        is_dry_run = False

    target_file = None
    target_work = None
    target_refs = []

    # Case 1: Direct file specified
    if args.file:
        target_file = Path(args.file)
        if not target_file.exists():
            logger.error(f"Story file not found: {target_file}")
            sys.exit(1)
        logger.info(f"Using direct file: {target_file}")

    # Case 2: Daily automated generation from Aozora catalog
    else:
        target_work = history_mgr.select_next_work(work_id=args.work_id, force=args.force)
        if not target_work:
            logger.error("No unposted works found in catalog! Use --force to reboot an earlier work.")
            sys.exit(1)

        logger.info(f"Selected Aozora work: '{target_work['title']}' by {target_work['author']} (ID: {target_work['id']})")
        
        # Generate new story via Gemini
        generator = StoryGenerator()
        content, reboot_title, target_refs = generator.generate_story(target_work)

        # Save to content directory
        today_str = datetime.now(JST).strftime("%Y-%m-%d")
        safe_id = target_work['id'].replace("-", "_")
        target_file = Path(f"content/{today_str}_{safe_id}.md")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_text(content, encoding="utf-8")
        logger.info(f"Generated story saved to: {target_file}")

    # Format content for WordPress email
    formatted = format_post_content(
        str(target_file),
        status_override=args.status,
        include_jetpack_shortcodes=config.use_jetpack_shortcodes
    )

    logger.info(f"Ready to post: '{formatted.title}' (Status: {formatted.status})")

    # HTML Preview
    if args.preview_html or is_dry_run:
        preview_file = Path("preview_output.html")
        preview_file.write_text(formatted.content_html, encoding="utf-8")
        logger.info(f"Rendered HTML saved to: {preview_file.resolve()}")

    # Dispatch via SMTP
    sender = WordPressMailSender(config)
    result = sender.send_post(formatted, dry_run=is_dry_run)

    if not result.get("success"):
        logger.error(f"Dispatch failed: {result.get('error')}")
        sys.exit(1)

    # If live dispatch was successful and this was a generated work, record in history
    if not is_dry_run and target_work:
        history_mgr.record_post(
            work=target_work,
            reboot_title=formatted.title,
            file_path=str(target_file),
            references=target_refs,
            status=formatted.status
        )
        logger.info(f"Recorded '{formatted.title}' in data/history.json and data/POSTED_STORIES.md")

    if is_dry_run:
        logger.info("Dry-run finished. To post for real and update history, run with '--send'.")
    else:
        logger.info("Workflow completed successfully!")

if __name__ == "__main__":
    main()
