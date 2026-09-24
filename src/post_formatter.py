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
    """
    Lightweight fallback Markdown to HTML converter.
    NEVER produces <hr> or stray <br> tags to prevent WordPress email truncating.
    """
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

        # Horizontal rule / Scene separators (NEVER use <hr>)
        if stripped in ("---", "***", "___", "* * *", "- - -", "◆ ◆ ◆"):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append('<div style="text-align: center; margin: 2em 0; letter-spacing: 0.5em; color: #888;">◆ ◆ ◆</div>')
            continue

        # Headings
        if stripped.startswith("# "):
            html_lines.append(f"<h1 style='margin-top: 1.5em; margin-bottom: 0.8em;'>{html.escape(stripped[2:])}</h1>")
            continue
        if stripped.startswith("## "):
            html_lines.append(f"<h2 style='margin-top: 1.5em; margin-bottom: 0.8em;'>{html.escape(stripped[3:])}</h2>")
            continue
        if stripped.startswith("### "):
            html_lines.append(f"<h3 style='margin-top: 1.5em; margin-bottom: 0.8em;'>{html.escape(stripped[4:])}</h3>")
            continue
        if stripped.startswith("#### "):
            html_lines.append(f"<h4 style='margin-top: 1.2em; margin-bottom: 0.6em;'>{html.escape(stripped[5:])}</h4>")
            continue

        # Blockquote
        if stripped.startswith("> "):
            html_lines.append(f"<blockquote style='border-left: 4px solid #ccc; padding-left: 1em; margin: 1em 0; color: #666;'><p style='margin: 0;'>{html.escape(stripped[2:])}</p></blockquote>")
            continue

        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:]
            item = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", item)
            item = re.sub(r"\*(.*?)\*", r"<em>\1</em>", item)
            item = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', item)
            if not in_list:
                html_lines.append('<ul style="margin: 1em 0; padding-left: 1.5em;">')
                in_list = True
            html_lines.append(f"<li style='margin-bottom: 0.5em;'>{item}</li>")
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
        html_lines.append(f"<p style='margin-bottom: 1.5em; line-height: 1.9;'>{p_text}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_code_block:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)

def parse_markdown_with_frontmatter(file_path: str) -> Tuple[Dict[str, Any], str]:
    """Parses a markdown file that contains YAML frontmatter or code blocks."""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()

    frontmatter: Dict[str, Any] = {}
    body = text

    # Case 1: Standard YAML frontmatter between --- and ---
    match_dash = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    # Case 2: Code fence ```yaml ... ```
    match_fence = re.match(r"^```(?:ya?ml)?\s*\n(.*?)\n```\s*\n(.*)$", text, re.DOTALL)
    # Case 3: Stray yaml\n ... ```
    match_stray = re.match(r"^(?:ya?ml\s*\n)?(title:\s*.*?\n(?:status|tags|categories|author):\s*.*?)\n```\s*\n(.*)$", text, re.DOTALL)

    yaml_text = None
    if match_dash:
        yaml_text = match_dash.group(1)
        body = match_dash.group(2)
    elif match_fence:
        yaml_text = match_fence.group(1)
        body = match_fence.group(2)
    elif match_stray:
        yaml_text = match_stray.group(1)
        body = match_stray.group(2)

    if yaml_text:
        if HAS_YAML:
            try:
                frontmatter = yaml.safe_load(yaml_text) or {}
            except Exception:
                frontmatter = _fallback_yaml_parser(yaml_text)
        else:
            frontmatter = _fallback_yaml_parser(yaml_text)

    # Fallback title if still missing
    if "title" not in frontmatter:
        title_m = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        if title_m:
            frontmatter["title"] = title_m.group(1).strip()

    return frontmatter, body

def format_post_content(
    file_path: str,
    status_override: Optional[str] = None,
    include_jetpack_shortcodes: bool = True
) -> FormattedPost:
    """
    Loads a markdown story file and prepares both HTML and plain text
    formatted strictly for WordPress Post-via-Email.
    CRITICAL: Completely prevents <hr> and loose --- separators which cause
    WordPress email parsers to prematurely truncate content as an email signature.
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

    # Pre-clean 1: Automatically strip any '起', '承', '転', '結' headers or markers
    cleaned_body = re.sub(r"^[ \t]*#+[ \t]*[【\[（(]?[起承転結][】\]）)]?.*$", "", cleaned_body, flags=re.MULTILINE)
    cleaned_body = re.sub(r"[【\[（(][起承転結][】\]）)]", "", cleaned_body)
    cleaned_body = re.sub(r"^[ \t]*[【\[（(]?[起承転結][】\]）)]?[ \t]*$", "", cleaned_body, flags=re.MULTILINE)

    # Pre-clean 2: Replace markdown hr lines (---, ***, ___) with safe scene dividers to prevent email signature truncation
    cleaned_body = re.sub(r"^[ \t]*[-*_]{3,}[ \t]*$", "◆ ◆ ◆", cleaned_body, flags=re.MULTILINE)

    # Convert markdown to HTML
    if HAS_MARKDOWN:
        html_body = markdown.markdown(
            cleaned_body,
            extensions=["extra", "toc", "sane_lists"]
        )
    else:
        html_body = _fallback_markdown_to_html(cleaned_body)

    # CRITICAL POST-PROCESSING FOR WORDPRESS EMAIL:
    # 1. Replace all <hr>, <hr/>, <hr /> with safe styled div
    html_body = re.sub(
        r"<hr\s*/?>",
        '<div style="text-align: center; margin: 2em 0; letter-spacing: 0.5em; color: #888;">◆ ◆ ◆</div>',
        html_body,
        flags=re.IGNORECASE
    )

    # 2. Avoid multiple consecutive <br>
    html_body = re.sub(r"(?:<br\s*/?>\s*){2,}", "<p></p>", html_body, flags=re.IGNORECASE)

    # Wrap in clean, modern typography styling for WordPress email rendering
    styled_html = f"""<div class="sf-story-container" style="font-family: 'Hiragino Mincho ProN', 'Yu Mincho', serif; line-height: 1.9; font-size: 16px; color: #222;">
{html_body}
</div>"""

    # If Jetpack shortcodes are requested, append them using clean <p> tags (NO <br>)
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
        # Use individual <p> tags for each shortcode to avoid <br> issues in WordPress
        shortcodes_html_list = [f"<p style='color: #888; font-size: 12px; margin: 0.3em 0;'>{sc}</p>" for sc in sc_lines]
        final_html = f"{styled_html}\n<div class='wp-meta-shortcodes' style='margin-top: 2em;'>\n" + "\n".join(shortcodes_html_list) + "\n</div>"
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
