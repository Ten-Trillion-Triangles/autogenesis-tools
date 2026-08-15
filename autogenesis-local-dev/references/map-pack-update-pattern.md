# Map Pack In-Place Update Pattern

Use this when the canonical writing defaults change (or any other key in `mapData`) and you need to apply the new values to the 5 shipped map packs at `server/src/main/resources/maps/*.map` **without disturbing the rest of the map**.

## The Iron Rule (User Preference — Verified 2026-06-19)

**Do not touch files at random locations on the user's system.** The user is unforgiving about scope drift on this kind of work. The five shipped maps live at exactly:

```
server/src/main/resources/maps/
├── IO-map.map
├── Laurasiagondwana.map
├── San_Martello.map
├── fixedUSamerica.map
└── jupiter.map
```

Anything else (the kvisionApp-e2e test fixture at `kvisionApp-e2e/tests/fixtures/tiny-map.map`, runtime uploads in `UploadedMapRepository`, etc.) is out of scope unless the user names it explicitly.

## The Map Pack Format (Reminder)

Each `.map` file is a **ZIP archive** (not plain JSON despite the .map extension) with two entries — both STORED (no compression):

```
Foo.map
├── map.json   — the only file you modify
└── <image>    — the PNG background (map.png / laurasia_gondwana.png / san_martello.png)
```

See `references/map-system.md` for the full MapPack schema. The cardinal rule: the PNG and the rest of `mapData` (pins, connections, territory data, borders) are sacred. Touch only `mapData.writingAgentConfig` (or whichever sub-block you intend to change).

## The Safe Procedure (5 Steps)

### 1. Back up the originals to a safe location OUTSIDE the maps dir

```python
import shutil
from pathlib import Path
BACKUP = Path("/tmp/map_backup_<YYYY-MM-DD>")
BACKUP.mkdir(exist_ok=True)
for f in sorted((Path("server/src/main/resources/maps")).glob("*.map")):
    if not (BACKUP / f.name).exists():
        shutil.copy2(f, BACKUP / f.name)
```

Pick a dated path; the user can roll back with `cp /tmp/map_backup_<date>/*.map server/src/main/resources/maps/` if anything goes wrong. The `git checkout -- server/src/main/resources/maps/` route also works because git tracks the files — but a /tmp backup survives even a botched `git reset`.

### 2. Build the new sub-block in memory (don't mutate shared dicts)

If you have a function returning the new defaults (e.g. from `defaultWritingAgentConfig()` in Kotlin), parse it into a Python dict. If you only have a `.kt` source, parse it with regex (the WritingAgentDefaults format is stable enough). Either way, **deep-copy before each map**:

```python
new_wac = json.loads(json.dumps(new_wac_template))  # JSON round-trip = deep copy
```

This prevents shared-reference mutations from leaking between iterations.

### 3. For each map: read all entries, mutate `map.json` only, repack

```python
import os, json, zipfile
for f in sorted(MAPS.glob("*.map")):
    with zipfile.ZipFile(f, "r") as zin:
        entries = [(info, zin.read(info.filename)) for info in zin.infolist()]
    for i, (info, data) in enumerate(entries):
        if info.filename == "map.json":
            obj = json.loads(data.decode("utf-8"))
            obj["mapData"]["writingAgentConfig"] = new_wac  # mutate the only field you mean to
            entries[i] = (info, json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    # Write a new zip in a sibling temp file with the same compression
    tmp = f.with_suffix(".map.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as zout:
        for info, data in entries:
            new_info = zipfile.ZipInfo(filename=info.filename, date_time=info.date_time)
            new_info.compress_type = info.compress_type
            new_info.external_attr = info.external_attr
            new_info.create_system = info.create_system
            zout.writestr(new_info, data)
    os.replace(tmp, f)  # atomic on POSIX
```

Key choices:
- **Preserve `compress_type`** (0 = STORED) — matches the original
- **Preserve `date_time` and `external_attr`** — not strictly required, but keeps the zip metadata close to original
- **`os.replace(tmp, f)`** — atomic on POSIX; the user never sees a half-written file
- **JSON with `separators=(",", ":")`** — matches the existing compact style; ~15% smaller than default

### 4. Verify (mandatory — do not skip)

```python
# Reopen every map and prove:
for f in sorted(MAPS.glob("*.map")):
    with zipfile.ZipFile(BACKUP / f.name) as zb, zipfile.ZipFile(f) as za:
        # (a) PNG byte-identical
        o_png = next(n for n in zb.namelist() if n != "map.json")
        u_png = next(n for n in za.namelist() if n != "map.json")
        assert o_png == u_png, "PNG entry renamed!"
        assert hashlib.sha256(zb.read(o_png)).hexdigest() == hashlib.sha256(za.read(u_png)).hexdigest(), "PNG changed!"

        # (b) mapData minus the field you changed must be identical
        o = json.loads(zb.read("map.json").decode("utf-8"))
        u = json.loads(za.read("map.json").decode("utf-8"))
        o_md = dict(o.get("mapData", {})); o_wac = o_md.pop("writingAgentConfig", None)
        u_md = dict(u.get("mapData", {})); u_wac = u_md.pop("writingAgentConfig", None)
        assert o_md == u_md, f"Other mapData fields changed in {f.name}!"
        assert len(u["mapData"]["pins"]) == len(o["mapData"]["pins"]), "Pin count drifted!"

        # (c) the new value matches what you intended
        assert u_wac["selectionCriteria"][0]["chancePercent"] == 0, "Kafka should be 0%"
        # ... etc — assert the exact values you wrote
```

A failure on any of (a), (b), or (c) means roll back from `/tmp/map_backup_<date>/` and start over.

### 5. Report concretely

Show the user:
- One-line summary of what changed
- Per-map "before sha256[:16] / after sha256[:16]" so they can see the diff is real
- Pin count and imageName unchanged per map
- Rollback command (`cp /tmp/map_backup_<date>/*.map server/src/main/resources/maps/`)
- Note that the dev server is untouched — they can hot-reload or restart at their leisure

## Common Mistakes (Don't)

- **Editing the JSON in-place and resaving** — corrupts the binary PNG entry or strips the zip envelope. Always rebuild the archive.
- **Using `json.dumps(..., indent=2)`** — bloats file size; the originals are compact.
- **Mutating a shared `new_wac` dict across maps** — if the first map's serialization changes the object, subsequent maps pick up the change. Use the JSON round-trip deep-copy pattern.
- **Forgetting that some maps don't have a `writingAgentConfig` block** — adding it is fine, but your "verify other mapData fields unchanged" check must use `pop("writingAgentConfig", None)` (not direct access), or it'll raise KeyError.
- **Touching kvisionApp-e2e/test fixtures** — out of scope; the user said "the maps" and they mean the 5 shipped ones.

## Worked Example (2026-06-19 — applying new writing defaults to 5 maps)

Commit `0d0dc45d2` introduced `sharedModel/.../WritingAgentDefaults.kt` with new roll chances. The 5 shipped maps had stale or missing `writingAgentConfig` blocks. Procedure above was applied:

```
backup:    /tmp/map_backup_2026_06_19/  (5 files, 15.6 MB total)
operation: replaced mapData.writingAgentConfig in every .map
result:    PNGs byte-identical (5/5), other mapData unchanged (5/5),
           pin counts unchanged (94, 90, 49, 47, 87), all 5 maps now
           carry the new defaults from WritingAgentDefaults.kt
rollback:  cp /tmp/map_backup_2026_06_19/*.map server/src/main/resources/maps/
```

The full diff captured by the verification step is in the session's git status output (`M server/src/main/resources/maps/*.map`).
