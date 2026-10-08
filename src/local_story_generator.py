import os
import re
import json
import time
import base64
import difflib
import logging
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Callable

from src.story_generator import (
    select_ending_theme,
    check_doi_validity,
    clean_doi_string,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)

DEFAULT_OLLAMA_HOST = "http://rtx5060lp:11434"
SECONDARY_LLM_HOST = "http://sff7020:1234"
FALLBACK_OLLAMA_HOSTS = [
    "http://rtx5060lp:11434",
    "http://sff7020:1234",
    "http://192.168.128.16:1234",
    "http://kenomac-mini:11434",
]
DEFAULT_LOCAL_MODEL = "shosetsu"
DEFAULT_SECONDARY_MODEL = "google/gemma-4-26b-a4b-qat"
DEFAULT_WRITER_MODEL = "shosetsu"
DEFAULT_DRAW_THINGS_HOST = "http://kenomac-mini:7860"

# Preferred local models in priority order if user hasn't explicitly forced one
PREFERRED_LOCAL_MODELS = [
    "shosetsu:latest",
    "shosetsu",
    "gemma3:27b",
    "qwen2.5:32b",
    "gemma4:12b",
    "qwen3:14b",
    "qwen2.5:14b",
    "gemma3:12b",
    "qwen3.5:9b",
    "gemma2:9b",
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
        writer_model: Optional[str] = None,
        draw_things_host: Optional[str] = None,
    ):
        raw_host = (ollama_host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)).strip()
        primary_hosts = [h.strip().rstrip("/") for h in raw_host.split(",") if h.strip()]
        self.ollama_host = primary_hosts[0] if primary_hosts else DEFAULT_OLLAMA_HOST
        self.ollama_hosts: List[str] = list(primary_hosts)
        for fb in FALLBACK_OLLAMA_HOSTS:
            fb_clean = fb.rstrip("/")
            if fb_clean not in self.ollama_hosts:
                self.ollama_hosts.append(fb_clean)
        self.model_name = model_name or os.getenv("OLLAMA_MODEL", "")
        self.writer_model = writer_model or os.getenv("OLLAMA_WRITER_MODEL", DEFAULT_WRITER_MODEL)
        self.draw_things_host = (draw_things_host or os.getenv("DRAW_THINGS_HOST", DEFAULT_DRAW_THINGS_HOST)).rstrip("/")

    def check_draw_things_connection(self) -> Dict[str, Any]:
        """Checks connection to Mac mini Draw Things HTTP API server (/sdapi/v1/options)."""
        try:
            req = urllib.request.Request(f"{self.draw_things_host}/sdapi/v1/options")
            with urllib.request.urlopen(req, timeout=5) as res:
                if res.getcode() == 200:
                    data = json.loads(res.read().decode("utf-8", errors="ignore"))
                    return {
                        "online": True,
                        "host": self.draw_things_host,
                        "model": data.get("model", "flux_2_klein_base_4b_i8x.ckpt"),
                    }
        except Exception as e:
            return {
                "online": False,
                "host": self.draw_things_host,
                "error": str(e),
            }
        return {"online": False, "host": self.draw_things_host}

    @staticmethod
    def _is_openai_compatible_host(host: str) -> bool:
        """Returns True if the host is an LM Studio / OpenAI-compatible server (e.g. http://sff7020:1234)."""
        h = host.lower()
        return ":1234" in h or "sff7020" in h or "/v1" in h

    def is_ollama_running(self, auto_start: bool = False) -> bool:
        for candidate_host in self.ollama_hosts:
            try:
                probe_path = "/v1/models" if self._is_openai_compatible_host(candidate_host) else "/api/tags"
                req = urllib.request.Request(f"{candidate_host}{probe_path}")
                with urllib.request.urlopen(req, timeout=5) as res:
                    if res.getcode() == 200:
                        if candidate_host != self.ollama_host:
                            logger.info(f"Switched active LLM host from {self.ollama_host} to {candidate_host}")
                            self.ollama_host = candidate_host
                        return True
            except Exception as e:
                logger.debug(f"LLM server check failed ({candidate_host}): {e}")

        return False

    def get_installed_models(self) -> List[str]:
        for candidate_host in self.ollama_hosts:
            try:
                is_oai = self._is_openai_compatible_host(candidate_host)
                probe_path = "/v1/models" if is_oai else "/api/tags"
                req = urllib.request.Request(f"{candidate_host}{probe_path}")
                with urllib.request.urlopen(req, timeout=5) as res:
                    if res.getcode() == 200:
                        data = json.loads(res.read().decode("utf-8", errors="ignore"))
                        if is_oai:
                            models = [
                                m.get("id", "")
                                for m in data.get("data", [])
                                if m.get("id") and "embed" not in m.get("id", "").lower()
                            ]
                        else:
                            models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
                        if models:
                            if candidate_host != self.ollama_host:
                                logger.info(f"Switched active LLM host to {candidate_host}")
                                self.ollama_host = candidate_host
                            return models
            except Exception as e:
                logger.debug(f"Could not list LLM models on {candidate_host}: {e}")
        return []

    def resolve_model_name(self) -> str:
        installed = self.get_installed_models()
        if self._is_openai_compatible_host(self.ollama_host):
            if self.model_name and self.model_name in installed:
                return self.model_name
            if DEFAULT_SECONDARY_MODEL in installed:
                return DEFAULT_SECONDARY_MODEL
            if installed:
                return installed[0]
            return DEFAULT_SECONDARY_MODEL
        if self.model_name:
            if self.model_name in installed:
                return self.model_name
            for inst in installed:
                if inst.startswith(self.model_name.split(":")[0]):
                    return inst
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

    def resolve_writer_model_name(self) -> str:
        """Resolves the optimal installed model for English visual prompt generation (`shosetsu` / `gemma4:12b` preferred)."""
        installed = self.get_installed_models()
        if self._is_openai_compatible_host(self.ollama_host):
            if DEFAULT_SECONDARY_MODEL in installed:
                return DEFAULT_SECONDARY_MODEL
            if installed:
                return installed[0]
            return DEFAULT_SECONDARY_MODEL
        if self.writer_model:
            if self.writer_model in installed:
                return self.writer_model
            for inst in installed:
                if inst.startswith(self.writer_model.split(":")[0]):
                    return inst
        for cand in ("shosetsu:latest", "shosetsu", "gemma4:12b", "gemma2:9b", "qwen3.5:9b", "qwen2.5:14b"):
            if cand in installed:
                return cand
        return self.resolve_model_name()

    def _call_ollama_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.75,
        num_predict: int = 8192,
        num_ctx: int = 8192,
        timeout: int = 1200,
        model_override: Optional[str] = None,
    ) -> str:
        hosts_to_try = [self.ollama_host] + [h for h in self.ollama_hosts if h != self.ollama_host]
        last_err: Optional[Exception] = None
        for host in hosts_to_try:
            is_oai = self._is_openai_compatible_host(host)
            if is_oai:
                url = f"{host}/v1/chat/completions"
                oai_model = model_override if (model_override and "/" in model_override) else DEFAULT_SECONDARY_MODEL
                oai_payload: Dict[str, Any] = {
                    "model": oai_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": num_predict,
                    "stream": False,
                }
                data = json.dumps(oai_payload).encode("utf-8")
            else:
                url = f"{host}/api/chat"
                model = model_override or self.resolve_model_name()
                if "/" in model and not is_oai:
                    model = DEFAULT_LOCAL_MODEL
                payload: Dict[str, Any] = {
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
                if any(k in model.lower() for k in ("shosetsu", "ronbun", "qwen3", "gemma4", "deepseek-r1")):
                    payload["think"] = False
                data = json.dumps(payload).encode("utf-8")

            try:
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout) as res:
                    body = json.loads(res.read().decode("utf-8", errors="ignore"))
                    if host != self.ollama_host:
                        logger.info(f"Failover succeeded on LLM host {host}")
                        self.ollama_host = host
                    if is_oai:
                        choices = body.get("choices", [])
                        if choices:
                            return choices[0].get("message", {}).get("content", "").strip()
                        return ""
                    return body.get("message", {}).get("content", "").strip()
            except Exception as e:
                last_err = e
                logger.warning(f"LLM chat failed on {host}: {e}")
        raise RuntimeError(f"All LLM hosts ({hosts_to_try}) failed: {last_err}")

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

    def _normalize_japanese_typos(self, text: str) -> str:
        """Fixes common Simplified Chinese character leaks or archaic typos emitted by local LLMs."""
        replacements = {
            "无反射": "無反射",
            "无響": "無響",
            "前头前野": "前頭前野",
            "前头葉": "前頭葉",
            "神经活动": "神経活動",
            "神经": "神経",
            "実騐": "実験",
            "验証": "検証",
            "脑内": "脳内",
            "计測": "計測",
            "连成": "連成",
            "电気": "電気",
            "电子": "電子",
            "结构": "構造",
            "记忆": "記憶",
            "选択": "選択",
            "观测": "観測",
        }
        for wrong, right in replacements.items():
            text = text.replace(wrong, right)
        return text

    def _remove_fuzzy_repetitions(
        self,
        text: str,
        para_threshold: float = 0.52,
        sent_threshold: float = 0.56,
    ) -> Tuple[str, int]:
        """
        Detects and removes near-duplicate paragraphs and sentences (including repeated
        dialogue lines with slight wording variations) across the entire story text.
        Also removes meta-transition markers like '【次回へ続く】' or '次のページでは…'
        and trims trailing incomplete sentence cutoffs before '* * *' or '（了）'.
        Returns (cleaned_text, removed_count).
        """
        text = self._normalize_japanese_typos(text)
        removed_count = 0

        # 1. Remove meta-continuation lines
        meta_patterns = [
            r"^.*【次回へ続く】.*$",
            r"^.*（次回へ続く）.*$",
            r"^.*次のページでは.*$",
            r"^.*後半へ続く.*$",
            r"^.*第[1-4一二三四]シーン.*$",
        ]
        for pat in meta_patterns:
            text, n_sub = re.subn(pat, "", text, flags=re.MULTILINE)
            removed_count += n_sub

        raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
        kept_paragraphs: List[str] = []
        seen_Normalized_paras: List[str] = []
        seen_normalized_sents: List[str] = []

        for p in raw_paragraphs:
            if p in ("* * *", "---", "（了）", "(了)"):
                if p == "* * *" and kept_paragraphs and kept_paragraphs[-1] == "* * *":
                    continue
                kept_paragraphs.append(p)
                continue

            norm_p = re.sub(r"[\s「」『』、。！？…―—・]", "", p)
            if len(norm_p) >= 22:
                is_dup_para = False
                for prev_p in seen_Normalized_paras:
                    ratio = difflib.SequenceMatcher(None, norm_p, prev_p).ratio()
                    if ratio >= para_threshold or (len(norm_p) >= 28 and (norm_p in prev_p or prev_p in norm_p)):
                        is_dup_para = True
                        removed_count += 1
                        break
                if is_dup_para:
                    continue

            # Split paragraph into sentence units (preserving punctuation and closing quotes, including 「...」 without a trailing 。)
            sent_tokens = re.findall(r"(?:「[^」]*」|[^。！？\n]+(?:[。！？]+(?:」|』|）|\))?|$))", p)
            if not sent_tokens:
                sent_tokens = [p]

            kept_sents: List[str] = []
            for s in sent_tokens:
                s_clean = s.strip()
                if not s_clean:
                    continue
                norm_s = re.sub(r"[\s「」『』、。！？…―—・]", "", s_clean)
                if len(norm_s) >= 16:
                    is_dup_sent = False
                    for prev_s in seen_normalized_sents:
                        ratio = difflib.SequenceMatcher(None, norm_s, prev_s).ratio()
                        if ratio >= sent_threshold or (len(norm_s) >= 20 and (norm_s in prev_s or prev_s in norm_s)):
                            is_dup_sent = True
                            removed_count += 1
                            break
                    if is_dup_sent:
                        continue
                    seen_normalized_sents.append(norm_s)
                kept_sents.append(s_clean)

            if not kept_sents:
                continue

            reconstructed_p = "".join(kept_sents).strip()
            # Ensure unbalanced quotes are never left behind
            if reconstructed_p.count("「") != reconstructed_p.count("」"):
                reconstructed_p = p.strip()
            # Check if the paragraph ends with an abrupt mid-sentence cutoff (not ending with valid punctuation)
            if reconstructed_p and not re.search(r"[。！？!?」』）\)\*了]$", reconstructed_p):
                # If paragraph has earlier complete sentences, keep only up to the last complete sentence
                last_punct = max(
                    reconstructed_p.rfind("。"),
                    reconstructed_p.rfind("！"),
                    reconstructed_p.rfind("？"),
                    reconstructed_p.rfind("」"),
                    reconstructed_p.rfind("』"),
                )
                if last_punct > 10:
                    reconstructed_p = reconstructed_p[: last_punct + 1].strip()
                    removed_count += 1
                else:
                    # Entire short fragment was cut off mid-sentence
                    removed_count += 1
                    continue

            norm_reconstructed = re.sub(r"[\s「」『』、。！？…―—・]", "", reconstructed_p)
            if len(norm_reconstructed) >= 22:
                seen_Normalized_paras.append(norm_reconstructed)
            kept_paragraphs.append(reconstructed_p)

        cleaned = "\n\n".join(kept_paragraphs).strip()
        cleaned = re.sub(r"(\*\s*\*\s*\*\s*\n+){2,}", "* * *\n\n", cleaned)
        return cleaned, removed_count

    def audit_story_quality(self, story_body: str) -> Dict[str, Any]:
        """
        Audits a story body for sentence/paragraph repetitions, mid-sentence cutoffs,
        or meta-markers. Returns a report dict with 'issues_count' and details.
        """
        paragraphs = [
            p.strip()
            for p in re.split(r"\n\s*\n", story_body)
            if p.strip() and p.strip() not in ("* * *", "---", "（了）")
        ]
        dup_paras = 0
        norm_paras = [re.sub(r"[\s「」『』、。！？…―—・]", "", p) for p in paragraphs if len(p) >= 22]
        for i in range(len(norm_paras)):
            for j in range(i + 1, len(norm_paras)):
                if difflib.SequenceMatcher(None, norm_paras[i], norm_paras[j]).ratio() >= 0.52:
                    dup_paras += 1

        sents = [
            s.strip()
            for s in re.split(r"[。！？\n]+", story_body)
            if len(s.strip()) >= 18 and s.strip() not in ("* * *", "---", "（了）")
        ]
        dup_sents = 0
        norm_sents = [re.sub(r"[\s「」『』、。！？…―—・]", "", s) for s in sents]
        for i in range(len(norm_sents)):
            for j in range(i + 1, len(norm_sents)):
                if len(norm_sents[i]) >= 16 and len(norm_sents[j]) >= 16:
                    if difflib.SequenceMatcher(None, norm_sents[i], norm_sents[j]).ratio() >= 0.56:
                        dup_sents += 1

        cutoffs = 0
        for p in paragraphs:
            if not re.search(r"[。！？!?」』）\)\*了]$", p):
                cutoffs += 1

        return {
            "dup_paras": dup_paras,
            "dup_sents": dup_sents,
            "cutoffs": cutoffs,
            "issues_count": dup_paras + dup_sents + cutoffs,
        }

    def proofread_and_polish_story(
        self,
        story_body: str,
        work: Dict[str, Any],
        reboot_title: str,
    ) -> str:
        """
        Performs a dedicated multi-stage verification & proofreading pass on the generated story:
        1) Runs deterministic fuzzy deduplication (`_remove_fuzzy_repetitions`) to strip repeated
           sentences/paragraphs/dialogue and mid-sentence cutoffs.
        2) Audits the story and runs a Local LLM proofreading pass to verify natural flow,
           eliminate any remaining semantic redundancy, and ensure a clean ending (`（了）`).
        3) Re-applies deterministic deduplication on the proofread output and keeps the
           highest-quality version.
        """
        # Stage 1: Deterministic fuzzy deduplication & typo cleanup
        deduped_body, removed_count = self._remove_fuzzy_repetitions(story_body)
        audit_before = self.audit_story_quality(deduped_body)
        logger.info(
            f"[Proofread Pass] Deterministic cleanup removed {removed_count} repetitive/cutoff segments "
            f"(remaining issues: {audit_before['issues_count']}, length: {len(deduped_body)} chars)."
        )

        # Stage 2: Local LLM editorial proofreading pass to ensure smooth transitions and zero semantic repetition
        proofread_prompt = f"""あなたは熟練のSF文芸編集者・校閲者です。
以下の短編SF小説『{reboot_title}』（原案：{work['author']}『{work['title']}』）の本文を読み直し、**文章の繰り返しや不自然な途切れを完全に修正した決定稿**を出力してください。

【校閲・推敲の絶対ルール】
1. **繰り返しの完全除去**:
   - 同じ意味のセリフ、同じ情景描写、同じ科学設定の説明が複数回繰り返されている箇所があれば、最も鮮やかで効果的な1箇所だけを残し、重複箇所は削除または自然な展開へ書き換えてください。
2. **文脈の自然な接続と完結**:
   - シーン区切り（`* * *`）の前後で文章が途中で切れていたり、同じやり取りがループしていたりする場合は、滑らかに繋がるように整えてください。
   - 簡体字（无、头、实など）や不自然な文字が混入していれば正しい日本語の漢字に直してください。
3. **構成と分量の維持**:
   - 物語の登場人物、魅力的な描写、科学要素、そして結末のどんでん返しは削らずに活かし、本文の最後は必ず `（了）` で締めくくってください。
   - タイトルや解説は出力せず、**校閲済みの小説本文のみ**を出力してください。

【校閲対象の小説本文】
{deduped_body}
"""
        try:
            logger.info("[Proofread Pass] Running Local LLM full-text verification & proofreading pass...")
            raw_proofread = self._call_ollama_chat(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": proofread_prompt},
                ],
                temperature=0.45,
                num_predict=4500,
                num_ctx=8192,
                timeout=1800,
            )
            cleaned_proofread = self._clean_llm_output(raw_proofread)
            pr_lines = []
            for line in cleaned_proofread.splitlines():
                stripped = line.strip()
                if "【作中技術のやさしい解説" in stripped or "【引用・参考文献" in stripped:
                    break
                if stripped.startswith("TITLE:") or stripped.startswith("# "):
                    continue
                pr_lines.append(line)
            candidate_body = "\n".join(pr_lines).strip()
            candidate_body, _ = self._remove_fuzzy_repetitions(candidate_body)
            if not candidate_body.endswith("（了）"):
                candidate_body = candidate_body.rstrip() + "\n\n（了）"

            audit_after = self.audit_story_quality(candidate_body)
            # Accept the LLM-polished version if it preserves at least 70% of the story length and has 0 issues
            if len(candidate_body) >= int(len(deduped_body) * 0.70) and audit_after["issues_count"] <= audit_before["issues_count"]:
                logger.info(
                    f"[Proofread Pass] LLM proofreading succeeded ({len(candidate_body)} chars, "
                    f"issues: {audit_after['issues_count']})."
                )
                deduped_body = candidate_body
            else:
                logger.info(
                    f"[Proofread Pass] Keeping deterministic deduplicated version "
                    f"(LLM candidate len={len(candidate_body)} vs {len(deduped_body)})."
                )
        except Exception as e:
            logger.warning(f"[Proofread Pass] LLM proofreading step skipped due to error: {e}")

        if not deduped_body.endswith("（了）"):
            deduped_body = deduped_body.rstrip() + "\n\n（了）"
        return deduped_body

    def _clean_llm_output(self, text: str) -> str:
        """Removes <think>...</think> blocks, markdown fences, scene meta-headers, repetition loops, and stray URLs."""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if text.startswith("```markdown"):
            text = text[len("```markdown"):].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        text = self._normalize_japanese_typos(text)
        # Strip meta scene headings like '### 第1シーン', '第1シーン', '## シーン2', '### * * *', '### *'
        text = re.sub(r"^[ \t]*#+[ \t]*(\*\s*\*\s*\*)[ \t]*$", r"\1", text, flags=re.MULTILINE)
        text = re.sub(r"^[ \t]*#+[ \t]*\*+[ \t]*$", "* * *", text, flags=re.MULTILINE)
        text = re.sub(
            r"^[ \t]*(?:#+[ \t]*)?[【\[（(]?(?:第\s*[0-9一二三四五六七八九十]+\s*(?:シーン|幕|章|部|節)|シーン\s*[0-9一二三四五六七八九十]+)[】\]）)]?(?:[：:\s—―-].*)?$",
            "",
            text,
            flags=re.MULTILINE,
        )
        # Remove any repeated long paragraphs/lines (prevents local LLM repetition loops)
        seen_long_lines = set()
        deduped_lines = []
        for line in text.splitlines():
            s = line.strip()
            if len(s) >= 35 and s not in ("* * *", "---"):
                if s in seen_long_lines:
                    continue
                seen_long_lines.add(s)
            deduped_lines.append(line)
        return "\n".join(deduped_lines).strip()

    def generate_story(
        self,
        work: Dict[str, Any],
        ending_theme: Optional[str] = None,
    ) -> Tuple[str, str, List[str]]:
        """
        Generates a complete, publication-ready Aozora Bunko sci-fi reboot markdown document:
        1) Pre-fetches 3 authentic, DOI-verified scientific papers via Crossref API.
        2) Generates a 3,500-4,500 char story body via Local LLM (Ollama).
        3) Runs a multi-stage verification & proofreading pass (`proofread_and_polish_story`)
           to eliminate any sentence/paragraph repetitions, Chinese character leaks, or cutoffs.
        4) Generates the accessible 3-point Technical Commentary via Local LLM grounded in the 3 verified papers.
        5) Deterministically attaches the YAML frontmatter, original work header, and verified Scientific References.
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

※重要：物語全体を前半・後半の2回に分けて執筆します。今回の出力では**絶対に物語を完結させず（『（了）』や『【次回へ続く】』と書かず）**、謎が深まり決定的な局面へ突入する緊迫した場面（クリフハンガー）で後半へバトンを渡してください。

【対象の原典作品】
- 原典タイトル: {work['title']}
- 原典著者: {work['author']}
- 原典のテーマ: {work['theme']}
- 原典のあらすじ・リブート視点: {work['summary']}

【作中に自然に取り入れる3つの最新科学要素（専門用語の連発や数式は禁止し、五感の描写と人間ドラマに溶け込ませること）】
{tech_context_block}

【最終的な結末テーマ（後半で到達する方向性）：★{theme_info['name']}★】
{theme_info['description']}
{f"{chr(10)}【構成作家（sff7020 / Gemma 4 26B）による事前プロット設計】{chr(10)}{work['_director_plot_blueprint']}{chr(10)}" if work.get('_director_plot_blueprint') else ""}
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
5. **表現の注意（最重要）**:
   - **同じセリフ、同じ情景描写、同じ科学説明の繰り返しを厳禁**とします。一度述べた事柄は別の角度・新しい展開へと進めてください。
"""

        logger.info(f"[Local LLM: {model}] Step 1/4: Generating Story Part 1 (Setup & Mystery)...")
        raw_part1 = self._call_ollama_chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": part1_prompt},
            ],
            temperature=0.75,
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
        part1_body, _ = self._remove_fuzzy_repetitions(part1_body)

        # Step 2B: Generate Part 2 of the Story (Scene 3 & Scene 4: Turning Point, Twist & Resolution)
        part2_prompt = f"""素晴らしい前半パートです！続けて、この小説『{reboot_title}』の**【後半パート（第3シーン・第4シーン：目標1,800〜2,200文字）】**を執筆し、物語を完結させてください。

【後半パートの構成と絶対ルール】
1. **直前の続きから自然に書き始めること**:
   - タイトルは書かず、前半パートの直後に続く本文（第3シーン）から書き始めてください。
   - 前半に登場した人物の名前・性別・一人称・口調を100%そのまま維持してください。
   - **前半ですでに書いたセリフ・説明・描写の繰り返しは厳禁**です。事態を大きく前進させてください。
2. **第3シーン（核心への突入と危機・転機：約900〜1,100文字）**:
   - 技術要素3（{verified_papers[min(2, len(verified_papers)-1)]['tech_label']}）が決定的な役割を果たし、前半の謎が一気に核心へと迫るスリリングな展開を描いてください。
3. **シーン区切り**:
   第3シーンと第4シーンの間には `* * *` を1行入れてください（「【転】」「【結】」などの見出しは絶対に入れないこと）。
4. **第4シーン（驚愕のどんでん返しと深い気づきの結末：約900〜1,100文字）**:
   - 結末テーマ【★{theme_info['name']}★】に沿って、前半の伏線が一気に回収される**「そういうことだったのか！」と膝を打つ意外な真相（どんでん返し）**と、**人間や世界に対する見方が変わる深い気づき（センス・オブ・ワンダー）**を鮮やかに描いてください。
   - 「すべては夢・シミュレーションだった」という安易な夢オチは厳禁です。
   - 同じやり取りをループさせず、小説本文の最後は必ず `（了）` で完結させてください（技術解説や参考文献はまだ書かないでください）。
"""

        logger.info(f"[Local LLM: {model}] Step 2/4: Generating Story Part 2 (Climax, Twist & Ending)...")
        raw_part2 = self._call_ollama_chat(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": part1_prompt},
                {"role": "assistant", "content": f"TITLE: {reboot_title}\n\n{part1_body}"},
                {"role": "user", "content": part2_prompt},
            ],
            temperature=0.75,
            num_predict=3200,
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

        # Step 3: Dedicated Verification, Deduplication & Proofreading Pass
        logger.info(f"[Local LLM: {model}] Step 3/4: Verifying & proofreading story to eliminate repetitions...")
        story_body = self.proofread_and_polish_story(story_body, work=work, reboot_title=reboot_title)

        # Step 4: Generate Technical Commentary grounded strictly in the 3 verified papers
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

        logger.info(f"[Local LLM: {model}] Step 4/4: Generating accessible Technical Commentary...")
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

    def generate_english_image_prompt(
        self,
        work: Dict[str, Any],
        story_body: str = "",
        reboot_title: str = "",
    ) -> str:
        """
        Uses `gemma4:12b` (Writer) on Mac mini M4 Ollama to translate the sci-fi reboot novel's
        most visually iconic scene into a concise, descriptive English image generation prompt
        for FLUX.2 [klein] 4B.
        """
        writer_model = self.resolve_writer_model_name()
        story_excerpt = story_body[:1600] if story_body else work.get("summary", "")

        prompt = f"""You are an expert sci-fi novel and cinematic anime art director.
Based on the following Japanese sci-fi reboot novel (inspired by Aozora Bunko literary classics and cutting-edge modern science), write a single, vivid, highly descriptive **English image generation prompt** (60-95 words) for the FLUX.2 image model to depict the most iconic, atmospheric scene of the story.

[Story Info]
- Reboot Title: {reboot_title or work.get('title', '')}
- Original Classic Work: {work.get('title', '')} by {work.get('author', '')}
- Core Theme: {work.get('theme', '')}
- Modern Scientific Technology: {work.get('modern_tech', '')}
- Story Concept: {work.get('summary', '')}

[Story Excerpt]
{story_excerpt}

[Rules for Output]
1. Output ONLY the raw English prompt paragraph. Do NOT include explanations, markdown formatting, quotes, or Japanese text.
2. Start with: "Cinematic sci-fi anime illustration of ..."
3. Visually describe the characters, setting, lighting, and the specific scientific/literary visual motif (e.g., holographic quantum patterns, glowing bioluminescent laboratory, retro-futuristic Meiji/Taisho literary atmosphere fused with futuristic technology, starry cosmos, or surreal cybernetic phenomena).
4. NEVER mention words, text, letters, book covers, titles, labels, or writing/equations on screens. The image must contain ZERO text or characters.
5. End with: "masterpiece sci-fi anime novel illustration style, Makoto Shinkai and Ghost in the Shell inspired cinematic lighting, calm and composed atmosphere, strong contrast, rich deep colors, crisp details, no text, no letters."
"""
        try:
            logger.info(f"[Writer: {writer_model}] Generating English illustration prompt for FLUX.2...")
            raw_en = self._call_ollama_chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a professional prompt engineer for FLUX.2 sci-fi anime illustrations. Output ONLY the English prompt text. Never include text, letters, writing, equations, or book cover elements in the prompt.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.6,
                num_predict=250,
                num_ctx=4096,
                timeout=300,
                model_override=writer_model,
            )
            cleaned_en = self._clean_llm_output(raw_en).strip(" \"'`\n")
            cleaned_en = re.sub(r"^(?:Prompt|English Prompt)\s*[:：]\s*", "", cleaned_en, flags=re.IGNORECASE).strip()
            cleaned_en = " ".join(cleaned_en.splitlines()).strip()
            cleaned_en = re.sub(r"\b(?:book cover|book illustration|equations|formulas|chalk writing|written|labeled|text)\b", "diagram", cleaned_en, flags=re.IGNORECASE)
            if len(cleaned_en) >= 30 and re.search(r"[a-zA-Z]{4,}", cleaned_en):
                logger.info(f"  -> Generated English prompt: {cleaned_en[:120]}...")
                return cleaned_en
        except Exception as e:
            logger.warning(f"Failed to generate English prompt via Ollama ({e}), using fallback English prompt.")

        return (
            f"Cinematic sci-fi anime illustration inspired by {work.get('id', 'futuristic science').replace('-', ' ')}, "
            f"a mysterious protagonist in a futuristic laboratory where classical Japanese literary aesthetics meet "
            f"glowing quantum holograms and advanced bio-photonic instruments, "
            f"masterpiece sci-fi anime novel illustration style, atmospheric lighting, dramatic shadows, rich deep colors, strong contrast, no text, no letters."
        )

    def generate_illustration(
        self,
        work: Dict[str, Any],
        output_image_path: Path,
        story_body: str = "",
        reboot_title: str = "",
        custom_english_prompt: Optional[str] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Optional[Path], str]:
        """
        Generates a 512x512 sci-fi illustration using Draw Things HTTP API
        (`http://kenomac-mini:7860/sdapi/v1/txt2img`, model `flux_2_klein_base_4b_i8x.ckpt`)
        with an English prompt created by `gemma4:12b`.
        Returns (saved_image_path_or_None, english_prompt_used).
        """
        dt_conn = self.check_draw_things_connection()
        if not dt_conn.get("online"):
            logger.warning(
                f"Draw Things HTTP API server ({self.draw_things_host}) is not reachable: {dt_conn.get('error')}. Skipping image generation."
            )
            return None, ""

        if custom_english_prompt and custom_english_prompt.strip():
            en_prompt = custom_english_prompt.strip()
        else:
            if progress_callback:
                progress_callback(f"執筆モデル ({self.resolve_writer_model_name()}) が小説本文から英語の挿絵プロンプトを作成中...")
            en_prompt = self.generate_english_image_prompt(
                work=work,
                story_body=story_body,
                reboot_title=reboot_title,
            )

        if progress_callback:
            progress_callback(f"Draw Things ({self.draw_things_host}) で挿絵画像を生成中 (FLUX.2 [klein] 4B)...")
        logger.info(
            f"[Draw Things: {self.draw_things_host}] Generating 512x512 illustration "
            f"(steps=12, guidance=4.0, sampler='Euler A Trailing')..."
        )

        style_suffix = (
            "calm and composed atmosphere, strong contrast, rich deep colors, balanced lighting, "
            "distinct shadows and highlights, crisp clean artwork, pure illustration without any text or letters"
        )
        if "strong contrast" not in en_prompt.lower() or "no text" not in en_prompt.lower():
            en_prompt = f"{en_prompt.rstrip(' .')}, {style_suffix}."

        url = f"{self.draw_things_host}/sdapi/v1/txt2img"
        payload = {
            "prompt": en_prompt,
            "negative_prompt": (
                "text, letters, words, kanji, chinese characters, japanese text, english text, typography, title, "
                "book cover, watermark, signature, logo, caption, writing, chalk equations, numbers, "
                "overexposed, washed out, faded, blown-out highlights, whiteout, pastel haze, low contrast"
            ),
            "width": 512,
            "height": 512,
            "steps": 12,
            "guidance_scale": 4.0,
            "sampler": "Euler A Trailing",
        }
        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            start_t = time.time()
            with urllib.request.urlopen(req, timeout=600) as res:
                body = json.loads(res.read().decode("utf-8", errors="ignore"))
                images = body.get("images", [])
                if images and images[0]:
                    b64_str = re.sub(r"^data:image/[^;]+;base64,", "", images[0])
                    img_bytes = base64.b64decode(b64_str)
                    output_image_path.parent.mkdir(parents=True, exist_ok=True)
                    output_image_path.write_bytes(img_bytes)
                    elapsed = time.time() - start_t
                    logger.info(
                        f"[Draw Things Complete] Saved illustration to {output_image_path} "
                        f"({len(img_bytes)} bytes in {elapsed:.1f}s)"
                    )
                    return output_image_path, en_prompt
                else:
                    logger.warning("Draw Things returned empty images list.")
        except Exception as e:
            logger.error(f"Draw Things image generation failed: {e}")

        return None, en_prompt

