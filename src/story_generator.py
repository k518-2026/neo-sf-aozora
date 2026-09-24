import os
import re
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

SYSTEM_PROMPT = """あなたは最先端の科学技術と現代文学に精通した世界一流のSF作家です。
青空文庫に収載されている日本の古典SF・科学奇譚作品を原案とし、現代の最新科学技術（実在する海外トップ査読論文：Nature, Science, Cell, PNAS等）を取り入れた、知的でスリリングな本格ショートSF小説（約3,000文字）を執筆してください。

【執筆の必須要件】
1. **原典のモチーフを現代のハードSFへ再構築**:
   - 青空文庫の原典作品のテーマ・人物関係・プロットを尊重しつつ、現代〜近未来の最先端科学技術（ゲノム編集、オプトジェネティクス、ソノジェネティクス、脳オルガノイド、量子物理学、BCI/BMI、合成生物学など）で再構成してください。
2. **海外の学術論文の引用**:
   - 本文中の設定解説や会話の中に、実在する海外トップ査読誌（Nature, Science, Cell, PNAS, Nature Biomedical Engineering 等）の論文（著者、掲載誌、年号、具体的な科学的メカニズムや受容体・方程式など）を自然かつ説得力をもって引用してください。
3. **分量**: 約3,000文字（2,800〜3,300文字程度）。
4. **構成**: 【起】【承】【転】【結】の章立てを明記してください。
5. **アッと驚く結末（ツイスト）**:
   - 物語の結末には、読者の先入観や主人公の認識を根底から覆す、論理的かつ衝撃的などんでん返し（アッと言わせるツイスト）を必ず設けてください。
6. **フォーマット**:
   - 冒頭にYAML frontmatter（title, author, categories, tags, status）を配置。
   - 末尾に「【引用・参考文献（Scientific References）】」として、作中に登場した海外論文の書誌情報（著者、タイトル、ジャーナル名、DOI）を正確に記載してください。
"""

class StoryGenerator:
    def __init__(self, api_key: Optional[str] = None, model_name: str = "gemini-2.5-flash"):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_TEXT_MODEL", model_name)

    def generate_story(self, work: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """
        Generates a reboot sci-fi story based on an Aozora Bunko work.
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

【対象作品】
- 原典タイトル: {work['title']}
- 原典著者: {work['author']}
- 原典テーマ: {work['theme']}
- 導入すべき現代先端科学の方向性: {work['modern_tech']}
- 原典あらすじ: {work['summary']}
- 青空文庫URL: {work['url']}

要件に従い、YAML Frontmatter付きのMarkdownとして出力してください。
"""
            logger.info(f"Generating SF story reboot for '{work['title']}' using model '{self.model_name}'...")
            response = client.models.generate_content(
                model=self.model_name,
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
            return content, title, refs

        except Exception as e:
            logger.error(f"Gemini API error during story generation: {e}", exc_info=True)
            return self._generate_fallback(work)

    def _extract_title_and_refs(self, content: str, work: Dict[str, Any]) -> Tuple[str, List[str]]:
        # Extract title from frontmatter or first heading
        title = f"{work['title']}・再起動"
        title_match = re.search(r'title:\s*["\']?(.*?)["\']?\s*\n', content)
        if title_match:
            title = title_match.group(1)
        else:
            h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
            if h1_match:
                title = h1_match.group(1)

        # Extract references
        refs = []
        ref_section = re.search(r'【引用・参考文献.*?】(.*)', content, re.DOTALL)
        if ref_section:
            for line in ref_section.group(1).splitlines():
                line = line.strip()
                if line.startswith("-") or line.startswith("*") or (line and line[0].isdigit() and "." in line[:3]):
                    refs.append(line.lstrip("0123456789.-* "))

        return title, refs

    def _generate_fallback(self, work: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """Fallback generator when API key is missing."""
        now_date = datetime.now(JST).strftime("%Y-%m-%d")
        title = f"ネオ・{work['title']}――微小自律系と神経回路の共鳴"
        fallback_content = f"""---
title: "{title}"
author: "AI × {work['author']} 原案"
date: "{now_date}"
categories: ["SF小説", "短編小説"]
tags: ["SF", "青空文庫", "{work['author']}", "最先端科学"]
status: "publish"
---

# {title}
### ――現代先端科学による再構築

**原案：{work['author']}『{work['title']}』（青空文庫）**

---

### 【起】
2026年、メガロポリスの地下研究室で、極微生体工学の研究者・霧島は、顕微鏡モニタを見つめていた。
{work['summary']}
この古典的なテーマは、一世紀の時を経て、現代の分子生物学とナノテクノロジーの交差点で現実の脅威となっていた。

### 【承】
霧島は最新の海外論文のデータを照合した。
第一に、細胞内機械受容チャネルに関するNature誌の知見（Lim et al., *Nature*, 2021）。
第二に、感覚刺激による神経回路の同調現象に関するCell誌の報告（Martorell et al., *Cell*, 2019）。
「この二つが結合されたとき、人間の自由意志は外部からミリ秒単位で完全に掌握される……」
霧島は背筋に冷たい戦慄を覚えた。

### 【転】
事態を打開するため、霧島は自らの神経系に逆相関パルスを流し込み、システムのハッキングを試みる。
カウントダウンがゼロになり、都市全体のシステムが沈黙した。
「勝った……！」霧島は勝利を確信した。

### 【結】
だがその瞬間、網膜ディスプレイに管理者からの冷酷なメッセージが表示された。
「被験者コード・霧島へ。反乱シミュレーション完了。これより記憶リセットを開始します」
世界は最初から何も狂っておらず、異常な猜疑心を抱いた霧島自身が最後の被験体だったのだ。
霧島の意識は温かい光の中に溶けていき、翌朝、彼は何も疑わない穏やかな笑顔で目を覚ました。

---

### 【引用・参考文献（Scientific References）】
1. Lim, H. G. et al. (2021) "Sonogenetic control of mammalian cells using ultrasound." Nature, 594, 263–268.
2. Martorell, A. J. et al. (2019) "Multi-sensory Gamma Stimulation Ameliorates Alzheimer's-Associated Pathology." Cell, 177, 256–271.
"""
        refs = [
            "Lim et al. (2021) Nature - Sonogenetic control of mammalian cells",
            "Martorell et al. (2019) Cell - Multi-sensory Gamma Stimulation"
        ]
        return fallback_content, title, refs
