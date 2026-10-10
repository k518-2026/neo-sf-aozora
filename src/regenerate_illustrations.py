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
    {
        "index": 11,
        "work_id": "oguri-20th-century-iron-mask",
        "title": "二十世紀鉄仮面",
        "author": "小栗虫太郎",
        "content_paths": [Path("content/2026-09-28_oguri_20th_century_iron_mask.png")],
        "docs_path": Path("docs/assets/images/oguri-20th-century-iron-mask.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Chief Inspector Kagami, an elite forensic investigator in his early 30s with short black hair, wearing a sleek modern dark suit. "
            "Masterpiece medium shot: dignified intelligent handsome face, beautifully detailed expressive eyes, clear luminous pupils, delicate iris reflections with crisp light catchlights, sharp symmetrical anime facial features, focused calm expression. "
            "In the high-tech interior of an autonomous vehicle speeding through a vibrant neon-lit metropolis at night, he examines floating 3D holographic models of DNA facial profiling and biological biometric masks in luminous cyan, emerald, and electric blue. "
            "Well-lit illuminated interior with ambient dashboard glow and vibrant city highway light streaks outside the panoramic window, crisp clean contrast, radiant highlights, no murky gloom, pure art without text."
        ),
    },
    {
        "index": 12,
        "work_id": "unno-floating-island",
        "title": "浮かぶ飛行島",
        "author": "海野十三",
        "content_paths": [Path("content/2026-09-28_unno_floating_island.png")],
        "docs_path": Path("docs/assets/images/unno-floating-island.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Shinichi Kamiya, a brilliant aerospace engineer in his late 20s with tidy black hair, wearing a high-tech flight-suit style engineering jacket. "
            "Masterpiece half-body portrait: passionate determined handsome face, captivating expressive eyes, clear dark irises with detailed specular catchlights, sharp symmetrical anime facial features, resolute dignified expression. "
            "Standing on the grand panoramic observation control deck of the colossal floating megastructure 'Icarus Pier' in the stratosphere at 15,000 meters altitude. "
            "Outside the massive glass dome, the brilliant curved blue horizon of Earth glows against the deep stratospheric sky under radiant sunlight. Holographic superconducting levitation consoles glow in golden-amber and bright cyan. "
            "Well-lit illuminated control deck with radiant daylight and solar lens flares, crisp dynamic contrast, no muddy shadows, pure art without text."
        ),
    },
    {
        "index": 13,
        "work_id": "unno-captive",
        "title": "俘囚",
        "author": "海野十三",
        "content_paths": [Path("content/2026-09-29_unno_captive.png")],
        "docs_path": Path("docs/assets/images/unno-captive.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Susumu Sonezaki, a genius theoretical physicist in his early 30s with sharp features and determined dark hair, wearing a minimalist high-tech containment suit. "
            "Masterpiece medium shot: fearless defiant handsome face, breathtaking detailed expressive eyes, sharp clear pupils with sparkling light reflections, refined symmetrical anime facial structure, triumphant visionary smile. "
            "Inside a sterile high-security quantum containment chamber with reinforced white ceramic walls. "
            "As he opens his arms, a miraculous AdS/CFT holographic quantum wormhole manifests around him, with brilliant radiant rings of cobalt blue, violet, and crystalline particle light tearing open a spacetime singularity gateway. "
            "Highly illuminated environment, vivid luminous energy arcs, strong clean contrast, gleaming highlights, no murky pitch-black room, pure art without text."
        ),
    },
    {
        "index": 14,
        "work_id": "unno-metal-man",
        "title": "金属人間",
        "author": "海野十三",
        "content_paths": [Path("content/2026-09-29_unno_metal_man.png")],
        "docs_path": Path("docs/assets/images/unno-metal-man.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Masumi Kusano, an intellectual biochemist in his late 20s with neatly parted hair and spectacles, wearing a modern crisp white lab coat. "
            "Masterpiece half-body portrait: calm intellectual handsome face, striking beautiful expressive eyes reflecting a faint mysterious sapphire Cherenkov glow deep within the pupils, delicate catchlights, symmetrical refined anime facial features, serene visionary expression. "
            "In an illuminated state-of-the-art medical biotechnology laboratory. "
            "His rolled-up right sleeve reveals his forearm under a soft infrared beam: beneath translucent skin, intricate self-assembling liquid gallium-indium alloy nano-circuits gleam in radiant liquid silver and glowing cyan lines pulsing harmoniously. "
            "Bright modern lab lighting, clean crisp contrast, radiant metallic reflections, no murky darkness, pure art without text."
        ),
    },
    {
        "index": 15,
        "work_id": "hisao-insect-catalog",
        "title": "昆虫図",
        "author": "久生十蘭",
        "content_paths": [Path("content/2026-09-29_hisao_insect_catalog.png")],
        "docs_path": Path("docs/assets/images/hisao-insect-catalog.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Shuji Kusano, a young computational biologist in his late 20s with gentle dark hair, wearing a white research coat over a crisp shirt. "
            "Masterpiece medium close-up portrait: sensitive intelligent handsome face, beautifully drawn deeply expressive eyes, clear luminous pupils with delicate iris details, sharp symmetrical anime facial features, contemplative wonder expression. "
            "In a brightly lit botanical bio-cybernetics laboratory surrounded by lush illuminated greenhouse foliage and glass terrariums. "
            "Floating before him are glowing microfluidic biochips and shimmering swarm-intelligence pheromone networks: iridescent cerulean-and-emerald robotic jewel beetles and bio-engineered fireflies radiating warm golden and turquoise specks of light in the air. "
            "Well-lit ambient room, crisp vivid colors, strong dynamic contrast, radiant highlights, no gloom, pure art without text."
        ),
    },
    {
        "index": 16,
        "work_id": "edogawa-human-chair",
        "title": "人間椅子",
        "author": "江戸川乱歩",
        "content_paths": [Path("content/2026-09-30_edogawa_human_chair.png")],
        "docs_path": Path("docs/assets/images/edogawa-human-chair.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Yoshiko, an elegant and beautiful Japanese female author in her mid-20s with glossy dark shoulder-length hair, wearing a sophisticated cream-colored silk blouse and long skirt. "
            "Masterpiece half-body portrait: strikingly gorgeous feminine face, mesmerizing beautifully detailed anime eyes with long delicate eyelashes, luminous brown irises with crystal-clear catchlights, graceful refined facial features, a gentle melancholic and blissful sigh. "
            "Seated comfortably in a sleek, luxurious autonomous smart armchair 'Anima' in an airy modern sunlit private library. "
            "The ergonomic black armchair has subtle micro-sensor electronic skin lines (E-skin) pulsing with soft warm golden and rose-gold haptic feedback light. "
            "Bright daylight streaming through large arching windows illuminating book collections, radiant ambient room lighting, crisp contrast, warm exquisite aesthetic, no murky dark shadows, pure art without text."
        ),
    },
    {
        "index": 17,
        "work_id": "edogawa-mirror-hell",
        "title": "鏡地獄",
        "author": "江戸川乱歩",
        "content_paths": [Path("content/2026-09-30_edogawa_mirror_hell.png")],
        "docs_path": Path("docs/assets/images/edogawa-mirror-hell.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Reiji Sawamura, a passionate optical physicist in his late 20s with stylish dark hair, wearing a white tech-fabric research coat. "
            "Masterpiece medium shot: handsome intense face filled with awe, extraordinarily detailed expressive anime eyes reflecting infinite prismatic mirror reflections, crystal-clear pupils with specular light catches, sharp symmetrical facial features, mesmerized dignified expression. "
            "Standing at the epicenter of a gigantic spherical topological metamaterial optical resonator inside a high-tech cleanroom. "
            "Around him, countless negative-index mirrors and topological photonic crystals bounce infinite beams of pure light, creating a breathtaking kaleidoscope of cosmic microwave background radiation and rainbow spectral flares. "
            "Brilliantly illuminated environment, gleaming crystalline prisms, intense vibrant colors, sharp clean contrast, radiant lighting, no dark gloom, pure art without text."
        ),
    },
    {
        "index": 18,
        "work_id": "edogawa-psychological-test",
        "title": "心理試験",
        "author": "江戸川乱歩",
        "content_paths": [Path("content/2026-09-30_edogawa_psychological_test.png")],
        "docs_path": Path("docs/assets/images/edogawa-psychological-test.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Seiichiro Fukiya, a 21-year-old elite university prodigy in theoretical computing with sleek neat black hair, wearing a crisp dark collared shirt. "
            "Masterpiece close-up half-body portrait: impeccably handsome, cold yet refined face, mesmerizingly clear and piercing expressive eyes with sharp pupils and delicate iris catchlights, perfectly symmetrical anime features, a subtle composed enigmatic smirk. "
            "In a modern well-lit cognitive neuro-forensic examination room. Wearing a minimalist high-tech fNIRS headset emitting subtle near-infrared laser sensors on his brow. "
            "Before him, transparent holographic monitors display perfectly balanced brainwave waveforms, oxygenation metrics, and zero-knowledge cryptographic proofs in soft glowing cyan and mint-green lines. "
            "Fully illuminated clean architectural room, high dynamic contrast, crisp outlines, no dark gloom, pure art without text."
        ),
    },
    {
        "index": 19,
        "work_id": "edogawa-attic-stroller",
        "title": "屋根裏の散歩者",
        "author": "江戸川乱歩",
        "content_paths": [Path("content/2026-10-01_edogawa_attic_stroller.png")],
        "docs_path": Path("docs/assets/images/edogawa-attic-stroller.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Saburo Goda, a solitary electromagnetic radio researcher in his mid-20s with slightly tousled dark hair, wearing a casual dark tech-hoodie. "
            "Masterpiece medium shot: sharp observant handsome face, intense and deeply focused expressive eyes with clear pupils and radiant monitor reflections, crisp symmetrical anime facial features, deeply engrossed expression. "
            "In an atmospheric yet well-lit converted attic laboratory filled with planar array antennas, signal processors, and glowing multicaster displays. "
            "On his ultra-wide monitors glow holographic 3D wireframe human body meshes and terahertz through-wall scattering radar fields in vibrant electric cyan and violet hues, mapping real-time cardiac rhythm attractors. "
            "Clear dynamic contrast, warm ambient desk lamps balancing the glowing screens, radiant highlights, clean sharp details, no murky darkness, pure art without text."
        ),
    },
    {
        "index": 20,
        "work_id": "edogawa-picture-traveler",
        "title": "押絵と旅する男",
        "author": "江戸川乱歩",
        "content_paths": [Path("content/2026-10-01_edogawa_picture_traveler.png")],
        "docs_path": Path("docs/assets/images/edogawa-picture-traveler.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of an emotional scene from 'The Man Traveling with the Brocade Picture': in a warmly lit vintage express train observation car speeding through a snowy twilight. "
            "A dignified, gentle elderly Japanese man in his late 60s with neat silver-white hair and kind expressive eyes, wearing an elegant wool coat, gently holds an ornate antique picture frame. "
            "Inside the glowing frame is an extraordinarily beautiful anime girl in her late teens dressed in Taisho-roman modern attire, with sparkling expressive brown eyes, radiant smile, and delicate hair ribbons, alive and gently moving within a topological superconducting quantum processor field that emits soft golden starlight and faint blue luminescence. "
            "Warm train cabin lighting, soft snow falling outside the large window, rich dynamic contrast, exquisite nostalgic and futuristic aesthetic, clear detailed facial anatomy, no murky gloom, pure art without text."
        ),
    },
    {
        "index": 21,
        "work_id": "edogawa-panorama-island",
        "title": "パノラマ島綺譚",
        "author": "江戸川乱歩",
        "content_paths": [Path("content/2026-10-01_edogawa_panorama_island.png")],
        "docs_path": Path("docs/assets/images/edogawa-panorama-island.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Seiji Kusaka, a genius mathematical ecologist in his early 30s with sharp features and a modern white lab coat over a dark vest. Masterpiece medium close-up: highly intelligent, visionary handsome face, breathtaking detailed expressive eyes with sharp clear pupils and emerald-cyan iris reflections, clean symmetrical anime facial features, confident enigmatic smile. Standing atop a rocky promontory overlooking Panorama Island at night: beneath him, the entire island glows as an artificial closed biosphere of bioluminescent luciferase flora, radiant cyan phytoplankton bays, and pulsing geometric energy conduits. Brightly illuminated scene under a starry twilight sky, vivid neon-cyan and warm gold organic highlights, dynamic clear contrast, no murky darkness, pure art without text."
        ),
    },
    {
        "index": 22,
        "work_id": "unno-subterranean-battleship",
        "title": "地底戦艦",
        "author": "海野十三",
        "content_paths": [Path("content/2026-10-02_unno_subterranean_battleship.png")],
        "docs_path": Path("docs/assets/images/unno-subterranean-battleship.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Akari Minase, an elite lead analyst in her mid-20s wearing a sleek form-fitting deep-subterranean navigator uniform. Masterpiece half-body portrait: calm, highly focused feminine beauty, strikingly detailed expressive dark amber eyes with crystal-clear specular highlights, graceful symmetrical anime facial anatomy, cool composed expression. Inside the control command bridge of the subterranean battleship Orochi navigating the core-mantle boundary at 2,900 km depth. Before her float vivid bio-holographic seismic tomography consoles displaying magma convection vectors and mantle stratification in glowing molten-orange, gold, and azure lines. Brightly lit high-tech command center, vibrant contrast between warm thermal graphics and cool architectural lighting, radiant highlights, no murky pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 23,
        "work_id": "unno-earth-theft",
        "title": "地球盗難",
        "author": "海野十三",
        "content_paths": [Path("content/2026-10-02_unno_earth_theft.png")],
        "docs_path": Path("docs/assets/images/unno-earth-theft.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Akira Asakura, a brilliant young celestial dynamicist in his late 20s with neat dark hair and a warm winter jacket. Masterpiece half-body portrait: passionate and determined handsome face, deeply expressive dark brown eyes filled with intellectual fire, clear pupils with intricate light catchlights, sharp symmetrical anime features. In the grand panoramic analysis hall of the National Astronomical Observatory. Outside the massive glass dome, soft snow falls over the city skyline, while inside, towering holographic displays project the Earth's chaotic Lagrange-point invariant manifolds and celestial orbital leap vectors in luminous cyan, violet, and gold. Well-lit observatory interior, dynamic high-contrast lighting balancing glowing cosmic trajectories and atmospheric ambient glow, no murky shadows, pure art without text."
        ),
    },
    {
        "index": 24,
        "work_id": "unno-electric-bath-death",
        "title": "電気風呂の怪死",
        "author": "海野十三",
        "content_paths": [Path("content/2026-10-02_unno_electric_bath_death.png")],
        "docs_path": Path("docs/assets/images/unno-electric-bath-death.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Soji Homura, a refined and brilliant physicist-detective in his early 30s wearing a stylish dark modern trench coat over a tailored shirt. Masterpiece medium shot: impeccably handsome, observant face, penetrating detailed gray-blue eyes with sharp pupils and delicate iris reflections, refined symmetrical anime facial structure, astute confident expression. In a luxurious marble high-tech bathroom investigating an electromagnetic mystery. He scans a wall of topological insulator honeycomb lattice film with a handheld scanning SQUID quantum flux sensor, projecting radiant cobalt-blue laser grids and rainbow interference fringes into the room. Brilliantly illuminated modern interior, crisp geometric reflections, clean dynamic contrast, vibrant luminous highlights, no pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 25,
        "work_id": "oguri-submarine-eagles-nest",
        "title": "潜航艇「鷹の巣」",
        "author": "小栗虫太郎",
        "content_paths": [Path("content/2026-10-02_oguri_submarine_eagles_nest.png")],
        "docs_path": Path("docs/assets/images/oguri-submarine-eagles-nest.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Rei Mifune, a brilliant young deep-sea acoustic communications engineer in her mid-20s with dark hair tied in a clean ponytail, wearing an advanced marine research jacket. Masterpiece half-body portrait: resolute, courageous feminine face, captivating large expressive hazel eyes with shimmering light reflections, delicate long eyelashes, symmetrical refined anime features, unwavering hopeful expression. In the primary operations control room of the deep-sea mothership 'Wadatsumi'. She operates multi-layered holographic consoles reconstructing ultra-low frequency ocean acoustic tomography maps of the Mariana Trench 10,000 meters below, with luminous turquoise and emerald error-correcting signal graphs rippling across the air. Well-lit control room with sleek azure and cool white ambient illumination, strong crisp contrast, radiant reflections, no dark gloom, pure art without text."
        ),
    },
    {
        "index": 26,
        "work_id": "unno-mars-corps",
        "title": "火星兵団",
        "author": "海野十三",
        "content_paths": [Path("content/2026-10-03_unno_mars_corps.png")],
        "docs_path": Path("docs/assets/images/unno-mars-corps.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Sosuke Jinnai, a dedicated radio astronomer in his mid-30s with slightly tousled dark hair, wearing a rugged mountain observatory parka. Masterpiece medium shot: intense, vigilant handsome face, sharp piercing dark eyes reflecting starlight and monitor telemetry, clear pupils, dignified symmetrical anime facial anatomy, serious awe-inspired expression. At the high-altitude Atacama Desert Radio Observatory under a breathtaking, radiant canopy of the Milky Way and towering parabolic dish antennas. His field tablet projects a gleaming 3D swarm network of geometric self-replicating von Neumann automatons expanding along the Martian orbital plane in fiery orange and electric cyan vector nodes. Crisp vibrant contrast between the radiant starlit desert sky and glowing high-tech instrumentation, bright highlights, no muddy shadows, pure art without text."
        ),
    },
    {
        "index": 27,
        "work_id": "edogawa-hakuchumu",
        "title": "白昼夢",
        "author": "江戸川乱歩",
        "content_paths": [Path("content/2026-10-03_edogawa_hakuchumu.png")],
        "docs_path": Path("docs/assets/images/edogawa-hakuchumu.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Hajime Shiga, a distressed young neuro-researcher in his late 20s wearing a disheveled modern suit, standing amidst the dazzling sunlight of a Tokyo metropolitan plaza. Masterpiece medium close-up: emotionally intense handsome face, hauntingly beautiful expressive anime eyes filled with sorrow and desperate plea, clear dark irises with vivid catchlights, refined facial anatomy. Around him in mid-air, adversarial perturbation patches and transcranial focused ultrasound generate surreal holographic illusions of kaleidoscopic light-fractals, phantom silhouettes, and shimmering red-and-gold visual mirages distorting the summer heatwave. Blazing mid-day sunlight flooding the futuristic city boulevard, radiant sun flares, crisp dynamic contrast, vibrant vivid colors, no pitch-black darkness, pure art without text."
        ),
    },
    {
        "index": 28,
        "work_id": "yumeno-binzume-jigoku",
        "title": "瓶詰地獄",
        "author": "夢野久作",
        "content_paths": [Path("content/2026-10-03_yumeno_binzume_jigoku.png")],
        "docs_path": Path("docs/assets/images/yumeno-binzume-jigoku.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Amano, a sharp oceanic data forensic investigator in his late 20s with short black hair and glasses, working in an illuminated marine archaeology cleanroom. Masterpiece half-body portrait: intellectual, compassionate handsome face, captivating expressive anime eyes with crystalline catchlights behind fine spectacles, symmetrical refined facial structure, thoughtful gentle expression. On the illuminated laboratory pedestal before him rest three thick quartz glass pressure cylinders containing glowing amber DNA data storage fluid. Holographic decoding lasers project floating strands of recovered historical letters and genetic timestamps in luminous warm gold and cyan characters. Clean, brightly lit high-tech laboratory with soft white ambient panels, exquisite dynamic contrast between the warm glowing bottles and cool glass surfaces, no muddy gloom, pure art without text."
        ),
    },
    {
        "index": 29,
        "work_id": "miyazawa-ginga",
        "title": "銀河鉄道の夜",
        "author": "宮沢賢治",
        "content_paths": [Path("content/2026-10-03_miyazawa_ginga.png")],
        "docs_path": Path("docs/assets/images/miyazawa-ginga.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Sho Kamiya, a 28-year-old brilliant astrophysicist with neat dark hair, wearing a high-tech laboratory vest over a casual sweater. Masterpiece medium shot: awe-inspired handsome face, strikingly clear and expressive starry-dark eyes reflecting deep cosmic constellations, fine pupils with brilliant specular highlights, gentle visionary smile. Inside an advanced quantum telecommunications facility. Before him, an ER=EPR quantum entanglement tensor network manifests as an ethereal, luminous celestial railway of starlight traversing a swirling sapphire and violet galactic nebula, guided by millisecond pulsar navigation beacons. Brilliantly illuminated cosmic research environment, vibrant radiant light streams of starlight and celestial nebulae, strong clean contrast, luminous sparkling particles, no pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 30,
        "work_id": "akutagawa-haguruma",
        "title": "歯車",
        "author": "芥川龍之介",
        "content_paths": [Path("content/2026-10-03_akutagawa_haguruma.png")],
        "docs_path": Path("docs/assets/images/akutagawa-haguruma.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Rin Shiina, a compassionate female cognitive neuroscientist in her late 20s with elegant dark hair in a loose bun, wearing a crisp modern white lab coat. Masterpiece half-body portrait: exquisitely beautiful feminine face, warm deeply expressive brown eyes filled with empathy and intelligence, delicate long eyelashes, sharp pupils with clear specular catchlights, gentle reassuring smile. In a clean, modern magnetically shielded neuroimaging suite. Before her MEG monitor, mathematical Turing patterns and reaction-diffusion visual models manifest in the air as intricate, semi-transparent spinning clockwork gears made of pure radiant crystalline light and soft golden geometry. Brightly lit laboratory with cool azure and pearl-white ambient illumination, crisp dynamic contrast, sparkling light highlights, no muddy shadows, pure art without text."
        ),
    },
    {
        "index": 31,
        "work_id": "akutagawa-kappa",
        "title": "河童",
        "author": "芥川龍之介",
        "content_paths": [Path("content/2026-10-03_akutagawa_kappa.png")],
        "docs_path": Path("docs/assets/images/akutagawa-kappa.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Ryosuke Tamura, a dedicated synthetic genomics lead researcher in his late 20s with short tidy black hair, wearing a white research jacket. Masterpiece half-body portrait: earnest, morally questioning handsome face, clear deeply expressive anime eyes with detailed irises and sharp pupils, delicate catchlights, symmetrical refined anime features, contemplative dignified gaze. Inside the subterranean bio-ecological laboratory of the Kappa Colony. Behind him stands an illuminated transparent artificial womb bio-pod filled with glowing pale emerald-cyan synthetic nutrient fluid, flanked by holographic brain-computer interface telemetry showing harmonious fetal neural oscillations in mint-green and amber waveforms. Brightly illuminated high-tech bio-facility, crisp reflections on glass chambers, strong dynamic contrast, clean radiant aesthetic, no murky dark shadows, pure art without text."
        ),
    },
    {
        "index": 32,
        "work_id": "akutagawa-kumonoito",
        "title": "蜘蛛の糸",
        "author": "芥川龍之介",
        "content_paths": [Path("content/2026-10-04_akutagawa_kumonoito.png")],
        "docs_path": Path("docs/assets/images/akutagawa-kumonoito.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Kandata, a rugged yet handsome former hacker in his late 20s wearing worn subterranean miner gear with a utility belt, in a monumental deep-earth cavern station. Masterpiece medium shot: resolute, redeemed expression, intense expressive eyes filled with newfound purpose and hope, sharp pupils reflecting silver light, detailed anime facial anatomy. From the vaulted ceiling 3,000 meters above, a single micro-thin ultra-long carbon nanotube tether descends like a radiant thread of spun silver, gleaming with pure brilliant white light. A small mechanical maintenance spider with a glowing cyan eye perches loyally on his armored boot. Dramatic yet well-illuminated industrial sci-fi cavern, radiant beams of silver and golden salvation light cutting through clear air, high dynamic contrast, crisp details, no murky pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 33,
        "work_id": "nakajima-sangetsuki",
        "title": "山月記",
        "author": "中島敦",
        "content_paths": [Path("content/2026-10-04_nakajima_sangetsuki.png")],
        "docs_path": Path("docs/assets/images/nakajima-sangetsuki.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Federal Science Auditor Ensan, an elegant 30-year-old official in an aristocratic modern travel coat, meeting his transformed friend under the moonlit Tianshan Mountains. Masterpiece medium shot: Ensan's refined handsome face is rendered with deep emotion and tearful nostalgic recognition, his expressive eyes reflecting the moonlight with crystal clarity. Beside him among moonlit alpine crags stands a majestic 3-meter bio-hybrid guardian tiger (Ri Cho), its fur possessing subtle optical camouflage circuits, with gentle, sorrowful glowing amber eyes radiating human intelligence and pride. Bathed in radiant silvery moonlight under a sweeping starry sky, soft mountain mist glowing with bioluminescent spores, crisp dynamic contrast, poignant and magnificent atmosphere, no pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 34,
        "work_id": "kajii-lemon",
        "title": "檸檬",
        "author": "梶井基次郎",
        "content_paths": [Path("content/2026-10-04_kajii_lemon.png")],
        "docs_path": Path("docs/assets/images/kajii-lemon.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Saki Kujo, a dignified and beautiful female quantum biochemist in her late 20s with wavy dark hair, wearing a tailored white lab coat over a traditional embroidered shawl. Masterpiece half-body portrait: radiant feminine beauty, mesmerizing expressive anime eyes with golden-amber irises and luminous catchlights, gentle enigmatic smile, flawless facial symmetry. In a warm vintage botanical research atelier in Kyoto. In her delicate palm rests a vivid, glowing lemon-yellow fruit radiating quantum vibrational resonance: as its aroma disperses, an explosion of synesthetic light cascades through the room—vibrant chromatic ribbons of ruby, azure, and gold swirling like living masterwork paintings. Warm golden interior gaslight harmonizing with the dazzling synesthetic colors, high dynamic contrast, crisp luminous highlights, enchanting aesthetic, no murky shadows, pure art without text."
        ),
    },
    {
        "index": 35,
        "work_id": "miyazawa-gusukobudori",
        "title": "グスコーブドリの伝記",
        "author": "宮沢賢治",
        "content_paths": [Path("content/2026-10-04_miyazawa_gusukobudori.png")],
        "docs_path": Path("docs/assets/images/miyazawa-gusukobudori.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Guskobudori, a determined 23-year-old volcanic climate engineer with tidy dark hair, wearing a protective high-heat engineering coat. Masterpiece half-body portrait: noble, selfless handsome face, extraordinarily clear and resolute dark blue eyes filled with compassion, sharp pupils with gleaming catchlights, refined symmetrical anime features, calm heroic resolve. In the primary observation control station of Mount Carbonado volcano. Through heat-resistant panoramic glass, glowing crimson and golden volcanic magma chambers pulse below, while before him, holographic climate engineering simulations display stratospheric aerosol dispersal curves in electric cyan and emerald arcs. Highly illuminated control room with dynamic contrast between the fiery volcanic glow and the cool holographic telemetry, radiant highlights, no murky darkness, pure art without text."
        ),
    },
    {
        "index": 36,
        "work_id": "kajii-sakuranoki",
        "title": "桜の樹の下には",
        "author": "梶井基次郎",
        "content_paths": [Path("content/2026-10-04_kajii_sakuranoki.png")],
        "docs_path": Path("docs/assets/images/kajii-sakuranoki.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Motojiro, an observant plant neurophysiologist in his late 20s with short dark hair, wearing a field researcher's jacket and carrying a handheld multispectral scanner. Masterpiece medium shot: contemplative sensitive handsome face, captivating deeply expressive anime eyes reflecting shimmering cherry blossom petals, clear pupils with delicate light highlights, thoughtful awe-struck expression. Standing beneath a breathtaking grove of colossal, luminous cherry blossom trees in full magnificent bloom in the environmental regeneration valley. Beneath the soil, a vast Wood Wide Web of common mycorrhizal fungi pulses with subtle bioluminescent cyan and violet electrical signals, making the translucent pink petals glow from within against a sunlit spring sky. Brilliant spring daylight, radiant falling sakura petals, vibrant natural and bio-photonic colors, crisp dynamic contrast, no muddy gloom, pure art without text."
        ),
    },
    {
        "index": 37,
        "work_id": "soseki-yume-juuya",
        "title": "夢十夜",
        "author": "夏目漱石",
        "content_paths": [Path("content/2026-10-04_soseki_yume_juuya.png")],
        "docs_path": Path("docs/assets/images/soseki-yume-juuya.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Special Inspector Tsuda, a keen detective in his mid-30s with short slicked hair, wearing an elegant dark wool trench coat over a sharp suit. Masterpiece medium shot: sharp perceptive handsome face, striking slate-gray expressive eyes with piercing clarity and fine specular catchlights, stoic dignified expression. Inside an ancient yet advanced underground vault with vaulted stone pillars. Before him, a massive pearl-white cryogenic preservation capsule stands open, billowing cool white vapor; inside rests an exquisitely preserved beautiful young noblewoman in a pure white Victorian gown, bathed in starlight-like cryogenic monitoring lasers. Well-lit subterranean chamber with glowing azure ambient lightbars and crystalline frost reflections, high dynamic contrast, crisp outlines, no pitch-black gloom, pure art without text."
        ),
    },
    {
        "index": 38,
        "work_id": "ango-sakura-no-mori",
        "title": "桜の森の満開の下",
        "author": "坂口安吾",
        "content_paths": [Path("content/2026-10-04_ango_sakura_no_mori.png")],
        "docs_path": Path("docs/assets/images/ango-sakura-no-mori.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Maiko, a brilliant female cognitive neuroscientist in her late 20s with sleek dark hair, wearing a white tech-fabric research coat. Masterpiece half-body portrait: striking intellectual feminine beauty, mesmerizing sharp dark eyes with clear pupils and radiant catchlights, refined symmetrical anime facial anatomy, serious awe-inspired expression. Standing beside a transparent observation partition outside an anechoic, non-reflective metamaterial chamber. Inside the chamber, volumetric light-field aerial projection systems illuminate the absolute void with an overwhelming, hyper-realistic storm of tens of thousands of pink and silver cherry blossom petals swirling in radiant three-dimensional light. Crisp clean laboratory lighting, dazzling volumetric sakura storm against controlled ambient illumination, high dynamic contrast, vibrant luminous highlights, no muddy darkness, pure art without text."
        ),
    },
    {
        "index": 39,
        "work_id": "yumeno-dogra-magra",
        "title": "ドグラ・マグラ",
        "author": "夢野久作",
        "content_paths": [Path("content/2026-10-04_yumeno_dogra_magra.png")],
        "docs_path": Path("docs/assets/images/yumeno-dogra-magra.png"),
        "prompt": (
            "Cinematic sci-fi anime illustration of Shinji Yajima, a brilliant 27-year-old neurogeneticist with slightly messy dark hair, wearing an open white laboratory coat over a dark shirt. Masterpiece close-up half-body portrait: intensely intellectual, handsome face etched with thrilling realization, deeply expressive eyes reflecting holographic neural patterns, clear pupils with sparkling catchlights, sharp symmetrical anime features. In an illuminated advanced neurogenetics laboratory. Before his multielectrode array incubator, a holographic cerebral organoid pulses with complex self-referential gamma waves, manifesting in the air as a mesmerizing, luminous golden and cyan 'Strange Loop' recursive fractal diagram. Brightly lit state-of-the-art cleanroom, crisp glass reflections, radiant holographic telemetry, high dynamic contrast, no murky darkness, pure art without text."
        ),
    },
]


def generate_single_illustration(spec: Dict[str, Any], url: str = DRAW_THINGS_URL) -> bool:
    idx = spec["index"]
    title = spec["title"]
    work_id = spec["work_id"]
    prompt = spec["prompt"]

    logger.info(f"[{idx}] Generating improved illustration for #{idx} {title} ({work_id})...")
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
            logger.info(f"[{idx}] Image received: {len(img_bytes)} bytes in {elapsed:.1f}s")

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
    parser = argparse.ArgumentParser(description="Regenerate illustrations with improved eyes and contrast")
    parser.add_argument("--start", type=int, default=21, help="Start index (1-39)")
    parser.add_argument("--end", type=int, default=39, help="End index (1-39)")
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
            commit_title = f"chore(site): Rebuild GitHub Pages with regenerated illustrations #{args.start}-#{args.end}"
            subprocess.run(["git", "commit", "-m", commit_title], check=False)
            subprocess.run(["git", "pull", "--rebase", "--autostash", "origin", "main"], check=False)
            subprocess.run(["git", "push", "origin", "HEAD:main"], check=False)
    except Exception as e:
        logger.warning(f"Site build warning: {e}")


if __name__ == "__main__":
    main()

