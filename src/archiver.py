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

def extract_story_parts(raw_md: str) -> Dict[str, str]:
    """
    Extracts title, subtitle, author, narration body, technical commentary,
    references, and next preview from a full story markdown.
    """
    # Remove frontmatter
    body = raw_md
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw_md, re.DOTALL)
    if fm_match:
        body = fm_match.group(2).strip()

    # Extract title
    title = "無題"
    h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
    if h1_match:
        title = h1_match.group(1).strip()

    # Extract subtitle
    subtitle = ""
    sub_match = re.search(r"^###?\s+――?(.+)$", body, re.MULTILINE)
    if sub_match:
        subtitle = sub_match.group(1).strip()

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
    parts = extract_story_parts(raw_md)

    safe_title = re.sub(r'[\\/*?:"<>|]', "", parts["title"]).replace(" ", "_")
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

    # Mapping of known works
    works_order = [
        (1, "unno-18-music", Path("content/story.md")),
        (2, "unno-fly-man", Path("content/2026-09-24_unno_fly_man.md")),
        (3, "unno-cyborg-incident", Path("content/2026-09-24_unno_cyborg_incident.md")),
        (4, "unno-vibration-demon", Path("content/2026-09-25_unno_vibration_demon.md")),
        (5, "ran-plant-man", Path("content/2026-09-25_ran_plant_man.md")),
    ]

    # Also detect other markdown files in content/
    existing_paths = {p.resolve() for _, _, p in works_order}
    content_dir = Path("content")
    if content_dir.exists():
        for f in sorted(content_dir.glob("*.md")):
            if f.resolve() not in existing_paths:
                # determine work_id from name
                name = f.stem
                matched_w = None
                for w in catalog:
                    if w["id"] in name or w["id"].replace("-", "_") in name:
                        matched_w = w
                        break
                next_no = len(works_order) + 1
                w_id = matched_w["id"] if matched_w else name
                works_order.append((next_no, w_id, f))
                existing_paths.add(f.resolve())

    archive_records = []
    for no, w_id, path in works_order:
        if path.exists():
            cat_info = catalog_map.get(w_id, {})
            meta = archive_single_story(no, w_id, path, cat_info)
            archive_records.append(meta)

    # Write index JSON
    index_json = json.dumps(archive_records, ensure_ascii=False, indent=2)
    target_dirs = [PROJECT_ARCHIVE_DIR]
    if EXTERNAL_TOOL_ARCHIVE_DIR.parent.exists():
        target_dirs.append(EXTERNAL_TOOL_ARCHIVE_DIR)

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
