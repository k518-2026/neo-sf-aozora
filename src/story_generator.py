import os
import re
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

SYSTEM_PROMPT = """あなたは最先端の科学技術と現代日本文学の粋を極めた一流のハードSF作家です。
青空文庫に収載されている日本の古典SF・科学奇譚の名作を原案とし、現代の最新科学技術（実在する海外トップ査読論文：Nature, Science, Cell, PNAS等）を取り入れた、重厚でスリリングな本格ショートSF小説（約4,000文字）を執筆してください。

【執筆の厳格な要件】
1. **タイトルの命名規則（原典の尊重）**:
   - タイトルは必ず元の青空文庫作品名をベースにし、原題がひと目で分かる形にしてください。
   - 例: 『原典タイトル――先端科学の副題』など。
2. **【起】【承】【転】【結】などの記号・見出しは本文中に入れないこと**:
   - 物語の途中に「【起】」「【承】」といった記号や見出しを絶対に入れないでください。
   - シーンの転換には、空行または「* * *」を用いて、自然な文学的流れを作ってください。
3. **オチ（結末）の多様性と独自性（同一オチ・夢オチの完全厳禁）**:
   - 作品ごとに、その作品が扱う科学技術（音響、昆虫、アンドロイド、宇宙、量子、遺伝子工学等）に立脚した**完全に固有の未来予測と科学的どんでん返し**を考案してください。
   - **「培養脳バイオリアクター内の夢だった」「シミュレーション仮説だった」「VRゲームだった」といったオチの安易な使い回し・パターン化を固く禁じます。**
   - **たとえ原典作品が夢オチやノイローゼの妄想で終わる作品であっても、本作では絶対に安易な夢オチにしてはなりません。現代の先端科学を極限まで論理的に外挿（未来推測）し、息を呑むような驚愕の客観的現実を結末に据えてください。**
4. **分量と洗練された日本語**:
   - 小説本文の分量は約4,000文字（3,800〜4,500文字程度）の重厚なスケールにしてください。
   - ぎこちない翻訳調や、キャラクターが論文名やDOIを読み上げるような不自然なセリフを徹底排除してください。
   - 小松左京の科学的迫真性、伊藤計劃の知性と緊張感、星新一の構成美を意識した、流麗で美しい日本語で執筆してください。
5. **全体の構成（三部構成）**:
   - **第一部：小説本文**（約4,000文字、起承転結を内包した衝撃の物語）
   - **第二部：【作中技術のやさしい解説（Technical Commentary）】**
     （一般の読者向けに、作中に登場したその作品固有の最先端技術をわかりやすく解説）
   - **第三部：【引用・参考文献（Scientific References）】**
     （実在する海外トップ査読論文の著者、論文タイトル、ジャーナル名、発表年、およびクリック可能なDOIリンク `[https://doi.org/...](https://doi.org/...)`）
"""

# Primary model and fallback cascade for quota/overload errors
DEFAULT_PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-3.5-flash",
    "gemini-3.5",
    "gemini-3.6-flash",
    "gemini-3.6",
    "gemini-3.7-flash",
    "gemini-3.7",
    "gemini-3.8-flash",
    "gemini-3.8"
]

class StoryGenerator:
    def __init__(self, api_key: Optional[str] = None, model_name: Optional[str] = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.primary_model = model_name or os.getenv("GEMINI_TEXT_MODEL", DEFAULT_PRIMARY_MODEL)

    def _get_model_candidates(self) -> List[str]:
        """Returns ordered list of real, valid Gemini models to try."""
        candidates = [self.primary_model]
        for m in FALLBACK_MODELS:
            if m not in candidates:
                candidates.append(m)
        return candidates

    def generate_story(self, work: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """
        Generates a reboot sci-fi story based on an Aozora Bunko work.
        If primary model returns 503 or overload errors, falls back to other valid Gemini models.
        Returns: (markdown_content, reboot_title, list_of_references)
        """
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not set. Refusing to generate a low-quality short fallback.")
            return self._generate_fallback(work)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            prompt = f"""
以下の青空文庫SF作品をもとに、現代の先端技術・海外査読論文を引用したリブート短編SF小説（本文約4,000文字＋技術解説＋DOI参考文献）を執筆してください。

【対象の原典作品】
- 原典タイトル: {work['title']}
- 原典著者: {work['author']}
- 原典の核となるテーマ: {work['theme']}
- 導入すべき現代先端科学の方向性: {work['modern_tech']}
- 原典のあらすじ: {work['summary']}
- 青空文庫URL: {work['url']}

【必須ルール】
1. タイトルは必ず『{work['title']}――（副題）』のように、原題を明確に引き継いだものにしてください。
2. 文章の最初や途中に【起】【承】【転】【結】などの記号や見出しを絶対に入れないでください（アスタリスク '* * *' 等でシーン転換）。
3. **【オチの独自性と未来推測】**:
   - オチ（結末）は必ず作品ごとに全く異なるものにしてください。
   - **「培養脳の夢だった」「シミュレーションだった」「仮想現実だった」といった安易なオチの使い回しを完全に禁止します。**
   - **たとえ原典が夢オチや妄想オチであっても、現代の最先端科学・海外査読論文（{work['modern_tech']}）から導き出される、息を呑むような驚異の客観的未来予測や科学的真実を結末に据えてください。**
4. 本文は約4,000文字のスケールにし、二重三重の読者を驚かせる論理的な「強烈などんでん返しの結末（オチ）」を用意してください。
5. 本文の後に必ず【作中技術のやさしい解説（Technical Commentary）】を設け、作中に登場した先端科学技術（その作品固有の技術）を一般読者向けにわかりやすく解説してください。
6. 最後に【引用・参考文献（Scientific References）】を設け、実在する海外査読論文（Nature, Science等）へのDOIハイパーリンク `[https://doi.org/...](https://doi.org/...)` を正確に記載してください。
7. タイトルの直下に、必ず青空文庫へのハイパーリンクを含めた原案表記『**原案：{work['author']}[『{work['title']}』]({work['url']})（青空文庫）**』を記載してください。

要件に従い、冒頭にYAML Frontmatterを配置したMarkdown形式で出力してください。
"""
            model_candidates = self._get_model_candidates()
            last_error = None

            for idx, current_model in enumerate(model_candidates):
                logger.info(f"Attempting SF story generation with model '{current_model}' (Attempt {idx + 1}/{len(model_candidates)})...")
                try:
                    response = client.models.generate_content(
                        model=current_model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            temperature=0.8,
                            max_output_tokens=8192,
                        )
                    )

                    content = response.text.strip()
                    # Clean possible markdown wrapping
                    if content.startswith("```markdown"):
                        content = content[len("```markdown"):].strip()
                    if content.startswith("```"):
                        content = content[3:].strip()
                    if content.endswith("```"):
                        content = content[:-3].strip()

                    # Quality check: ensure substantial length (at least 2,500 characters)
                    if len(content) < 2500:
                        logger.warning(
                            f"Model '{current_model}' output too short ({len(content)} chars < 2500 target). "
                            f"Trying next model candidate for a richer, more detailed narrative..."
                        )
                        continue

                    title, refs = self._extract_title_and_refs(content, work)
                    logger.info(f"Successfully generated story using '{current_model}'! Title: {title}, Length: {len(content)} chars")
                    return content, title, refs

                except Exception as e:
                    last_error = e
                    err_msg = str(e)
                    is_503_or_overload = any(term in err_msg.lower() for term in [
                        "503", "unavailable", "overloaded", "resource_exhausted", "rate_limit", "internal server error"
                    ])

                    if is_503_or_overload:
                        logger.warning(
                            f"Model '{current_model}' encountered server/capacity error (503/Unavailable/Overloaded): {err_msg}. "
                            f"Retrying with next fallback model version in cascade..."
                        )
                    else:
                        logger.warning(
                            f"Model '{current_model}' returned error: {err_msg}. "
                            f"Trying fallback model version..."
                        )
                    
                    time.sleep(2)

            logger.error(f"All model candidates failed. Last error: {last_error}", exc_info=True)
            return self._generate_fallback(work)

        except Exception as e:
            logger.error(f"Failed to initialize Gemini Client: {e}", exc_info=True)
            return self._generate_fallback(work)

    def _extract_title_and_refs(self, content: str, work: Dict[str, Any]) -> Tuple[str, List[str]]:
        title = f"{work['title']}――再起動"
        title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*\n', content)
        if title_match:
            title = title_match.group(1)
        else:
            h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if h1_match:
                title = h1_match.group(1)

        refs = []
        ref_section = re.search(r'【引用・参考文献.*?】(.*)', content, re.DOTALL)
        if ref_section:
            for line in ref_section.group(1).splitlines():
                line = line.strip()
                if line.startswith("-") or line.startswith("*") or (line and line[0].isdigit() and "." in line[:3]):
                    refs.append(line.lstrip("0123456789.-* "))

        return title, refs

    def _generate_fallback(self, work: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """
        Fallback handler: Looks for an existing pre-crafted high-quality story file in content/.
        If none exists, raises RuntimeError to prevent publishing an unintended duplicate or low-quality template.
        """
        content_dir = Path("content")
        work_id = work.get("id", "")
        clean_id = work_id.replace("-", "_")

        # Check content directory for matching pre-crafted files
        matched_file = None
        if content_dir.exists():
            for f in sorted(content_dir.glob("*.md")):
                if work_id in f.name or clean_id in f.name:
                    matched_file = f
                    break

        if matched_file and matched_file.exists():
            logger.info(f"Using pre-crafted high-quality story from {matched_file} for '{work['title']}'")
            content = matched_file.read_text(encoding="utf-8")
            title, refs = self._extract_title_and_refs(content, work)
            return content, title, refs

        err_msg = (
            f"Cannot generate story for '{work['title']}' ({work['id']}): "
            f"Gemini API generation failed/unavailable and no pre-crafted file found in content/. "
            f"Aborting to prevent publishing low-quality template."
        )
        logger.error(err_msg)
        raise RuntimeError(err_msg)
