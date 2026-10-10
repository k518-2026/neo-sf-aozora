import html
import json
import logging
import re
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.history_manager import HistoryManager
from src.post_formatter import parse_markdown_with_frontmatter, HAS_MARKDOWN, _fallback_markdown_to_html

if HAS_MARKDOWN:
    import markdown

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

DOCS_DIR = Path("docs")
STORIES_DIR = DOCS_DIR / "stories"
IMAGES_DIR = DOCS_DIR / "assets" / "images"


def _render_web_markdown(md_text: str) -> str:
    """
    Renders story Markdown to rich HTML for the GitHub Pages web reader,
    preserving clickable Aozora Bunko and DOI links.
    """
    cleaned = re.sub(r"\[(category|tags|status|title|excerpt)[^\]]*\]", "", md_text).strip()
    cleaned = re.sub(r"^[ \t]*#+[ \t]*(\*\s*\*\s*\*)[ \t]*$", r"\1", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^[ \t]*#+[ \t]*\*+[ \t]*$", "* * *", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(
        r"^[ \t]*(?:#+[ \t]*)?[【\[（(]?(?:第\s*[0-9一二三四五六七八九十]+\s*(?:シーン|幕|章|部|節)|シーン\s*[0-9一二三四五六七八九十]+)[】\]）)]?(?:[：:\s—―-].*)?$",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(r"^[ \t]*#+[ \t]*[【\[（(]?[起承転結][】\]）)]?.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"[【\[（(][起承転結][】\]）)]", "", cleaned)
    cleaned = re.sub(r"^[ \t]*[【\[（(]?[起承転結][】\]）)]?[ \t]*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^[ \t]*#+[ \t]*第[一二三123]部[：:\s]*小説本文.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^(#+[ \t]*)第[一二三123]部[：:\s]*", r"\1", cleaned, flags=re.MULTILINE)
    # Remove trailing Next Work Preview from static pages since we provide native Prev/Next buttons
    cleaned = re.sub(r"\n*(?:---|◆ ◆ ◆|\* \* \*)\s*\n+###\s*【次回作の予告】.*$", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", "◆ ◆ ◆", cleaned, flags=re.MULTILINE)

    if HAS_MARKDOWN:
        rendered = markdown.markdown(cleaned, extensions=["extra", "sane_lists"])
    else:
        rendered = _fallback_markdown_to_html(cleaned)

    rendered = re.sub(
        r"<p>\s*◆ ◆ ◆\s*</p>|<hr\s*/?>",
        '<div class="scene-divider">◆ ◆ ◆</div>',
        rendered,
        flags=re.IGNORECASE,
    )
    rendered = re.sub(
        r"<a\b([^>]*?)>",
        r'<a\1 target="_blank" rel="noopener noreferrer">',
        rendered,
        flags=re.IGNORECASE,
    )
    return rendered


def collect_all_stories(history_mgr: Optional[HistoryManager] = None) -> List[Dict[str, Any]]:
    """
    Collects all stories in content/ in chronological publication/creation order
    (matching archive_index.json: first data/history.json order, then content/*.md sorted by date/mtime).
    When reversed for index.html and README.md, the newest story is always at the very top.
    """
    if history_mgr is None:
        history_mgr = HistoryManager()

    catalog_by_id = {w["id"]: (idx, w) for idx, w in enumerate(history_mgr.catalog, start=1)}
    ordered_pairs: List[ tuple[str, Path] ] = []
    seen_work_ids = set()
    seen_paths = set()

    # 1. Chronological order from data/history.json
    for entry in history_mgr.history:
        wid = entry.get("work_id", "")
        fp_str = entry.get("file_path", "").replace("\\", "/")
        md_path = Path(fp_str) if fp_str else None
        if (md_path is None or not md_path.exists()) and wid:
            md_path = history_mgr.find_stock_file_for_work(wid)
        if md_path and md_path.exists() and wid in catalog_by_id and wid not in seen_work_ids:
            ordered_pairs.append((wid, md_path))
            seen_work_ids.add(wid)
            seen_paths.add(md_path.resolve())

    # 2. Remaining stocked files in content/, ordered chronologically by filename date prefix & catalog order
    unposted_candidates: List[tuple[str, int, str, Path]] = []
    for idx, work in enumerate(history_mgr.catalog, start=1):
        wid = work["id"]
        if wid in seen_work_ids:
            continue
        md_path = history_mgr.find_stock_file_for_work(wid)
        if md_path is None or not md_path.exists():
            continue
        date_prefix = md_path.name[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", md_path.name) else "0000-00-00"
        unposted_candidates.append((date_prefix, idx, wid, md_path))

    unposted_candidates.sort(key=lambda item: (item[0], item[1], item[3].name))
    for _, _, wid, md_path in unposted_candidates:
        ordered_pairs.append((wid, md_path))
        seen_work_ids.add(wid)
        seen_paths.add(md_path.resolve())

    stories: List[Dict[str, Any]] = []
    for wid, md_path in ordered_pairs:
        idx, work = catalog_by_id[wid]
        meta, body = parse_markdown_with_frontmatter(str(md_path))
        full_title = meta.get("title", "").strip().strip("『』\"'") or work["title"]
        if "――" in full_title:
            main_title, subtitle = [p.strip() for p in full_title.split("――", 1)]
        else:
            main_title, subtitle = full_title, ""

        png_path = md_path.with_suffix(".png")
        has_image = png_path.exists()
        image_rel = f"assets/images/{wid}.png" if has_image else ""

        char_count = len(re.sub(r"\s+", "", body))
        stories.append({
            "no": len(stories) + 1,
            "catalog_no": idx,
            "work_id": wid,
            "full_title": full_title,
            "main_title": main_title,
            "subtitle": subtitle,
            "original_title": work.get("title", ""),
            "original_author": work.get("author", ""),
            "aozora_url": work.get("url", ""),
            "modern_tech": work.get("modern_tech", ""),
            "summary": work.get("summary", ""),
            "theme": work.get("theme", ""),
            "tags": meta.get("tags", ["SF", "青空文庫", work.get("author", "")]),
            "md_path": md_path,
            "png_path": png_path if has_image else None,
            "has_image": has_image,
            "image_rel": image_rel,
            "page_rel": f"stories/{wid}.html",
            "char_count": char_count,
            "body_md": body,
        })

    return stories


def _write_stylesheet(target_css: Path):
    css = """/* Neo Aozora Sci-Fi Library - GitHub Pages Stylesheet */
:root {
  --bg-primary: #0f141c;
  --bg-secondary: #171f2c;
  --bg-card: #1b2434;
  --bg-reader: #131a26;
  --text-primary: #e6edf5;
  --text-secondary: #9fb0c7;
  --text-muted: #6e8098;
  --accent: #38bdf8;
  --accent-soft: rgba(56, 189, 248, 0.14);
  --gold: #f59e0b;
  --border: #28354a;
  --reader-font-size: 17.5px;
}

[data-theme="light"] {
  --bg-primary: #f6f5f0;
  --bg-secondary: #eae7df;
  --bg-card: #ffffff;
  --bg-reader: #fcfbf8;
  --text-primary: #1f242d;
  --text-secondary: #4a5568;
  --text-muted: #718096;
  --accent: #0284c7;
  --accent-soft: rgba(2, 132, 199, 0.1);
  --gold: #b45309;
  --border: #dcd8ce;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  background-color: var(--bg-primary);
  color: var(--text-primary);
  font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", "Meiryo", sans-serif;
  line-height: 1.75;
  transition: background-color 0.25s ease, color 0.25s ease;
}

a {
  color: var(--accent);
  text-decoration: none;
}
a:hover {
  text-decoration: underline;
}

/* Header & Hero */
.site-header {
  background: linear-gradient(135deg, #0b111e 0%, #16243b 60%, #1a2d42 100%);
  border-bottom: 1px solid var(--border);
  padding: 2.8rem 1.5rem 2.2rem;
  text-align: center;
  color: #f8fafc;
}
.site-badge {
  display: inline-block;
  font-size: 0.78rem;
  letter-spacing: 0.12em;
  padding: 0.3rem 0.9rem;
  border-radius: 999px;
  background: rgba(56, 189, 248, 0.18);
  border: 1px solid rgba(56, 189, 248, 0.4);
  color: #7dd3fc;
  margin-bottom: 0.9rem;
}
.site-title {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(1.65rem, 3.5vw, 2.5rem);
  font-weight: 700;
  margin: 0 0 0.7rem;
  letter-spacing: 0.04em;
}
.site-subtitle {
  max-width: 760px;
  margin: 0 auto 1.5rem;
  color: #cbd5e1;
  font-size: 0.96rem;
}
.stats-bar {
  display: flex;
  justify-content: center;
  gap: 1.2rem;
  flex-wrap: wrap;
  margin-top: 1rem;
}
.stat-pill {
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 10px;
  padding: 0.45rem 1rem;
  font-size: 0.86rem;
  color: #e2e8f0;
}
.stat-pill strong {
  color: #38bdf8;
  font-size: 1.05rem;
  margin-right: 0.25rem;
}

/* Controls & Toolbar */
.container {
  max-width: 1180px;
  margin: 0 auto;
  padding: 1.8rem 1.25rem 4rem;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 0.8rem;
  align-items: center;
  justify-content: space-between;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 1rem 1.2rem;
  margin-bottom: 1.8rem;
}
.filter-group {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  align-items: center;
  flex: 1;
}
.search-input, .select-filter {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.55rem 0.85rem;
  font-size: 0.9rem;
}
.search-input {
  min-width: 220px;
  flex: 1;
}
.btn-toggle {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.5rem 0.85rem;
  font-size: 0.85rem;
  cursor: pointer;
}
.btn-toggle:hover {
  border-color: var(--accent);
}

/* Story Cards Grid */
.story-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  gap: 1.4rem;
}
.story-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}
.story-card:hover {
  transform: translateY(-3px);
  border-color: var(--accent);
  box-shadow: 0 10px 26px rgba(0, 0, 0, 0.25);
}
.card-thumb-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 10;
  background: linear-gradient(135deg, #162235 0%, #1f334d 100%);
  overflow: hidden;
}
.card-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.card-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1.2rem;
  text-align: center;
  color: #94a3b8;
  font-family: "Hiragino Mincho ProN", "Yu Mincho", serif;
}
.card-no-badge {
  position: absolute;
  top: 0.65rem;
  left: 0.65rem;
  background: rgba(15, 20, 28, 0.84);
  color: #38bdf8;
  border: 1px solid rgba(56, 189, 248, 0.4);
  font-size: 0.76rem;
  font-weight: 700;
  padding: 0.2rem 0.6rem;
  border-radius: 6px;
}
.card-body {
  padding: 1.2rem 1.25rem 1.35rem;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.card-origin {
  font-size: 0.8rem;
  color: var(--gold);
  font-weight: 600;
  margin-bottom: 0.35rem;
}
.card-title {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: 1.18rem;
  font-weight: 700;
  margin: 0 0 0.55rem;
  line-height: 1.45;
}
.card-title a {
  color: var(--text-primary);
}
.card-title a:hover {
  color: var(--accent);
  text-decoration: none;
}
.card-tech {
  font-size: 0.78rem;
  background: var(--accent-soft);
  color: var(--accent);
  padding: 0.28rem 0.65rem;
  border-radius: 6px;
  margin-bottom: 0.75rem;
  line-height: 1.45;
}
.card-summary {
  font-size: 0.87rem;
  color: var(--text-secondary);
  margin: 0 0 1rem;
  flex: 1;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-top: 1px solid var(--border);
  padding-top: 0.75rem;
  font-size: 0.8rem;
  color: var(--text-muted);
}
.read-link {
  font-weight: 600;
  color: var(--accent);
}

/* Story Reader Page */
.reader-nav {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding: 0.7rem 1.25rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.6rem;
}
.reader-controls {
  display: flex;
  gap: 0.45rem;
  align-items: center;
}
.reader-container {
  max-width: 820px;
  margin: 2rem auto 4.5rem;
  padding: 2.5rem 2.2rem;
  background: var(--bg-reader);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
}
@media (max-width: 640px) {
  .reader-container {
    margin: 0.75rem;
    padding: 1.4rem 1.15rem;
  }
}
.story-meta-box {
  background: var(--bg-secondary);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  padding: 1rem 1.2rem;
  margin-bottom: 1.8rem;
  font-size: 0.9rem;
}
.story-meta-box div {
  margin-bottom: 0.35rem;
}
.story-meta-box div:last-child {
  margin-bottom: 0;
}
.story-hero-image {
  width: 100%;
  max-width: 560px;
  margin: 0 auto 2rem;
  display: block;
  border-radius: 12px;
  border: 1px solid var(--border);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
}
.story-header-title {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: clamp(1.5rem, 3vw, 2.15rem);
  line-height: 1.45;
  margin: 0 0 1.2rem;
}
.story-content {
  font-family: "Hiragino Mincho ProN", "Yu Mincho", "Noto Serif JP", serif;
  font-size: var(--reader-font-size);
  line-height: 2.0;
  color: var(--text-primary);
}
.story-content p {
  margin: 0 0 1.45em;
  text-align: justify;
}
.story-content h2, .story-content h3, .story-content h4 {
  font-family: "Hiragino Kaku Gothic ProN", "Yu Gothic", sans-serif;
  margin-top: 2.2em;
  margin-bottom: 0.8em;
  padding-bottom: 0.35em;
  border-bottom: 1px solid var(--border);
  color: var(--accent);
}
.story-content ul, .story-content ol {
  padding-left: 1.5em;
  margin-bottom: 1.5em;
}
.story-content li {
  margin-bottom: 0.65em;
  line-height: 1.8;
}
.scene-divider {
  text-align: center;
  margin: 2.4em 0;
  letter-spacing: 0.5em;
  color: var(--text-muted);
  font-size: 0.95rem;
}
.story-pager {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}
.pager-btn {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 0.8rem 1.1rem;
  color: var(--text-primary);
  font-size: 0.9rem;
  max-width: 48%;
}
.pager-btn:hover {
  border-color: var(--accent);
  text-decoration: none;
}
.site-footer {
  text-align: center;
  padding: 2.5rem 1rem;
  border-top: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 0.85rem;
}
"""
    target_css.write_text(css, encoding="utf-8")


def _build_story_page(
    story: Dict[str, Any],
    prev_story: Optional[Dict[str, Any]],
    next_story: Optional[Dict[str, Any]],
) -> str:
    rendered_body = _render_web_markdown(story["body_md"])
    hero_img_html = ""
    if story["has_image"]:
        hero_img_html = (
            f'<img class="story-hero-image" src="../{html.escape(story["image_rel"])}" '
            f'alt="{html.escape(story["full_title"])}" loading="lazy" />'
        )

    prev_html = (
        f'<a class="pager-btn" href="{html.escape(prev_story["work_id"])}.html">'
        f'← 前の作品：#{prev_story["no"]:02d} {html.escape(prev_story["main_title"])}</a>'
        if prev_story
        else '<span></span>'
    )
    next_html = (
        f'<a class="pager-btn" href="{html.escape(next_story["work_id"])}.html">'
        f'次の作品：#{next_story["no"]:02d} {html.escape(next_story["main_title"])} →</a>'
        if next_story
        else '<span></span>'
    )

    aozora_link = (
        f'<a href="{html.escape(story["aozora_url"])}" target="_blank" rel="noopener noreferrer">'
        f'{html.escape(story["original_author"])}『{html.escape(story["original_title"])}』（青空文庫）</a>'
        if story["aozora_url"]
        else f'{html.escape(story["original_author"])}『{html.escape(story["original_title"])}』'
    )

    return f"""<!DOCTYPE html>
<html lang="ja" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{html.escape(story["full_title"])} | 青空文庫✕最先端科学 ハードSFリブート図書館</title>
  <link rel="stylesheet" href="../style.css" />
</head>
<body>
  <nav class="reader-nav">
    <a href="../index.html">← 作品一覧（図書館トップ）へ戻る</a>
    <div class="reader-controls">
      <button class="btn-toggle" onclick="setFontSize('15.5px')">文字 小</button>
      <button class="btn-toggle" onclick="setFontSize('17.5px')">文字 中</button>
      <button class="btn-toggle" onclick="setFontSize('20px')">文字 大</button>
      <button class="btn-toggle" onclick="toggleTheme()" id="themeBtn">☀️ ライト表示</button>
    </div>
  </nav>

  <main class="reader-container">
    <div class="site-badge">ARCHIVE #{story["no"]:02d}</div>
    <h1 class="story-header-title">{html.escape(story["full_title"])}</h1>

    <div class="story-meta-box">
      <div><strong>📖 原典作品：</strong>{aozora_link}</div>
      <div><strong>🔬 導入先端科学：</strong>{html.escape(story["modern_tech"])}</div>
      <div><strong>🌏 SFリブートの視点：</strong>{html.escape(story["summary"])}</div>
    </div>

    {hero_img_html}

    <article class="story-content">
      {rendered_body}
    </article>

    <div class="story-pager">
      {prev_html}
      {next_html}
    </div>
  </main>

  <footer class="site-footer">
    <p>青空文庫 ✕ 最先端科学 ハードSFリブート図書館 — Powered by Local LLM &amp; FLUX.2 on Mac mini M4</p>
  </footer>

  <script>
    function toggleTheme() {{
      const root = document.documentElement;
      const curr = root.getAttribute('data-theme') || 'dark';
      const next = curr === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('sf_theme', next);
      document.getElementById('themeBtn').textContent = next === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
    }}
    function setFontSize(size) {{
      document.documentElement.style.setProperty('--reader-font-size', size);
      localStorage.setItem('sf_font_size', size);
    }}
    (function initPrefs() {{
      const savedTheme = localStorage.getItem('sf_theme');
      if (savedTheme) {{
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.getElementById('themeBtn').textContent = savedTheme === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
      }}
      const savedSize = localStorage.getItem('sf_font_size');
      if (savedSize) {{
        document.documentElement.style.setProperty('--reader-font-size', savedSize);
      }}
    }})();
  </script>
</body>
</html>
"""


def _build_index_page(stories: List[Dict[str, Any]]) -> str:
    total_count = len(stories)
    illustrated_count = sum(1 for s in stories if s["has_image"])
    authors = sorted({s["original_author"] for s in stories if s["original_author"]})
    updated_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    author_options = "\n".join(
        f'          <option value="{html.escape(a)}">{html.escape(a)}</option>' for a in authors
    )

    cards_html_list = []
    # Show newest/illustrated works or allow sorting; default order: reverse catalog order (latest first) with toggle
    for s in reversed(stories):
        if s["has_image"]:
            thumb_inner = (
                f'<img class="card-thumb" src="{html.escape(s["image_rel"])}" '
                f'alt="{html.escape(s["full_title"])}" loading="lazy" />'
            )
        else:
            thumb_inner = (
                f'<div class="card-placeholder">'
                f'<div style="font-size:1.1rem;color:#7dd3fc;margin-bottom:0.3rem;">『{html.escape(s["original_title"])}』</div>'
                f'<div style="font-size:0.82rem;">{html.escape(s["original_author"])} ✕ 先端科学SF</div>'
                f'</div>'
            )

        cards_html_list.append(
            f"""      <article class="story-card" data-no="{s['no']}" data-author="{html.escape(s['original_author'])}" data-illustrated="{'yes' if s['has_image'] else 'no'}" data-search="{html.escape((s['full_title'] + ' ' + s['original_title'] + ' ' + s['original_author'] + ' ' + s['modern_tech'] + ' ' + s['summary']).lower())}">
        <a href="{html.escape(s['page_rel'])}" class="card-thumb-wrap">
          {thumb_inner}
          <span class="card-no-badge">#{s['no']:02d}</span>
        </a>
        <div class="card-body">
          <div class="card-origin">原典：{html.escape(s['original_author'])}『{html.escape(s['original_title'])}』</div>
          <h2 class="card-title"><a href="{html.escape(s['page_rel'])}">{html.escape(s['full_title'])}</a></h2>
          <div class="card-tech">🔬 {html.escape(s['modern_tech'])}</div>
          <p class="card-summary">{html.escape(s['summary'])}</p>
          <div class="card-footer">
            <span>約 {s['char_count']:,} 文字 {'🎨 挿絵付' if s['has_image'] else ''}</span>
            <a class="read-link" href="{html.escape(s['page_rel'])}">作品を読む →</a>
          </div>
        </div>
      </article>"""
        )

    cards_block = "\n".join(cards_html_list)

    return f"""<!DOCTYPE html>
<html lang="ja" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>青空文庫 ✕ 最先端科学 ハードSFリブート図書館</title>
  <link rel="stylesheet" href="style.css" />
</head>
<body>
  <header class="site-header">
    <div class="site-badge">NEO AOZORA SCI-FI ARCHIVE</div>
    <h1 class="site-title">青空文庫 ✕ 最先端科学 ハードSFリブート図書館</h1>
    <p class="site-subtitle">
      日本文学の不朽の名作（青空文庫）を、実在する査読付き先端科学論文（Nature / Science / Cell 等）の知見で再構築した本格SF小説アーカイブ。<br/>
      Mac mini M4 ローカルAI（Ollama &amp; Draw Things FLUX.2）により執筆・挿絵生成し、GitHub Pages上で公開しています。
    </p>
    <div class="stats-bar">
      <div class="stat-pill"><strong>{total_count}</strong> 収録作品</div>
      <div class="stat-pill"><strong>{illustrated_count}</strong> 挿絵付き作品</div>
      <div class="stat-pill"><strong>{len(authors)}</strong> 原典文豪</div>
      <div class="stat-pill">最終更新: {updated_str}</div>
    </div>
  </header>

  <main class="container">
    <div class="toolbar">
      <div class="filter-group">
        <input type="search" id="searchInput" class="search-input" placeholder="作品名・原典・科学技術キーワードで検索..." oninput="filterCards()" />
        <select id="authorFilter" class="select-filter" onchange="filterCards()">
          <option value="">すべての原典作家（{len(authors)}名）</option>
{author_options}
        </select>
        <select id="imageFilter" class="select-filter" onchange="filterCards()">
          <option value="">すべて表示</option>
          <option value="yes">🎨 挿絵ありのみ ({illustrated_count})</option>
        </select>
        <select id="sortOrder" class="select-filter" onchange="sortCards()">
          <option value="desc">新しい順（#大 → #01）</option>
          <option value="asc">作品番号順（#01 → #大）</option>
        </select>
      </div>
      <button class="btn-toggle" onclick="toggleTheme()" id="themeBtn">☀️ ライト表示</button>
    </div>

    <div class="story-grid" id="storyGrid">
{cards_block}
    </div>
  </main>

  <footer class="site-footer">
    <p>青空文庫 ✕ 最先端科学 ハードSFリブート図書館 — Generated locally on Mac mini M4 &amp; Published on GitHub Pages</p>
  </footer>

  <script>
    function filterCards() {{
      const q = (document.getElementById('searchInput').value || '').trim().toLowerCase();
      const author = document.getElementById('authorFilter').value;
      const imgOnly = document.getElementById('imageFilter').value;
      const cards = document.querySelectorAll('.story-card');
      cards.forEach(card => {{
        const matchQ = !q || (card.getAttribute('data-search') || '').includes(q);
        const matchAuthor = !author || card.getAttribute('data-author') === author;
        const matchImg = !imgOnly || card.getAttribute('data-illustrated') === imgOnly;
        card.style.display = (matchQ && matchAuthor && matchImg) ? '' : 'none';
      }});
    }}
    function sortCards() {{
      const order = document.getElementById('sortOrder').value;
      const grid = document.getElementById('storyGrid');
      const cards = Array.from(grid.querySelectorAll('.story-card'));
      cards.sort((a, b) => {{
        const na = parseInt(a.getAttribute('data-no'), 10);
        const nb = parseInt(b.getAttribute('data-no'), 10);
        return order === 'asc' ? na - nb : nb - na;
      }});
      cards.forEach(c => grid.appendChild(c));
    }}
    function toggleTheme() {{
      const root = document.documentElement;
      const curr = root.getAttribute('data-theme') || 'dark';
      const next = curr === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      localStorage.setItem('sf_theme', next);
      document.getElementById('themeBtn').textContent = next === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
    }}
    (function initPrefs() {{
      const savedTheme = localStorage.getItem('sf_theme');
      if (savedTheme) {{
        document.documentElement.setAttribute('data-theme', savedTheme);
        document.getElementById('themeBtn').textContent = savedTheme === 'dark' ? '☀️ ライト表示' : '🌙 ダーク表示';
      }}
    }})();
  </script>
</body>
</html>
"""


def _write_root_readme(stories: List[Dict[str, Any]], target_readme: Path = Path("README.md")):
    """
    Generates the root README.md containing links to the GitHub Pages web library
    and a complete index table with direct links to every novel (Web Reader + Markdown + Illustration).
    """
    pages_base = "https://k518-2026.github.io/neo-sf-aozora"
    illustrated_count = sum(1 for s in stories if s["has_image"])
    authors = sorted({s["original_author"] for s in stories if s["original_author"]})
    updated_str = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    lines = [
        "# 青空文庫 ✕ 最先端科学 ハードSFリブート図書館（Neo Aozora Sci-Fi Library）",
        "",
        f"🌐 **Webサイト（GitHub Pages）で読む**: **[{pages_base}/]({pages_base}/)**",
        "",
        "日本文学の不朽の名作（青空文庫）をモチーフに、実在する査読付き先端科学論文（*Nature* / *Science* / *Cell* / *PNAS* 等）の知見を取り入れて再構築した本格SF短編小説コレクションです。",
        "",
        "- **執筆・挿絵生成**: Mac mini M4 ローカルAI（Ollama `qwen2.5:14b` / `gemma4:12b` ＆ Draw Things `FLUX.2 [klein] 4B`）",
        "- **外部生成AI API不使用**: 外部の商用生成AI APIは一切使用せず、すべてローカル環境で執筆・画像生成を行っています。",
        f"- **収録作品数**: 全 **{len(stories)}** 作品（うち挿絵付き **{illustrated_count}** 作品 / 原典文豪 **{len(authors)}** 名 / 最終更新: {updated_str}）",
        "",
        "---",
        "",
        "## 📚 収録SF小説一覧（リンク集）",
        "",
        "| No. | リブート小説タイトル | Webページで読む | 原稿 (Markdown) | 挿絵 | 原典作品（青空文庫） | 導入した現代先端科学技術 | 文字数 |",
        "|:---:|:---|:---:|:---:|:---:|:---|:---|---:|",
    ]

    for s in reversed(stories):
        md_rel = s["md_path"].as_posix()
        web_url = f"{pages_base}/{s['page_rel']}"
        img_cell = f"[🎨挿絵]({s['png_path'].as_posix()})" if s["has_image"] and s["png_path"] else "—"
        orig_cell = (
            f"{s['original_author']}[『{s['original_title']}』]({s['aozora_url']})"
            if s["aozora_url"]
            else f"{s['original_author']}『{s['original_title']}』"
        )
        lines.append(
            f"| {s['no']:02d} | **[{s['full_title']}]({md_rel})** | [🌐Web版]({web_url}) | [📄原稿]({md_rel}) | {img_cell} | {orig_cell} | {s['modern_tech']} | {s['char_count']:,}字 |"
        )

    lines.extend([
        "",
        "---",
        "",
        "## 🛠️ ローカル執筆＆GitHub Pages更新コマンド（Mac mini M4連携）",
        "",
        "```powershell",
        "# 未生成の小説と挿絵をMac mini M4 (Ollama + Draw Things) でバッチ生成してGitHub Pagesへ反映",
        ".\\run_local_stock.ps1 -Count 3",
        "",
        "# 既存小説のうち未生成の挿絵 (.png) を生成してGitHub Pagesへ反映",
        "python -m src.batch_stock --generate-images --push",
        "",
        "# Webサイト (docs/) と README.md のリンク一覧を再ビルド",
        "python -m src.site_builder",
        "```",
        "",
    ])

    target_readme.write_text("\n".join(lines), encoding="utf-8")


def build_github_pages(history_mgr: Optional[HistoryManager] = None) -> Dict[str, Any]:
    """
    Generates the static GitHub Pages site in `docs/` and updates root `README.md`
    from all Markdown stories and PNG illustrations in `content/`.
    """
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    STORIES_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Ensure GitHub Pages serves static files directly without Jekyll processing
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    stories = collect_all_stories(history_mgr)
    _write_stylesheet(DOCS_DIR / "style.css")

    # Copy illustrations and build individual story HTML pages
    for idx, story in enumerate(stories):
        if story["has_image"] and story["png_path"] is not None:
            dest_img = IMAGES_DIR / f"{story['work_id']}.png"
            shutil.copy2(story["png_path"], dest_img)

        prev_story = stories[idx - 1] if idx > 0 else None
        next_story = stories[idx + 1] if idx + 1 < len(stories) else None
        page_html = _build_story_page(story, prev_story=prev_story, next_story=next_story)
        (STORIES_DIR / f"{story['work_id']}.html").write_text(page_html, encoding="utf-8")

    # Write index.html (descending: newest story at the very top)
    index_html = _build_index_page(stories)
    (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")

    # Write machine-readable catalog index in docs/stories.json (descending: newest first)
    manifest = [
        {
            "no": s["no"],
            "work_id": s["work_id"],
            "title": s["full_title"],
            "original_title": s["original_title"],
            "original_author": s["original_author"],
            "modern_tech": s["modern_tech"],
            "has_image": s["has_image"],
            "url": s["page_rel"],
            "image": s["image_rel"],
            "char_count": s["char_count"],
        }
        for s in reversed(stories)
    ]
    (DOCS_DIR / "stories.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Fallback / alias for https://k518-2026.github.io/neo-sf-aozora/docs/
    docs_sub = DOCS_DIR / "docs"
    docs_sub.mkdir(parents=True, exist_ok=True)
    docs_redirect_html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"ja\">\n"
        "<head>\n"
        "  <meta charset=\"UTF-8\">\n"
        "  <meta http-equiv=\"refresh\" content=\"0; url=../\">\n"
        "  <title>青空文庫SF進化論 - 自動リダイレクト</title>\n"
        "  <script>\n"
        "    window.location.replace('../' + window.location.search + window.location.hash);\n"
        "  </script>\n"
        "</head>\n"
        "<body style=\"font-family: sans-serif; text-align: center; padding: 40px;\">\n"
        "  <p>青空文庫SF進化論 ライブラリへ移動しています... <a href=\"../\">トップページはこちら</a></p>\n"
        "</body>\n"
        "</html>\n"
    )
    (docs_sub / "index.html").write_text(docs_redirect_html, encoding="utf-8")

    # 404.html with automatic redirection for legacy /docs/ subpaths or invalid URLs
    not_found_html = (
        "<!DOCTYPE html>\n"
        "<html lang=\"ja\">\n"
        "<head>\n"
        "  <meta charset=\"UTF-8\">\n"
        "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n"
        "  <title>青空文庫SF進化論</title>\n"
        "  <script>\n"
        "    (function() {\n"
        "      var p = window.location.pathname;\n"
        "      if (p.indexOf('/neo-sf-aozora/docs/') !== -1) {\n"
        "        var target = p.replace('/neo-sf-aozora/docs/', '/neo-sf-aozora/') + window.location.search + window.location.hash;\n"
        "        window.location.replace(target);\n"
        "      }\n"
        "    })();\n"
        "  </script>\n"
        "  <link rel=\"stylesheet\" href=\"/neo-sf-aozora/style.css\">\n"
        "</head>\n"
        "<body style=\"font-family: sans-serif; text-align: center; padding: 60px 20px; background: #0f172a; color: #f8fafc;\">\n"
        "  <h2 style=\"color: #38bdf8;\">青空文庫SF進化論 ライブラリ</h2>\n"
        "  <p style=\"color: #94a3b8;\">お探しのページへ移動しています...</p>\n"
        "  <p style=\"margin-top: 24px;\"><a href=\"/neo-sf-aozora/\" style=\"color: #38bdf8; text-decoration: underline;\">トップページへ戻る</a></p>\n"
        "</body>\n"
        "</html>\n"
    )
    (DOCS_DIR / "404.html").write_text(not_found_html, encoding="utf-8")

    # Update root README.md with links to all novels
    _write_root_readme(stories, Path("README.md"))

    illustrated = sum(1 for s in stories if s["has_image"])
    logger.info(
        f"GitHub Pages site built in docs/ and README.md updated: {len(stories)} stories ({illustrated} with illustrations)"
    )
    return {
        "total_stories": len(stories),
        "illustrated_stories": illustrated,
        "docs_dir": str(DOCS_DIR.resolve()),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    build_github_pages()

