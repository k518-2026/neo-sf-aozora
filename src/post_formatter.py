import re
import html
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

# Try importing yaml, with fallback to built-in parser
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Try importing markdown, with fallback to built-in converter
try:
    import markdown
    HAS_MARKDOWN = True
except ImportError:
    HAS_MARKDOWN = False

@dataclass
class FormattedPost:
    title: str
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    status: str = "publish"
    content_raw: str = ""
    content_html: str = ""
    content_plain: str = ""

def _fallback_yaml_parser(text: str) -> Dict[str, Any]:
    """Lightweight fallback YAML parser for simple frontmatter dictionaries."""
    data: Dict[str, Any] = {}
    for line in text.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()
            # Handle quotes
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            # Handle simple bracket lists: ["a", "b"]
            if val.startswith("[") and val.endswith("]"):
                items = [item.strip().strip("'\"") for item in val[1:-1].split(",") if item.strip()]
                data[key] = items
            else:
                data[key] = val
    return data

def _fallback_markdown_to_html(md_text: str) -> str:
    """Lightweight fallback Markdown to HTML converter using regex."""
    lines = md_text.splitlines()
    html_lines = []
    in_code_block = False
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Code blocks
        if stripped.startswith("```"):
            if in_code_block:
                html_lines.append("</code></pre>")
                in_code_block = False
            else:
                html_lines.append("<pre><code>")
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(html.escape(line))
            continue

        # Horizontal rule
        if stripped in ("---", "***", "___"):
            html_lines.append("<hr>")
            continue

        # Headings
        if stripped.startswith("# "):
            html_lines.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h3>{html.escape(stripped[4:])}</h3>")
            continue
        if stripped.startswith("#### "):
            html_lines.append(f"<h4>{html.escape(stripped[5:])}</h4>")
            continue

        # Blockquote
        if stripped.startswith("> "):
            html_lines.append(f"<blockquote><p>{html.escape(stripped[2:])}</p></blockquote>")
            continue

        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:]
            item = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", item)
            item = re.sub(r"\*(.*?)\*", r"<em>\1</em>", item)
            item = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', item)
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{item}</li>")
            continue
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False

        # Empty line
        if not stripped:
            continue

        # Regular paragraph with inline formatting
        p_text = stripped
        p_text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", p_text)
        p_text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", p_text)
        p_text = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', p_text)
        html_lines.append(f"<p>{p_text}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_code_block:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)

def parse_markdown_with_frontmatter(file_path: str) -> Tuple[Dict[str, Any], str]:
    """Parses a markdown file that contains YAML frontmatter."""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    frontmatter = {}
    body = text

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if match:
        yaml_text = match.group(1)
        body = match.group(2)
        if HAS_YAML:
            try:
                frontmatter = yaml.safe_load(yaml_text) or {}
            except Exception:
                frontmatter = _fallback_yaml_parser(yaml_text)
        else:
            frontmatter = _fallback_yaml_parser(yaml_text)

    return frontmatter, body

def format_post_content(
    file_path: str,
    status_override: Optional[str] = None,
    include_jetpack_shortcodes: bool = True
) -> FormattedPost:
    """
    Loads a markdown story file and prepares both HTML and plain text
    formatted for WordPress Post-via-Email.
    """
    meta, body = parse_markdown_with_frontmatter(file_path)

    title = meta.get("title", "無題のSF作品")
    categories = meta.get("categories", ["SF小説"])
    if isinstance(categories, str):
        categories = [c.strip() for c in categories.split(",")]

    tags = meta.get("tags", ["SF", "青空文庫"])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    status = status_override or meta.get("status", "publish")

    # Clean existing shortcodes in body if already present
    cleaned_body = re.sub(r"\[(category|tags|status|title|excerpt)[^\]]*\]", "", body).strip()

    # Convert markdown to HTML
    if HAS_MARKDOWN:
        html_body = markdown.markdown(
            cleaned_body,
            extensions=["extra", "toc", "sane_lists"]
        )
    else:
        html_body = _fallback_markdown_to_html(cleaned_body)

    # Wrap in clean, modern typography styling for WordPress email rendering
    styled_html = f"""<div class="sf-story-container" style="font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif; line-height: 1.9; font-size: 16px; color: #222;">
{html_body}
</div>"""

    # If Jetpack shortcodes are requested, prepend/append them
    sc_lines = []
    if status:
        sc_lines.append(f"[status {status}]")
    if categories:
        sc_lines.append(f"[category {', '.join(categories)}]")
    if tags:
        sc_lines.append(f"[tags {', '.join(tags)}]")

    final_plain = cleaned_body
    if include_jetpack_shortcodes and sc_lines:
        shortcode_block = "\n".join(sc_lines)
        final_plain = f"{final_plain}\n\n{shortcode_block}"
        final_html = f"{styled_html}\n<p style='color: #888; font-size: 12px;'>" + "<br>".join(sc_lines) + "</p>"
    else:
        final_html = styled_html

    return FormattedPost(
        title=title,
        categories=categories,
        tags=tags,
        status=status,
        content_raw=cleaned_body,
        content_html=final_html,
        content_plain=final_plain
    )
