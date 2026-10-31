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
SECONDARY_LLM_HOST = "http://rtx5060lp:11434"
FALLBACK_OLLAMA_HOSTS = [
    "http://rtx5060lp:11434",
    "http://192.168.128.62:11434",
]
DEFAULT_LOCAL_MODEL = "shosetsu"
DEFAULT_SECONDARY_MODEL = "shosetsu"
DEFAULT_WRITER_MODEL = "shosetsu"
DEFAULT_DRAW_THINGS_HOST = "http://192.168.128.59:7860"

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
    "dazai-ningen-shikkaku": [
        (
            "ブレイン・マシン・インターフェースによる神経デコーディング",
            "Willett Hochberg Shenoy High-performance brain-to-text communication via handwriting Nature 2021",
        ),
        (
            "マイクロ表情・情動自律神経バイオフィードバック",
            "Ekman Friesen Constants across cultures in the face and emotion Journal of Personality and Social Psychology",
        ),
        (
            "脳波同期と他者共感の計算論的神経科学",
            "Hasson Uri Neural coupling between speakers and listeners Proceedings of the National Academy of Sciences 2010",
        ),
    ],
    "soseki-wagahai-wa-neko": [
        (
            "生体神経とナノバイオセンサーのハイブリッド結合",
            "Lieber Nanoscale electronic interfaces with cells and tissues Nano Letters 2012",
        ),
        (
            "マルチスペクトル環境知覚と超音波センシング",
            "Jones Sensory ecology How organisms acquire and process information Nature 2008",
        ),
        (
            "群知能による分散型都市環境モニタリング",
            "Bonabeau Dorigo Theraulaz Swarm Intelligence From Natural to Artificial Systems Oxford 1999",
        ),
    ],
    "soseki-botchan": [
        (
            "マルチエージェント強化学習と組織ダイナミクス",
            "Vinyals Silver Grandmaster level in StarCraft II using multi-agent reinforcement learning Nature 2019",
        ),
        (
            "量子暗号と改ざん不能な分散型監査ログ",
            "Bennett Brassard Quantum cryptography Public key distribution and coin tossing IEEE 1984",
        ),
        (
            "非ゼロサムゲーム理論と集団協力メカニズム",
            "Axelrod Hamilton The Evolution of Cooperation Science 1981",
        ),
    ],
    "akutagawa-hana": [
        (
            "モルフォゲン濃度勾配とバイオ3Dプリンティング組織再生",
            "Turing The Chemical Basis of Morphogenesis Philosophical Transactions of the Royal Society 1952",
        ),
        (
            "軟骨オルガノイドの自己組織化リモデリング",
            "Lancaster Knoblich Organogenesis in a dish Modeling development and disease using organoid technologies Science 2014",
        ),
        (
            "自己身体認知と容貌知覚の神経心理学",
            "Kanwisher McDermott Chun The fusiform face area a module in human extrastriate cortex Journal of Neuroscience 1997",
        ),
    ],
    "akutagawa-jigokuhen": [
        (
            "深層拡散モデルによるニューラルイメージングと情動デコーディング",
            "Ho Jain Abbeel Denoising diffusion probabilistic models NeurIPS 2020",
        ),
        (
            "極低温プラズマ分光イメージング",
            "Becker The European Physical Journal D plasma spectroscopy imaging 2006",
        ),
        (
            "美学的知覚における報酬系ドーパミンサージ",
            "Zeki Beauty in the brain Culture and Brain neuroesthetics 2014",
        ),
    ],
    "edogawa-kaijin-nijumenso": [
        (
            "電気光学メタマテリアルによる動的皮膚迷彩と光学的クローキング",
            "Schurig Pendry Smith Metamaterial Electromagnetic Cloak at Microwave Frequencies Science 2006",
        ),
        (
            "マルチモーダル顔面特徴点のリアルタイム模倣と生体認証欺瞞",
            "Jain Flynn Ross Handbook of Biometrics Springer 2008",
        ),
        (
            "量子セキュア認証と自律分散センシング網",
            "Gisin Ribordy Tittel Zbinden Quantum cryptography Reviews of Modern Physics 2002",
        ),
    ],
    "edogawa-d-zaka": [
        (
            "光コヒーレンストモグラフィと光子遅延復元技術",
            "Hecht optical coherence tomography Science 1991",
        ),
        (
            "微細眼球運動（マイクロサッカード）と視覚情報認知",
            "Martinez-Conde Macknik Fixational eye movements in normal and pathological vision Nature Reviews Neuroscience 2004",
        ),
        (
            "シャノン情報エントロピーと閉鎖系通信理論",
            "Shannon A Mathematical Theory of Communication Bell System Technical Journal 1948",
        ),
    ],
    "akutagawa-yabu-no-naka": [
        (
            "事後言語介入による記憶再構成（ロフタス効果）",
            "Loftus Palmer Reconstruction of automobile destruction an example of the interaction between language and memory Journal of Verbal Learning 1974",
        ),
        (
            "エピソード記憶の再固定化（リコンソリデーション）神経機構",
            "Nader Hardt A single standard for memory The case for reconsolidation Nature Reviews Neuroscience 2009",
        ),
        (
            "量子観測問題と客観的実在の測定論（ホイーラー・ズレック）",
            "Wheeler Zurek Quantum Theory and Measurement Princeton University Press 1983",
        ),
    ],
    "dazai-fugaku-hyakkei": [
        (
            "大気中水分滞留時間と地球規模循環ダイナミクス",
            "Trenberth Atmospheric Moisture Residence Time and Planetary Scale Circulation Journal of Climate 1998",
        ),
        (
            "大気エアロゾルと雲のマルチ波長光学リモートセンシング",
            "Kerr Optical remote sensing of atmospheric aerosols and clouds Nature 2000",
        ),
        (
            "人新世（Anthropocene）における地球惑星工学と環境適応",
            "Crutzen Geology of mankind Nature 2002",
        ),
    ],
    "soseki-sanshiro": [
        (
            "光子放射圧と光ピンセットによる微細物質捕捉",
            "Ashkin Acceleration and Trapping of Particles by Radiation Pressure Physical Review Letters 1970",
        ),
        (
            "前頭頭頂ネットワークにおける注意制御ダイナミクス",
            "Corbetta Shulman Control of goal-directed and stimulus-driven attention in the brain Nature Reviews Neuroscience 2002",
        ),
        (
            "スモールワールド複雑ネットワークにおける社会的感情伝播",
            "Watts Strogatz Collective dynamics of small-world networks Nature 1998",
        ),
    ],
    "mori-sansho-dayu": [
        (
            "ナノ足場材料と人工皮膚組織再生工学",
            "Langer Vacanti Tissue Engineering Science 1993",
        ),
        (
            "量子暗号鍵配送と長距離生体もつれテレメトリ",
            "Bennett Brassard Quantum cryptography Public key distribution and coin tossing Theoretical Computer Science 2014",
        ),
        (
            "下肢パワード外骨格と重負荷バイオメカニクス",
            "Dollar Herr Lower extremity exoskeletons and active orthoses a review IEEE 2008",
        ),
    ],
    "akutagawa-torokko": [
        (
            "磁気浮上（マグレブ）推進とマスドライバー軌道力学",
            "Lee Kim Lee Review of maglev train technologies IEEE 2006",
        ),
        (
            "扁桃体を中心とする情動・恐怖回路と自律神経サージ",
            "LeDoux Emotion Circuits in the Brain Annual Review of Neuroscience 2000",
        ),
        (
            "極限的恐怖・パニック状態における主観的時間伸長（タキサイキア現象）",
            "Stetson Fiesta Eagleman Does time really slow down during a frightening event PLoS ONE 2007",
        ),
    ],
    "nakajima-riryo": [
        (
            "DNA分子ストレージによる超長期デジタル記録保存",
            "Church Gao Kosuri Next-generation digital information storage in DNA Science 2012",
        ),
        (
            "極限環境適応におけるエピジェネティック遺伝子発現制御",
            "Jaenisch Bird Epigenetic regulation of gene expression Nature Genetics 2003",
        ),
        (
            "社会的孤立・極限監禁下における神経認知防御機構",
            "Cacioppo Hawkley Social isolation and health Neuroscience 2003",
        ),
    ],
    "soseki-mon": [
        (
            "量子情報境界と事象の地平線（ファイアウォール理論）",
            "Almheiri Marolf Polchinski Sully Black holes complementarity or firewalls Journal of High Energy Physics 2013",
        ),
        (
            "デフォルトモードネットワーク（DMN）の神経同期と瞑想変容意識",
            "Brewer Worhunsky Gray Meditation experience is associated with differences in default-mode network PNAS 2011",
        ),
        (
            "道徳的感情（罪悪感・羞恥）を司る前頭葉神経回路",
            "Tangney Stuewig Mashek Moral Emotions and Moral Behavior Annual Review of Psychology 2007",
        ),
    ],
    "akutagawa-butoukai": [
        (
            "回転式宇宙ステーションにおける人工重力ダイナミクス",
            "Clement Bukley Artificial Gravity Springer 2007",
        ),
        (
            "レーザー誘起プラズマ発光分光（LIBS）と光子放射スペクトル",
            "Cremers Radziemski Handbook of Laser-Induced Breakdown Spectroscopy Wiley 2006",
        ),
        (
            "自伝的記憶想起とノスタルジア知覚における神経相関",
            "Wildschut Sedikides Nostalgia content triggers functions Journal of Personality and Social Psychology 2006",
        ),
    ],
    "edogawa-kogane-kamen": [
        (
            "金ナノ粒子局在表面プラズモン共鳴（LSPR）と光散乱",
            "Willets Van Duyne Localized Surface Plasmon Resonance Spectroscopy Annual Review 2007",
        ),
        (
            "超電導量子干渉計（SQUID）による極微弱生体磁気計測",
            "Fagaly Superconducting quantum interference device Review of Scientific Instruments 2006",
        ),
        (
            "物理世界における敵対的機械学習摂動（Adversarial Perturbations）",
            "Goodfellow Shlens Szegedy Explaining and harnessing adversarial examples 2014",
        ),
    ],
    "dazai-shayo": [
        (
            "閉鎖生態系生命維持システム（CELSS）と物質循環熱力学",
            "Nelson Dempster Closed ecological systems Biosphere 2 to space life support PNAS 2009",
        ),
        (
            "ヘリウム3（³He）次世代核融合炉と代替エネルギー代謝",
            "Wittenberg Santarius Kulcinski Lunar helium-3 and fusion power Fusion Technology 1986",
        ),
        (
            "過酷環境下における協力と利他行動の進化五法則（Nowakモデル）",
            "Nowak Five Rules for the Evolution of Cooperation Science 2006",
        ),
    ],
    "miyazawa-cello-goushe": [
        (
            "コヒーレント・フォノン工学と音響メタマテリアル熱制御",
            "Maldovan Sound and heat revolutions in phononics Nature 2013",
        ),
        (
            "種間音響コミュニケーション（バイオアコースティクス）と認知進化",
            "Fitch The evolution of speech a comparative review Trends in Cognitive Sciences 2000",
        ),
        (
            "音楽音響刺激による脳神経可塑性誘導と認知機能回復",
            "Sarkamo Tervaniemi Cognitive recovery and mood enhancement by music listening Brain 2008",
        ),
    ],
    "dazai-kachikachi-yama": [
        (
            "ナノ流体コロイド懸濁液の動的熱伝導性と構造崩壊",
            "Murshed Leong Rice A review of nanofluids analysis synthesis and applications Applied Thermal Engineering 2008",
        ),
        (
            "熱分解プラズマ燃焼工学と高エネルギー推進",
            "Glassman Yetter Combustion Academic Press 2008",
        ),
        (
            "進化ゲーム理論における捕食・被食者の欺瞞戦略",
            "Maynard Smith Evolution and the Theory of Games Cambridge 1982",
        ),
    ],
    "akutagawa-imogayu": [
        (
            "中脳ドーパミン系による報酬予測誤差と欲求動機づけ",
            "Schultz Dayan Montague A neural substrate of prediction and reward Science 1997",
        ),
        (
            "ナノエマルジョン脂質キャリアによる味覚分子合成",
            "McClements Weiss Emulsion-based delivery systems for lipophilic bioactive components 2007",
        ),
        (
            "快楽適応（ヘドニック・トレッドミル）と欲求充足後の実存的空虚化",
            "Berridge Robinson What is the role of dopamine in reward Brain Research Reviews 1998",
        ),
    ],
    "soseki-jitensha-nikki": [
        (
            "線形化二輪ビークル動力学方程式（ステア・バランス連成制御）",
            "Meijaard Papadopoulos Ruina Schwab Linearized dynamics equations for bicycle Proceedings of the Royal Society A 2007",
        ),
        (
            "小脳プルキンエ細胞における長期抑圧（LTD）と内部モデル学習",
            "Ito Control of mental activities by internal models in the cerebellum Nature Reviews Neuroscience 2008",
        ),
        (
            "感覚運動フィードバックループにおける神経伝達遅延と適応制御",
            "Wolpert Ghahramani Computational principles of movement neuroscience Nature Neuroscience 2000",
        ),
    ],
    "sakaguchi-hakuchi": [
        (
            "非言語生体脳波同調・対人ニューロシンクロニー",
            "Dumas Nadel Inter-brain synchronization during social interaction PLoS ONE 2010",
        ),
        (
            "大規模火災旋風および対流プルーム流体力学",
            "Tohidi Kaye Comprehensive review of fire whirls fluid dynamics",
        ),
        (
            "極限ストレス下における神経保護と生体適応",
            "Charney Psychobiology of resilience to extreme stress Nature Reviews Neuroscience 2004",
        ),
    ],
    "akutagawa-majutsu": [
        (
            "凝縮系核反応・格子支援核融合（常温核変換）",
            "McKubre Cold fusion experimental status Current Science 2015",
        ),
        (
            "没入型バーチャルリアリティと身体所有感・知覚変容",
            "Slater Sanchez-Vives Enhancing our lives with immersive virtual reality Frontiers in Robotics and AI 2016",
        ),
        (
            "強化学習における強欲アルゴリズム（Greedy policy）の限界",
            "Mnih Silver Human-level control through deep reinforcement learning Nature 2015",
        ),
    ],
    "edogawa-nisen-doka": [
        (
            "ナノステガノグラフィおよび物理的偽造防止技術",
            "Kumar Nanoparticle physical unclonable functions anti-counterfeiting Nature Communications",
        ),
        (
            "量子アニーリングおよび組合せ最適化暗号解読",
            "Kadowaki Nishimori Quantum annealing in the transverse Ising model Physical Review E 1998",
        ),
        (
            "ゼロ知識証明および対話型暗号プロトコル",
            "Goldwasser Micali Rackoff The knowledge complexity of interactive proof systems SIAM Journal on Computing 1989",
        ),
    ],
    "dazai-goodbye": [
        (
            "分散表現学習における関係性の解きほぐし（Disentanglement）",
            "Higgins Matthey beta-VAE Learning Basic Visual Concepts with a Constrained Variational Framework",
        ),
        (
            "暗号学的匿名クレデンシャルとゼロ知識身元証明",
            "Camenisch Lysyanskaya Signature schemes and anonymous credentials",
        ),
        (
            "安定結婚問題と非協力ゲームにおけるマッチング均衡",
            "Gale Shapley College Admissions and the Stability of Marriage American Mathematical Monthly",
        ),
    ],
    "miyazawa-donguri-to-yamaneko": [
        (
            "社会的選択理論におけるアローの不可能性定理と選好集約",
            "Arrow A Difficulty in the Concept of Social Welfare Journal of Political Economy 1950",
        ),
        (
            "多目的進化的アルゴリズムにおけるパレート最適性（NSGA-II）",
            "Deb Pratap Agarwal Meyarivan A fast and elitist multiobjective genetic algorithm NSGA-II IEEE Transactions on Evolutionary Computation 2002",
        ),
        (
            "マルコフ連鎖を用いたウェブ検索ランキング集約アルゴリズム",
            "Dwork Kumar Naor Sivakumar Rank aggregation methods for the Web WWW 2001",
        ),
    ],
    "nakajima-mojika": [
        (
            "生成AIの自己再帰学習における表象崩壊（Model Collapse）現象",
            "Shumailov Shumaylov AI models collapse when trained on recursively generated data Nature 2024",
        ),
        (
            "アルゴリズム情報理論とコルモゴロフ複雑性による記号限界",
            "Kolmogorov Three approaches to the quantitative definition of information Problems of Information Transmission 1965",
        ),
        (
            "物理的記号接地問題（Symbol Grounding Problem）と意味論の起源",
            "Harnad The symbol grounding problem Physica D 1990",
        ),
    ],
    "miyazawa-yodaka-no-hoshi": [
        (
            "超薄膜光圧放射圧レーザーセイル推進",
            "Lubin A Roadmap to Interstellar Flight JBIS 2016",
        ),
        (
            "慣性閉じ込め核融合とレーザー爆縮物理",
            "Betti Hurricane Inertial-confinement fusion with lasers Nature Physics 2016",
        ),
        (
            "超新星残骸における相対論的粒子加速と放射",
            "Reynolds Supernova remnants at high energy Annual Review of Astronomy and Astrophysics 2008",
        ),
    ],
    "dazai-chikukendan": [
        (
            "深層強化学習における報酬ハッキングと意図的欺瞞",
            "Park Goldstein AI deception A survey of examples risks and potential solutions Patterns 2024",
        ),
        (
            "四足歩行ロボットの深層強化学習運動制御",
            "Hwangbo Lee Learning agile and dynamic motor skills for legged robots Science Robotics 2019",
        ),
        (
            "恐怖条件づけの消去学習と前頭前野神経回路",
            "Quirk Mueller Neural mechanisms of extinction learning and retrieval Neuropsychopharmacology 2008",
        ),
    ],
    "izumi-yashagaike": [
        (
            "音響放射圧およびホログラフィック音響浮遊トラップ",
            "Marzo Seah Drinkwater Acoustic levitation with holographic acoustic elements Nature Communications 2015",
        ),
        (
            "ダム決壊における極限水理学的段波と流体力学",
            "Stansby Chegini Shigematsu The initial stages of dam-break flow Journal of Fluid Mechanics 1998",
        ),
        (
            "気象改変ジオエンジニアリングと熱力学的暴走リスク",
            "Robock 20 reasons why geoengineering may be a bad idea Bulletin of the Atomic Scientists 2008",
        ),
    ],
    "mori-maihime": [
        (
            "受動歩行およびダイナミック二足歩行運動制御力学",
            "Collins Ruina Efficient bipedal robots based on passive-dynamic walkers Nature 2005",
        ),
        (
            "機能的脳機能画像による情動知覚の神経デコーディング",
            "Kragel LaBar Decoding facial expressions of emotion from frontoparietal cortex Nature Communications 2018",
        ),
        (
            "進化ゲーム理論における利他性と強い互恵性の進化",
            "Bowles Gintis The evolution of strong reciprocity cooperation in heterogeneous populations Theoretical Population Biology 2004",
        ),
    ],
    "izumi-gekaritsu": [
        (
            "脊髄膠様質痛覚制御機構とゲートコントロール理論",
            "Melzack Wall Pain mechanisms A new theory Science 1965",
        ),
        (
            "経頭蓋磁気刺激と脳波摂動複雑性指標（PCI）による意識判定",
            "Casali Gosseries Massimini A theoretically based index of consciousness independent of sensory processing Science Translational Medicine 2013",
        ),
        (
            "完全準同型暗号による秘密計算と生体データ保護",
            "Gentry A fully homomorphic encryption scheme Stanford University 2009",
        ),
    ],
    "miyazawa-yamanashi": [
        (
            "単一気泡ソノルミネッセンスと流体音響キャビテーション",
            "Brenner Hilgenfeldt Lohse Single-bubble sonoluminescence Reviews of Modern Physics 2002",
        ),
        (
            "群ロボティクスにおける自律分散協調と創発行動",
            "Brambilla Ferrante Birattari Dorigo Swarm robotics a review from the swarm engineering perspective Swarm Intelligence 2013",
        ),
        (
            "出芽酵母による揮発性芳香エステル化合物生合成機構",
            "Saerens Duong Verstrepen Production of volatile aroma compounds by Saccharomyces cerevisiae Applied Microbiology and Biotechnology 2010",
        ),
    ],
    "nakajima-deshi": [
        (
            "大規模言語モデルにおける強化学習と規範倫理アライメント",
            "Training language models to follow instructions with human feedback NeurIPS 2022",
        ),
        (
            "ビザンチン障害耐性分散合意形成アルゴリズム",
            "Castro Practical Byzantine Fault Tolerance OSDI 1999",
        ),
        (
            "運動機能再建のための侵襲型ブレイン・マシン・インターフェース",
            "Lebedev Nicolelis Brain machine interfaces past present and future Trends in Neurosciences 2006",
        ),
    ],
    "dazai-hifu-to-kokoro": [
        (
            "フレキシブル有機電界効果トランジスタによる大面積人工皮膚",
            "Someya flexible pressure sensor matrix organic field-effect transistors PNAS 2004",
        ),
        (
            "身体醜形障害における顔面視覚情報処理と神経基盤",
            "Feusner Visual information processing of faces in body dysmorphic disorder 2007",
        ),
        (
            "標的化ナノ粒子ドラッグデリバリーによる生体組織修復",
            "Farokhzad Langer Impact of nanotechnology on drug delivery ACS Nano 2009",
        ),
    ],
    "miyazawa-otsuberu-to-zo": [
        (
            "アジアゾウにおける超低周波不可聴インフラサウンド音響通信",
            "Payne Infrasonic calls of the Asian elephant 1986",
        ),
        (
            "生体骨格筋アクチュエータを用いたバイオハイブリッド・ロボティクス",
            "Raman Cvetkovic A filament-based biohybrid robot with onboard neuromuscular units PNAS 2016",
        ),
        (
            "サイバーフィジカル生産システムにおける自律分散型製造制御",
            "Monostori Cyber-physical Production Systems Roots Expectations CIRP Annals",
        ),
    ],
}