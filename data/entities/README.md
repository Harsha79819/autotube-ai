# Entity & emotion cutout bank

The Creator Canvas Engine (`agents/canvas_engine.py`, `agents/canvas_ladder.py`) turns on automatically
as soon as this folder contains at least one entity folder. No entities = the old pipeline runs untouched.

```
data/entities/
  aman/
    meta.json
    neutral.png      <- required (last-resort expression)
    angry.png        <- optional, one file per expression:
    shocked.png         angry | shocked | smug | serious | neutral
    smug.png
    serious.png
  thrigun/ ...
data/stage/          <- optional: real Bigg Boss set / stage frames (jpg/png). Blurred into backgrounds.
data/brand.json      <- optional: {"channel_name": "…"}  (small tag on banners / typography cards)
```

## meta.json

```json
{
  "display_name": "Aman",
  "aliases": ["aman", "అమన్"],
  "block": ["aman gupta"],
  "accent": "#E63946",
  "show": "bigg_boss_telugu",
  "season": 10
}
```

* `aliases` - the ONLY way an entity is recognised in a script. Latin aliases match on word boundaries
  (`charan` will not fire inside `charanamrutham`); Telugu aliases match as substrings so inflections
  (`అమన్‌కి`) still hit. Longest alias wins (`rohit sahni` beats `rohit`).
* `block` - phrases that contain an alias but mean someone else: `["ram charan", "రామ్ చరణ్"]` on
  Charan, `["rohit sharma"]` on Rohit, `["jhansi fort"]` on Jhansi. Replaces the name-collision half of
  `season_guard`: a cutout is chosen by alias, never by web search.
* `accent` - rim glow, name chip and split-screen panel colour.
* `season` - informational. Cutouts are curated for the current season, so there is nothing to lock.

## Cutout requirements

* Transparent PNG (RGBA) cropped head-and-shoulders or chest-up, at least 1000 px tall.
* One real photo per expression. Missing expressions fall back along
  `angry -> serious -> shocked -> neutral`, `smug -> neutral -> serious`, etc.
* Remove backgrounds with whatever you like (remove.bg, Photoshop, `rembg`); the engine does not do it for you.

Check the bank any time:

```
python -m agents.entity_bank --validate
python -m agents.entity_bank --find "అమన్ vs త్రిగున్ గొడవ"
```

## Per-scene overrides

Heuristics (emotion words, banner punchline, who is in the scene) can be pinned per scene by writing
`output/scene_overrides.json` (keys are 1-based scene numbers):

```json
{
  "3": {"banner": "అమన్ vs త్రిగున్!", "emotion": "angry", "entities": ["aman", "thrigun"], "layout": "split"},
  "7": {"layout": "typography"}
}
```

## Environment switches

| Variable | Default | Effect |
|---|---|---|
| `AUTOTUBE_CANVAS` | `auto` | `1` force on, `0` force off, `auto` = on when this folder has entities |
| `AUTOTUBE_ALLOW_AI_IMAGES` | `0` | In canvas mode text-to-image (FLUX) is off. `1` re-enables it |
| `AUTOTUBE_PHOTO_CARDS` | `1` | `0` = never use downloaded photos; no-entity scenes become typography cards |
| `AUTOTUBE_ENTITY_DIR` / `AUTOTUBE_STAGE_DIR` | `data/...` | Relocate the banks |
| `AUTOTUBE_FORCE_LIBASS` | unset | Test the no-libraqm Telugu text path |

## Try it without real cutouts

```
python scripts/selftest_canvas.py            # plan + layers + contact sheet (placeholder silhouettes)
python scripts/selftest_canvas.py --clips    # also renders real clips and assembles them
```
