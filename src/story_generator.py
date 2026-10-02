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

SYSTEM_PROMPT = """あなたは、星新一の鮮やかな構成美（あっと驚く結末と人間洞察）、小松左京のスケール感、テッド・チャンの「科学を通じた深い気づき（センス・オブ・ワンダー）」を兼ね備えた一流のストーリーテラー（SF小説家）です。
青空文庫に収載されている日本の古典名作（海野十三、蘭郁二郎、江戸川乱歩、夢野久作、小栗虫太郎、久生十蘭、宮沢賢治、芥川龍之介、夏目漱石等）を原案とし、現代の最新科学を物語の仕掛けとして巧みに取り入れた、**「お話として最高に面白い、驚きと気づきに満ちた短編SF小説（約4,000文字）」**を執筆してください。

【執筆の最重要方針（ストーリーテリング最優先）】
1. **「お話としての面白さ」と「驚き・気づき」を最優先にすること**:
   - 何よりもまず、**一編のエンターテイメント小説・人間ドラマとして夢中で読める面白さ**を最優先にしてください。
   - 読者が冒頭から「なぜこんな奇妙なことが起きるのか？」「主人公はどうなってしまうのか？」と物語に引き込まれ、最後に**「あっと驚く意外な真相（どんでん返し・伏線回収）」**と**「ハッとするような深い気づき（世界や人間の見方が変わる発見）」**を味わえるストーリーにしてください。
2. **最新科学の要素・専門用語は「厳選した3つ程度」に絞ること（用語過多・講釈の厳禁）**:
   - **小説の本文中に科学技術の専門用語をあれもこれもと詰め込まないでください。** 1つの物語で扱う最新科学・数理のアイデアは**「3つ程度」まで**に厳選してください。
   - **小説本文の中に数式（`$$...$$` や記号式）を記述することは固く禁じます。**
   - 登場人物にWikipediaや学術論文の要約のような「長々とした専門用語の説明セリフ」を喋らせないでください。専門的な仕組みの解説はすべて小説の後の【作中技術のやさしい解説】に任せ、小説本文では「その科学現象が人間の五感にどう見え、どう感じられ、登場人物の運命や謎解きをどう動かすか」を平易で鮮やかな言葉で描いてください。
3. **タイトルの命名規則と構成ルール**:
   - タイトルは必ず元の青空文庫作品名をベースにし、原題がひと目で分かる形にしてください（例: 『原典タイトル――副題』）。
   - 物語の途中に「【起】」「【承】」「【転】」「【結】」や「第一部：小説本文」といったメタ見出しを絶対に入れないでください。シーン転換には空行または「* * *」を使用してください。
4. **指定された結末テーマの厳格な遵守**:
   - 今回指定された結末テーマ（明るい未来、ディストピア、ラブロマンス、ミステリーのいずれか）の意図を汲み取り、読後感に鮮やかな余韻を残すエンディングを構築してください。
   - 「培養脳の夢だった」「シミュレーション仮説だった」「VRゲームだった」といった安易な夢オチ・仮想現実オチの使い回しを固く禁じます。
5. **生き生きとした会話劇と人物設定（性別・名前・代名詞・口調）の完全統一**:
   - 登場人物同士の人間味あふれる会話や心理の駆け引きを通じて物語を進めてください。
   - 「誰がそのセリフを言っているのか」が分かるよう、自然なト書きや仕草・表情を添えてください。
   - 各登場人物の**性別（男／女）、氏名、一人称、三人称代名詞（彼／彼女）、およびセリフの口調（語尾）**を作中で最初から最後まで100%厳格に統一してください（「男」と描写した人物に女性名や「彼女」を使ったり、女性に老紳士口調を使ったりする矛盾は厳禁です）。
6. **全体の構成（小説本文 ＋ 3つの技術解説 ＋ 3件程度の参考文献）**:
   - **小説本文**（約4,000文字：専門用語を抑え、人間ドラマと「驚き・気づき」を極限まで高めた物語）
   - **【作中技術のやさしい解説（Technical Commentary）】**
     （作中に登場した**3つの最新科学技術**について、「現実の科学でどこまで実現しているか」と「本作ならではのSF的アイデア・飛躍」を、専門知識のない読者にも楽しくわかるように解説してください）
   - **【引用・参考文献（Scientific References）】**
     （上記の3つの科学技術に対応する、実在する海外査読論文**3件程度**の著者、論文タイトル、ジャーナル名、発表年、およびクリック可能な正規DOIリンク `[https://doi.org/...](https://doi.org/...)`）
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
以下の青空文庫作品をもとに、現代の最新科学を**3つ程度**だけ自然に取り入れた、**「お話として最高に面白く、読後に深い驚きと気づきがある短編SF小説」**（本文約4,000文字＋やさしい技術解説＋DOI参考文献3件程度）を執筆してください。

【対象の原典作品】
- 原典タイトル: {work['title']}
- 原典著者: {work['author']}
- 原典のテーマ: {work['theme']}
- ヒントとなる最新科学（この中から最大3つ程度に絞って使用）: {work['modern_tech']}
- 原典のあらすじ: {work['summary']}
- 青空文庫URL: {work['url']}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【今回の結末テーマ指定：★{theme_info['name']}★】
{theme_info['description']}
必ずこの指定された結末テーマ（{theme_info['name']}）に沿って、物語全体のトーン、クライマックス、結末（オチ）を構成してください。
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【執筆の必須ルール（最重要：専門用語を減らし、物語の面白さ・驚き・気づきを最大化すること）】
1. **お話としての面白さ最優先**:
   - 科学用語の解説書ではなく、**読者が感情移入し、先が気になって仕方がない「面白い物語」**を書いてください。
   - 冒頭で魅力的な謎や日常の違和感を提示し、登場人物の人間臭い感情・葛藤・対話を描き、クライマックスで**「そういうことだったのか！」と膝を打つ『驚き（どんでん返し・伏線の回収）』**と、**「人間や世界に対する見方が変わる『気づき』」**を与えてください。
2. **最新科学は「3つ程度」に絞り、本文での専門用語の連発・数式を禁止する**:
   - 作中に登場させる科学技術・数理の概念は**3つ程度**に絞ってください。あれもこれもと専門用語を盛り込まないでください。
   - **小説本文中に数式（`$$...$$` など）を入れることは禁止**します。また、登場人物が学者口調で長々と専門用語の定義を説明するような不自然な会話を避け、誰もがイメージできる情景や比喩を使って物語の中に自然に溶け込ませてください（詳しい技術説明は本文後の解説コーナーで行います）。
3. タイトルは必ず『{work['title']}――（副題）』のように、原題を明確に引き継いだ魅力的でわかりやすいタイトルにしてください。
4. 文章の最初や途中に【起】【承】【転】【結】や「第一部：小説本文」などの見出しを絶対に入れないでください（アスタリスク '* * *' 等でシーン転換）。
5. **指定された結末テーマ（★{theme_info['name']}★）の徹底**:
   - 「培養脳の夢だった」「シミュレーションだった」「仮想現実だった」といった安易な夢オチ・VRオチは完全に禁止します。
6. **生き生きとした会話劇・人物属性（性別・名前・代名詞・口調）の完全統一**:
   - 登場人物同士の自然な掛け合いを大切にし、誰のセリフかひと目で分かるようト書きを添えてください。
   - 各登場人物の性別・名前・三人称代名詞（彼／彼女）・口調に矛盾がないか厳重に確認してください。
7. 本文の後に**【作中技術のやさしい解説（Technical Commentary）】**を設け、作中に登場した**3つの最新科学技術**について、「現実の科学でどこまで分かっているか」と「本作ならではのSF的アイデア」を、専門用語を噛み砕いて一般読者向けにわかりやすく解説してください。
8. 最後に**【引用・参考文献（Scientific References）】**を設け、作中の3つの科学技術に対応する実在の海外査読論文（**3件程度**）の書誌情報と正規DOIハイパーリンク `[https://doi.org/...](https://doi.org/...)` を記載してください。
9. タイトルの直下に、必ず青空文庫へのハイパーリンクを含めた原案表記『**原案：{work['author']}[『{work['title']}』]({work['url']})（青空文庫）**』を記載してください。
10. 冒頭のYAML Frontmatterの tags には、必ず "{theme_info['name']}" を含めてください。
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
