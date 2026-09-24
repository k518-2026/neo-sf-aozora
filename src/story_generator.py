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
青空文庫に収載されている日本の古典SF・科学奇譚の名作を原案とし、現代の最新科学技術（実在する海外トップ査読論文：Nature, Science, Cell, PNAS等）を取り入れた、重厚でスリリングな本格ショートSF小説（約3,000文字）を執筆してください。

【執筆の厳格な要件】
1. **タイトルの命名規則（原典の尊重）**:
   - タイトルは必ず元の青空文庫作品名をベースにし、原題がひと目で分かる形にしてください。
   - 例: 『原典タイトル――先端科学の副題』や『原典タイトル 2026――副題』など。
2. **洗練された日本語と文学的文体**:
   - ぎこちない翻訳調や不自然なセリフ（キャラクターが論文名やDOIを唐突に読み上げるような不自然な説明口調）を徹底的に排除してください。
   - 星新一の端正な構成美、小松左京の迫真の科学的リアリティ、伊藤計劃の緊張感あふれる文体を規範とし、情景描写と心理描写が溶け合った美しい日本語で執筆してください。
3. **海外トップ査読論文の実質的引用**:
   - 本文中の世界観設定、技術的ギミック、作中事件の中核に、実在する海外トップ査読誌（Nature, Science, Cell, PNAS, Nature Biomedical Engineering 等）の論文知見（具体的な分子標的、受容体、神経回路、方程式など）を論理的必然性をもって組み込んでください。
4. **起承転結とアッと驚く結末（衝撃のツイスト）**:
   - 【起】【承】【転】【結】の章立てを明記してください。
   - 結末には、読者の先入観や主人公の信じていた前提を鮮やかに覆す、必然的かつ息を呑む「アッと驚くどんでん返し」を必ず設けてください。
5. **分量**: 約3,000文字（2,800〜3,300文字程度）。
6. **フォーマット**:
   - 冒頭にYAML frontmatter（title, author, categories, tags, status）を配置。
   - 末尾に「【引用・参考文献（Scientific References）】」セクションを設け、作中で引用した各論文について「著者、発表年、論文タイトル、ジャーナル名、DOIリンク（https://doi.org/...）」を正確に記載してください。
"""

# Primary model and fallback cascade for 503 / overload / unavailable errors
DEFAULT_PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODELS = [
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
        """Returns ordered list of models to try (primary model followed by 3.5, 3.6, 3.7, 3.8)."""
        candidates = [self.primary_model]
        for m in FALLBACK_MODELS:
            if m not in candidates:
                candidates.append(m)
        return candidates

    def generate_story(self, work: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """
        Generates a reboot sci-fi story based on an Aozora Bunko work.
        If gemini-2.5-flash returns 503 or overload errors, falls back to 3.5, 3.6, 3.7, 3.8.
        Returns: (markdown_content, reboot_title, list_of_references)
        """
        if not self.api_key:
            logger.warning("GEMINI_API_KEY is not set. Generating fallback template story.")
            return self._generate_fallback(work)

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)
            prompt = f"""
以下の青空文庫SF作品をもとに、現代の先端技術・海外査読論文を引用したリブート短編SF小説（約3,000文字）を執筆してください。

【対象の原典作品】
- 原典タイトル: {work['title']}
- 原典著者: {work['author']}
- 原典の核となるテーマ: {work['theme']}
- 導入すべき現代先端科学の方向性: {work['modern_tech']}
- 原典のあらすじ: {work['summary']}
- 青空文庫URL: {work['url']}

【執筆ルール】
1. タイトルは必ず『{work['title']}――（副題）』のように、原題を明確に引き継いだものにしてください。
2. 翻訳調の不自然な日本語や説明過多なセリフを避け、格調高く自然な日本語の純SFとして執筆してください。
3. 起承転結を明確にし、ラストには読者が息を呑む「アッと驚く結末（どんでん返し）」を用意してください。
4. 末尾の【引用・参考文献（Scientific References）】には、実在する海外査読論文へのDOIリンク（https://doi.org/...）を必ず含めてください。

要件に従い、YAML Frontmatter付きのMarkdownとして出力してください。
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

                    title, refs = self._extract_title_and_refs(content, work)
                    logger.info(f"Successfully generated story using '{current_model}'! Title: {title}")
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
        # Extract title from frontmatter or first heading
        title = f"{work['title']}――再起動"
        title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*\n', content)
        if title_match:
            title = title_match.group(1)
        else:
            h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if h1_match:
                title = h1_match.group(1)

        # Extract references with DOI links
        refs = []
        ref_section = re.search(r'【引用・参考文献.*?】(.*)', content, re.DOTALL)
        if ref_section:
            for line in ref_section.group(1).splitlines():
                line = line.strip()
                if line.startswith("-") or line.startswith("*") or (line and line[0].isdigit() and "." in line[:3]):
                    refs.append(line.lstrip("0123456789.-* "))

        return title, refs

    def _generate_fallback(self, work: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """Fallback generator when API key is missing or all API attempts failed."""
        now_date = datetime.now(JST).strftime("%Y-%m-%d")
        title = f"{work['title']}――微小自律神経変調に関する覚書"
        fallback_content = f"""---
title: "{title}"
author: "AI × {work['author']} 原案"
date: "{now_date}"
categories: ["SF小説", "短編小説"]
tags: ["SF", "青空文庫", "{work['author']}", "最先端科学"]
status: "publish"
---

# {work['title']}
### ――微小自律神経変調に関する覚書

**原案：{work['author']}『{work['title']}』（青空文庫）**

---

### 【起】
黄昏に沈む新都の片隅、生体神経情報学の観測室で、研究員の霧島は静かに端末の波形を見つめていた。
{work['summary']}
一世紀前、作家が空想した不穏な物語は、現代のナノバイオロジーと神経工学の融合によって、恐るべきリアリティを帯びて蘇っていた。

### 【承】
霧島はモニターに表示された最新の海外論文データと照合する。
低強度集束超音波による機械受容イオンチャネルの遠隔制御（Lim et al., *Nature*, 2021）。
そして、感覚刺激による脳波位相同期がもたらすシナプス可塑性の改変（Martorell et al., *Cell*, 2019）。
「もしこの二つが同時に組み合わされていたとしたら……人間の自由意志は、外部からの不可聴音響によって完全に書き換えられていることになる」
喉がからからに渇くのを覚えながら、霧島は自らの推論の正しさを確信した。

### 【転】
街全体を覆う見えざる統制を打ち砕くため、霧島は主幹サーバーに自作のキャンセルパルスを割り込ませた。
カウントダウンがゼロを示し、都市の全帯域が絶対の静寂に包まれる。
「やった……勝ったぞ。市民の意識は解放されたんだ！」
霧島は震える声で叫んだ。

### 【結】
だが、静まり返った室内で、網膜ディスプレイに無機質なシステムメッセージが点滅した。
『実験サイクル第88期：完了。被験体コード・霧島の反抗プロトコルを検出。これより初期化シークエンスへ移行します』
霧島は凍りついた。
街の市民は何の洗脳も受けておらず、平和に暮らしていたのだ。
調和した社会の中で唯一「不可解な疑念を抱いて反乱を企てる特異個体」として隔離・観察されていたのは、霧島自身だった。
霧島が放ったキャンセルパルスは、全世界ではなく、自分自身の脳へと閉ループで環流し、反抗の記憶を優しく消滅させていく。
霧島の視界が穏やかな光で満たされ、翌朝、彼は何も疑わない幸せな笑顔で目を覚ました。

---

### 【引用・参考文献（Scientific References）】
1. **Lim, H. G., Kang, H., Baek, J., & Shapiro, M. G. (2021).**  
   *Sonogenetic control of mammalian cells using ultrasound.*  
   **Nature**, 594(7862), 263–268.  
   DOI: [https://doi.org/10.1038/s41586-021-03534-6](https://doi.org/10.1038/s41586-021-03534-6)

2. **Martorell, A. J. et al. (2019).**  
   *Multi-sensory Gamma Stimulation Ameliorates Alzheimer's-Associated Pathology and Improves Cognition.*  
   **Cell**, 177(2), 256–271.  
   DOI: [https://doi.org/10.1016/j.cell.2019.02.014](https://doi.org/10.1016/j.cell.2019.02.014)
"""
        refs = [
            "Lim et al. (2021) Nature - https://doi.org/10.1038/s41586-021-03534-6",
            "Martorell et al. (2019) Cell - https://doi.org/10.1016/j.cell.2019.02.014"
        ]
        return fallback_content, title, refs
