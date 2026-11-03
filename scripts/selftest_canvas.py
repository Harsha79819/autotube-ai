"""
End-to-end self-test for the Creator Canvas Engine. No network, no real photos needed.

    python scripts/selftest_canvas.py                # plan + render layers + contact sheet
    python scripts/selftest_canvas.py --clips        # also render real scene clips + xfade assembly
    AUTOTUBE_FORCE_LIBASS=1 python scripts/selftest_canvas.py   # exercise the no-libraqm text path

Builds a throw-away entity bank of placeholder SILHOUETTES (labelled, obviously not real
people) so you can see layouts before you curate real cutouts. Output goes to a temp dir
that is printed at the end.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

import agents.entity_bank as eb  # noqa: E402
from agents.entity_bank import EMOTIONS, EntityBank  # noqa: E402
from agents.scene_planner import describe, plan_scenes  # noqa: E402

EMO_TONE = {"angry": (200, 60, 60), "shocked": (60, 150, 210), "smug": (140, 90, 200),
            "serious": (210, 150, 90), "neutral": (150, 150, 150)}


def make_demo_bank(root: Path) -> EntityBank:
    people = {
        "aman": ("Aman", ["aman", "అమన్"], "#E63946", True),
        "thrigun": ("Thrigun", ["thrigun", "త్రిగున్"], "#2A9D8F", True),
        "jhansi": ("Jhansi", ["jhansi", "ఝాన్సీ"], "#F4A261", False),  # named but NO cutouts
    }
    for slug, (name, aliases, accent, with_cutouts) in people.items():
        d = root / slug
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(json.dumps(
            {"display_name": name, "aliases": aliases, "accent": accent, "show": "demo", "season": 10}),
            encoding="utf-8")
        if not with_cutouts:
            continue
        for emo in EMOTIONS:
            if slug == "thrigun" and emo in ("angry", "shocked"):
                continue  # force the fallback chain (angry -> serious)
            im = Image.new("RGBA", (1000, 1500), (0, 0, 0, 0))
            dr = ImageDraw.Draw(im)
            tone = EMO_TONE[emo]
            dr.ellipse((50, 700, 950, 1900), fill=(*tone, 255))          # shoulders
            dr.ellipse((300, 120, 700, 620), fill=(*tone, 255))           # head
            dr.rectangle((420, 560, 580, 760), fill=(*tone, 255))         # neck
            dr.text((330, 1000), f"PLACEHOLDER\n{name}\n{emo}", fill=(255, 255, 255, 255))
            im.save(d / f"{emo}.png")
    bank = EntityBank(root)
    eb._BANK = bank  # make get_bank() return this one
    return bank


TELUGU_SCRIPT = [
    "బిగ్ బాస్ తెలుగు హౌస్ లో ఈ వారం పెద్ద గొడవ జరిగింది.",
    "అందరూ ఊహించనిది అక్కడ జరిగింది.",
    "అమన్ నామినేషన్ రూమ్ లో సేఫ్ గేమ్ ఆడుతున్నాడు.",
    "కెమెరాల ముందు మాత్రం చాలా మంచివాడిలా నటన.",
    "ఇంతలో ఝాన్సీ ఒక్కసారిగా పైకి లేచి అరిచింది.",
    "పూర్తి గొంతుతో అరుస్తూ అందరినీ షాక్ చేసింది.",
    "హౌస్ అంతా ఒక్క క్షణం నిశ్శబ్దం.",
    "త్రిగున్ మాత్రం ఏమీ జరగనట్టు చూస్తూ ఉన్నాడు.",
    "అమన్ vs త్రిగున్ గొడవ అక్కడే మొదలైంది.",
    "అమన్ కోపంతో ఊగిపోయాడు.",
    "త్రిగున్ మాత్రం నవ్వుతూ సమాధానం చెప్పాడు.",
    "నేను నా గేమ్ ఆడుతున్నాను అన్నాడు.",
    "అమన్ మాటలకు ఎవరూ నమ్మలేకపోయారు.",
    "ఈ గొడవ తర్వాత నామినేషన్స్ లిస్ట్ మారిపోయింది.",
    "కెప్టెన్ తీసుకున్న నిర్ణయం అందరికీ షాక్.",
    "ఇప్పుడు హౌస్ లో రెండు గ్రూపులు తయారయ్యాయి.",
    "ఒక వైపు అమన్ గ్రూప్.",
    "మరో వైపు త్రిగున్ గ్రూప్.",
    "ప్రేక్షకులు మాత్రం సోషల్ మీడియాలో ఊరుకోలేదు.",
    "ట్రోల్స్ వరదలా వచ్చాయి.",
    "ఈ వారం ఎలిమినేషన్ ఎవరికి అనేది సస్పెన్స్.",
    "మీ అభిప్రాయం ఏమిటి కామెంట్ చేయండి.",
    "ఇలాంటి మరిన్ని అప్‌డేట్స్ కోసం ఫాలో అవ్వండి.",
    "మళ్ళీ కలుద్దాం.",
]


def synth_sections(total=70.0):
    n = len(TELUGU_SCRIPT)
    per = total / n
    return [{"section": i + 1, "visual": i + 1, "start": i * per, "end": (i + 1) * per, "narration": t}
            for i, t in enumerate(TELUGU_SCRIPT)]


def check_entity_collisions():
    """The name collisions the old season_guard existed for, now solved per-entity with `block` phrases."""
    t = Path(tempfile.mkdtemp(prefix="collide_"))

    def mk(slug, **meta):
        d = t / slug
        d.mkdir()
        (d / "meta.json").write_text(json.dumps(meta), encoding="utf-8")

    mk("charan", display_name="Charan", aliases=["charan", "చరణ్"], block=["ram charan", "రామ్ చరణ్"])
    mk("rohit_sahni", display_name="Rohit Sahni", aliases=["rohit sahni", "rohit"], block=["rohit sharma"])
    mk("jhansi", display_name="Jhansi", aliases=["jhansi", "ఝాన్సీ"], block=["jhansi fort"])
    bank = EntityBank(t)
    cases = {
        "Ram Charan new movie": [], "రామ్ చరణ్ సినిమా": [], "Charan played safe": ["charan"],
        "Charan met Ram Charan": ["charan"], "Rohit Sharma scored a century": [],
        "Rohit Sahni got nominated": ["rohit_sahni"], "visited Jhansi Fort": [],
        "Jhansi screamed loudly": ["jhansi"], "charanamrutham": [], "చరణ్‌కి కోపం వచ్చింది": ["charan"],
    }
    bad = {k: [e.slug for e, _ in bank.find_entities(k)] for k, v in cases.items()
           if [e.slug for e, _ in bank.find_entities(k)] != v}
    assert not bad, f"entity collision regressions: {bad}"
    print(f"entity collisions OK ({len(cases)} cases)")


def check_text_ink(render_text):
    """A text path that silently renders nothing must FAIL the test (the libass path once did)."""
    import numpy as np
    img = render_text("అమన్ నామినేషన్ రూమ్ లో సేఫ్ గేమ్ ఆడుతున్నాడు", 800, max_lines=2, start=80,
                      accent=(230, 57, 70, 255), highlight_last=True)
    a = np.asarray(img)
    ink = a[..., 3] > 128
    assert ink.sum() > 2500, f"text rendered no ink ({int(ink.sum())} px) - shaping path is broken"
    white = ink & (a[..., :3].min(axis=2) > 200)
    red = ink & (a[..., 0] > 200) & (a[..., 1] < 120)
    black = ink & (a[..., :3].max(axis=2) < 40)
    assert white.sum() > 500, "no white fill pixels"
    assert red.sum() > 100, "highlighted last word is not in the accent colour"
    assert black.sum() > 100, "no dark outline pixels"
    print(f"text ink OK: white={int(white.sum())} accent={int(red.sum())} outline={int(black.sum())}")


def contact_sheet(scenes_layers, out: Path, cols=5):
    from PIL import Image as I
    tw, th = 270, 480
    rows = (len(scenes_layers) + cols - 1) // cols
    sheet = I.new("RGB", (cols * tw, rows * th), (0, 0, 0))
    for i, sl in enumerate(scenes_layers):
        frame = I.open(sl.bg).convert("RGBA")
        for spec in sl.layers:
            if not spec.empty:  # layers are cropped to their bbox; paste back at the stored offset
                frame.alpha_composite(I.open(spec.path).convert("RGBA"), (spec.ox, spec.oy))
        sheet.paste(frame.convert("RGB").resize((tw, th), I.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    sheet.save(out)


def main():
    clips = "--clips" in sys.argv
    out = Path(tempfile.mkdtemp(prefix="canvas_selftest_"))
    bank = make_demo_bank(out / "entities")
    print("bank problems:", bank.validate() or "none")
    check_entity_collisions()

    sections = synth_sections()
    scenes = plan_scenes(sections, bank)
    print(describe(scenes))

    # ---- assertions on the pacing contract ----
    assert 8 <= len(scenes) <= 10, f"expected 8-10 scenes, got {len(scenes)}"
    assert abs(sum(s.duration for s in scenes) - 70.0) < 0.01, "scenes must cover the full audio"
    assert scenes[0].start == 0 and all(a.end == b.start for a, b in zip(scenes, scenes[1:])), "gaps/overlaps"
    long = [s for s in scenes if s.duration > 10.5]
    assert not long, f"scene(s) too long: {[s.index for s in long]}"
    layouts = {s.layout for s in scenes}
    print("layouts used:", sorted(layouts))
    assert "split" in layouts and "solo" in layouts, "expected solo + split scenes"
    assert "name_card" in layouts or any(s.mentioned_without_cutout for s in scenes), "Jhansi has no cutouts"
    thr = [e for s in scenes for e in s.entities if e.entity.slug == "thrigun"]
    assert all(e.expression_used in ("serious", "neutral", "smug") for e in thr), "fallback chain broken"

    from agents.canvas_engine import HAS_RAQM, compose_scene, render_scene_clip, render_text
    print("Telugu shaping path:", "Pillow+raqm" if HAS_RAQM else "libass fallback")
    check_text_ink(render_text)
    layers = []
    for sc in scenes:
        force = "typography" if sc.layout == "broll" else None
        layers.append(compose_scene(sc, out / "layers", force=force))
    contact_sheet(layers, out / "contact_sheet.png")

    if clips:
        from ken_burns import assemble_with_transitions
        paths, durs = [], []
        for i, (sc, sl) in enumerate(zip(scenes, layers)):
            dur = min(sc.duration, 2.2)  # keep the self-test quick
            p = out / "clips" / f"c{i:02d}.mp4"
            render_scene_clip(sl, p, dur + 0.35, fps=30, is_hook=(i == 0))
            paths.append(str(p))
            durs.append(dur)
        final = out / "assembled.mp4"
        assemble_with_transitions(paths, str(final), scene_durations=durs)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=width,height,duration",
                                "-of", "csv=p=0", str(final)], capture_output=True, text=True).stdout.strip()
        print("assembled:", probe)
        assert probe.startswith("1080,1920"), probe

    print(f"\nOK  -> {out}")
    print(f"contact sheet: {out / 'contact_sheet.png'}")


if __name__ == "__main__":
    main()
