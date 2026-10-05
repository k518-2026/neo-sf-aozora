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
            img_mark = "🎨[挿絵あり]" if sf.with_suffix(".png").exists() else "  [挿絵なし]"
            print(f"  [{idx:02d}] {img_mark} {w['title']}（{w['author']}） -> {sf}")
    else:
        print("\n[!] 現在、未配信の書き溜めストックは 0 本です。")

    if unstocked_list:
        print("\n[NEXT] 【未生成・次回のローカルLLM執筆対象（先頭5件）】")
        for idx, w in unstocked_list[:5]:
            print(f"  [{idx:02d}] {w['id']} : {w['title']}（{w['author']}）")
    print("=" * 72 + "\n")


def git_sync_and_push(generated_files: List[Path]) -> bool:
    """
    Pulls latest history from GitHub, stages newly generated content/, archive/, and docs/ (GitHub Pages) files,
    commits, and pushes to origin/main so GitHub Pages updates automatically.
    """
    if not generated_files:
        return True

    try:
        logger.info("Syncing with remote GitHub repository (git pull --rebase origin main)...")
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)

        cmd_add = ["git", "add", "content/", "archive/", "docs/"]
        subprocess.run(cmd_add, check=True)

        # Check if there are staged changes
        diff_res = subprocess.run(["git", "diff", "--staged", "--quiet"])
        if diff_res.returncode == 0:
            logger.info("No new changes in content/, archive/, or docs/ to commit.")
            return True

        msg = f"feat(pages): Add {len(generated_files)} SF story/illustration asset(s) via Mac mini M4 & update GitHub Pages"
        subprocess.run(["git", "commit", "-m", msg], check=True)
        logger.info(f"Committed {len(generated_files)} stocked asset(s) and docs/. Pushing to origin/main...")
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)
        logger.info("Successfully pushed stocked stories, illustrations & GitHub Pages to GitHub!")
        return True
    except Exception as e:
        logger.error(f"Git push failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Local LLM Batch Story & Illustration Stock Generator (Crossref + Ollama + Draw Things FLUX.2)"
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=6,
        help="Number of unstocked works to generate in this batch (default: 6)"
    )
    parser.add_argument(
        "--work-id",
        default=None,
        help="Generate a specific work ID from catalog"
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Ollama server URL (default: http://192.168.128.59:11434 on Mac mini M4)"
    )
    parser.add_argument(
        "--draw-things-host",
        default=None,
        help="Draw Things HTTP API URL (default: http://192.168.128.59:7860 on Mac mini M4)"
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        help="Ollama model name (e.g., qwen2.5:14b, gemma4:12b, qwen3.5:9b)"
    )
    parser.add_argument(
        "--ending",
        choices=["random", "bright", "dystopia", "romance", "mystery"],
        default="random",
        help="Ending theme (default: random 3:2:3:2 weighted)"
    )
    parser.add_argument(
        "--generate-images",
        action="store_true",
        help="Generate missing .png illustrations for existing stocked stories in content/ via Draw Things FLUX.2"
    )
    parser.add_argument(
        "--build-pages",
        action="store_true",
        help="Rebuild GitHub Pages static site (docs/) from existing content/ without generating new stories"
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Automatically git commit & push generated stock files and docs/ to GitHub after generation"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show current stock & publication status without generating"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite even if a stock file or illustration already exists"
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

    if args.build_pages:
        from src.site_builder import build_github_pages
        build_github_pages(history_mgr)
        if args.push:
            git_sync_and_push([Path("docs/index.html")])
        return

    local_gen = LocalStoryGenerator(
        ollama_host=args.host,
        model_name=args.model,
        draw_things_host=args.draw_things_host,
    )
    if not local_gen.is_ollama_running():
        logger.error(
            f"Ollama server on Mac mini M4 is not reachable at {local_gen.ollama_host}. "
            "Please make sure Ollama is running on Mac mini M4 (`OLLAMA_HOST=0.0.0.0:11434 ollama serve`)."
        )
        sys.exit(1)

    installed_models = local_gen.get_installed_models()
    if not installed_models:
        logger.error(
            f"No models are installed in Ollama at {local_gen.ollama_host} yet."
        )
        sys.exit(1)

    resolved_model = local_gen.resolve_model_name()
    logger.info(
        f"Using Mac mini M4 Ollama ({local_gen.ollama_host}) | "
        f"Model: '{resolved_model}' (Available: {', '.join(installed_models)})"
    )

    # Generate missing illustrations for existing stocked stories
    if args.generate_images:
        dt_conn = local_gen.check_draw_things_connection()
        if not dt_conn.get("online"):
            logger.error(
                f"Cannot reach Draw Things HTTP API at {local_gen.draw_things_host}: {dt_conn.get('error')}. "
                "Please enable HTTP Server (port 7860) in Draw Things on Mac mini M4."
            )
            sys.exit(1)

        posted_ids = history_mgr.get_posted_ids()
        generated_imgs: List[Path] = []
        for w in history_mgr.catalog:
            if args.work_id and w["id"] != args.work_id:
                continue
            if w["id"] in posted_ids and not args.force and not args.work_id:
                continue
            sf = history_mgr.find_stock_file_for_work(w["id"])
            if sf is None:
                continue
            img_path = sf.with_suffix(".png")
            if img_path.exists() and not args.force:
                logger.info(f"Illustration already exists for {w['id']}: {img_path}")
                continue
            md_text = sf.read_text(encoding="utf-8", errors="ignore")
            saved_img, _ = local_gen.generate_illustration(
                work=w,
                output_image_path=img_path,
                story_body=md_text,
                reboot_title=w["title"],
            )
            if saved_img:
                generated_imgs.append(saved_img)

        if generated_imgs:
            try:
                from src.site_builder import build_github_pages
                build_github_pages(history_mgr)
            except Exception as e:
                logger.warning(f"GitHub Pages build warning: {e}")
        if args.push and generated_imgs:
            git_sync_and_push(generated_imgs)
        print_stock_status(history_mgr)
        return

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

            img_out_path = out_path.with_suffix(".png")
            saved_img, _ = local_gen.generate_illustration(
                work=work,
                output_image_path=img_out_path,
                story_body=content,
                reboot_title=reboot_title,
            )
            if saved_img:
                generated_files.append(saved_img)
        except Exception as e:
            logger.error(f"Failed to generate story for '{work['title']}' ({work['id']}): {e}", exc_info=True)

    if generated_files:
        try:
            from src.archiver import update_archive_all
            update_archive_all()
        except Exception as e:
            logger.warning(f"Archive update warning: {e}")

        try:
            from src.site_builder import build_github_pages
            build_github_pages(history_mgr)
        except Exception as e:
            logger.warning(f"GitHub Pages build warning: {e}")

        if args.push:
            git_sync_and_push(generated_files)

    print_stock_status(history_mgr)


if __name__ == "__main__":
    main()
