import argparse
import sys
import logging
from pathlib import Path

from src.config import get_config
from src.post_formatter import format_post_content
from src.mail_sender import WordPressMailSender

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S"
    )

def main():
    parser = argparse.ArgumentParser(
        description="WordPress Post via Email - Aozora Sci-Fi Reboot Publisher"
    )
    parser.add_argument(
        "--file", "-f",
        default="content/story.md",
        help="Path to the story markdown file (default: content/story.md)"
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Actually send the email to WordPress (if omitted, runs in dry-run mode)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly run in dry-run mode (no email sent)"
    )
    parser.add_argument(
        "--preview-html",
        action="store_true",
        help="Export rendered HTML to preview_output.html for browser preview"
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

    file_path = Path(args.file)
    if not file_path.exists():
        logger.error(f"Story file not found: {file_path}")
        sys.exit(1)

    config = get_config()
    logger.info(f"Loaded story from: {file_path}")

    # Format content
    formatted = format_post_content(
        str(file_path),
        status_override=args.status,
        include_jetpack_shortcodes=config.use_jetpack_shortcodes
    )

    logger.info(f"Title: {formatted.title}")
    logger.info(f"Status: {formatted.status}")
    logger.info(f"Categories: {formatted.categories}")
    logger.info(f"Tags: {formatted.tags}")

    # Preview HTML if requested
    if args.preview_html:
        preview_file = Path("preview_output.html")
        preview_file.write_text(formatted.content_html, encoding="utf-8")
        logger.info(f"Rendered HTML saved to: {preview_file.resolve()}")

    # Determine dry-run status:
    # If --send is NOT given, or --dry-run is given, default to dry-run
    is_dry_run = True
    if args.send and not args.dry_run:
        is_dry_run = False

    sender = WordPressMailSender(config)
    result = sender.send_post(formatted, dry_run=is_dry_run)

    if result.get("success"):
        if is_dry_run:
            logger.info("Dry-run finished successfully! To send real email, run with '--send'.")
        else:
            logger.info("Post successfully dispatched to WordPress!")
    else:
        logger.error(f"Dispatch failed: {result.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
