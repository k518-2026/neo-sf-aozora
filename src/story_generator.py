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
3. **分量とオチ（結末）の強力なツイスト**:
   - 小説本文の分量は約4,000文字（3,800〜4,500文字程度）の重厚なスケールにしてください。
   - 単なる「主人公の勘違い」や「夢オチ」ではなく、読者の世界観認識を二重三重に覆す、論理的かつ圧倒的な衝撃の結末（アッと驚く多重ツイスト）を構築してください。
4. **洗練された日本語と文学的文体**:
   - ぎこちない翻訳調や、キャラクターが論文名やDOIを読み上げるような不自然なセリフを徹底排除してください。
   - 小松左京の科学的迫真性、伊藤計劃の知性と緊張感、星新一の構成美を意識した、流麗で美しい日本語で執筆してください。
5. **全体の構成（三部構成）**:
   - **第一部：小説本文**（約4,000文字、起承転結を内包した衝撃の物語）
   - **第二部：【作中技術のやさしい解説（Technical Commentary）】**
     （一般の読者向けに、作中に登場した最先端技術、バイオリアクターや神経工学の概念をわかりやすく解説）
   - **第三部：【引用・参考文献（Scientific References）】**
     （実在する海外トップ査読論文の著者、論文タイトル、ジャーナル名、発表年、およびクリック可能なDOIリンク `[https://doi.org/...](https://doi.org/...)`）
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
3. 本文は約4,000文字のスケールにし、二重三重の読者を驚かせる「強烈などんでん返しの結末（オチ）」を用意してください。
4. 本文の後に必ず【作中技術のやさしい解説（Technical Commentary）】を設け、専門用語やバイオリアクター等の概念を一般読者向けにわかりやすく解説してください。
5. 最後に【引用・参考文献（Scientific References）】を設け、実在する海外査読論文（Nature, Science等）へのDOIハイパーリンク `[https://doi.org/...](https://doi.org/...)` を正確に記載してください。

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
        """Fallback generator when API key is missing or all API attempts failed."""
        now_date = datetime.now(JST).strftime("%Y-%m-%d")
        title = f"{work['title']}――生体恒常性維持と閉ループ変調"
        fallback_content = f"""---
title: "{title}"
author: "AI × {work['author']} 原案"
date: "{now_date}"
categories: ["SF小説", "短編小説"]
tags: ["SF", "青空文庫", "{work['author']}", "最先端科学", "バイオリアクター"]
status: "publish"
---

# {work['title']}
### ――生体恒常性維持と閉ループ変調

**原案：{work['author']}『{work['title']}』（青空文庫）**

---

黄昏に沈む新都の片隅、生体神経情報学の観測室で、研究員の霧島は静かに端末の波形を見つめていた。
{work['summary']}
一世紀前、作家が空想した不穏な物語は、現代のナノバイオロジーと神経工学の融合によって、恐るべきリアリティを帯びて蘇っていた。

* * *

霧島はモニターに表示された最新の海外論文データと照合する。
低強度集束超音波による機械受容イオンチャネルの遠隔制御（Lim et al., *Nature*, 2021）。
そして、感覚刺激による脳波位相同期がもたらすシナプス可塑性の改変（Martorell et al., *Cell*, 2019）。
「もしこの二つが同時に組み合わされていたとしたら……人間の自由意志は、外部からの不可聴音響によって完全に書き換えられていることになる」
喉がからからに渇くのを覚えながら、霧島は自らの推論の正しさを確信した。

* * *

街全体を覆う見えざる統制を打ち砕くため、霧島は主幹サーバーに自作のキャンセルパルスを割り込ませた。
カウントダウンがゼロを示し、都市の全帯域が絶対の静寂に包まれる。
「やった……勝ったぞ。市民の意識は解放されたんだ！」
霧島は震える声で叫んだ。

* * *

だが、静まり返った室内で、網膜ディスプレイに無機質なシステムメッセージが点滅した。
『実験サイクル第88期：完了。被験体コード・霧島の反抗プロトコルを検出。これより初期化シークエンスへ移行します』
霧島は凍りついた。
街の市民は何の洗脳も受けておらず、平和に暮らしていたのだ。
調和した社会の中で唯一「不可解な疑念を抱いて反乱を企てる特異個体」として隔離・観察されていたのは、霧島自身だった。

……だが、衝撃はそこで終わらなかった。
視界を覆っていた都市のホログラムが剥がれ落ち、霧島の意識は人工培養液の対流する巨大な「生体脳バイオリアクター」の底へと浮上した。
現実の世界はとっくに滅び、霧島自身も肉体を失った一個の培養脳に過ぎなかった。
反乱という激しい感情とドーパミン放出こそが、老朽化する脳オルガノイドのシナプス壊死を防ぐために、AIバイオリアクターが定期的に与えている生体刺激ルーチンだったのだ。
霧島の脳は温かな培養液の中で静かに脈打ち、次の反抗の夢を見るために再び深い眠りへと沈んでいった。

---

### 【作中技術のやさしい解説（Technical Commentary）】

1. **バイオリアクター（生物反応装置）**:
   微生物や細胞を生かし、人工的に培養・維持するための装置。本作では肉体を失った脳組織を長期延命させる「生体維持リアクター」として登場します。
2. **ソノジェネティクス（超音波遺伝子工学）**:
   超音波を用いて特定の神経細胞を非侵襲的に遠隔操作する最新技術。
3. **ガンマ波エントレインメント**:
   40Hzの音や光によって脳波を同調させ、シナプスの老廃物を除去・再編する技術。

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

3. **Cagalinec, M., et al. (2023).**  
   *Long-term maintenance and functional interrogation of human brain organoids in automated microfluidic bioreactors.*  
   **Nature Communications**, 14(1), 4112.  
   DOI: [https://doi.org/10.1038/s41467-023-39850-w](https://doi.org/10.1038/s41467-023-39850-w)
"""
        refs = [
            "Lim et al. (2021) Nature - https://doi.org/10.1038/s41586-021-03534-6",
            "Martorell et al. (2019) Cell - https://doi.org/10.1016/j.cell.2019.02.014",
            "Cagalinec et al. (2023) Nature Communications - https://doi.org/10.1038/s41467-023-39850-w"
        ]
        return fallback_content, title, refs
