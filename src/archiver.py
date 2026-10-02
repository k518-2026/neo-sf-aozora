import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Primary project archive directory
PROJECT_ARCHIVE_DIR = Path("archive")
# External tool archive directory (MakeMP3FromAozora)
EXTERNAL_TOOL_ARCHIVE_DIR = Path(r"E:\GoogleAntigravity\tools\MakeMP3FromAozora\data\neo_sf_archive")

def extract_story_parts(raw_md: str, fallback_title: str = "") -> Dict[str, str]:
    """
    Extracts title, subtitle, author, narration body, technical commentary,
    references, and next preview from a full story markdown.
    """
    # 1. Extract title and subtitle from YAML frontmatter if present
    extracted_title = ""
    extracted_subtitle = ""

    # Look for title: ... in frontmatter or yaml header
    fm_title_match = re.search(r"^\s*title\s*:\s*[\"']?『?([^\"'\n]+?)』?[\"']?\s*$", raw_md, re.MULTILINE)
    if fm_title_match:
        full_fm_title = fm_title_match.group(1).strip()
        # Handle '――' or '―' subtitle separation in title field
        if "――" in full_fm_title:
            parts = full_fm_title.split("――", 1)
            extracted_title = parts[0].strip().strip("『』\"'")
            extracted_subtitle = parts[1].strip().strip("『』\"'")
        elif "―" in full_fm_title:
            parts = full_fm_title.split("―", 1)
            extracted_title = parts[0].strip().strip("『』\"'")
            extracted_subtitle = parts[1].strip().strip("『』\"'")
        else:
            extracted_title = full_fm_title.strip().strip("『』\"'")

    # Remove frontmatter block (supporting ---, ```yaml, or yaml)
    body = raw_md
    fm_match = re.match(r"^(?:---|```yaml|yaml)\s*\n(.*?)\n(?:---|```)\s*\n(.*)$", raw_md, re.DOTALL)
    if fm_match:
        body = fm_match.group(2).strip()

    # If no title from frontmatter, try H1 header
    if not extracted_title:
        h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        if h1_match:
            raw_h1 = h1_match.group(1).strip().strip("『』\"'")
            if "――" in raw_h1:
                parts = raw_h1.split("――", 1)
                extracted_title = parts[0].strip()
                if not extracted_subtitle:
                    extracted_subtitle = parts[1].strip()
            else:
                extracted_title = raw_h1

    # Extract subtitle if not already found
    if not extracted_subtitle:
        sub_match = re.search(r"^###?\s+――?(.+)$", body, re.MULTILINE)
        if sub_match:
            extracted_subtitle = sub_match.group(1).strip().strip("『』\"'")

    title = extracted_title if extracted_title else (fallback_title if fallback_title else "無題")
    subtitle = extracted_subtitle

    # Extract original work attribution
    attribution = ""
    attr_match = re.search(r"^\*\*原案：(.+?)\*\*", body, re.MULTILINE)
    if attr_match:
        # Strip markdown links
        raw_attr = attr_match.group(1).strip()
        attribution = re.sub(r"\[(.*?)\]\([^)]+\)", r"\1", raw_attr)

    # Cut off commentary, references, and next preview to get pure story text
    story_end_pos = len(body)
    for marker in ["【作中技術のやさしい解説", "### 【作中技術", "【引用・参考文献", "### 【引用", "【次回作の予告", "### 【次回"]:
        idx = body.find(marker)
        if idx != -1 and idx < story_end_pos:
            story_end_pos = idx

    story_body_raw = body[:story_end_pos].strip()

    # Clean story body for narration:
    # Remove headers, original author line, horizontal divider lines
    cleaned_lines = []
    skip_header = True
    for line in story_body_raw.splitlines():
        stripped = line.strip()
        if not stripped:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("**原案："):
            continue
        if stripped in ("---", "***", "___", "* * *", "- - -", "◆ ◆ ◆"):
            # Scene separator in narration -> clean pause indicator
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        # Remove markdown inline formatting
        line_clean = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped)
        line_clean = re.sub(r"\*(.*?)\*", r"\1", line_clean)
        line_clean = re.sub(r"\[(.*?)\]\([^)]+\)", r"\1", line_clean)
        # Remove ending parenthesis (了) or （了）
        if line_clean in ("（了）", "(了)", "（完）", "(完)"):
            continue
        cleaned_lines.append(line_clean)

    narration_body = "\n".join(cleaned_lines).strip()

    # Create TTS-ready narration text
    header_parts = [f"『{title}』"]
    if subtitle:
        header_parts.append(f"――{subtitle}")
    if attribution:
        header_parts.append(f"原案：{attribution}")
    
    full_narration_text = "\n\n".join(header_parts) + "\n\n" + narration_body

    return {
        "title": title,
        "subtitle": subtitle,
        "attribution": attribution,
        "narration_text": full_narration_text,
        "pure_body": narration_body,
        "full_text": body
    }

def archive_single_story(
    work_no: int,
    work_id: str,
    file_path: Path,
    catalog_info: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Archives a single story to both local archive/ and MakeMP3FromAozora/."""
    raw_md = file_path.read_text(encoding="utf-8")
    fallback = catalog_info.get("title", "") if catalog_info else ""
    parts = extract_story_parts(raw_md, fallback_title=fallback)

    safe_title = re.sub(r'[\\/*?:"<>|]', "", parts["title"]).replace(" ", "_").strip()
    if not safe_title or safe_title == "無題":
        if fallback:
            safe_title = re.sub(r'[\\/*?:"<>|]', "", fallback).replace(" ", "_").strip()
    prefix = f"{work_no:02d}_{safe_title}"

    meta = {
        "work_no": work_no,
        "work_id": work_id,
        "title": parts["title"],
        "subtitle": parts["subtitle"],
        "attribution": parts["attribution"],
        "original_author": catalog_info.get("author", "") if catalog_info else "",
        "original_title": catalog_info.get("title", "") if catalog_info else "",
        "aozora_url": catalog_info.get("url", "") if catalog_info else "",
        "modern_tech": catalog_info.get("modern_tech", "") if catalog_info else "",
        "summary": catalog_info.get("summary", "") if catalog_info else "",
        "char_count": len(parts["narration_text"]),
        "narration_file": f"{prefix}_narration.txt",
        "full_file": f"{prefix}_full.txt",
        "original_md_file": f"{prefix}.md"
    }

    # Write to target directories
    target_dirs = [PROJECT_ARCHIVE_DIR]
    if EXTERNAL_TOOL_ARCHIVE_DIR.parent.exists():
        target_dirs.append(EXTERNAL_TOOL_ARCHIVE_DIR)

    for out_dir in target_dirs:
        out_dir.mkdir(parents=True, exist_ok=True)
        # Narration text for TTS
        (out_dir / f"{prefix}_narration.txt").write_text(parts["narration_text"], encoding="utf-8")
        # Full text
        (out_dir / f"{prefix}_full.txt").write_text(parts["full_text"], encoding="utf-8")
        # Original markdown
        (out_dir / f"{prefix}.md").write_text(raw_md, encoding="utf-8")

    logger.info(f"Archived No.{work_no} '{parts['title']}' ({len(parts['narration_text'])} chars)")
    return meta

def update_archive_all() -> List[Dict[str, Any]]:
    """Scans all published/recreated works and updates archive directories and index files."""
    catalog_path = Path("data/aozora_catalog.json")
    catalog = []
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

    catalog_map = {w["id"]: w for w in catalog}

    # Mapping of known works: prioritize chronological order from data/history.json
    works_order = []
    existing_paths = set()
    seen_work_ids = set()

    history_path = Path("data/history.json")
    if history_path.exists():
        try:
            history_entries = json.loads(history_path.read_text(encoding="utf-8"))
            for entry in history_entries:
                w_id = entry.get("work_id", "")
                fp_str = entry.get("file_path", "")
                if fp_str:
                    fp = Path(fp_str)
                    if fp.exists() and fp.resolve() not in existing_paths and w_id not in seen_work_ids:
                        next_no = len(works_order) + 1
                        works_order.append((next_no, w_id, fp))
                        existing_paths.add(fp.resolve())
                        if w_id:
                            seen_work_ids.add(w_id)
        except Exception as e:
            logger.warning(f"Could not read data/history.json for archive ordering: {e}")

    # Fallback for any markdown files in content/ not yet in history.json
    content_dir = Path("content")
    if content_dir.exists():
        for f in sorted(content_dir.glob("*.md")):
            if f.resolve() not in existing_paths:
                name = f.stem
                matched_w = None
                for w in catalog:
                    if w["id"] in name or w["id"].replace("-", "_") in name:
                        matched_w = w
                        break
                w_id = matched_w["id"] if matched_w else name
                if w_id in seen_work_ids:
                    continue
                next_no = len(works_order) + 1
                works_order.append((next_no, w_id, f))
                existing_paths.add(f.resolve())
                seen_work_ids.add(w_id)

    # Clean up obsolete or shifted numbered files from target directories
    target_dirs = [PROJECT_ARCHIVE_DIR]
    if EXTERNAL_TOOL_ARCHIVE_DIR.parent.exists():
        target_dirs.append(EXTERNAL_TOOL_ARCHIVE_DIR)

    archive_records = []
    valid_filenames = {"README.md", "archive_index.json"}
    for no, w_id, path in works_order:
        if path.exists():
            cat_info = catalog_map.get(w_id, {})
            meta = archive_single_story(no, w_id, path, cat_info)
            archive_records.append(meta)
            valid_filenames.add(meta["narration_file"])
            valid_filenames.add(meta["full_file"])
            valid_filenames.add(meta["original_md_file"])

    for out_dir in target_dirs:
        if out_dir.exists():
            for existing_f in out_dir.iterdir():
                if existing_f.is_file() and existing_f.name not in valid_filenames:
                    try:
                        existing_f.unlink()
                        logger.info(f"Removed stale archive file: {existing_f}")
                    except Exception as e:
                        logger.warning(f"Failed to remove {existing_f}: {e}")

    # Write index JSON
    index_json = json.dumps(archive_records, ensure_ascii=False, indent=2)

    for out_dir in target_dirs:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "archive_index.json").write_text(index_json, encoding="utf-8")

        # Generate README.md
        readme_lines = [
            "# Neo Aozora Sci-Fi Reboot 作品アーカイブ",
            "",
            "青空文庫の古典名作をもとに、現代の最新科学技術を取り入れてリブートされた本格SF小説のアーカイブです。",
            "音声合成ツール（`MakeMP3FromAozora` 等）での朗読音声（MP3）および動画（MP4）生成に最適な形式で保存されています。",
            "",
            "## 📁 ファイル構成",
            "- `*_narration.txt`: 朗読・音声合成（TTS）専用のクリーンテキスト（タイトル＋小説本文のみ）",
            "- `*_full.txt`: 小説本文＋技術解説＋引用文献＋次回予告を含む完全テキスト",
            "- `*.md`: オリジナルMarkdown原稿",
            "- `archive_index.json`: 作品メタデータ一覧（JSON）",
            "",
            "## 📚 収録作品一覧",
            "",
            "| No. | タイトル | 原典作品（著者） | 導入先端科学 | 朗読文字数 | 音声用テキスト |",
            "|:---:|:---|:---|:---|:---:|:---|"
        ]

        for r in archive_records:
            orig = f"{r['original_title']}（{r['original_author']}）"
            readme_lines.append(
                f"| {r['work_no']} | **{r['title']}** | {orig} | {r['modern_tech']} | {r['char_count']:,}字 | [`{r['narration_file']}`]({r['narration_file']}) |"
            )

        readme_lines.append("")
        (out_dir / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")

    logger.info(f"Archive updated successfully. Total works: {len(archive_records)}")
    return archive_records

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    update_archive_all()
