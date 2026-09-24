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
        title = f"{work['title']}――地殻共振遮断と能動音響防壁"
        fallback_content = f"""---
title: "{title}"
author: "AI × {work['author']} 原案"
date: "{now_date}"
categories: ["SF小説", "短編小説"]
tags: ["SF", "青空文庫", "{work['author']}", "最先端科学", "ソノジェネティクス"]
status: "publish"
---

# {work['title']}
### ――地殻共振遮断と能動音響防壁

**原案：{work['author']}[『{work['title']}』]({work['url']})（青空文庫）**

---

黄昏に沈む新都の片隅、生体音響防衛局の観測室で、上級音響技師の霧島は静かに端末の周波数スペクトラムを見つめていた。
街角のあらゆるスピーカー、全家庭の音響端末から、毎日夕刻十八時きっかりに流れる無機質な合成交響曲――『十八時の音楽浴』。
「国家は音楽という美名のもとに、市民の脳波を40ヘルツのガンマ帯域へ強制同期させ、猜疑心や反抗心を根こそぎ奪っている」
霧島はそう確信していた。一世紀前、海野十三が警告したディストピアの予言は、いまや最先端の超音波音響工学によって現実のものとなっていたのだ。

* * *

霧島はモニターに表示された海外論文のデータを指でなぞる。
低強度集束超音波による機械受容イオンチャネル（Piezo1）の遠隔変調（Lim et al., *Nature*, 2021）。
そして、感覚刺激の同調によってシナプス可塑性と認知状態を書き換える閉ループ脳波制御（Martorell et al., *Cell*, 2019）。
「この二つを全都市網で連動させれば、市民の自由意志など容易に消去できる。こんな非人道的な統制を許してはならない」
霧島は三年を費やして自作した位相反転キャンセラー回路を、都市音響グリッドの中枢ノードへと直結させた。
カウントダウンがゼロに達し、十八時の時報とともに、街のスピーカーから逆位相パルスが一斉に解き放たれる。

都市を覆っていた音楽が、プツリと途絶えた。
絶対の静寂。
「やった……勝ったぞ！　音楽浴の呪縛は消滅した。人間は、思考の自由を取り戻したんだ！」
霧島は立ち上がり、歓喜の叫びをあげた。

* * *

だが、静寂が訪れたのは、ほんの数秒に過ぎなかった。

突如として、建物の床が、壁が、窓ガラスが、目に見えない強烈な「重低音の唸り」によって小刻みに共振し始めた。
窓の外を見下ろすと、街頭を歩いていた市民たちが一斉に激痛で頭を抱え、耳を押さえて路上に昏倒していく。
鼓膜を突き破らんばかりの、だが耳には聴こえない、内臓を激しく揺さぶる「地球の呻き」。

「な……んだ、これは……？　なぜ市民が倒れる！？」

室内のドアが開き、上席監理官の佐伯が防音マスクを装着した姿で入ってきた。その目には冷たい憐憫の色が浮かんでいた。
「愚かなことをしてくれましたね、霧島技師。……『洗脳』などという子供じみた陰謀論のために、都市の防壁を打ち破ってしまうとは」

「佐伯……？　何を言っている！　あの音楽は市民の脳を操るための――」

「音楽浴は統制プログラムなどではありません」佐伯は端末の地殻変動モニターを突きつけた。
「現在、プレート境界の超深部断層で発生している、周波数1.8ヘルツの極超低周波・地殻共振波（インフラサウンド）です。大陸規模で進行するマントルの摩擦エネルギーが、都市の地盤を通じて全住民の頭蓋骨と前頭葉に破壊的な共鳴微振動を引き起こしているのです。放置すれば、三十分で全市民の毛細血管と血液脳関門が物理的に破壊され、脳内出血で全滅する」

「……な、に……？」

「毎夕十八時、気圧と地殻応力が急変する薄暮の時間帯に合わせて、国家はこのインフラサウンドを中和・相殺する『全都市能動的音響キャンセリング波』を音楽浴として放射していたのです。なぜなら、真実を公表すれば全土がパニックに陥り、避難もままならず経済が崩壊するからだ。……だが、あなたが放った逆位相パルスによって、防御シールドは完全に破壊された」

霧島の視界が赤く染まり始める。
耳から生ぬるい液体が滴り落ち、思考がバラバラに砕け散っていく。
窓の向こう、夕暮れに染まる巨大都市の摩天楼が、大地の深底から湧き上がる音なき唸りによって、音を立てて共振破壊を起こし始めていた。
自由を求めた自分の正義が、都市を丸ごと破滅へと突き落としたのだという戦慄の事実を胸に刻みながら、霧島は崩れ落ちる床へと沈んでいった。

（了）

---

### 【作中技術のやさしい解説（Technical Commentary）】

本作に登場する先進的な音響工学および神経科学の概念について、一般の読者向けにわかりやすく解説します。

#### 1. 能動的音響制御（アクティブ・ノイズキャンセリング / ANC）
逆位相の音波をぶつけることで不要な音を打ち消す技術。ヘッドホン等でおなじみですが、本作ではこれを都市規模に拡大し、地殻変動に伴う有害な極超低周波（インフラサウンド）から市民を守る巨大な音響防壁として描かれています。

#### 2. インフラサウンド（超低周波音）の生体影響
人間の耳には聞こえない20Hz以下の超低周波音は、大気中を減衰せずに長距離伝播し、内臓や頭蓋骨と共振して激しい頭痛、平衡感覚の喪失、組織損傷を引き起こす物理的性質を持ちます。

#### 3. ソノジェネティクス（超音波遺伝子工学）
光ではなく「超音波」を用いて、機械受容チャネル（Piezo1等）を通じて生体細胞や神経回路を遠隔刺激する最先端の非侵襲医療技術です。

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

3. **Le Pichon, A., Blanc, E., & Hauchecorne, A. (Eds.). (2018).**  
   *Infrasound Monitoring for Atmospheric Studies: Challenges in Middle Atmosphere Dynamics and Societal Benefits.*  
   **Springer Nature**.  
   DOI: [https://doi.org/10.1007/978-3-319-75140-5](https://doi.org/10.1007/978-3-319-75140-5)
"""
        refs = [
            "Lim et al. (2021) Nature - https://doi.org/10.1038/s41586-021-03534-6",
            "Martorell et al. (2019) Cell - https://doi.org/10.1016/j.cell.2019.02.014",
            "Le Pichon et al. (2018) Springer - https://doi.org/10.1007/978-3-319-75140-5"
        ]
        return fallback_content, title, refs
