"""
Check if today's story has been published to GitHub/WordPress/Blogger/X.
If not, trigger the GitHub Actions publication workflow ('Publish to X, WordPress & Blogger').
"""

import base64
import json
import logging
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
REPO = "k518-2026/neo-sf-aozora"
WORKFLOW_ID = "366006847"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("startup-publisher")


def get_github_token() -> str:
    res = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
    )
    for line in res.stdout.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    return ""


def get_latest_posted_date(token: str) -> str:
    url = f"https://api.github.com/repos/{REPO}/contents/data/history.json"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "StartupPublisher/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = base64.b64decode(data["content"]).decode("utf-8")
            history = json.loads(content)
            if history and isinstance(history, list):
                last_post = history[-1]
                posted_at = last_post.get("posted_at", "")
                logger.info(f"Latest posted work: #{len(history)} '{last_post.get('reboot_title', last_post.get('work_id'))}' at {posted_at}")
                if posted_at:
                    return posted_at[:10]  # YYYY-MM-DD
    except Exception as e:
        logger.warning(f"Failed to fetch remote history.json: {e}")
    return ""


def is_workflow_active_or_queued(token: str) -> bool:
    for status in ["in_progress", "queued"]:
        url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_ID}/runs?status={status}"
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "StartupPublisher/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("total_count", 0) > 0:
                    logger.info(f"Publication workflow is currently {status}. No new trigger needed.")
                    return True
        except Exception as e:
            logger.warning(f"Failed to check workflow status ({status}): {e}")
    return False


def trigger_publish_workflow(token: str) -> bool:
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW_ID}/dispatches"
    payload = json.dumps({"ref": "main"}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "StartupPublisher/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status in (200, 204):
                logger.info("Successfully triggered 'Publish to X, WordPress & Blogger' on GitHub Actions!")
                return True
            else:
                logger.warning(f"Trigger returned status: {resp.status}")
    except urllib.error.HTTPError as e:
        logger.error(f"HTTPError triggering workflow: {e.code} - {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        logger.error(f"Error triggering workflow: {e}")
    return False


def main():
    today_jst = datetime.now(JST).strftime("%Y-%m-%d")
    logger.info(f"Checking today's ({today_jst} JST) post status for {REPO}...")

    token = get_github_token()
    if not token:
        logger.error("GitHub token not found via git credential. Exiting.")
        sys.exit(1)

    latest_date = get_latest_posted_date(token)
    if latest_date == today_jst:
        logger.info(f"Today's article ({today_jst}) has already been posted. Nothing to do.")
        return

    logger.warning(f"Today's article has NOT been posted yet (latest was {latest_date}). Checking workflow queue...")

    if is_workflow_active_or_queued(token):
        logger.info("Workflow is already in queue or running.")
        return

    logger.info("Sending publication dispatch command to GitHub Actions...")
    ok = trigger_publish_workflow(token)
    if ok:
        logger.info("Dispatch command sent successfully.")
    else:
        logger.error("Failed to send dispatch command.")


if __name__ == "__main__":
    main()
