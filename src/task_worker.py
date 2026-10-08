import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.archiver import update_archive_all
from src.history_manager import HistoryManager
from src.local_story_generator import LocalStoryGenerator
from src.site_builder import build_github_pages

JST = timezone(timedelta(hours=9))
logger = logging.getLogger("neosf-task-worker")

TASKS_JSON_PATH = Path("data/tasks.json")
TASKS_MD_PATH = Path("data/TASKS.md")
PLOTS_DIR = Path("data/plots")

PROJECT_ID = "b531d04e-6cb0-4202-9ea3-0056c8e2d7f6"
PROJECT_NAME = "neo-sf-aozora"
PROJECT_TITLE = "Neo SF Aozora（青空文庫×最先端科学 ハードSFリブート）"

DEFAULT_ROLES_CONFIG = {
    "rtx5060lp": {
        "node": "rtx5060lp",
        "role": "writer_primary",
        "host": "http://rtx5060lp:11434",
        "fallback_host": "http://192.168.128.62:11434",
        "model": "shosetsu",
        "daily_quota": 1,
        "description": "【プライマリ小説執筆】奇数番・交互担当で青空文庫SFリブート小説本文・技術解説を執筆（Ollama shosetsu）",
    },
    "sff7020": {
        "node": "sff7020",
        "role": "writer_secondary",
        "host": "http://sff7020:1234",
        "fallback_host": "http://192.168.128.16:1234",
        "model": "google/gemma-4-26b-a4b-qat",
        "daily_quota": 1,
        "description": "【セカンダリ小説執筆＆プロット/校閲】偶数番・交互担当で煽り・ケレン味のあるSF小説を執筆＆先行プロット設計（LM Studio :1234）",
    },
    "kenomac-mini": {
        "node": "kenomac-mini",
        "role": "illustrator",
        "host": "http://kenomac-mini:7860",
        "fallback_host": "http://192.168.128.59:7860",
        "ollama_host": "http://kenomac-mini:11434",
        "fallback_ollama_host": "http://192.168.128.59:11434",
        "model": "flux_2_klein_base_4b_i8x.ckpt",
        "daily_quota": 5,
        "description": "【挿絵生成＆Web公開】FLUX.2 挿絵生成（content/*.png）＆ GitHub Pages（docs/・archive/）ビルド更新",
    },
}


def setup_logging(verbose: bool = False):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def git_pull_latest() -> bool:
    try:
        logger.info("GitHubから最新の作業リストと原稿を同期中 (git pull --rebase origin main)...")
        subprocess.run(["git", "checkout", "--", "data/tasks.json", "data/TASKS.md"], check=False)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        return True
    except Exception as e:
        logger.warning(f"git pull warning: {e}")
        return False


def git_commit_and_push(message: str, paths: Optional[List[str]] = None) -> bool:
    target_paths = paths or ["README.md", "content/", "archive/", "data/", "docs/"]
    try:
        for p in target_paths:
            if Path(p).exists():
                subprocess.run(["git", "add", p], check=False)
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff_res.returncode == 0:
            logger.info("コミット対象の変更はありません。")
            return True
        subprocess.run(["git", "commit", "-m", message], check=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        logger.info(f"GitHubへの自動プッシュ完了: {message}")
        return True
    except Exception as e:
        logger.error(f"Git push error: {e}")
        return False


def probe_http_json(url: str, timeout: int = 3) -> Optional[Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AntigravityTaskWorker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            if res.getcode() == 200:
                return json.loads(res.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None
    return None


def resolve_reachable_url(candidates: List[str], probe_path: str, timeout: int = 3) -> Optional[str]:
    for base in candidates:
        if not base:
            continue
        clean_base = base.rstrip("/")
        if probe_http_json(f"{clean_base}{probe_path}", timeout=timeout) is not None:
            return clean_base
    return None


def call_lm_studio_chat(
    host: str,
    messages: List[Dict[str, str]],
    preferred_model: str = "google/gemma-4-26b-a4b-qat",
    temperature: float = 0.65,
    max_tokens: int = 2200,
    timeout: int = 300,
) -> Optional[str]:
    models_data = probe_http_json(f"{host}/v1/models", timeout=4)
    model_id = preferred_model
    if models_data and isinstance(models_data.get("data"), list):
        available = [m.get("id", "") for m in models_data["data"] if m.get("id")]
        non_embed = [m for m in available if "embed" not in m.lower()]
        if preferred_model in available:
            model_id = preferred_model
        elif non_embed:
            model_id = non_embed[0]

    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = json.loads(res.read().decode("utf-8", errors="ignore"))
            choices = body.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                return content
    except Exception as e:
        logger.warning(f"LM Studio call failed on {host} ({model_id}): {e}")
    return None


def sync_tasks_manifest(history_mgr: HistoryManager) -> Dict[str, Any]:
    existing_data: Dict[str, Any] = {}
    if TASKS_JSON_PATH.exists():
        try:
            existing_data = json.loads(TASKS_JSON_PATH.read_text(encoding="utf-8"))
        except Exception:
            existing_data = {}

    existing_tasks_map: Dict[str, Dict[str, Any]] = {
        t["id"]: t for t in existing_data.get("tasks", []) if isinstance(t, dict) and "id" in t
    }
    roles_cfg = dict(DEFAULT_ROLES_CONFIG)
    posted_ids = history_mgr.get_posted_ids()

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    synced_tasks: List[Dict[str, Any]] = []
    # Since rtx5060lp wrote the latest completed stories (#56, #57), start the pending queue with sff7020 first!
    uncompleted_queue_idx = 0

    for idx, work in enumerate(history_mgr.catalog, start=1):
        wid = work["id"]
        prev = existing_tasks_map.get(wid, {})
        stock_md = history_mgr.find_stock_file_for_work(wid)
        stock_png = stock_md.with_suffix(".png") if stock_md else None
        plot_path = PLOTS_DIR / f"{wid}.md"

        md_rel = str(stock_md).replace("\\", "/") if stock_md and stock_md.exists() else None
        png_rel = str(stock_png).replace("\\", "/") if stock_png and stock_png.exists() else None
        plot_rel = str(plot_path).replace("\\", "/") if plot_path.exists() else None

        if md_rel and png_rel:
            status = "completed"
        elif md_rel and not png_rel:
            status = "pending_illustration"
        elif wid in posted_ids and not md_rel:
            status = "completed"
        elif plot_rel:
            status = "plot_ready"
        else:
            status = "pending"

        inferred_date = None
        if stock_md and re.match(r"^\d{4}-\d{2}-\d{2}_", stock_md.name):
            inferred_date = stock_md.name[:10]

        # Alternating writer assignment: sff7020 (Secondary :1234) and rtx5060lp (Primary :11434) take turns!
        if status in ("pending", "plot_ready"):
            # Count how many completed works exist so far so every new completion naturally flips the next turn
            completed_so_far = sum(1 for t in synced_tasks if t["status"] in ("completed", "pending_illustration"))
            assigned_writer = "sff7020" if ((completed_so_far + uncompleted_queue_idx) % 2 == 1) else "rtx5060lp"
            uncompleted_queue_idx += 1
        else:
            assigned_writer = prev.get("assigned_writer") or prev.get("written_by") or "rtx5060lp"

        task_entry = {
            "id": wid,
            "work_num": idx,
            "title": work.get("title", ""),
            "author": work.get("author", ""),
            "theme": work.get("theme", ""),
            "modern_tech": work.get("modern_tech", ""),
            "status": status,
            "assigned_writer": assigned_writer,
            "plot_file": plot_rel,
            "plot_by": prev.get("plot_by") or ("sff7020" if plot_rel else None),
            "plot_at": prev.get("plot_at"),
            "md_file": md_rel,
            "written_by": prev.get("written_by") or (assigned_writer if md_rel else None),
            "written_at": prev.get("written_at") or inferred_date,
            "reviewed_by": prev.get("reviewed_by"),
            "reviewed_at": prev.get("reviewed_at"),
            "png_file": png_rel,
            "illustrated_by": prev.get("illustrated_by") or ("kenomac-mini" if png_rel else None),
            "illustrated_at": prev.get("illustrated_at") or (inferred_date if png_rel else None),
        }
        synced_tasks.append(task_entry)

    manifest = {
        "project_id": PROJECT_ID,
        "project_name": PROJECT_NAME,
        "project_title": PROJECT_TITLE,
        "updated_at": datetime.now(JST).isoformat(),
        "roles": roles_cfg,
        "tasks": synced_tasks,
    }

    TASKS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_tasks_markdown(manifest)
    return manifest


def write_tasks_markdown(manifest: Dict[str, Any]) -> None:
    tasks = manifest.get("tasks", [])
    completed = [t for t in tasks if t["status"] == "completed"]
    pending_ill = [t for t in tasks if t["status"] == "pending_illustration"]
    plot_ready = [t for t in tasks if t["status"] == "plot_ready"]
    pending = [t for t in tasks if t["status"] == "pending"]

    lines = [
        f"# 📋 分散ローカルLLM 自動作業リスト (`{PROJECT_NAME}`)",
        "",
        f"- **会話ID**: `{PROJECT_ID}`",
        f"- **最終同期日時 (JST)**: `{manifest.get('updated_at', '')[:19]}`",
        f"- **進捗サマリー**: 全 **{len(tasks)}** 作品 （完了: **{len(completed)}** / 挿絵待ち: **{len(pending_ill)}** / プロット作成済: **{len(plot_ready)}** / 未着手: **{len(pending)}**）",
        "- **交互執筆モード**: プライマリ **`rtx5060lp:11434`** (`shosetsu`) と セカンダリ **`sff7020:1234`** (`gemma-4-26b-a4b-qat`) が1作ずつ交互に小説執筆を担当します（相手がオフライン時はオンライン側がフェイルオーバー代行）。",
        "",
        "## 🖥️ 各ローカルLLM PCの役割分担とノルマ",
        "",
        "| PCホスト名 | 役割 (`role`) | エンドポイント / モデル | 1日あたり上限 | 担当作業内容 |",
        "|:---|:---|:---|:---:|:---|",
        "| **`rtx5060lp`** | `writer_primary` | `http://rtx5060lp:11434` (`shosetsu`) | 1 作品 | 【プライマリ執筆】交互担当（奇数枠）で正統派ハードSF小説・技術解説を執筆 (`content/*.md`) |",
        "| **`sff7020`** | `writer_secondary` | `http://sff7020:1234` (`gemma-4-26b-a4b-qat`) | 1 作品 | 【セカンダリ執筆＆プロット】交互担当（偶数枠）で煽り・ケレン味のあるSF小説を執筆＆プロット設計 |",
        "| **`kenomac-mini`** | `illustrator` | `http://kenomac-mini:7860` (`FLUX.2`) | 5 枚 | 【挿絵＆Web公開】FLUX.2 挿絵生成 (`content/*.png`) ＆ GitHub Pages (`docs/`) 更新 |",
        "",
        "### ⚡ メインPC (`MINISFORUM64GB`) 電源OFF時の各PC単独・自律実行セットアップ",
        "- **Windows (`rtx5060lp` / `sff7020`)**: リポジトリ内で `git pull` 後、`.\\setup_autonomous_worker.ps1` を1回実行すると、PC起動時＆毎日20:00/21:00にGitHubからタスクを読み取って自律実行・Pushします（普段既に `run_worker.ps1` を自動実行している場合は自動で最新化されます）。",
        "- **Mac (`kenomac-mini`)**: リポジトリ内で `git pull && bash setup_autonomous_worker.sh` を1回実行すると、macOS `LaunchAgent` に登録され、Mac起動時＆毎日20:15/21:15に未挿絵作品を検知して FLUX.2 挿絵生成＆GitHub Pages更新を自律実行します。",
        "",
        "## 🚀 次回PC起動時の自動実行タスクキュー（GitHub蓄積タスク一覧）",
        "",
        "| No. | 作品ID | 原典タイトル（著者） | 先端科学テーマ | 現在の状態 | 次回担当ライター（交互割当） |",
        "|:---:|:---|:---|:---|:---:|:---|",
    ]

    active_queue = pending_ill + plot_ready + pending
    if not active_queue:
        lines.append("| - | - | （全作品完了済み） | - | Completed | - |")
    else:
        for t in active_queue[:20]:
            st = t["status"]
            assigned = t.get("assigned_writer", "rtx5060lp")
            if st == "pending_illustration":
                next_pc = "🎨 `kenomac-mini:7860` (挿絵生成)"
            elif assigned == "sff7020":
                next_pc = "🔥 **セカンダリ `sff7020:1234`** (煽り系SF執筆)"
            else:
                next_pc = "✍️ **プライマリ `rtx5060lp:11434`** (`shosetsu` 執筆)"
            lines.append(
                f"| #{t.get('work_num', 0):02d} | `{t['id']}` | {t['title']}（{t.get('author', '')}） | {t.get('modern_tech', '')} | `{st}` | {next_pc} |"
            )

    lines.extend([
        "",
        "## ✅ 完了済み作品（最新10件）",
        "",
        "| No. | 作品ID | 原典タイトル（著者） | プロット (`sff7020`) | 執筆担当 (`written_by`) | 校閲 (`sff7020`) | 挿絵 (`kenomac-mini`) |",
        "|:---:|:---|:---|:---:|:---:|:---:|:---:|",
    ])
    for t in list(reversed(completed))[:10]:
        p_mark = f"✓ ({t.get('plot_by')})" if t.get("plot_file") else "-"
        w_by = t.get("written_by") or "rtx5060lp"
        w_mark = f"✓ `{w_by}` ({str(t.get('written_at') or '')[:10]})" if t.get("md_file") else "-"
        r_mark = f"✓ ({t.get('reviewed_by')})" if t.get("reviewed_by") else "校閲済"
        i_mark = f"🎨 ({t.get('illustrated_by')})" if t.get("png_file") else "-"
        lines.append(
            f"| #{t.get('work_num', 0):02d} | `{t['id']}` | {t['title']}（{t.get('author', '')}） | {p_mark} | {w_mark} | {r_mark} | {i_mark} |"
        )

    TASKS_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _try_generate_illustration_if_online(
    local_gen: LocalStoryGenerator,
    manifest: Dict[str, Any],
    task: Dict[str, Any],
    work: Dict[str, Any],
    out_path: Path,
    content: str,
    reboot_title: str,
) -> None:
    dt_cfg = manifest.get("roles", {}).get("kenomac-mini", {})
    dt_host = resolve_reachable_url(
        [
            os.getenv("DRAW_THINGS_HOST", ""),
            dt_cfg.get("host", "http://kenomac-mini:7860"),
            dt_cfg.get("fallback_host", "http://192.168.128.59:7860"),
        ],
        "/sdapi/v1/options",
    )
    if dt_host:
        try:
            local_gen.draw_things_host = dt_host
            img_path = out_path.with_suffix(".png")
            logger.info(f"[-> kenomac-mini] Draw Things ({dt_host}) がオンラインのため、続けて挿絵を生成します: {img_path.name}")
            saved_img, _ = local_gen.generate_illustration(
                work=work,
                output_image_path=img_path,
                story_body=content,
                reboot_title=reboot_title,
            )
            if saved_img:
                task["png_file"] = str(saved_img).replace("\\", "/")
                task["illustrated_by"] = "kenomac-mini"
                task["illustrated_at"] = datetime.now(JST).isoformat()
                task["status"] = "completed"
        except Exception as img_err:
            logger.warning(f"[-> kenomac-mini] 挿絵の即時生成をスキップしました: {img_err}")


def determine_next_writer_turn(manifest: Dict[str, Any]) -> str:
    """
    Determines whether 'rtx5060lp' (Primary) or 'sff7020' (Secondary :1234) should write next,
    strictly alternating based on who wrote the most recently completed/stocked story.
    """
    written_tasks = [
        t for t in manifest.get("tasks", [])
        if t.get("md_file") and t.get("written_by") in ("rtx5060lp", "sff7020")
    ]
    if not written_tasks:
        return "rtx5060lp"
    # Sort by written_at and work_num so the very latest story determines the next turn
    written_tasks.sort(key=lambda t: (str(t.get("written_at") or ""), int(t.get("work_num") or 0)))
    last_writer = written_tasks[-1].get("written_by", "rtx5060lp")
    return "sff7020" if last_writer == "rtx5060lp" else "rtx5060lp"


def run_director_role(
    manifest: Dict[str, Any],
    history_mgr: HistoryManager,
    quota_override: Optional[int] = None,
    push_to_git: bool = True,
) -> int:
    role_cfg = manifest["roles"]["sff7020"]
    quota = quota_override if quota_override is not None else int(role_cfg.get("daily_quota", 1))
    lm_host = resolve_reachable_url(
        [
            os.getenv("LM_STUDIO_HOST", ""),
            role_cfg.get("host", "http://sff7020:1234"),
            role_cfg.get("fallback_host", "http://192.168.128.16:1234"),
            "http://localhost:1234",
        ],
        "/v1/models",
    )
    if not lm_host:
        logger.info("[sff7020 / secondary] LM Studio サーバー (http://sff7020:1234) がオフラインのためスキップします。")
        return 0

    logger.info(f"[sff7020 / secondary] LM Studio ({lm_host}) に接続しました。")
    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    now_iso = datetime.now(JST).isoformat()
    actions_done = 0

    # 1. Review unreviewed stories
    unreviewed = [
        t for t in reversed(manifest["tasks"])
        if t.get("md_file") and not t.get("reviewed_by") and Path(t["md_file"]).exists()
    ]
    for task in unreviewed[:2]:
        md_path = Path(task["md_file"])
        raw_md = md_path.read_text(encoding="utf-8", errors="ignore")
        cleaned_md = LocalStoryGenerator()._normalize_japanese_typos(raw_md)
        if cleaned_md != raw_md:
            md_path.write_text(cleaned_md, encoding="utf-8")
            logger.info(f"[sff7020 / secondary] 原稿の表記揺れ・簡体字を自動補正しました: {md_path.name}")
        task["reviewed_by"] = "sff7020"
        task["reviewed_at"] = now_iso
        actions_done += 1

    # 2. Pre-generate plot blueprint for 1 upcoming task if none exists yet
    plots_today = sum(
        1 for t in manifest["tasks"]
        if str(t.get("plot_at") or "").startswith(today_str)
    )
    pending_tasks = [t for t in manifest["tasks"] if t["status"] == "pending"]
    catalog_map = {w["id"]: w for w in history_mgr.catalog}

    if plots_today < 1 and pending_tasks:
        task = pending_tasks[0]
        work = catalog_map.get(task["id"])
        if work:
            logger.info(f"[sff7020 / secondary] 先行SFプロット作成中: [{work['id']}] {work['title']}（{work.get('author')}）...")
            prompt = f"""あなたは青空文庫の名作を現代の先端科学で再構築する『Neo SF Aozora』の構成作家です。
次回執筆するための詳細な4シーン構成プロットを作成してください。

【原典作品情報】
- 作品ID: {work['id']}
- 原典タイトル: {work['title']}（著者: {work.get('author', '')}）
- 主題・モチーフ: {work.get('theme', '')}
- 融合させる先端科学技術: {work.get('modern_tech', '')}
- リブート構想: {work.get('summary', '')}

【出力フォーマット】
1. SFリブート副題案（『{work['title']}――〇〇』）
2. 主人公と重要人物の名前・役職・関係性
3. 第1シーン（発端と奇妙な違和感：原典モチーフと科学技術1の融合）
4. 第2シーン（対話・調査と深まる謎：科学技術2による検証と伏線）
5. 第3シーン（転換と真相の解明：科学技術3が明かす驚きの真実）
6. 第4シーン（結末と叙情的な余韻）
"""
            plot_text = call_lm_studio_chat(
                host=lm_host,
                messages=[
                    {"role": "system", "content": "あなたは青空文庫の古典名作を現代ハードSFへと昇華させる優秀なSF構成作家です。"},
                    {"role": "user", "content": prompt},
                ],
                preferred_model=role_cfg.get("model", "google/gemma-4-26b-a4b-qat"),
            )
            if plot_text and len(plot_text) >= 150:
                PLOTS_DIR.mkdir(parents=True, exist_ok=True)
                plot_file = PLOTS_DIR / f"{work['id']}.md"
                plot_file.write_text(plot_text, encoding="utf-8")
                task["plot_file"] = str(plot_file).replace("\\", "/")
                task["plot_by"] = "sff7020"
                task["plot_at"] = now_iso
                task["status"] = "plot_ready"
                actions_done += 1
                logger.info(f"[sff7020 / secondary] プロット保存完了: {plot_file}")

    if actions_done > 0:
        manifest["updated_at"] = datetime.now(JST).isoformat()
        TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_tasks_markdown(manifest)
        if push_to_git:
            git_commit_and_push(f"feat(sff7020): Update {actions_done} SF plot/review task(s) via sff7020 LM Studio")

    return actions_done


def run_writer_role(
    manifest: Dict[str, Any],
    history_mgr: HistoryManager,
    quota_override: Optional[int] = None,
    push_to_git: bool = True,
    preferred_node: Optional[str] = None,
) -> int:
    """
    Executes novel writing from the GitHub-queued tasks, alternating between:
      - Primary: `rtx5060lp` (`http://rtx5060lp:11434`, model `shosetsu`)
      - Secondary: `sff7020` (`http://sff7020:1234`, model `google/gemma-4-26b-a4b-qat`)
    If the designated turn's server is offline when the PC boots, automatically fails over
    to whichever server is online so daily progress never stalls.
    """
    rtx_cfg = manifest["roles"].get("rtx5060lp", DEFAULT_ROLES_CONFIG["rtx5060lp"])
    sff_cfg = manifest["roles"].get("sff7020", DEFAULT_ROLES_CONFIG["sff7020"])

    rtx_candidates = [
        os.getenv("OLLAMA_HOST", ""),
        rtx_cfg.get("host", "http://rtx5060lp:11434"),
        rtx_cfg.get("fallback_host", "http://192.168.128.62:11434"),
    ]
    if preferred_node == "rtx5060lp" or "rtx5060lp" in socket.gethostname().lower():
        rtx_candidates.insert(0, "http://localhost:11434")
    rtx_host = resolve_reachable_url(rtx_candidates, "/api/tags")

    sff_candidates = [
        os.getenv("LM_STUDIO_HOST", ""),
        sff_cfg.get("host", "http://sff7020:1234"),
        sff_cfg.get("fallback_host", "http://192.168.128.16:1234"),
    ]
    if preferred_node == "sff7020" or "sff7020" in socket.gethostname().lower():
        sff_candidates.insert(0, "http://localhost:1234")
    sff_host = resolve_reachable_url(sff_candidates, "/v1/models")

    if not rtx_host and not sff_host:
        logger.info("[writer] Primary (rtx5060lp:11434) も Secondary (sff7020:1234) もオフラインのため執筆をスキップします。")
        return 0

    today_str = datetime.now(JST).strftime("%Y-%m-%d")
    total_daily_quota = quota_override if quota_override is not None else 1
    written_today = sum(
        1 for t in manifest["tasks"]
        if str(t.get("written_at") or "").startswith(today_str)
    )
    needed = max(0, total_daily_quota - written_today)
    if needed == 0:
        logger.info(f"[writer] 本日の執筆ノルマ ({written_today}/{total_daily_quota} 作品) は達成済みです。")
        return 0

    candidates = [t for t in manifest["tasks"] if t["status"] == "plot_ready"] + [
        t for t in manifest["tasks"] if t["status"] == "pending"
    ]
    catalog_map = {w["id"]: dict(w) for w in history_mgr.catalog}
    written_count = 0

    for task in candidates[:needed]:
        work = catalog_map.get(task["id"])
        if not work:
            continue

        # Determine which writer is up next (strict alternation based on history or task assignment)
        turn_node = preferred_node or task.get("assigned_writer") or determine_next_writer_turn(manifest)
        if turn_node == "sff7020":
            if sff_host:
                active_node = "sff7020"
                active_host = sff_host
                active_model = sff_cfg.get("model", "google/gemma-4-26b-a4b-qat")
                logger.info(f"[Alternating Writer] 今回はセカンダリ『sff7020 ({active_host})』の順番です！煽り・ケレン味のあるSF小説を執筆します。")
            else:
                active_node = "rtx5060lp"
                active_host = rtx_host
                active_model = rtx_cfg.get("model", "shosetsu")
                logger.info(f"[Alternating Writer] セカンダリ sff7020:1234 がオフラインのため、プライマリ『rtx5060lp ({active_host})』が代行執筆します。")
        else:
            if rtx_host:
                active_node = "rtx5060lp"
                active_host = rtx_host
                active_model = rtx_cfg.get("model", "shosetsu")
                logger.info(f"[Alternating Writer] 今回はプライマリ『rtx5060lp ({active_host})』の順番です！({active_model})")
            else:
                active_node = "sff7020"
                active_host = sff_host
                active_model = sff_cfg.get("model", "google/gemma-4-26b-a4b-qat")
                logger.info(f"[Alternating Writer] プライマリ rtx5060lp:11434 がオフラインのため、セカンダリ『sff7020 ({active_host})』が代行執筆します。")

        local_gen = LocalStoryGenerator(
            ollama_host=active_host,
            model_name=active_model,
        )

        if task.get("plot_file") and Path(task["plot_file"]).exists():
            work["_director_plot_blueprint"] = Path(task["plot_file"]).read_text(encoding="utf-8", errors="ignore")
            logger.info(f"[{active_node} / writer] 先行プロット ({task['plot_file']}) を読み込んで執筆します。")

        logger.info(f"[{active_node} / writer] SF小説執筆開始 ({written_count + 1}/{needed}): [{work['id']}] {work['title']}（{work.get('author')}）")
        try:
            content, reboot_title, _ = local_gen.generate_story(work=work, ending_theme="random")
            safe_id = work["id"].replace("-", "_")
            out_path = Path(f"content/{today_str}_{safe_id}.md")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")

            task["md_file"] = str(out_path).replace("\\", "/")
            task["written_by"] = active_node
            task["written_at"] = datetime.now(JST).isoformat()
            task["status"] = "pending_illustration"
            written_count += 1

            # If kenomac-mini Draw Things is online on the LAN right now, generate the illustration immediately
            _try_generate_illustration_if_online(
                local_gen=local_gen,
                manifest=manifest,
                task=task,
                work=work,
                out_path=out_path,
                content=content,
                reboot_title=reboot_title,
            )

            # Re-sync manifest so remaining queued tasks flip their alternating assignment cleanly
            manifest = sync_tasks_manifest(history_mgr)
            try:
                update_archive_all()
            except Exception:
                pass
            build_github_pages(history_mgr)
            if push_to_git:
                git_commit_and_push(f"feat({active_node}): Write SF reboot '{work['id']}' via {active_node} & update task queue")
        except Exception as e:
            logger.error(f"[{active_node} / writer] '{work['id']}' の執筆に失敗しました: {e}")

    return written_count


def run_illustrator_role(
    manifest: Dict[str, Any],
    history_mgr: HistoryManager,
    quota_override: Optional[int] = None,
    push_to_git: bool = True,
) -> int:
    role_cfg = manifest["roles"]["kenomac-mini"]
    quota = quota_override if quota_override is not None else int(role_cfg.get("daily_quota", 5))
    dt_host = resolve_reachable_url(
        [
            os.getenv("DRAW_THINGS_HOST", ""),
            role_cfg.get("host", "http://kenomac-mini:7860"),
            role_cfg.get("fallback_host", "http://192.168.128.59:7860"),
            "http://localhost:7860",
        ],
        "/sdapi/v1/options",
    )
    if not dt_host:
        logger.info("[kenomac-mini / illustrator] Draw Things サーバー (kenomac-mini:7860) がオフラインのためスキップします。")
        return 0

    ollama_host = resolve_reachable_url(
        [
            role_cfg.get("ollama_host", "http://kenomac-mini:11434"),
            role_cfg.get("fallback_ollama_host", "http://192.168.128.59:11434"),
            "http://localhost:11434",
            os.getenv("OLLAMA_HOST", "http://rtx5060lp:11434"),
        ],
        "/api/tags",
    ) or "http://kenomac-mini:11434"

    local_gen = LocalStoryGenerator(
        ollama_host=ollama_host,
        draw_things_host=dt_host,
    )

    pending_ill = [
        t for t in manifest["tasks"]
        if t.get("md_file") and Path(t["md_file"]).exists() and not Path(t["md_file"]).with_suffix(".png").exists()
    ]
    if not pending_ill:
        logger.info("[kenomac-mini / illustrator] 未挿絵のSF作品はありません。GitHub Pages を最新状態に同期します。")
        build_github_pages(history_mgr)
        return 0

    catalog_map = {w["id"]: w for w in history_mgr.catalog}
    illustrated_count = 0

    for task in pending_ill[:quota]:
        work = catalog_map.get(task["id"])
        if not work:
            continue
        md_path = Path(task["md_file"])
        img_path = md_path.with_suffix(".png")
        md_text = md_path.read_text(encoding="utf-8", errors="ignore")
        reboot_title = work.get("title", "")
        for line in md_text.splitlines():
            if line.strip().startswith("title:"):
                reboot_title = line.split(":", 1)[1].strip().strip("\"'")
                break
        logger.info(f"[kenomac-mini / illustrator] FLUX.2 挿絵生成中 ({illustrated_count + 1}/{min(quota, len(pending_ill))}): {img_path.name}")
        saved_img, _ = local_gen.generate_illustration(
            work=work,
            output_image_path=img_path,
            story_body=md_text,
            reboot_title=reboot_title,
        )
        if saved_img:
            task["png_file"] = str(saved_img).replace("\\", "/")
            task["illustrated_by"] = "kenomac-mini"
            task["illustrated_at"] = datetime.now(JST).isoformat()
            task["status"] = "completed"
            illustrated_count += 1

            manifest["updated_at"] = datetime.now(JST).isoformat()
            TASKS_JSON_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            write_tasks_markdown(manifest)
            try:
                update_archive_all()
            except Exception:
                pass
            build_github_pages(history_mgr)
            if push_to_git:
                git_commit_and_push(f"feat(kenomac-mini): Add FLUX.2 illustration for '{work['id']}' & rebuild GitHub Pages")

    return illustrated_count


def detect_local_role() -> str:
    hostname = socket.gethostname().lower()
    if "rtx5060lp" in hostname:
        return "rtx5060lp"
    if "kenomac-mini" in hostname or "mac-mini" in hostname:
        return "kenomac-mini"
    if "sff7020" in hostname:
        return "sff7020"
    return "lan-dispatch"


def main():
    parser = argparse.ArgumentParser(
        description="GitHub-Synced Distributed Local LLM Task Worker for neo-sf-aozora"
    )
    parser.add_argument(
        "--role",
        choices=["auto", "lan-dispatch", "writer", "rtx5060lp", "illustrator", "kenomac-mini", "director", "sff7020", "sync"],
        default="auto",
        help="Worker role to run (default: auto-detect by hostname or dispatch to online LAN servers)",
    )
    parser.add_argument("--quota", type=int, default=None, help="Override daily task quota for this run")
    parser.add_argument("--no-push", action="store_true", help="Do not git commit/push changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    setup_logging(args.verbose)
    push_to_git = not args.no_push

    if push_to_git:
        git_pull_latest()

    history_mgr = HistoryManager()
    manifest = sync_tasks_manifest(history_mgr)

    role = args.role
    if role == "auto":
        role = detect_local_role()
        logger.info(f"ホスト名 '{socket.gethostname()}' から自動判定された自律実行モード: {role}")

    if role == "sync":
        if push_to_git:
            git_commit_and_push("chore(tasks): Sync distributed task queue manifest (data/tasks.json & data/TASKS.md)")
        return

    if role == "director":
        run_director_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
    elif role == "sff7020":
        # Autonomous sff7020 mode: 1) review & pre-plot, 2) write if it's sff7020's turn (or failover), 3) illustrate if kenomac-mini is reachable
        run_director_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
        manifest = sync_tasks_manifest(history_mgr)
        run_writer_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git, preferred_node="sff7020")
    elif role in ("writer", "rtx5060lp"):
        # Autonomous rtx5060lp mode: write if it's rtx5060lp's turn (or failover), and illustrate if kenomac-mini is reachable
        pref = "rtx5060lp" if role == "rtx5060lp" else None
        run_writer_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git, preferred_node=pref)
    elif role in ("illustrator", "kenomac-mini"):
        # Autonomous kenomac-mini mode: generate any pending illustrations & rebuild GitHub Pages
        run_illustrator_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
    elif role == "lan-dispatch":
        logger.info("=== GitHubのタスクキューから次回の担当タスクを読み取り、プライマリ(rtx5060lp:11434)とセカンダリ(sff7020:1234)で交互に実行します ===")
        run_director_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
        manifest = sync_tasks_manifest(history_mgr)
        run_writer_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)
        manifest = sync_tasks_manifest(history_mgr)
        run_illustrator_role(manifest, history_mgr, quota_override=args.quota, push_to_git=push_to_git)


if __name__ == "__main__":
    main()
