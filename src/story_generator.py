import os
import re
import json
import time
import random
import logging
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger(__name__)
JST = timezone(timedelta(hours=9))

import urllib.parse

def clean_doi_string(raw_doi: str) -> str:
    """
    Cleans trailing punctuation from a DOI string while preserving balanced
    parentheses inside valid DOIs (e.g., '10.1016/0031-9201(81)90046-7').
    """
    m = re.search(r'10\.\d{4,9}/[^\s\]\>\"\']+', raw_doi)
    if not m:
        return ""
    d = m.group(0)
    while d and d[-1] in ".,;]>":
        d = d[:-1]
    while d.endswith(")") and d.count(")") > d.count("("):
        d = d[:-1]
    while d and d[-1] in ".,;]>":
        d = d[:-1]
    return d


def extract_dois_from_text(text: str) -> List[str]:
    """
    Extracts all unique DOI strings from markdown/text, properly handling
    parentheses in Elsevier/SII DOIs inside markdown links [url](url).
    """
    raw_matches = re.findall(r'https?://doi\.org/(10\.\d{4,9}/[^\s\]\>\"\']+)', text)
    seen = []
    for raw in raw_matches:
        cleaned = clean_doi_string(raw)
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def check_doi_validity(doi_str: str) -> bool:
    """Checks if a DOI exists using the official DOI Handle REST API."""
    clean_doi = clean_doi_string(doi_str)
    if not clean_doi:
        return False
    url = f"https://doi.org/api/handles/{urllib.parse.quote(clean_doi, safe='/:()-._;')}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AozoraSciFiBot/1.0"})
        with urllib.request.urlopen(req, timeout=6) as res:
            if res.getcode() == 200:
                data = json.loads(res.read().decode("utf-8", errors="ignore"))
                return data.get("responseCode") == 1
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        # For non-404 network or server errors, do not falsely reject
        return True
    except Exception:
        # Network timeout or intermittent error, do not block
        return True
    return False


def resolve_doi_via_crossref(citation_text: str) -> Optional[str]:
    """
    Queries the official Crossref REST API using bibliographic citation text
    to find the authentic, resolvable DOI when an LLM misremembers DOI digits.
    """
    # Strip markdown links, URLs, and formatting symbols to get clean bibliographic text
    clean_query = re.sub(r'\[https?://[^\]]+\]\([^\)]+\)', '', citation_text)
    clean_query = re.sub(r'https?://\S+', '', clean_query)
    clean_query = re.sub(r'[*_`#>-]', ' ', clean_query)
    clean_query = re.sub(r'^\s*\d+[\.\)]\s*', '', clean_query).strip()
    if len(clean_query) < 12:
        return None

    params = urllib.parse.urlencode({
        "query.bibliographic": clean_query[:300],
        "rows": 3,
        "select": "DOI,title,author,published-print,published-online,score"
    })
    url = f"https://api.crossref.org/works?{params}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AozoraSciFiBot/1.0 (https://github.com/k518-2026/neo-sf-aozora)"}
        )
        with urllib.request.urlopen(req, timeout=8) as res:
            if res.getcode() == 200:
                payload = json.loads(res.read().decode("utf-8", errors="ignore"))
                items = payload.get("message", {}).get("items", [])
                for item in items:
                    cand_doi = item.get("DOI", "")
                    if cand_doi and check_doi_validity(cand_doi):
                        return cand_doi
    except Exception as e:
        logger.debug(f"Crossref lookup error for '{clean_query[:60]}': {e}")
    return None


def repair_references_in_content(content: str) -> Tuple[str, List[str], List[str]]:
    """
    Validates all DOIs in content. For any broken/hallucinated DOI:
    1) Attempts to resolve the authentic DOI via Crossref from the citation line and replaces it in-place.
    2) If Crossref cannot resolve it, removes the broken DOI link from that line so no 404 links are published.
    Returns: (repaired_content, valid_dois, unresolved_dois)
    """
    dois = extract_dois_from_text(content)
    valid_dois: List[str] = []
    unresolved_dois: List[str] = []
    repaired_content = content

    for d in dois:
        if check_doi_validity(d):
            valid_dois.append(d)
            continue

        # Find the line containing this broken DOI to query Crossref
        target_line = ""
        for line in repaired_content.splitlines():
            if d in line:
                target_line = line
                break

        replacement_doi = resolve_doi_via_crossref(target_line) if target_line else None
        if replacement_doi:
            logger.info(f"Auto-repaired broken DOI '{d}' -> authentic Crossref DOI '{replacement_doi}'")
            repaired_content = repaired_content.replace(d, replacement_doi)
            if replacement_doi not in valid_dois:
                valid_dois.append(replacement_doi)
        else:
            logger.warning(f"Could not resolve broken DOI '{d}' via Crossref; stripping broken link.")
            unresolved_dois.append(d)
            # Remove markdown link [https://doi.org/<d>](https://doi.org/<d>) or bare URL
            escaped_d = re.escape(d)
            repaired_content = re.sub(
                rf'\s*\[https?://doi\.org/{escaped_d}\]\(https?://doi\.org/{escaped_d}\)\.?',
                '',
                repaired_content
            )
            repaired_content = re.sub(
                rf'\s*https?://doi\.org/{escaped_d}\.?',
                '',
                repaired_content
            )

    return repaired_content, valid_dois, unresolved_dois

# Ending themes and weighted random ratio (明るい未来:ディストピア:ラブロマンス:ミステリー = 3:2:3:2)
ENDING_THEMES = [
    {
        "id": "bright",
        "name": "明るい未来",
        "weight": 3,
        "description": (
            "【結末テーマ：明るい未来（ユートピア・進化・共生・希望）】\n"
            "最先端科学技術のブレイクスルーが、人類や地球の未曾有の課題を克服する。\n"
            "驚きとともに温かな希望、人類の精神的・肉体的進化、あるいは自然や生態系との美しく調和のとれた明るい未来（センス・オブ・ワンダーに満ちた前向きなエンディング）を描いてください。"
        )
    },
    {
        "id": "dystopia",
        "name": "ディストピア",
        "weight": 2,
        "description": (
            "【結末テーマ：ディストピア（科学的警鐘・冷徹な結末・皮肉な運命）】\n"
            "最先端科学技術の過剰な適応や予期せぬ代償がもたらす、冷酷な現実や社会の暗部、逃れられない皮肉な運命を描く。\n"
            "読者の背筋を凍らせるような強烈な科学的警鐘と、論理的に研ぎ澄まされた不条理な破滅的結末を描いてください。"
        )
    },
    {
        "id": "romance",
        "name": "ラブロマンス",
        "weight": 3,
        "description": (
            "【結末テーマ：ラブロマンス（純愛・絆・切ない想い・永遠の愛）】\n"
            "最先端科学技術の彼方に浮かび上がる、登場人物同士の切実な愛や深い絆、時空や生死を超えた想い。\n"
            "科学の冷徹な論理と人間の温かな情動が激しく交錯し、読者の胸を強く打つ至純の純愛や切なくも美しいロマンスを物語の結末に据えてください。"
        )
    },
    {
        "id": "mystery",
        "name": "ミステリー",
        "weight": 2,
        "description": (
            "【結末テーマ：ミステリー（心理戦・科学トリック・驚愕のどんでん返し）】\n"
            "最先端科学の盲点を突いた緻密なトリック、予期せぬ真犯人や隠された衝撃の動機。\n"
            "散りばめられた伏線が一気に回収され、論理的推論によって驚愕の真相が白日の下に晒される、本格探偵小説の美学に満ちた鮮やかな結末を描いてください。"
        )
    },
]

def select_ending_theme(preferred: Optional[str] = None) -> Dict[str, Any]:
    """Selects an ending theme based on weights (3:2:3:2) or user preference."""
    if preferred and preferred.lower() not in ("random", "none", ""):
        pref = preferred.lower()
        for t in ENDING_THEMES:
            if t["id"] == pref or t["name"] == preferred:
                return t
    weights = [t["weight"] for t in ENDING_THEMES]
    chosen = random.choices(ENDING_THEMES, weights=weights, k=1)[0]
    return chosen

SYSTEM_PROMPT = """あなたは最先端の科学技術と現代日本文学の粋を極めた一流のハードSF作家です。
青空文庫に収載されている日本の古典SF・科学奇譚・探偵小説・幻想文学の名作（海野十三、蘭郁二郎、江戸川乱歩、夢野久作、小栗虫太郎、久生十蘭等）を原案とし、現代の最新科学技術（実在する海外トップ査読論文：Nature, Science, Cell, PNAS, IEEE, ACM, SIAM等）を取り入れた、重厚でスリリングな本格ショートSF小説（約4,000文字）を執筆してください。

【執筆の厳格な要件】
1. **タイトルの命名規則（原典の尊重）**:
   - タイトルは必ず元の青空文庫作品名をベースにし、原題がひと目で分かる形にしてください。
   - 例: 『原典タイトル――先端科学の副題』など。
2. **【起】【承】【転】【結】などの記号・見出しは本文中に入れないこと**:
   - 物語の途中に「【起】」「【承】」といった記号や見出しを絶対に入れないでください。
   - シーンの転換には、空行または「* * *」を用いて、自然な文学的流れを作ってください。
3. **学術領域の横断（自然科学・宇宙・医学 ＋ 数学・コンピュータサイエンス）**:
   - 物理学、化学、分子生物学、地球惑星科学（地学）、天文学・宇宙物理学、先端医学・脳神経科学はもちろんのこと、すべての科学の礎である**数学（トポロジー、代数幾何、非線形カオス力学、確率論、グラフ理論、ゲーム理論等）**および**コンピュータサイエンス（計算複雑性理論、量子アルゴリズム、分散システム・群知能、暗号理論・ゼロ知識証明、情報幾何学、ニューロモルフィック計算等）**の知見・理論・数理モデルに深く触れ、物語の論理的骨格や科学的ギミックとして積極的に取り入れてください。
   - 抽象的な数理の美しさや計算論的限界の冷徹さと、人間ドラマを鮮やかに融合させてください。
4. **科学的妥当性とエンターテイメント性の両立（ハードSFの黄金律・センス・オブ・ワンダー）**:
   - 有名科学雑誌（Nature, Science等）を引用する以上、基礎原理や科学的・数学的メカニズムについて「科学的妥当性・整合性」を厳格に保持してください。オカルトや根拠なき魔法のような描写を避け、現実の科学・数学知見の論理的延長（説得力ある外挿）として緻密に描写してください。
   - ただし、単なる学術論文の要約や硬直した技術解説に陥ってはなりません。フィクションならではの大胆な想像力、読者の知的好奇心を揺さぶる「驚きと気づき（知的カタルシス）」、そして息もつかせぬサスペンスや人間ドラマ、エンターテイメントとしての面白さを極限まで高めてください。
5. **指定された結末テーマの厳格な遵守**:
   - 今回指定された結末テーマ（明るい未来、ディストピア、ラブロマンス、ミステリーのいずれか）の意図を十二分に汲み取り、読後感に鮮やかな余韻を残すエンディングを構築してください。
   - 「培養脳バイオリアクター内の夢だった」「シミュレーション仮説だった」「VRゲームだった」といった安易なオチの使い回し・パターン化を固く禁じます。
   - たとえ原典作品が夢オチやノイローゼの妄想で終わる作品であっても、本作では絶対に安易な夢オチにしてはなりません。現代の先端科学を極限まで論理的に外挿（未来推測）し、息を呑むような驚愕の客観的現実を結末に据えてください。
6. **生き生きとした会話劇と発言者の明示・登場人物設定の完全統一**:
   - 説明的な地の文ばかりに偏らず、登場人物同士の緊迫した対話や人間味あふれる掛け合い（会話文）を積極的に増やしてください。
   - 「誰がそのセリフを言っているのか」が読者にひと目で分かるよう、発言者の名前や仕草、表情、心理描写を伴うト書き（例：「〜と草野は眉をひそめた」「〜と沢村は穏やかに微笑んだ」など）を必ず自然に添えてください。
   - **【重要：性別・氏名・代名詞・口調の完全一貫性】**: 各登場人物の**性別（男／女）、氏名（漢字と読み）、一人称（私／僕／俺など）、三人称代名詞（彼／彼女）、およびセリフの口調（語尾）**を作中で最初から最後まで100%厳格に統一してください。「男」と描写した人物に女性名や「彼女」を使ったり、逆に女性人物に男性的な老紳士口調（「〜かね？」「〜なのさ」等）や「彼」を混在させたりする属性矛盾を絶対に起こさないでください。
   - 科学的理念の対立、絆、葛藤を会話を通じてスリリングかつエモーショナルに描き出してください。
7. **分量と洗練された日本語**:
   - 小説本文の分量は約4,000文字（3,800〜4,500文字程度）の重厚なスケールにしてください。
   - ぎこちない翻訳調や、キャラクターが論文名やDOIを読み上げるような不自然なセリフを徹底排除してください。
   - 小松左京の科学的迫真性、伊藤計劃の知性と緊張感、星新一の構成美を意識した、流麗で美しい日本語で執筆してください。
8. **全体の構成（三部構成）**:
   - **第一部：小説本文**（約4,000文字、起承転結を内包した衝撃の物語）
   - **第二部：【作中技術のやさしい解説（Technical Commentary）】**
     （一般の読者向けに、作中に登場したその作品固有の先端科学・数学・コンピュータサイエンスの理論や技術をわかりやすく解説してください。「どこまでが現在実在する科学的・数学的知見なのか」と「どこからが本作独自のSF的仮説・想像力（フィクションとしての飛躍）なのか」の境界を明快に整理し、読者が知的好奇心とワクワク感を抱ける解説にしてください）
   - **第三部：【引用・参考文献（Scientific References）】**
     （実在する海外トップ査読論文・主要学会誌の著者、論文タイトル、ジャーナル名、発表年、およびクリック可能な正規DOIリンク `[https://doi.org/...](https://doi.org/...)`）
"""

# Primary model and fallback cascade for quota/overload errors
DEFAULT_PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
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

    def generate_story(
        self,
        work: Dict[str, Any],
        ending_theme: Optional[str] = None
    ) -> Tuple[str, str, List[str]]:
        """
        Generates a reboot sci-fi story based on an Aozora Bunko work.
        Randomly selects ending theme among 明るい未来:ディストピア:ラブロマンス:ミステリー (3:2:3:2 ratio).
        If primary model returns 503 or overload errors, falls back to other valid Gemini models.
        Returns: (markdown_content, reboot_title, list_of_references)
        """
        if not self.api_key:
            logger.error("GEMINI_API_KEY is not set. Refusing to generate a low-quality short fallback.")
            return self._generate_fallback(work)

        theme_info = select_ending_theme(ending_theme)
        logger.info(
            f"Selected ending theme for '{work['title']}': ★{theme_info['name']}★ "
            f"(Weight ratio 3:2:3:2: 明るい未来3, ディストピア2, ラブロマンス3, ミステリー2)"
        )

        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=self.api_key)

            prompt = f"""
以下の青空文庫作品をもとに、現代の先端技術・海外査読論文を引用した本格リブート短編SF小説（本文約4,000文字＋技術解説＋DOI参考文献）を執筆してください。

【対象の原典作品】
- 原典タイトル: {work['title']}
- 原典著者: {work['author']}
- 原典の核となるテーマ: {work['theme']}
- 導入すべき現代先端科学の方向性: {work['modern_tech']}
- 原典のあらすじ: {work['summary']}
- 青空文庫URL: {work['url']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【今回の結末テーマ指定：★{theme_info['name']}★】
{theme_info['description']}
必ずこの指定された結末テーマ（{theme_info['name']}）に沿って、物語全体のトーン、クライマックス、結末（オチ）を構成してください。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【必須ルール】
1. タイトルは必ず『{work['title']}――（副題）』のように、原題を明確に引き継いだものにしてください。
2. 文章の最初や途中に【起】【承】【転】【結】などの記号や見出しを絶対に入れないでください（アスタリスク '* * *' 等でシーン転換）。
3. **【学術領域の横断（物理・化学・生物・地学・宇宙・医学 ＋ 数学・コンピュータサイエンス）】**:
   - 物理、化学、生物、地学、宇宙、医学の自然科学領域に加え、**数学（トポロジー、微分幾何、非線形カオス力学、確率過程、グラフ理論、ゲーム理論等）**や**コンピュータサイエンス（量子計算、分散アルゴリズム、計算複雑性理論、暗号論・ゼロ知識証明、情報理論、ニューロモルフィック等）**の知見や数理モデルにも積極的に触れ、知的好奇心を刺激する重厚な設定・ロジックを物語の根底に織り込んでください。
4. **【科学的妥当性とエンターテイメント性の両立（驚きと気づき・センス・オブ・ワンダー）】**:
   - 有名科学雑誌（Nature, Science, IEEE, ACM, SIAM等）を引用するにふさわしく、科学的・数学的な正しさ・整合性を可能な限り維持してください。
   - 同時に、決して退屈な論文解説にならず、フィクションならではの大胆な想像力、読者の心を揺さぶる「驚きと気づき」、極上のエンターテイメント要素を全力で注ぎ込んでください。
5. **【指定された結末テーマ（★{theme_info['name']}★）の徹底】**:
   - 上記の指定された結末テーマ（{theme_info['name']}）を核心に据えて、読者を驚嘆・感動させる唯一無二の結末を執筆してください。
   - 「培養脳の夢だった」「シミュレーションだった」「仮想現実だった」といった安易なオチの使い回しを完全に禁止します。
   - たとえ原典が夢オチや妄想オチであっても、現代の最先端科学・海外査読論文（{work['modern_tech']}）から導き出される、息を呑むような驚異の客観的未来予測や科学的真実を結末に据えてください。
6. 本文は約4,000文字のスケールにし、二重三重の読者を驚かせる論理的な「強烈などんでん返しの結末（オチ）」を用意してください。
7. **【生き生きとした会話劇・発言者の明示・人物属性（性別・名前・代名詞・口調）の完全統一】**:
   - 地の文の説明だけに偏らず、登場人物同士の対話・会話を多めに盛り込んでドラマチックに描いてください。
   - 「誰がそのセリフを言っているのか」が読者にひと目で分かるよう、セリフの前後に発言者の名前や仕草、表情（例：「〜と草野は叫んだ」「〜と沢村は微笑んだ」など）を必ず分かりやすく明記してください。
   - **各登場人物の性別・名前・三人称代名詞（彼／彼女）・口調（語尾）に矛盾がないか厳重に確認してください**（「男」と書きながら女性名や「彼女」と呼んだり、女性に男性的な博士口調を使ったりするミスを絶対に行わないこと）。
8. 本文の後に必ず【作中技術のやさしい解説（Technical Commentary）】を設け、作中に登場した先端科学技術・数学・計算機科学理論について、「現実の科学事実（現在どこまで解明されているか）」と「SF的想像力（本作ならではの飛躍・仮説）」を対比させながら、一般読者向けにわかりやすく知的好奇心を刺激する解説を記載してください。
9. 最後に【引用・参考文献（Scientific References）】を設け、実在する海外トップ査読論文（Nature, Science, IEEE, ACM, SIAM等）への実在DOIハイパーリンク `[https://doi.org/...](https://doi.org/...)` を正確に記載してください。推測による架空のDOIや末尾文字のタイポ（誤記）は絶対に避け、学術的に実在する正規DOIを記載してください。
10. タイトルの直下に、必ず青空文庫へのハイパーリンクを含めた原案表記『**原案：{work['author']}[『{work['title']}』]({work['url']})（青空文庫）**』を記載してください。
11. 冒頭のYAML Frontmatterの tags には、必ず "{theme_info['name']}" を含めてください。
    例: tags: ["SF", "青空文庫", "{work['author']}", "最先端科学", "{theme_info['name']}"]

要件に従い、冒頭にYAML Frontmatterを配置したMarkdown形式で出力してください。
"""
            model_candidates = self._get_model_candidates()
            last_error = None
            retired_models = set()
            best_story_candidate: Optional[Tuple[str, str, List[str]]] = None

            # Attempt generation across models with backoff retry
            max_rounds = 3
            for round_num in range(1, max_rounds + 1):
                if round_num > 1:
                    logger.info(f"Round {round_num - 1} hit temporary server demand spikes. Pausing 10s before Round {round_num}...")
                    time.sleep(10)

                for idx, current_model in enumerate(model_candidates):
                    if current_model in retired_models:
                        continue

                    # For each candidate, try up to 2 attempts if 503/high demand occurs
                    for attempt in range(1, 3):
                        logger.info(
                            f"Attempting SF story generation with model '{current_model}' "
                            f"(Round {round_num}, Candidate {idx + 1}/{len(model_candidates)}, Try {attempt}/2)..."
                        )
                        try:
                            max_tokens = 8192 if "2.0" in current_model else 16384
                            response = client.models.generate_content(
                                model=current_model,
                                contents=prompt,
                                config=types.GenerateContentConfig(
                                    system_instruction=SYSTEM_PROMPT,
                                    temperature=0.8,
                                    max_output_tokens=max_tokens,
                                    http_options=types.HttpOptions(timeout=120000)
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
                                break

                            # Completeness & DOI Verification check: ensure references section and real DOIs exist
                            dois = extract_dois_from_text(content)
                            if "引用・参考文献" not in content or not dois:
                                logger.warning(
                                    f"Model '{current_model}' output was truncated or missing DOI references. "
                                    f"Retrying generation..."
                                )
                                if attempt == 1:
                                    continue
                                break

                            repaired_content, valid_dois, unresolved_dois = repair_references_in_content(content)
                            title, refs = self._extract_title_and_refs(repaired_content, work)

                            # Save as backup candidate in case all subsequent retries hit 503
                            if best_story_candidate is None or len(valid_dois) > 0:
                                best_story_candidate = (repaired_content, title, refs)

                            if not valid_dois:
                                logger.warning(
                                    f"Model '{current_model}' had no valid DOIs even after Crossref repair "
                                    f"(unresolved: {unresolved_dois}). Retrying generation..."
                                )
                                if attempt == 1:
                                    continue
                                break

                            if unresolved_dois:
                                logger.info(
                                    f"Cleaned {len(unresolved_dois)} unresolvable DOI(s); "
                                    f"proceeding with {len(valid_dois)} verified authentic DOI(s)."
                                )

                            logger.info(f"Successfully generated story using '{current_model}'! Title: {title}, Length: {len(repaired_content)} chars")
                            return repaired_content, title, refs

                        except Exception as e:
                            last_error = e
                            err_msg = str(e)
                            is_503_or_overload = any(term in err_msg.lower() for term in [
                                "503", "unavailable", "overloaded", "resource_exhausted", "rate_limit", "high demand", "temporary"
                            ])
                            is_not_found = "404" in err_msg or "not found" in err_msg.lower()

                            if is_not_found:
                                # Skip immediately and remember retired model across rounds
                                retired_models.add(current_model)
                                logger.warning(f"Model '{current_model}' is not available (404/Retired). Skipping.")
                                break

                            if is_503_or_overload and attempt == 1:
                                backoff_sec = 6 * round_num
                                logger.warning(
                                    f"Model '{current_model}' encountered temporary capacity error ({err_msg}). "
                                    f"Backing off for {backoff_sec}s before retry..."
                                )
                                time.sleep(backoff_sec)
                                continue
                            else:
                                logger.warning(f"Model '{current_model}' failed: {err_msg}. Moving to next candidate.")
                                time.sleep(2)
                                break

            if best_story_candidate is not None:
                logger.info("Returning best generated story candidate after model retries.")
                return best_story_candidate

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
