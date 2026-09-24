import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

HISTORY_FILE = Path("data/history.json")
CATALOG_FILE = Path("data/aozora_catalog.json")
TABLE_FILE = Path("data/POSTED_STORIES.md")

JST = timezone(timedelta(hours=9))

class HistoryManager:
    def __init__(self, history_path: Path = HISTORY_FILE, catalog_path: Path = CATALOG_FILE):
        self.history_path = history_path
        self.catalog_path = catalog_path
        self.history = self._load_json(self.history_path)
        self.catalog = self._load_json(self.catalog_path)

    def _load_json(self, path: Path) -> List[Dict[str, Any]]:
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
            return []

    def get_posted_ids(self) -> set:
        return {item["work_id"] for item in self.history if "work_id" in item}

    def select_next_work(self, work_id: Optional[str] = None, force: bool = False) -> Optional[Dict[str, Any]]:
        """
        Selects the next unposted Aozora Bunko work to reboot.
        If work_id is specified, selects that work.
        If all works have been posted and not force, loops or selects the oldest posted one.
        """
        if not self.catalog:
            return None

        # If explicit work_id requested
        if work_id:
            for item in self.catalog:
                if item["id"] == work_id:
                    return item
            raise ValueError(f"Work ID '{work_id}' not found in catalog.")

        posted_ids = self.get_posted_ids()

        # Find unposted work
        unposted = [w for w in self.catalog if w["id"] not in posted_ids]
        if unposted:
            return unposted[0]

        # If all posted
        if force or len(posted_ids) >= len(self.catalog):
            print("All catalog works have been posted! Selecting the oldest one for a new variant.")
            return self.catalog[0]

        return None

    def reset_history(self, work_ids: Optional[List[str]] = None):
        """
        Resets history for specified work_ids, or resets all history if None.
        Enables re-posting of earlier works.
        """
        if work_ids is None:
            self.history = []
        else:
            self.history = [item for item in self.history if item.get("work_id") not in work_ids]

        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

        self._update_markdown_table()

    def record_post(
        self,
        work: Dict[str, Any],
        reboot_title: str,
        file_path: str,
        references: List[str],
        status: str = "published"
    ):
        """Records the newly published story into history.json and POSTED_STORIES.md."""
        now_jst = datetime.now(JST).isoformat()
        
        # Remove old record of same work_id if it exists to prevent duplicate entries
        self.history = [item for item in self.history if item.get("work_id") != work["id"]]

        record = {
            "work_id": work["id"],
            "original_title": work["title"],
            "original_author": work["author"],
            "reboot_title": reboot_title,
            "posted_at": now_jst,
            "file_path": file_path,
            "status": status,
            "references": references
        }
        self.history.append(record)

        # Save history.json
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

        # Update Markdown table
        self._update_markdown_table()

    def _update_markdown_table(self):
        lines = [
            "# 投稿済みSF作品 アーカイブ一覧\n",
            "青空文庫のSF古典作品をもとに、現代の海外査読学術論文の知見を取り入れてリブート・投稿された作品一覧です。\n",
            "毎日朝4時（JST）の自動定期実行により、重複のないよう更新されます。\n\n",
            "| No. | 投稿日 (JST) | リブート作品タイトル | 青空文庫 原典 (著者) | 主な引用論文 (DOIリンク) | ステータス |",
            "|:---:|:---:|:---|:---|:---|:---:|"
        ]

        if not self.history:
            lines.append("| - | - | （再投稿待機中） | - | - | Ready |")
        else:
            for i, item in enumerate(self.history, start=1):
                date_str = item.get("posted_at", "")[:10]
                reboot_title = item.get("reboot_title", "").split("――")[0]
                original = f"{item.get('original_title')}（{item.get('original_author')}）"
                refs = item.get("references", [])
                ref_summary = ", ".join([r.split(" - ")[0] for r in refs[:2]]) if refs else "Nature/Science/Cell"
                status = item.get("status", "published").capitalize()
                lines.append(f"| {i} | {date_str} | {reboot_title} | {original} | {ref_summary} | {status} |")

        TABLE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
