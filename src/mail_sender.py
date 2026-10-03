import re
import smtplib
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formatdate, make_msgid
from typing import Dict, Any, Optional
import logging

from src.config import SMTPConfig
from src.post_formatter import FormattedPost

logger = logging.getLogger(__name__)

class WordPressMailSender:
    """
    Sends posts to WordPress and Google Blogger via Email using standard SMTP.
    Supports Jetpack Post by Email, Postie, standard WP mail receivers, and Blogger Post using Email.
    """

    def __init__(self, config: SMTPConfig):
        self.config = config

    def create_mime_message(
        self,
        post: FormattedPost,
        to_email: Optional[str] = None,
        for_blogger: bool = False
    ) -> MIMEMultipart:
        """
        Constructs a MIMEMultipart email message with text and HTML parts.
        When for_blogger=True, omits WordPress Jetpack shortcodes ([status], [category], [tags])
        so they do not appear as literal text at the bottom of Blogger posts.
        """
        msg = MIMEMultipart("alternative")
        
        # Subject becomes the Post Title on both WordPress and Blogger
        msg["Subject"] = Header(post.title, "utf-8")
        
        # From header (avoid RFC 2047 encoding if display name is pure ASCII to prevent spam filter penalties)
        try:
            self.config.from_name.encode("ascii")
            from_display = self.config.from_name
        except UnicodeEncodeError:
            from_display = Header(self.config.from_name, "utf-8").encode()
        msg["From"] = f"{from_display} <{self.config.user}>"
        
        # Destination inbox
        recipient = to_email if to_email is not None else (
            self.config.blogger_post_email if for_blogger else self.config.wp_post_email
        )
        msg["To"] = recipient

        # Standard RFC 5322 headers to prevent Gmail/Blogger deduplication or spam filtering
        msg["Date"] = formatdate(localtime=True)
        domain = self.config.user.split("@")[-1] if "@" in self.config.user else "neo-sf-aozora.local"
        msg["Message-ID"] = make_msgid(domain=domain)

        if for_blogger:
            raw_plain = post.content_plain_clean or post.content_plain
            # Strip duplicate raw Markdown URLs from the plain-text part so outbound/inbound spam filters
            # do not count every URL twice across text/plain and text/html
            plain_body = re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", raw_plain)
            plain_body = re.sub(r"https?://(?:dx\.)?doi\.org/(10\.\S+)", r"DOI: \1", plain_body)
            html_body = post.content_html_clean or post.content_html
        else:
            plain_body = post.content_plain
            html_body = post.content_html

        # Attach text part and HTML part
        part_text = MIMEText(plain_body, "plain", "utf-8")
        part_html = MIMEText(html_body, "html", "utf-8")
        
        msg.attach(part_text)
        msg.attach(part_html)

        return msg

    def _get_blogger_recipients(self) -> list[str]:
        if not self.config.blogger_post_email:
            return []
        return [addr.strip() for addr in self.config.blogger_post_email.split(",") if addr.strip()]

    def _send_single_message(self, recipient: str, msg: MIMEMultipart):
        """Sends a single MIME message over a clean SMTP connection."""
        if self.config.use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.config.host, self.config.port, context=context) as server:
                server.login(self.config.user, self.config.password)
                server.sendmail(self.config.user, [recipient], msg.as_string())
        else:
            with smtplib.SMTP(self.config.host, self.config.port) as server:
                server.ehlo()
                if self.config.use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                server.login(self.config.user, self.config.password)
                server.sendmail(self.config.user, [recipient], msg.as_string())

    def send_post(
        self,
        post: FormattedPost,
        dry_run: bool = False,
        blogger_only: bool = False
    ) -> Dict[str, Any]:
        """
        Sends the formatted post to the WordPress mail receiver and (if configured) simultaneously to Blogger.
        If blogger_only is True, sends only to Blogger.
        If dry_run is True, skips actual network dispatch and logs details.
        """
        blogger_recipients = self._get_blogger_recipients()
        wp_recipient = "" if blogger_only else self.config.wp_post_email

        if dry_run or not self.config.user or (not wp_recipient and not blogger_recipients):
            logger.info("================ [DRY RUN / MOCK MODE] ================")
            if not blogger_only:
                logger.info(f"Target WP Email: {self.config.wp_post_email or '(Not Set - WP_POST_EMAIL)'}")
            logger.info(f"Target Blogger Email: {self.config.blogger_post_email or '(Not Set - BLOGGER_POST_EMAIL)'}")
            logger.info(f"Subject (Post Title): {post.title}")
            logger.info(f"From: {self.config.user or '(Not Set - SMTP_USER)'}")
            logger.info(f"Status: {post.status}")
            logger.info(f"Categories: {', '.join(post.categories)}")
            logger.info(f"Tags: {', '.join(post.tags)}")
            logger.info(f"WP HTML Content Length: {len(post.content_html)} chars")
            logger.info(f"Blogger Clean HTML Content Length: {len(post.content_html_clean or post.content_html)} chars")
            logger.info("========================================================")
            return {
                "success": True,
                "dry_run": True,
                "title": post.title,
                "to": self.config.blogger_post_email if blogger_only else self.config.wp_post_email,
                "blogger_to": blogger_recipients,
                "message": "Dry run completed successfully. No actual email sent."
            }

        logger.info(f"Connecting to SMTP server {self.config.host}:{self.config.port}...")
        
        try:
            sent_blogger = []
            # 1. Send to WordPress (if not blogger_only and wp_post_email is configured)
            if wp_recipient:
                wp_msg = self.create_mime_message(post, to_email=wp_recipient, for_blogger=False)
                self._send_single_message(wp_recipient, wp_msg)
                logger.info(f"Successfully posted to WordPress via email! Recipient: {wp_recipient}")

            # 2. Send to Blogger over a separate SMTP session (after a 10s pause if WP was just sent)
            for b_addr in blogger_recipients:
                try:
                    if wp_recipient:
                        time.sleep(10)
                    b_msg = self.create_mime_message(post, to_email=b_addr, for_blogger=True)
                    self._send_single_message(b_addr, b_msg)
                    sent_blogger.append(b_addr)
                    logger.info(f"Successfully posted to Blogger via email! Recipient: {b_addr}")
                except Exception as b_err:
                    if blogger_only:
                        raise
                    logger.error(f"Failed to send email to Blogger ({b_addr}): {b_err}", exc_info=True)

            return {
                "success": True,
                "dry_run": False,
                "title": post.title,
                "to": self.config.blogger_post_email if blogger_only else self.config.wp_post_email,
                "blogger_to": sent_blogger,
                "message": f"Post '{post.title}' successfully emailed."
            }
        except Exception as e:
            target_label = "Blogger" if blogger_only else "WordPress/Blogger"
            logger.error(f"Failed to send email to {target_label}: {e}", exc_info=True)
            return {
                "success": False,
                "dry_run": False,
                "title": post.title,
                "to": self.config.blogger_post_email if blogger_only else self.config.wp_post_email,
                "blogger_to": [],
                "error": str(e)
            }
