import argparse
import logging
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from src.history_manager import HistoryManager
from src.local_story_generator import LocalStoryGenerator

JST = timezone(timedelta(hours=9))
logger = logging.getLogger("batch-stock")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def print_stock_status(history_mgr: HistoryManager):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    posted_ids = history_mgr.get_posted_ids()
    posted_count = 0
    stocked_list = []
    unstocked_list = []

    for idx, w in enumerate(history_mgr.catalog, start=1):
        wid = w["id"]
        stock_file = history_mgr.find_stock_file_for_work(wid)
        if wid in posted_ids:
            posted_count += 1
        elif stock_file is not None:
            stocked_list.append((idx, w, stock_file))
        else:
            unstocked_list.append((idx, w))

    print("\n" + "=" * 72)
    print(" 【青空文庫SFリブート ストック＆配信状況レポート】")
    print("=" * 72)
    print(f"  ・カタログ総作品数       : {len(history_mgr.catalog)} 作品")
    print(f"  ・WordPress配信済み      : {posted_count} 作品")
    print(f"  ・書き溜め済み（配信待ち）: {len(stocked_list)} 作品 (約 {len(stocked_list) / 3:.1f} 日分)")
    print(f"  ・未生成（今後の執筆対象）: {len(unstocked_list)} 作品")
    print("-" * 72)

    if stocked_list:
        print("\n[OK] 【書き溜め済み・GitHub Actions 定期配信待ちリスト】")
        for idx, w, sf in stocked_list:
            print(f"  [{idx:02d}] {w['title']}（{w['author']}） -> {sf}")
    else:
        print("\n[!] 現在、未配信の書き溜めストックは 0 本です。")

    if unstocked_list:
        print("\n[NEXT] 【未生成・次回のローカルLLM執筆対象（先頭5件）】")
        for idx, w in unstocked_list[:5]:
            print(f"  [{idx:02d}] {w['id']} : {w['title']}（{w['author']}）")
    print("=" * 72 + "\n")


def git_sync_and_push(generated_files: List[Path]) -> bool:
    """
    Pulls latest history from GitHub, stages newly generated content/ and archive/ files,
    commits, and pushes to origin/main so GitHub Actions cron can publish them.
    """
    if not generated_files:
        return True

    try:
        logger.info("Syncing with remote GitHub repository (git pull --rebase origin main)...")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)

        cmd_add = ["git", "add", "content/", "archive/"]
        subprocess.run(cmd_add, check=True)

        # Check if there are staged changes
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff_res.returncode == 0:
            logger.info("No new changes in content/ or archive/ to commit.")
            return True

        msg = f"feat(stock): Add {len(generated_files)} pre-generated SF stories via Local LLM [skip ci]"
        subprocess.run(["git", "commit", "-m", msg], check=True)
        logger.info(f"Committed {len(generated_files)} stocked stories. Pushing to origin/main...")
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        logger.info("Successfully pushed stocked stories to GitHub!")
        return True
    except Exception as e:
        logger.error(f"Git push failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Local LLM Batch Story Stock Generator (Zero-Hallucination Crossref + Ollama)"
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=3,
        help="Number of unstocked works to generate in this batch (default: 3 = 1 day of posts)"
    )
    parser.add_argument(
        "--work-id",
        default=None,
        help="Generate a specific work ID from catalog"
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="Ollama model name (e.g., qwen2.5:14b, gemma3:27b)"
    )
    parser.add_argument(
        "--ending",
        choices=["random", "bright", "dystopia", "romance", "mystery"],
        default="random",
        help="Ending theme (default: random 3:2:3:2 weighted)"
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Automatically git commit & push generated stock files to GitHub after generation"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current stock & publication status without generating"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite even if a stock file already exists for the specified --work-id"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    # Pull latest history from GitHub first if pushing is enabled so we don't generate an already-posted work
    if args.push:
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)

    history_mgr = HistoryManager()

    if args.status:
        print_stock_status(history_mgr)
        return

    local_gen = LocalStoryGenerator(model_name=args.model)
    if not local_gen.is_ollama_running():
        logger.error(
            "Ollama server is not reachable at http://localhost:11434. "
            "Please make sure Ollama is running (`ollama serve`)."
        )
        sys.exit(1)

    installed_models = local_gen.get_installed_models()
    if not installed_models:
        logger.error(
            "No models are installed in Ollama yet. "
            "Run e.g. `ollama pull qwen2.5:14b` first."
        )
        sys.exit(1)

    resolved_model = local_gen.resolve_model_name()
    logger.info(f"Using Local LLM model: '{resolved_model}' (Available: {', '.join(installed_models)})")

    if args.work_id:
        target_work = next((w for w in history_mgr.catalog if w["id"] == args.work_id), None)
        if not target_work:
            logger.error(f"Work ID '{args.work_id}' not found in data/aozora_catalog.json")
            sys.exit(1)
        existing = history_mgr.find_stock_file_for_work(args.work_id)
        if existing and not args.force:
            logger.info(f"Work '{args.work_id}' already has a stock file at {existing}. Use --force to overwrite.")
            return
        targets = [target_work]
    else:
        targets = history_mgr.select_unstocked_works(count=args.count)

    if not targets:
        logger.info("All catalog works are already published or stocked in content/!")
        print_stock_status(history_mgr)
        return

    logger.info(f"Selected {len(targets)} work(s) for local batch generation: {[w['title'] for w in targets]}")
    generated_files: List[Path] = []

    for idx, work in enumerate(targets, start=1):
        logger.info(f"\n--- [{idx}/{len(targets)}] Generating '{work['title']}' ({work['author']}) ---")
        try:
            content, reboot_title, refs = local_gen.generate_story(
                work=work,
                ending_theme=args.ending,
            )
            today_str = datetime.now(JST).strftime("%Y-%m-%d")
            safe_id = work["id"].replace("-", "_")
            out_path = Path(f"content/{today_str}_{safe_id}.md")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(content, encoding="utf-8")
            generated_files.append(out_path)
            logger.info(f"Saved stocked story [{idx}/{len(targets)}]: {out_path} ('{reboot_title}')")
        except Exception as e:
            logger.error(f"Failed to generate story for '{work['title']}' ({work['id']}): {e}", exc_info=True)

    if generated_files:
        try:
            from src.archiver import update_archive_all
            update_archive_all()
        except Exception as e:
            logger.warning(f"Archive update warning: {e}")

        if args.push:
            git_sync_and_push(generated_files)

    print_stock_status(history_mgr)


if __name__ == "__main__":
    main()
