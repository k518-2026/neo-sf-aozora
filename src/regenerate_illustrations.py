"""
Batch Illustration Regenerator for Works #1 to #10
Targets Draw Things on Mac mini M4 (http://192.168.128.59:7860) with FLUX.2 Klein Base 9B.

Quality criteria requested by user:
1. "全体的にバックが暗すぎるので、もう少しだけ明るくするか、コントラストを出してください。"
   -> Illuminated environment, radiant ambient light, high contrast, vivid lighting, crisp highlights, no pitch-black gloom.
2. "人間の顔の目が変ですので、目を大切に描いてください。"
   -> Expressive beautifully drawn eyes, clear iris reflections, sharp pupils, delicate catchlights, symmetrical refined anime facial features, dignified calm expression.
"""

import argparse
import base64
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Dict, Any, List

DRAW_THINGS_URL = "http://192.168.128.59:7860"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("illust-regenerator")

NEGATIVE_PROMPT = (
    "pitch black background, murky dark room, underexposed, muddy shadows, low contrast, washed out, "
    "deformed eyes, asymmetrical eyes, weird eyes, crossed eyes, misaligned pupils, poorly drawn eyes, "
    "disfigured face, bad facial anatomy, mutated features, blurry face, creepy face, grotesque expression, "
    "text, letters, words, kanji, chinese characters, japanese text, english text, typography, title, "
    "watermark, signature, logo, caption, book cover"
)

WORKS_SPEC: List[Dict[str, Any]] = [
    {
        "index": 1,
        "work_id": "unno-18-music",
        "title": "十八時の音楽浴",
        "author": "海野十三",
        "content_paths": [Path("content/story.png"), Path("content/2026-09-24_unno_18_music.png")],
        "docs_path": Path("docs/assets/images/unno-18-music.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Hasumi, an elite acoustic neurophysiologist in an illuminated high-tech observatory laboratory overlooking a vibrant twilight city. "
            "Masterpiece close-up half-body portrait: focus on his intelligent, dignified face with beautifully detailed expressive eyes, clear luminous pupils, delicate iris reflections with crisp light catchlights, sharp symmetrical anime facial features. "
            "In front of him float radiant holographic spectrograms projecting glowing acoustic waveforms in luminous emerald, cyan, and amber. "
            "The observatory room is brightly lit with sleek architectural ambient lighting, expansive floor-to-ceiling panoramic windows revealing a breathtaking sunset cityscape with vivid orange, violet, and deep blue sky gradients, strong clean contrast, crisp sharp lines, no dark gloom, pure art without text."
        ),
    },
    {
        "index": 2,
        "work_id": "unno-fly-man",
        "title": "蠅男",
        "author": "海野十三",
        "content_paths": [Path("content/2026-09-24_unno_fly_man.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/unno-fly-man.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a futuristic bio-hybrid cyborg fly hovering above an advanced optical data pedestal in a clean, illuminated research cleanroom. "
            "The bio-cybernetic insect features intricate golden microneural circuits across its carapace, with large multifaceted jewel-like compound eyes sparkling with vivid turquoise, emerald, and prism reflections. "
            "The high-tech laboratory is well-lit with radiant ceiling panels, glowing translucent fiber-optic cables in luminous cyan and amber, bright reflective glass partitions creating crisp depth and clear dynamic contrast, rich vibrant colors, immaculate details, no pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 3,
        "work_id": "unno-cyborg-incident",
        "title": "人造人間事件",
        "author": "海野十三",
        "content_paths": [Path("content/2026-09-24_unno_cyborg_incident.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/unno-cyborg-incident.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a brilliant female cybernetics researcher standing next to an awakening elegant bio-organoid android inside an illuminated medical technology chamber. "
            "Both characters have exquisitely rendered, captivating eyes with crystal-clear pupils, intricate iris catchlights, and gentle dignified expressions, perfect symmetrical anime facial anatomy. "
            "The android rests in a brightly illuminated vertical glass bio-capsule infused with glowing pale-cyan nutrient fluids and shimmering bio-photonic neural circuits. "
            "The laboratory is bright and spacious with modern architectural lighting, clear white and azure illumination, high dynamic contrast, crisp details, no murky shadows, pure illustration without text."
        ),
    },
    {
        "index": 4,
        "work_id": "unno-vibration-demon",
        "title": "振動魔",
        "author": "海野十三",
        "content_paths": [Path("content/2026-09-25_unno_vibration_demon.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/unno-vibration-demon.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a young acoustic physicist manipulating an acoustic metamaterial levitation device in a bright modern physics laboratory. "
            "The scientist has an intense, focused gaze with beautifully detailed anime eyes, clear amber irises with radiant light highlights, clean eyelashes and pupils, refined facial structure. "
            "Between his hands, geometric crystalline metamaterial plates resonate with visible concentric waves of golden and sapphire sound pressure, causing delicate objects to float weightlessly. "
            "The research facility is well-lit with bright overhead LED lightbars, polished reflective workbenches, clean background architectural depth, vibrant colorful contrast, no pitch-black room, pure artwork without text."
        ),
    },
    {
        "index": 5,
        "work_id": "ran-plant-man",
        "title": "植物人間",
        "author": "蘭郁二郎",
        "content_paths": [Path("content/2026-09-25_ran_plant_man.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/ran-plant-man.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a bio-engineered young man possessing photosynthetic plant symbiosis, standing inside a magnificent sun-drenched botanical greenhouse atrium. "
            "Close portrait with serene, dignified expression: captivating bright emerald-green eyes with intricate botanical iris patterns, brilliant natural specular catchlights, delicately detailed facial features. "
            "Subtle bioluminescent leaf-vein patterns glow softly along his neck and hands, absorbing bright streaming sunlight cascading through crystal glass ceiling domes. "
            "The surrounding conservatory is vibrant and luminous with lush exotic plants, blooming crystalline flowers, warm golden daylight rays and vivid green tones, high radiant contrast, no murky darkness, pure art without text."
        ),
    },
    {
        "index": 6,
        "work_id": "ran-dream-demon",
        "title": "夢鬼",
        "author": "蘭郁二郎",
        "content_paths": [Path("content/2026-09-25_ran_dream_demon.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/ran-dream-demon.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a female cognitive neuroscientist operating a latent visual dream-decoding neural interface in a brightly lit neuroimaging laboratory. "
            "Striking close-up portrait: deep sapphire-blue eyes rendered with remarkable beauty, distinct pupils, sparkling multi-tone iris reflections, confident and curious gaze, flawless anime face symmetry. "
            "Above her console float luminous prismatic dream holograms displaying swirling surreal landscapes of clouds, stars, and fractal neuro-connections in radiant magenta and azure. "
            "The laboratory environment is brightly illuminated with soft ambient glow, polished silver fixtures, crisp clean highlights and vibrant chromatic contrast, no pitch-black shadows, pure art without text."
        ),
    },
    {
        "index": 7,
        "work_id": "ran-brain-surgery",
        "title": "脳髄手術",
        "author": "蘭郁二郎",
        "content_paths": [Path("content/2026-09-26_ran_brain_surgery.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/ran-brain-surgery.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a skilled female neurosurgeon in pristine medical attire overlooking an optogenetic neural modulation apparatus in a state-of-the-art surgical suite. "
            "Her face is in sharp focus, showing resolute, compassionate eyes with clear violet irises, finely rendered pupils with bright specular catchlights, perfectly balanced anime facial anatomy. "
            "In front of her, an illuminated 3D holographic human brain connectome glows with thousands of intricate gold and cyan optic fibers, casting radiant warm light across the room. "
            "The operating theatre is brightly illuminated with clean white and soft cyan architectural lighting, spotless glass monitors, high dynamic contrast, airy and pristine environment, no gloomy darkness, pure illustration without text."
        ),
    },
    {
        "index": 8,
        "work_id": "yumeno-human-record",
        "title": "人間レコード",
        "author": "夢野久作",
        "content_paths": [Path("content/2026-09-27_yumeno_human_record.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/yumeno-human-record.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a young female digital archivist inspecting molecular DNA data-storage crystals in a monumental, illuminated library of human civilization. "
            "Her expression is thoughtful and gentle, with captivating large hazel-amber eyes featuring intricate iris details, vivid pupils, and glowing reflections of memory crystals, beautiful refined facial features. "
            "She holds a glowing hexagonal glass prism containing spiral DNA strands radiating warm golden light. "
            "The background features soaring illuminated glass archive towers bathed in warm amber and cool white ambient illumination, clean geometric reflections, luminous airy atmosphere, strong crisp contrast, no pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 9,
        "work_id": "yumeno-bomb-peace",
        "title": "爆弾太平記",
        "author": "夢野久作",
        "content_paths": [Path("content/2026-09-27_yumeno_bomb_peace.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/yumeno-bomb-peace.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a young quantum physicist standing before an antimatter magnetic trap and laser-cooling reactor chamber in an illuminated particle physics institute. "
            "His face is rendered with striking anime clarity: confident, piercing azure eyes with sharp pupils, clean catchlights, serene resolute gaze, perfectly sculpted anime features. "
            "At the center of the ring-shaped collider floats a radiant miniature sphere of pure stabilized plasma, crisscrossed by focused ruby and sapphire laser beams. "
            "The research facility is brightly lit with sleek ceiling lightbars, polished titanium flooring, crisp colorful highlights, vibrant dynamic lighting contrast between glowing particle beams and the illuminated room, no muddy darkness, pure art without text."
        ),
    },
    {
        "index": 10,
        "work_id": "oguri-complete-crime",
        "title": "完全犯罪",
        "author": "小栗虫太郎",
        "content_paths": [Path("content/2026-09-28_oguri_complete_crime.md").with_suffix(".png")],
        "docs_path": Path("docs/assets/images/oguri-complete-crime.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of a keen detective-scientist in a Taisho-modern retro-futuristic forensic laboratory analyzing microscopic evidence with femtosecond photoacoustic lasers. "
            "His face is in clear focus with a sharp, perceptive gaze: striking slate-gray and gold eyes with meticulous iris detailing, clear pupils and bright specular highlights, sophisticated handsome features. "
            "On his laboratory table, delicate brass and quartz optical instruments disperse ultraviolet laser pulses, revealing luminous floating molecular crime scene reconstructions. "
            "The room is well-lit with warm glowing gas-filament lamps blended with electric cyan instrumentation, rich wood-and-chrome textures, high luminous contrast, beautiful vibrant depth, no pitch-black darkness, pure art without text."
        ),
    },
]


def generate_single_illustration(spec: Dict[str, Any], url: str = DRAW_THINGS_URL) -> bool:
    idx = spec["index"]
    title = spec["title"]
    work_id = spec["work_id"]
    prompt = spec["prompt"]

    logger.info(f"[{idx}/10] Generating improved illustration for #{idx} {title} ({work_id})...")
    payload = {
        "prompt": prompt,
        "negative_prompt": NEGATIVE_PROMPT,
        "width": 512,
        "height": 512,
        "steps": 16,
        "guidance_scale": 4.0,
        "sampler": "Euler A Trailing",
    }

    req = urllib.request.Request(
        f"{url}/sdapi/v1/txt2img",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as res:
            if res.getcode() != 200:
                logger.error(f"HTTP error {res.getcode()} from Draw Things")
                return False
            data = json.loads(res.read().decode("utf-8"))
            images = data.get("images", [])
            if not images or not images[0]:
                logger.error("No image data returned from Draw Things")
                return False

            b64_str = re.sub(r"^data:image/[^;]+;base64,", "", images[0])
            img_bytes = base64.b64decode(b64_str)
            elapsed = time.time() - t0
            logger.info(f"[{idx}/10] Image received: {len(img_bytes)} bytes in {elapsed:.1f}s")

            # Save to content paths
            for cp in spec["content_paths"]:
                cp.parent.mkdir(parents=True, exist_ok=True)
                cp.write_bytes(img_bytes)
                logger.info(f"  -> Saved to {cp}")

            # Save to docs path
            dp = spec["docs_path"]
            dp.parent.mkdir(parents=True, exist_ok=True)
            dp.write_bytes(img_bytes)
            logger.info(f"  -> Saved to {dp}")

            return True
    except Exception as e:
        logger.error(f"Generation failed for #{idx} {title}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Regenerate illustrations #1 to #10 with improved eyes and contrast")
    parser.add_argument("--start", type=int, default=1, help="Start index (1-10)")
    parser.add_argument("--end", type=int, default=10, help="End index (1-10)")
    parser.add_argument("--no-push", action="store_true", help="Do not git commit/push each work")
    args = parser.parse_args()

    targets = [s for s in WORKS_SPEC if args.start <= s["index"] <= args.end]
    logger.info(f"Starting batch illustration replacement for {len(targets)} works (#{args.start} to #{args.end})")

    success_count = 0
    for spec in targets:
        ok = generate_single_illustration(spec)
        if ok:
            success_count += 1
            if not args.no_push:
                try:
                    subprocess.run(["git", "add", "content/", "docs/"], check=False)
                    msg = f"feat(illust): Replace #{spec['index']} '{spec['title']}' illustration with refined eyes & high contrast"
                    subprocess.run(["git", "commit", "-m", msg], check=False)
                    subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], check=False)
                    subprocess.run(["git", "push", "origin", "HEAD:main"], check=False)
                    logger.info(f"Pushed #{spec['index']} to GitHub successfully.")
                except Exception as git_err:
                    logger.warning(f"Git push warning: {git_err}")

    logger.info(f"Batch completed: {success_count}/{len(targets)} works successfully replaced.")

    # Rebuild site
    try:
        from src.site_builder import build_github_pages
        from src.history_manager import HistoryManager
        from src.archiver import update_archive_all
        update_archive_all()
        build_github_pages(HistoryManager())
        if not args.no_push:
            subprocess.run(["git", "add", "docs/", "archive/", "README.md"], check=False)
            subprocess.run(["git", "commit", "-m", "chore(site): Rebuild GitHub Pages with regenerated illustrations #1-#10"], check=False)
            subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], check=False)
            subprocess.run(["git", "push", "origin", "HEAD:main"], check=False)
    except Exception as e:
        logger.warning(f"Site build warning: {e}")


if __name__ == "__main__":
    main()
