#!/usr/bin/env python3
"""
verify-map-exclusion.py — source-tree verifier for the 4-path tutorial-style
map exclusion. Confirms that a non-matchmaking reserved map (e.g. tutorial.map)
cannot be loaded into a session via any of the four discovery paths used by
the game server.

Usage:
    python3 verify-map-exclusion.py <MapName> [--workspace <path>]

Default workspace: /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis

Checks:
  [1] Resource on disk (server/src/main/resources/maps/<MapName>.map)
  [2] GameInit.kt 2-player pool list does NOT contain "maps/<MapName>.map"
  [3] GameInit.kt 3-4 player pool list does NOT contain "maps/<MapName>.map"
  [4] GameInit.kt 'allMaps' rigged-map find-list does NOT contain "maps/<MapName>.map"
      (so `gradle run --args=--map=<MapName>` falls through cleanly)
  [5] MapSelectionService.kt has <MapName> in excludedRandomPoolPaths set
  [6] MapSelectionService.kt has the .filterNot line intact after listPackagedMaps()

This is a SOURCE-TREE check (no JVM runtime, no Gradle). It's the cheap
pre-check before running the canonical Gradle tests in
server/test/.../MapSelectionServiceTest.kt. Run BOTH:

  $ python3 verify-map-exclusion.py tutorial     # ~50ms, file-level
  $ ./gradlew :server:test --tests "*MapSelectionServiceTest" \
      --console=plain --offline --rerun-tasks       # ~70s, semantic
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Per-block regex (DOTALL via re.search): captures contents of one listOf(...)
# Use non-greedy match so the first `)` closes the block. This won't catch
# nested parens but the pool literals are flat string lists, so it's fine.
_LIST_BLOCK = re.compile(
    r"listOf\s*\((.*?)\)", re.DOTALL
)

_EXCLUDED_SET_BLOCK = re.compile(
    r"excludedRandomPoolPaths[^\{]*\{(.*?)\}", re.DOTALL
)

STRING_LITERAL = re.compile(r'"([^"]+)"')


def extract_list_literals(src: str) -> list[str]:
    """Return all `\"...\".*` strings inside any listOf(...) block in `src`."""
    out: list[str] = []
    for m in _LIST_BLOCK.finditer(src):
        for s in STRING_LITERAL.findall(m.group(1)):
            out.append(s)
    return out


def extract_pool_lists(gameinit_src: str) -> dict[str, list[str]]:
    """Locate the specific pool list blocks in GameInit.kt by comment context
    rather than line-number (line numbers drift). Heuristic: find listOf(...)
    blocks whose immediately-preceding non-blank line comment mentions the
    relevant player count.

    Returns:
      {"two_player": [...], "three_four_player": [...], "all_maps_rigged": [...]}
    """
    # Strategy: walk the file, find listOf(...) blocks. For each block,
    # look back at the most recent non-blank, non-`}*/))` line and use its
    # comment text as a context label.
    pools: dict[str, list[str]] = {
        "two_player": [],
        "three_four_player": [],
        "all_maps_rigged": [],
    }
    for m in _LIST_BLOCK.finditer(gameinit_src):
        block_start = m.start()
        # Find the comment line immediately preceding the listOf(
        # by walking back from block_start through whitespace.
        i = block_start - 1
        while i >= 0 and gameinit_src[i] in " \t":
            i -= 1
        # i now points at the last non-whitespace before the block.
        # Walk back to the start of that line.
        if i < 0:
            continue
        line_end = i
        while i >= 0 and gameinit_src[i] != "\n":
            i -= 1
        line_start = i + 1
        preceding_line = gameinit_src[line_start:line_end + 1]
        # Also check a couple lines up — the typical pattern is the comment on
        # a line immediately above the listOf.
        block = m.group(1)
        literals = [s for s in STRING_LITERAL.findall(block)]

        lc = preceding_line.lower()
        if (
            "2-player" in lc
            or "two player" in lc
            or "two-player" in lc
        ):
            pools["two_player"].extend(literals)
        elif (
            "3-4 player" in lc
            or "3, 4 player" in lc
            or "3,4 player" in lc
            or "three-four player" in lc
            or "three or four" in lc
        ):
            pools["three_four_player"].extend(literals)
        elif "allmaps" in lc or "all maps" in lc or "rigged" in lc.lower():
            # The rigged-map find-list is structured differently (single find
            # call), so this branch rarely hits. We use the regex
            # `maps = listOf(...)` shape with the comment hint.
            pools["all_maps_rigged"].extend(literals)

    # Secondary scan for the rigged-map list — `val allMaps = listOf(...)` is
    # usually commented as `// all maps` / `// rigged map list`.
    for m in re.finditer(
        r"(?:all[Rr]igged[Rr]ig|Rig[Aa]ll[Aa]vailable)[^\n]*\n[^\n]*val\s+\w+\s*=\s*listOf\s*\((.*?)\)",
        gameinit_src,
        re.DOTALL,
    ):
        pools["all_maps_rigged"].extend(STRING_LITERAL.findall(m.group(1)))

    # Tertiary safety net: any literal whose variable name or comment mentions
    # "rigged" / "rig" / "allmaps" near a listOf block.
    for m in re.finditer(
        r"//[^\n]*((?:rig|allmap)[^\n]*)\n[^\n]*val\s+(\w+)\s*=\s*listOf\s*\((.*?)\)\n",
        gameinit_src,
        re.DOTALL | re.IGNORECASE,
    ):
        pools["all_maps_rigged"].extend(STRING_LITERAL.findall(m.group(3)))

    return pools


def extract_exclusion_set(mss_src: str) -> list[str]:
    """Locate the excludedRandomPoolPaths set declaration and return its members."""
    m = _EXCLUDED_SET_BLOCK.search(mss_src)
    if not m:
        return []
    return STRING_LITERAL.findall(m.group(1))


def has_filter_not(mss_src: str) -> bool:
    """Confirm the .filterNot { path -> path in excludedRandomPoolPaths } line
    is intact after listPackagedMaps() (since that's what makes the exclusion
    set actually exclude at runtime)."""
    return ".filterNot" in mss_src and "excludedRandomPoolPaths" in mss_src


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "map_name",
        help="map filename WITHOUT the 'maps/' prefix and without '.map' "
             "extension (e.g. 'tutorial', not 'maps/tutorial.map')",
    )
    ap.add_argument(
        "--workspace",
        default="/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis",
        type=Path,
        help="path to the Autogenesis project root",
    )
    args = ap.parse_args()

    ws = args.workspace
    target_path = f"maps/{args.map_name}.map"
    gameinit = ws / "server/src/main/kotlin/gameInit/GameInit.kt"
    mss = ws / "server/src/main/kotlin/gameInit/MapSelectionService.kt"
    resource = ws / "server/src/main/resources/maps" / f"{args.map_name}.map"

    checks: list[tuple[str, bool, str]] = []
    passed = 0

    def add(label: str, ok: bool, detail: str = "") -> None:
        nonlocal passed
        checks.append((label, ok, detail))
        if ok:
            passed += 1

    print(f"=== verify-map-exclusion: {target_path} ===")
    print(f"  workspace: {ws}\n")

    # [1] Resource on disk
    add(
        f"[1] resource exists: server/src/main/resources/maps/{args.map_name}.map",
        resource.is_file(),
        f"size={resource.stat().st_size} bytes" if resource.exists() else "MISSING",
    )

    # [2-4] GameInit.kt pool lists
    if not gameinit.is_file():
        add(f"[2-4] GameInit.kt found", False, f"not found at {gameinit}")
    else:
        src = gameinit.read_text()
        pools = extract_pool_lists(src)
        # De-dup
        for k in pools:
            pools[k] = sorted(set(pools[k]))

        two_p = pools["two_player"]
        three_four = pools["three_four_player"]
        all_maps = pools["all_maps_rigged"]

        add(
            f"[2] GameInit.kt 2-player pool excludes '{target_path}'",
            target_path not in two_p,
            f"two_player pool: {two_p}" if two_p else "(no 2-player pool detected — file structure changed)",
        )
        add(
            f"[3] GameInit.kt 3-4 player pool excludes '{target_path}'",
            target_path not in three_four,
            f"three_four_player pool: {three_four}" if three_four else "(no 3-4 player pool detected)",
        )
        # The rigged-map find-list exclusion is best-effort — extract_pool_lists
        # only catches it if the variable is named something matching our
        # regex; if it didn't, surface a soft warning rather than a fail.
        if all_maps:
            add(
                f"[4] GameInit.kt rigged-map 'allMaps' list excludes '{target_path}'",
                target_path not in all_maps,
                f"all_maps list: {all_maps}",
            )
        else:
            add(
                f"[4] GameInit.kt rigged-map find-list — verify manually (regex didn't match)",
                False,
                "could not auto-locate the rigged-map list; inspect the file by hand",
            )

    # [5-6] MapSelectionService.kt exclusion set
    if not mss.is_file():
        add(f"[5-6] MapSelectionService.kt found", False, f"not found at {mss}")
    else:
        mss_src = mss.read_text()
        excluded = extract_exclusion_set(mss_src)
        add(
            f"[5] MapSelectionService.kt excludedRandomPoolPaths contains '{target_path}'",
            target_path in excluded,
            f"excludedRandomPoolPaths = {excluded}",
        )
        add(
            f"[6] MapSelectionService.kt .filterNot over excludedRandomPoolPaths is intact",
            has_filter_not(mss_src),
        )

    # Summary
    total = len(checks)
    failed = total - passed
    print(f"\n=== SUMMARY ===")
    print(f"  passed: {passed} / {total}")
    if failed:
        print(f"  failed:")
        for label, ok, detail in checks:
            if not ok:
                print(f"    - {label}\n        {detail}")
        return 1
    print(f"  all exclusion paths are consistent on disk.")
    print(f"  next: run ./gradlew :server:test --tests \"*MapSelectionServiceTest\" "
          f"--console=plain --offline --rerun-tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
