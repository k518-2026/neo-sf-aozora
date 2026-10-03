import os
import re
import json
import time
import logging
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Any, List, Optional, Tuple

from src.story_generator import (
    select_ending_theme,
    check_doi_validity,
    clean_doi_string,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_LOCAL_MODEL = "qwen2.5:14b"

# Preferred local models in priority order if user hasn't explicitly forced one
PREFERRED_LOCAL_MODELS = [
    "gemma3:27b",
    "qwen2.5:32b",
    "qwen3:14b",
    "qwen2.5:14b",
    "gemma3:12b",
    "llama3.1:8b",
    "qwen2.5:7b",
]

# Pre-mapped accurate English academic search queries for catalog works
# Each work maps to 3 pairs of (Japanese tech concept label, English Crossref search query)
CATALOG_TECH_QUERIES: Dict[str, List[Tuple[str, str]]] = {
    "miyazawa-ginga": [
        (
            "量子もつれテンソルネットワーク（ER=EPR仮説）",
            "Maldacena Susskind Cool horizons for entangled black holes Fortschritte der Physik 2013",
        ),
        (
            "ミリ秒パルサー時空測位ナビゲーション（X線パルサー航法）",
            "Winternitz autonomous X-ray pulsar navigation NICER International Space Station",
        ),
        (
            "超流動ヘリウム冷却量子メモリ・コヒーレンス制御",
            "Awschalom quantum coherence solid state spin qubits Nature Physics",
        ),
    ],
    "miyazawa-gusukobudori": [
        (
            "成層圏エアロゾル・インジェクション気候制御",
            "Crutzen Albedo Enhancement by Stratospheric Sulfur Injections Climatic Change 2006",
        ),
        (
            "マグマ溜まり熱流体連成シミュレーション・火山物理学",
            "Sparks Cashman Dynamic Magma Systems Mantle to Eruption Science 2017",
        ),
        (
            "非線形気候力学系の分岐理論（ティッピング・ポイント解析）",
            "Lenton Tipping elements in the Earth's climate system PNAS 2008",
        ),
    ],
    "akutagawa-haguruma": [
        (
            "大脳視覚野の反応拡散方程式（エルメントラウト・コーワン数理モデル）",
            "Ermentrout Cowan A mathematical theory of visual hallucination patterns fabric of the mind Biological Cybernetics 1979",
        ),
        (
            "光遺伝学フェーズロック神経振動制御",
            "Cardin Carlen Driving fast-spiking cells induces gamma rhythm and controls sensory responses Nature 2009",
        ),
        (
            "神経雪（Visual Snow）および皮質興奮性位相解析",
            "Schankin Maniyar Visual snow a disorder distinct from persistent migraine aura Brain 2014",
        ),
    ],
    "akutagawa-kappa": [
        (
            "全ゲノム人工合成（GP-write / 合成真核生物ゲノム）",
            "Boeke Church Jef Boeke The Genome Project-Write Science 2016",
        ),
        (
            "非侵襲ブレイン・コンピュータ・インターフェース（神経デコーディング）",
            "Tang Huth Semantic reconstruction of continuous language from non-invasive brain recordings Nature Neuroscience 2023",
        ),
        (
            "メカニズムデザイン（数理経済学・社会的選択理論）",
            "Maskin Mechanism Design How to Implement Social Goals American Economic Review 2008",
        ),
    ],
    "akutagawa-kumonoito": [
        (
            "超長尺カーボンナノチューブ（CNT）マクロファイバー極限強度",
            "Bai Zhang Super-durable ultralong carbon nanotubes Science 2020",
        ),
        (
            "非協力ゲーム理論における利他的協調の進化",
            "Nowak Five rules for the evolution of cooperation Science 2006",
        ),
        (
            "軌道エレベーター・宇宙テザー共振制御力学",
            "Pearson The orbital tower a spacecraft launcher using the Earth's rotational energy Acta Astronautica 1975",
        ),
    ],
    "nakajima-sangetsuki": [
        (
            "種間キメラ胚補完法による異種臓器・組織形成",
            "Kobayashi Yamaguchi Generation of rat pancreas in mouse by interspecific blastocyst injection of pluripotent stem cells Cell 2010",
        ),
        (
            "全神経回路網（コネクトーム）構造と機能エミュレーション",
            "Winding Pedigo The connectome of an insect brain Science 2023",
        ),
        (
            "自己言及の計算論的限界と意識の情報統合理論",
            "Tononi Boly Massimini Koch Integrated information theory from consciousness to its physical substrate Nature Reviews Neuroscience 2016",
        ),
    ],
    "kajii-lemon": [
        (
            "嗅覚受容体の分子振動・量子トンネル効果理論",
            "Turin A spectroscopic mechanism for primary olfactory reception Chemical Senses 1996",
        ),
        (
            "五次元ナノ構造ガラス光メモリ結晶（超長期データ保存）",
            "Zhang Kazansky Seemingly unlimited lifetime data storage in nanostructured glass Physical Review Letters 2014",
        ),
        (
            "マルチモーダル共感覚と感覚横断ニューロフィードバック",
            "Cytowic Eagleman Wednesday is Indigo Blue Discovering the Brain of Synesthesia MIT Press",
        ),
    ],
    "kajii-sakuranoki": [
        (
            "共通菌根ネットワーク（Wood Wide Web）による植物間情報伝達",
            "Simard Perry Net transfer of carbon between ectomycorrhizal tree species in the field Nature 1997",
        ),
        (
            "環境DNA（eDNA）メタバーコーディングによる生態系記憶復元",
            "Thomsen Willerslev Environmental DNA An emerging tool in conservation for monitoring past and present biodiversity Biological Conservation 2015",
        ),
        (
            "エピジェネティックな記憶と植物の環境応答・開花制御",
            "Bastow Mylne Vernalization requires epigenetic silencing of FLC by histone methylation Nature 2004",
        ),
    ],
    "soseki-yume-juuya": [
        (
            "クリプトビオシス誘導とガラス化凍結保存（生体時間停止）",
            "Hashimoto Horikawa Extremotolerant tardigrade genome and improved radiotolerance of human cultured cells by tardigrade-unique protein Nature Communications 2016",
        ),
        (
            "量子ゼノン効果による量子状態・時間発展の凍結制御",
            "Itano Heinzen Bollinger Winekand Quantum Zeno effect Physical Review A 1990",
        ),
        (
            "睡眠中の記憶再活性化と時空間シミュレーション",
            "Wilson McNaughton Reactivation of hippocampal ensemble memories during sleep Science 1994",
        ),
    ],
    "ango-sakura-no-mori": [
        (
            "無響・無反射音響光学メタマテリアル空間",
            "Pendry Schurig Smith Controlling Electromagnetic Fields Science 2006",
        ),
        (
            "扁桃体―前頭前野情動ネットワークの神経デコーディング",
            "Phelps LeDoux Contributions of the amygdala to emotion processing Neuron 2005",
        ),
        (
            "三次元ボリュメトリック・ライトフィールド空中投影",
            "Smalley Nygaard Photophoretic-trap volumetric display Nature 2018",
        ),
    ],
    "yumeno-dogra-magra": [
        (
            "経世代エピジェネティック記憶継承（小分子RNAによる獲得形質の遺伝）",
            "Dias Ressler Parental olfactory experience influences behavior and neural structure in subsequent generations Nature Neuroscience 2014",
        ),
        (
            "脳オルガノイドにおける自発的神経振動とネットワーク形成",
            "Trujillo Muotri Complex oscillatory waves emerging from cortical organoids model early human brain network development Cell Stem Cell 2019",
        ),
        (
            "自己言及と生命の自己複製オートマトン・計算理論",
            "Hofstadter Godel Escher Bach An Eternal Golden Braid",
        ),
    ],
    "oguri-kokushikan": [
        (
            "形式手法と自動定理証明による複雑推論（Lean / 数学的検証）",
            "Trinh Wu Le Solving olympiad geometry without human demonstrations Nature 2024",
        ),
        (
            "超分子ホスト・ゲスト化学による分子カプセル・標的刺激応答放出",
            "Cram The Design of Molecular Hosts, Guests, and Their Complexes Science 1988",
        ),
        (
            "分散センサー網におけるビザンチン障害耐性（ビザンチン将軍問題）",
            "Lamport Shostak Pease The Byzantine Generals Problem ACM Transactions on Programming Languages and Systems 1982",
        ),
    ],
}


def format_crossref_item(item: Dict[str, Any], tech_label: str = "") -> Optional[Dict[str, str]]:
    """
    Formats a Crossref work item into a clean bibliography dictionary and verifies its DOI.
    Returns None if the DOI is invalid or basic metadata is missing.
    """
    raw_doi = item.get("DOI", "")
    clean_doi = clean_doi_string(raw_doi)
    if not clean_doi or not check_doi_validity(clean_doi):
        return None

    titles = item.get("title", [])
    title = titles[0].strip() if titles else ""
    if not title:
        return None
    # Strip HTML tags inside Crossref titles
    title = re.sub(r"<[^>]+>", "", title)

    # Extract authors
    authors_raw = item.get("author", [])
    author_names = []
    for a in authors_raw[:6]:
        family = a.get("family", "")
        given = a.get("given", "")
        if family and given:
            initials = ". ".join([p[0] for p in given.replace(".", " ").split() if p]) + "."
            author_names.append(f"{family}, {initials}")
        elif family:
            author_names.append(family)
        elif a.get("name"):
            author_names.append(a["name"])
    if len(authors_raw) > 6:
        author_names.append("et al.")
    authors_str = ", ".join(author_names) if author_names else "Research Collaboration"

    # Extract publication year
    year = ""
    for date_Field in ("published-print", "published-online", "issued", "created"):
        dp = item.get(date_Field, {}).get("date-parts", [])
        if dp and dp[0] and dp[0][0]:
            year = str(dp[0][0])
            break
    if not year:
        year = "2020"

    # Extract journal or publisher
    containers = item.get("container-title", [])
    journal = containers[0].strip() if containers else item.get("publisher", "Scientific Journal")
    journal = re.sub(r"<[^>]+>", "", journal)

    volume = item.get("volume", "")
    issue = item.get("issue", "")
    page = item.get("page", "")

    vol_part = f", {volume}" if volume else ""
    if volume and issue:
        vol_part += f"({issue})"
    page_part = f", {page}" if page else ""

    doi_url = f"https://doi.org/{clean_doi}"
    citation_md = (
        f"{authors_str} ({year}). {title}. *{journal}*{vol_part}{page_part}.\n"
        f"   [{doi_url}]({doi_url})"
    )
    short_ref = f"{authors_str} ({year}). {title}. *{journal}*. [{doi_url}]({doi_url})"

    return {
        "tech_label": tech_label,
        "authors": authors_str,
        "year": year,
        "title": title,
        "journal": journal,
        "doi": clean_doi,
        "doi_url": doi_url,
        "citation_markdown": citation_md,
        "short_ref": short_ref,
    }


def query_crossref_verified_paper(query_str: str, tech_label: str = "", used_dois: Optional[set] = None) -> Optional[Dict[str, str]]:
    """
    Searches Crossref REST API for a query string and returns the top authentic paper
    whose DOI passes live handle resolution (`check_doi_validity`).
    """
    if used_dois is None:
        used_dois = set()

    params = urllib.parse.urlencode({
        "query.bibliographic": query_str,
        "rows": 6,
        "select": "DOI,title,author,container-title,publisher,published-print,published-online,issued,volume,issue,page"
    })
    url = f"https://api.crossref.org/works?{params}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AozoraSciFiBot/2.0 (https://github.com/k518-2026/neo-sf-aozora)"}
        )
        with urllib.request.urlopen(req, timeout=12) as res:
            if res.getcode() == 200:
                payload = json.loads(res.read().decode("utf-8", errors="ignore"))
                items = payload.get("message", {}).get("items", [])
                for item in items:
                    cand_doi = clean_doi_string(item.get("DOI", ""))
                    if not cand_doi or cand_doi in used_dois:
                        continue
                    formatted = format_crossref_item(item, tech_label=tech_label)
                    if formatted:
                        used_dois.add(cand_doi)
                        return formatted
    except Exception as e:
        logger.warning(f"Crossref search error for '{query_str}': {e}")
    return None


class LocalStoryGenerator:
    """
    Generates Aozora Bunko sci-fi reboot stories using a Local LLM (Ollama)
    combined with pre-fetched, 100% DOI-verified Crossref scientific papers
    so that reference hallucination is physically impossible.
    """

    def __init__(
        self,
        ollama_host: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.ollama_host = (ollama_host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)).rstrip("/")
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "")

    def is_ollama_running(self, auto_start: bool = True) -> bool:
        try:
            req = urllib.request.Request(f"{self.ollama_host}/api/tags")
            with urllib.request.urlopen(req, timeout=4) as res:
                if res.getcode() == 200:
                    return True
        except Exception:
            pass

        if not auto_start:
            return False

        # Try auto-starting local ollama.exe serve
        import shutil
        import subprocess
        from pathlib import Path

        ollama_bin = shutil.which("ollama")
        if not ollama_bin:
            default_win = Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
            if default_win.exists():
                ollama_bin = str(default_win)

        if ollama_bin:
            logger.info(f"Ollama server not running. Auto-starting '{ollama_bin} serve' in background...")
            try:
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.Popen(
                    [ollama_bin, "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                for _ in range(8):
                    time.sleep(1)
                    if self.is_ollama_running(auto_start=False):
                        logger.info("Ollama server started successfully!")
                        return True
            except Exception as e:
                logger.warning(f"Failed to auto-start Ollama server: {e}")

        return False

    def get_installed_models(self) -> List[str]:
        try:
            req = urllib.request.Request(f"{self.ollama_host}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as res:
                if res.getcode() == 200:
                    data = json.loads(res.read().decode("utf-8", errors="ignore"))
                    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        except Exception as e:
            logger.debug(f"Could not list Ollama models: {e}")
        return []

    def resolve_model_name(self) -> str:
        installed = self.get_installed_models()
        if self.model_name:
            # If explicitly specified, use it
            return self.model_name
        for pref in PREFERRED_LOCAL_MODELS:
            if pref in installed:
                return pref
            # Also match prefix before tag if needed
            for inst in installed:
                if inst.startswith(pref.split(":")[0]):
                    return inst
        if installed:
            return installed[0]
        return DEFAULT_LOCAL_MODEL

    def _call_ollama_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.75,
        num_predict: int = 8192,
        num_ctx: int = 8192,
        timeout: int = 1200,
    ) -> str:
        model = self.resolve_model_name()
        url = f"{self.ollama_host}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": num_predict,
                "num_ctx": num_ctx,
                "repeat_penalty": 1.12,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.loads(res.read().decode("utf-8", errors="ignore"))
            return body.get("message", {}).get("content", "").strip()

    def _generate_english_queries_via_llm(self, work: Dict[str, Any]) -> List[Tuple[str, str]]:
        """
        If a work is not in CATALOG_TECH_QUERIES, splits modern_tech into 3 items and
        asks the local LLM for concise English academic search keywords for Crossref.
        """
        raw_techs = [t.strip() for t in re.split(r"[、,／/]", work.get("modern_tech", "")) if t.strip()][:3]
        while len(raw_techs) < 3:
            raw_techs.append(work.get("theme", "Quantum Physics"))

        prompt = (
            "Convert each of the following 3 Japanese scientific terms into an English academic search query "
            "(4 to 7 English keywords suitable for Crossref / Nature / Science search). "
            "Output ONLY 3 lines in the exact format: 1. <English keywords>\n\n"
            + "\n".join([f"{i+1}. {t}" for i, t in enumerate(raw_techs)])
        )
        try:
            resp = self._call_ollama_chat(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                num_predict=256,
                timeout=120,
            )
            queries = []
            for line in resp.splitlines():
                line = re.sub(r"^\s*\d+[\.\)]\s*", "", line).strip()
                # Keep ASCII keywords
                ascii_part = re.sub(r"[^\x20-\x7E]", " ", line).strip()
                if len(ascii_part) >= 5:
                    queries.append(ascii_part)
            if len(queries) >= 3:
                return list(zip(raw_techs, queries[:3]))
        except Exception as e:
            logger.warning(f"LLM English query translation fallback triggered: {e}")

        return [(t, "quantum neuroscience bioengineering nature science") for t in raw_techs]

    def fetch_verified_references_for_work(self, work: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Pre-fetches 3 100% real, DOI-verified scientific papers from Crossref for the given work.
        """
        work_id = work.get("id", "")
        tech_queries = CATALOG_TECH_QUERIES.get(work_id)
        if not tech_queries:
            tech_queries = self._generate_english_queries_via_llm(work)

        verified_papers: List[Dict[str, str]] = []
        used_dois: set = set()

        for tech_label, query_str in tech_queries:
            logger.info(f"Pre-fetching verified Crossref paper for [{tech_label}] (Query: '{query_str}')...")
            paper = query_crossref_verified_paper(query_str, tech_label=tech_label, used_dois=used_dois)
            if paper:
                logger.info(
                    f"  -> Verified real paper: {paper['authors']} ({paper['year']}) "
                    f"'{paper['title'][:60]}...' [{paper['doi_url']}]"
                )
                verified_papers.append(paper)
            else:
                # Fallback broader query using first 4 words
                short_q = " ".join(query_str.split()[:4])
                paper = query_crossref_verified_paper(short_q, tech_label=tech_label, used_dois=used_dois)
                if paper:
                    logger.info(f"  -> Verified real paper (broad): {paper['title'][:60]}... [{paper['doi_url']}]")
                    verified_papers.append(paper)

        if not verified_papers:
            raise RuntimeError(f"Could not verify any Crossref papers for work '{work_id}'.")

        return verified_papers

    def _clean_llm_output(self, text: str) -> str:
        """Removes <think>...</think> blocks, markdown fences, scene meta-headers, and stray URLs."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```markdown"):
            text = text[len("```markdown"):].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        # Strip meta scene headings like '### 第1シーン', '## シーン2', '### * * *'
        text = re.sub(r"^[ \t]*#+[ \t]*(\*\s*\*\s*\*)[ \t]*$", r"\1", text, flags=re.MULTILINE)
        text = re.sub(r"^[ \t]*#+[ \t]*(?:第\s*[0-9一二三四五六]+\s*(?:シーン|幕|章|部)|シーン\s*[0-9一二三四五六]+).*$", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[ \t]*(?:【第\s*[0-9一二三四五六]+\s*(?:シーン|幕|章|部).*?】)[ \t]*$", "", text, flags=re.MULTILINE)
        return text.strip()

    def generate_story(
        self,
        work: Dict[str, Any],
        ending_theme: Optional[str] = None,
    ) -> Tuple[str, str, List[str]]:
        """
        Generates a complete, publication-ready Aozora Bunko sci-fi reboot markdown document:
        1) Pre-fetches 3 authentic, DOI-verified scientific papers via Crossref API.
        2) Generates a 3,500-4,500 char story body via Local LLM (Ollama).
        3) Generates the accessible 3-point Technical Commentary via Local LLM grounded in the 3 verified papers.
        4) Deterministically attaches the YAML frontmatter, original work header, and verified Scientific References.
        Returns: (full_markdown, reboot_title, list_of_short_references)
        """
        model = self.resolve_model_name()
        theme_info = select_ending_theme(ending_theme)
        logger.info(
            f"[Local LLM: {model}] Starting generation for '{work['title']}' ({work['author']}) "
            f"| Ending Theme: ★{theme_info['name']}★"
        )

        # Step 1: Pre-fetch 100% real, DOI-verified scientific papers from Crossref
        verified_papers = self.fetch_verified_references_for_work(work)
        tech_summary_lines = []
        for idx, p in enumerate(verified_papers, start=1):
            tech_summary_lines.append(
                f"{idx}. 【技術要素{idx}: {p['tech_label']}】\n"
                f"   - 実在根拠論文: {p['authors']} ({p['year']}) \"{p['title']}\" ({p['journal']})"
            )
        tech_context_block = "\n".join(tech_summary_lines)

        # Step 2A: Generate Part 1 of the Story (Title + Scene 1 & Scene 2: Setup, Mystery & Investigation)
        part1_prompt = f"""以下の青空文庫の名作を原案とし、指定された3つの現代科学要素を取り入れた短編SF小説の**【前半パート（第1シーン・第2シーン：目標1,800〜2,200文字）】**を執筆してください。

※重要：物語全体を前半・後半の2回に分けて執筆します。今回の出力では**絶対に物語を完結させず（『（了）』と書かず）**、謎が深まり決定的な局面へ突入する緊迫した場面（クリフハンガー）で後半へバトンを渡してください。

【対象の原典作品】
- 原典タイトル: {work['title']}
- 原典著者: {work['author']}
- 原典のテーマ: {work['theme']}
- 原典のあらすじ・リブート視点: {work['summary']}

【作中に自然に取り入れる3つの最新科学要素（専門用語の連発や数式は禁止し、五感の描写と人間ドラマに溶け込ませること）】
{tech_context_block}

【最終的な結末テーマ（後半で到達する方向性）：★{theme_info['name']}★】
{theme_info['description']}

【前半パート（今回執筆する範囲）の構成と絶対ルール】
1. **1行目の出力形式**:
   1行目には必ず `TITLE: {work['title']}――（物語の核心を突く魅力的な副題）` の形式でタイトルのみを書いてください。
2. **第1シーン（発端と奇妙な違和感：約900〜1,100文字）**:
   - 舞台となる近未来・現代の情景、主人公と相棒（または重要人物）の具体的な名前・職業・関係性を鮮やかに描写してください。
   - 原典『{work['title']}』のモチーフを現代科学（技術要素1）と結びつけ、「なぜこんな奇妙な現象が起きているのか？」と読者を強く引き込む謎を提示してください。
3. **シーン区切り**:
   第1シーンと第2シーンの間には必ず `* * *` を1行入れてください（「第1章」「【起】」などの見出しは絶対に入れないこと）。
4. **第2シーン（対話・調査と深まる謎：約900〜1,100文字）**:
   - 登場人物同士の人間味あふれる会話劇と心理の駆け引きを通じて、技術要素2を用いた調査・実験を描いてください。
   - 後半の「あっと驚くどんでん返し」につながる重要な伏線を自然に張り、予想外の異常データや危機が浮かび上がった瞬間の緊迫した場面で前半を終えてください（まだ結末や真相は明かさないこと）。
5. **表現の注意**:
   - 同じセリフや同じ説明の繰り返しを厳禁とします。五感（光、音、手触り、温度、匂い）と人物の感情を丁寧に描写してください。
"""

        logger.info(f"[Local LLM: {model}] Step 1/3: Generating Story Part 1 (Setup & Mystery)...")
        raw_part1 = self._call_ollama_chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": part1_prompt},
            ],
            temperature=0.78,
            num_predict=3500,
            num_ctx=8192,
        )
        cleaned_part1 = self._clean_llm_output(raw_part1)

        # Extract title from first line of Part 1
        reboot_title = f"{work['title']}――未来への変奏"
        part1_lines = cleaned_part1.splitlines()
        p1_body_lines = []
        for idx, line in enumerate(part1_lines):
            stripped = line.strip()
            if idx < 5 and (stripped.startswith("TITLE:") or stripped.startswith("# ") or f"{work['title']}――" in stripped):
                cand = re.sub(r"^(?:TITLE:|#+)\s*", "", stripped).strip(" 『』\"'")
                if cand:
                    reboot_title = cand
                continue
            if stripped in ("（了）", "(了)", "（完）"):
                continue
            p1_body_lines.append(line)

        part1_body = "\n".join(p1_body_lines).strip()
        part1_body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", part1_body, flags=re.DOTALL).strip()
        part1_body = re.sub(r"^『?\*\*原案：.*?\*\*』?\s*\n*", "", part1_body).strip()

        # Step 2B: Generate Part 2 of the Story (Scene 3 & Scene 4: Turning Point, Twist & Resolution)
        part2_prompt = f"""素晴らしい前半パートです！続けて、この小説『{reboot_title}』の**【後半パート（第3シーン・第4シーン：目標1,800〜2,200文字）】**を執筆し、物語を完結させてください。

【後半パートの構成と絶対ルール】
1. **直前の続きから自然に書き始めること**:
   - タイトルは書かず、前半パートの直後に続く本文（第3シーン）から書き始めてください。
   - 前半に登場した人物の名前・性別・一人称・口調を100%そのまま維持してください。前半と同じセリフの繰り返しは避け、事態を大きく動かしてください。
2. **第3シーン（核心への突入と危機・転機：約900〜1,100文字）**:
   - 技術要素3（{verified_papers[min(2, len(verified_papers)-1)]['tech_label']}）が決定的な役割を果たし、前半の謎が一気に核心へと迫るスリリングな展開を描いてください。
3. **シーン区切り**:
   第3シーンと第4シーンの間には `* * *` を1行入れてください（「【転】」「【結】」などの見出しは絶対に入れないこと）。
4. **第4シーン（驚愕のどんでん返しと深い気づきの結末：約900〜1,100文字）**:
   - 結末テーマ【★{theme_info['name']}★】に沿って、前半の伏線が一気に回収される**「そういうことだったのか！」と膝を打つ意外な真相（どんでん返し）**と、**人間や世界に対する見方が変わる深い気づき（センス・オブ・ワンダー）**を鮮やかに描いてください。
   - 「すべては夢・シミュレーションだった」という安易な夢オチは厳禁です。
   - 小説本文の最後は必ず `（了）` で締めくくってください（技術解説や参考文献はまだ書かないでください）。
"""

        logger.info(f"[Local LLM: {model}] Step 2/3: Generating Story Part 2 (Climax, Twist & Ending)...")
        raw_part2 = self._call_ollama_chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": part1_prompt},
                {"role": "assistant", "content": f"TITLE: {reboot_title}\n\n{part1_body}"},
                {"role": "user", "content": part2_prompt},
            ],
            temperature=0.78,
            num_predict=2400,
            num_ctx=8192,
            timeout=1800,
        )
        cleaned_part2 = self._clean_llm_output(raw_part2)
        p2_lines = []
        for line in cleaned_part2.splitlines():
            stripped = line.strip()
            if "【作中技術のやさしい解説" in stripped or "【引用・参考文献" in stripped:
                break
            if stripped.startswith("TITLE:"):
                continue
            p2_lines.append(line)
        part2_body = "\n".join(p2_lines).strip()

        story_body = f"{part1_body}\n\n* * *\n\n{part2_body}".strip()
        # Clean duplicate scene dividers if Part 2 already started with * * *
        story_body = re.sub(r"(\*\s*\*\s*\*\s*\n+){2,}", "* * *\n\n", story_body)
        # Remove any stray URLs inside the novel body
        story_body = re.sub(r"https?://\S+", "", story_body)

        if not story_body.endswith("（了）"):
            story_body = story_body.rstrip() + "\n\n（了）"

        # Step 3: Generate Technical Commentary grounded strictly in the 3 verified papers
        commentary_prompt = f"""先ほど執筆した短編SF小説『{reboot_title}』（原案：{work['author']}『{work['title']}』）の読者向けに、作中に登場した以下の**3つの最新科学技術**についての**【作中技術のやさしい解説】**を執筆してください。

【解説する3つの最新科学技術と実在根拠論文】
{tech_context_block}

【出力フォーマット（以下の番号付きリスト形式のみを出力し、URLや参考文献リストは書かないでください）】
本作では、原案『{work['title']}』の世界観を現代科学で再構築するため、実在する3つの先端科学研究を取り入れています。

1. **{verified_papers[0]['tech_label']}**
   - **現実の科学**: （この技術が現実の科学研究でどこまで解明・実証されているかを、専門知識のない一般読者にも楽しくわかるように平易な言葉で解説）
   - **本作でのSF的飛躍**: （小説の中でこの科学技術をどのように物語の仕掛け・ドラマとして発展させたかを解説）

2. **{verified_papers[min(1, len(verified_papers)-1)]['tech_label']}**
   - **現実の科学**: （平易でわかりやすい解説）
   - **本作でのSF的飛躍**: （本作でのSF的アイデアの解説）

3. **{verified_papers[min(2, len(verified_papers)-1)]['tech_label']}**
   - **現実の科学**: （平易でわかりやすい解説）
   - **本作でのSF的飛躍**: （本作でのSF的アイデアの解説）
"""

        logger.info(f"[Local LLM: {model}] Step 2/2: Generating accessible Technical Commentary...")
        raw_commentary = self._call_ollama_chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": commentary_prompt},
            ],
            temperature=0.6,
            num_predict=2500,
            num_ctx=8192,
        )
        commentary_body = self._clean_llm_output(raw_commentary)
        # Strip heading if the model repeated it, and strip any stray URLs so only our verified DOIs appear
        commentary_body = re.sub(r"^#+.*作中技術のやさしい解説.*?\n", "", commentary_body).strip()
        commentary_body = re.sub(r"###\s*【引用・参考文献.*", "", commentary_body, flags=re.DOTALL).strip()
        commentary_body = re.sub(r"https?://\S+", "", commentary_body)

        # Step 4: Deterministically construct the verified Scientific References block
        ref_lines = []
        short_refs = []
        for idx, p in enumerate(verified_papers, start=1):
            ref_lines.append(f"{idx}. {p['citation_markdown']}")
            short_refs.append(p["short_ref"])
        references_block = "\n".join(ref_lines)

        # Assemble final Markdown document matching exact repository format
        safe_title = reboot_title.replace('"', '\\"')
        full_markdown = f"""---
title: "{safe_title}"
tags: ["SF", "青空文庫", "{work['author']}", "最先端科学", "{theme_info['name']}"]
---

『**原案：{work['author']}[『{work['title']}』]({work['url']})（青空文庫）**』

{story_body}

---

### 【作中技術のやさしい解説（Technical Commentary）】

{commentary_body}

---

### 【引用・参考文献（Scientific References）】

{references_block}
"""

        logger.info(
            f"[Local LLM: {model}] Completed '{reboot_title}'! "
            f"Total length: {len(full_markdown)} chars (Story body: {len(story_body)} chars), "
            f"Verified Crossref DOIs: {len(verified_papers)}"
        )
        return full_markdown, reboot_title, short_refs
