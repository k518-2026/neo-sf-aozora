import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

from src.config import SMTPConfig

logger = logging.getLogger("wp-autoposter")

URL_REGEX = re.compile(r"https?://\S+")


def calc_x_weight(text: str) -> int:
    """
    Calculates X (Twitter) character weight according to official twitter-text rules:
    - Each URL counts as 23 weighted characters.
    - ASCII / Latin-1 / half-width characters (code point <= 0x10FF) count as 1.
    - CJK / full-width characters and emojis count as 2.
    Maximum allowed weight for a standard post is 280 (equivalent to 140 full-width chars).
    """
    weight = 0
    last_idx = 0
    for match in URL_REGEX.finditer(text):
        start, end = match.span()
        segment = text[last_idx:start]
        weight += _segment_weight(segment)
        weight += 23
        last_idx = end
    weight += _segment_weight(text[last_idx:])
    return weight


def _segment_weight(segment: str) -> int:
    w = 0
    for ch in segment:
        # Newlines and basic Latin/half-width up to U+10FF count as 1 in X's v3 config
        if ord(ch) <= 0x10FF:
            w += 1
        else:
            w += 2
    return w


def _truncate_to_weight(text: str, max_weight: int) -> str:
    """Truncates text to fit within max_weight, appending '…' (weight 2) if truncated."""
    if calc_x_weight(text) <= max_weight:
        return text
    target = max(0, max_weight - 2)
    out = []
    curr = 0
    for ch in text:
        cw = 1 if ord(ch) <= 0x10FF else 2
        if curr + cw > target:
            break
        out.append(ch)
        curr += cw
    return "".join(out).rstrip("、。,. ") + "…"


def build_x_post_text(
    work: Optional[Dict[str, Any]],
    reboot_title: str = "",
    site_url: str = "",
    max_weight: int = 280
) -> str:
    """
    Builds an X (Twitter) post containing:
    - 原典作品名 (Original Aozora Bunko work author & title)
    - SFリブートの視点 (Sci-Fi reboot perspective / modern technology & summary)
    - リブート作品タイトル (Reboot story title)
    Strictly fits within X's 280 weighted character limit (140 Japanese chars).
    """
    clean_reboot_title = (reboot_title or "").strip().strip("『』")

    if work:
        author = work.get("author", "").strip()
        orig_title = work.get("title", "").strip()
        modern_tech = work.get("modern_tech", "").strip()
        summary = work.get("summary", "").strip()
        orig_label = f"{author}『{orig_title}』" if author else f"『{orig_title}』"
    else:
        orig_label = f"『{clean_reboot_title}』" if clean_reboot_title else "青空文庫古典作品"
        modern_tech = ""
        summary = "最先端の科学技術と数理モデルで古典名作を再構築したハードSFリブート。"

    # Construct candidate perspectives
    if summary and modern_tech:
        perspective_full = f"{summary}（導入科学：{modern_tech}）"
        perspective_base = summary
    elif summary:
        perspective_full = summary
        perspective_base = summary
    elif modern_tech:
        perspective_full = modern_tech
        perspective_base = modern_tech
    else:
        perspective_full = "最先端科学によるSFリブート"
        perspective_base = perspective_full

    footer_parts = ["#SF小説 #青空文庫"]
    if site_url and site_url.strip():
        footer_parts.append(site_url.strip())
    footer = "\n".join(footer_parts)

    origin_line = f"📖原典：{orig_label}"

    # Title line candidates (with and without prefix badge)
    if clean_reboot_title:
        title_candidates = [
            f"【SFリブート公開】『{clean_reboot_title}』",
            f"『{clean_reboot_title}』",
        ]
    else:
        title_candidates = ["【SFリブート公開】"]

    # Try fitting perspective_full or perspective_base without truncation first
    for p_text in (perspective_full, perspective_base):
        for t_line in title_candidates:
            candidate = f"{t_line}\n{origin_line}\n🔬SFリブートの視点：{p_text}\n{footer}"
            if calc_x_weight(candidate) <= max_weight:
                return candidate

    # If still over max_weight, use the most compact title line and truncate perspective_base
    compact_title = title_candidates[-1]
    fixed_shell = f"{compact_title}\n{origin_line}\n🔬SFリブートの視点：\n{footer}"
    shell_weight = calc_x_weight(fixed_shell)
    available_for_perspective = max_weight - shell_weight

    if available_for_perspective < 20:
        # In the extreme case where reboot_title itself is extraordinarily long, trim reboot_title first
        compact_title = _truncate_to_weight(compact_title, 60)
        fixed_shell = f"{compact_title}\n{origin_line}\n🔬SFリブートの視点：\n{footer}"
        available_for_perspective = max(20, max_weight - calc_x_weight(fixed_shell))

    trimmed_perspective = _truncate_to_weight(perspective_base, available_for_perspective)
    return f"{compact_title}\n{origin_line}\n🔬SFリブートの視点：{trimmed_perspective}\n{footer}"


def _percent_encode(val: str) -> str:
    """RFC 3986 percent-encoding required for OAuth 1.0a."""
    return urllib.parse.quote(str(val), safe="-._~")


def build_oauth1_header(
    method: str,
    url: str,
    api_key: str,
    api_secret: str,
    access_token: str,
    access_token_secret: str,
    nonce: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> str:
    """Builds an OAuth 1.0a Authorization header for X API v2 requests."""
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": access_token,
        "oauth_version": "1.0",
    }

    # Sort and encode parameters
    sorted_params = sorted(oauth_params.items(), key=lambda kv: (_percent_encode(kv[0]), _percent_encode(kv[1])))
    param_str = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in sorted_params)

    # Parse base URL without query string
    parsed = urllib.parse.urlsplit(url)
    base_url = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path}"

    base_string = "&".join([
        method.upper(),
        _percent_encode(base_url),
        _percent_encode(param_str),
    ])

    signing_key = f"{_percent_encode(api_secret)}&{_percent_encode(access_token_secret)}"
    digest = hmac.new(
        signing_key.encode("utf-8"),
        base_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    signature = base64.b64encode(digest).decode("utf-8")
    oauth_params["oauth_signature"] = signature

    header_items = ", ".join(
        f'{_percent_encode(k)}="{_percent_encode(v)}"'
        for k, v in sorted(oauth_params.items())
    )
    return f"OAuth {header_items}"


class XPoster:
    """Dispatches simultaneous announcement posts to X (Twitter) via X API v2 or Webhook."""

    API_ENDPOINTS = (
        "https://api.x.com/2/tweets",
        "https://api.twitter.com/2/tweets",
    )

    def __init__(self, config: SMTPConfig):
        self.config = config

    def is_configured(self) -> bool:
        has_oauth = all([
            self.config.x_api_key,
            self.config.x_api_secret,
            self.config.x_access_token,
            self.config.x_access_token_secret,
        ])
        has_webhook = bool(self.config.x_webhook_url)
        return has_oauth or has_webhook

    def post_update(
        self,
        work: Optional[Dict[str, Any]],
        reboot_title: str,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """
        Formats and posts the original work title and SF reboot perspective to X.
        In dry-run mode or when credentials are not yet configured, logs the post content gracefully.
        """
        tweet_text = build_x_post_text(
            work=work,
            reboot_title=reboot_title,
            site_url=self.config.wp_site_url,
        )
        weight = calc_x_weight(tweet_text)

        logger.info("=== X (Twitter) Post Content ===")
        for line in tweet_text.splitlines():
            logger.info(f"  {line}")
        logger.info(f"=== End X Post (Weight: {weight}/280) ===")

        if dry_run:
            logger.info("[DRY-RUN] X post simulated successfully.")
            return {
                "success": True,
                "dry_run": True,
                "text": tweet_text,
                "weight": weight,
            }

        if not self.is_configured():
            logger.warning(
                "X API credentials (X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET) "
                "or X_WEBHOOK_URL are not set. Skipping live X API request."
            )
            return {
                "success": False,
                "skipped": True,
                "reason": "credentials_not_configured",
                "text": tweet_text,
                "weight": weight,
            }

        # 1. If OAuth 1.0a credentials are provided, post directly to X API v2
        if all([
            self.config.x_api_key,
            self.config.x_api_secret,
            self.config.x_access_token,
            self.config.x_access_token_secret,
        ]):
            payload = json.dumps({"text": tweet_text}).encode("utf-8")
            last_error = None
            for endpoint in self.API_ENDPOINTS:
                try:
                    auth_header = build_oauth1_header(
                        method="POST",
                        url=endpoint,
                        api_key=self.config.x_api_key,
                        api_secret=self.config.x_api_secret,
                        access_token=self.config.x_access_token,
                        access_token_secret=self.config.x_access_token_secret,
                    )
                    req = urllib.request.Request(
                        endpoint,
                        data=payload,
                        headers={
                            "Authorization": auth_header,
                            "Content-Type": "application/json",
                            "User-Agent": "NeoSFAozoraAutoposter/1.0",
                        },
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=20) as resp:
                        resp_body = resp.read().decode("utf-8", errors="replace")
                        data = json.loads(resp_body) if resp_body else {}
                        tweet_id = data.get("data", {}).get("id", "")
                        logger.info(f"Successfully posted to X! (Tweet ID: {tweet_id})")
                        return {
                            "success": True,
                            "dry_run": False,
                            "tweet_id": tweet_id,
                            "text": tweet_text,
                            "weight": weight,
                        }
                except urllib.error.HTTPError as e:
                    err_body = e.read().decode("utf-8", errors="replace")
                    last_error = f"HTTP {e.code}: {err_body}"
                    logger.warning(f"X API request to {endpoint} failed ({last_error})")
                    # Do not retry on 4xx client/auth errors against the alias host
                    if 400 <= e.code < 500:
                        break
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"X API request to {endpoint} encountered error: {last_error}")

            logger.error(f"Failed to post to X via API v2: {last_error}")
            return {
                "success": False,
                "dry_run": False,
                "error": last_error,
                "text": tweet_text,
                "weight": weight,
            }

        # 2. Fallback: Webhook URL (e.g., IFTTT / Make / Zapier)
        if self.config.x_webhook_url:
            try:
                payload = json.dumps({
                    "text": tweet_text,
                    "value1": tweet_text,
                    "reboot_title": reboot_title,
                    "original_title": work.get("title", "") if work else "",
                    "original_author": work.get("author", "") if work else "",
                    "perspective": work.get("summary", "") if work else "",
                }).encode("utf-8")
                req = urllib.request.Request(
                    self.config.x_webhook_url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "NeoSFAozoraAutoposter/1.0",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=20) as resp:
                    logger.info(f"Successfully dispatched X post via Webhook (HTTP {resp.status}).")
                    return {
                        "success": True,
                        "dry_run": False,
                        "webhook": True,
                        "text": tweet_text,
                        "weight": weight,
                    }
            except Exception as e:
                logger.error(f"Failed to dispatch X post via Webhook: {e}")
                return {
                    "success": False,
                    "dry_run": False,
                    "error": str(e),
                    "text": tweet_text,
                    "weight": weight,
                }

        return {
            "success": False,
            "dry_run": False,
            "error": "No valid X posting transport available",
            "text": tweet_text,
            "weight": weight,
        }
