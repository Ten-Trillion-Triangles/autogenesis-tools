#!/usr/bin/env python3
"""
verify-map-removal.py — source-tree verifier for the 4-path map removal.

Confirms that a removed map (e.g. fixedUSamerica.map) is fully purged from the
game server's discovery surfaces. Inverse of verify-map-exclusion.py (which
checks the exclusion of a NON-matchmaking INSTALLED map).

Usage:
    python3 verify-map-removal.py <MapName> [--workspace <path>]

Default workspace: /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis

Checks:
  [1] Resource NOT on disk (server/src/main/resources/maps/<MapName>.map absent)
  [2] GameInit.kt 2-player pool list does NOT contain "maps/<MapName>.map"
  [3] GameInit.kt 3-4 player pool list does NOT contain "maps/<MapName>.map"
  [4] GameInit.kt 'allMaps' rigged-map find-list does NOT contain "maps/<MapName>.map"
  [5] Negative-path regression assertion in MapResourceRegistryTest.kt
      (maps.none { it.equals("maps/<MapName>.map") })
  [6] No other code references <MapName> remain in server/src/
      (the negative-pin in MapResourceRegistryTest is the INTENDED reference;
      any other reference in server/src/ is residue)

This is a SOURCE-TREE check (no JVM runtime, no Gradle). It's the cheap
pre-check before running the canonical Gradle tests in
server/test/.../MapResourceRegistryTest.kt. Run BOTH:

  $ python3 verify-map-removal.py fixedUSamerica   # ~50ms, file-level
  $ ./gradlew :server:test --tests "*MapResourceRegistryTest" \
      --console=plain --offline --rerun-tasks       # ~70s, semantic
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Shared regex helpers (duplicated from verify-map-exclusion.py for self-containment;
# if these two scripts diverge, it's a code smell — keep them in sync)
_LIST_BLOCK = re.compile(r"listOf\s*\((.*?)\)", re.DOTALL)
STRING_LITERAL = re.compile(r'"([^"]+)"')


def extract_pool_lists(gameinit_src: str) -> dict[str, list[str]]:
    """Same heuristic as verify-map-exclusion.py: walk listOf(...) blocks, label
    them by the preceding comment line, return per-pool string lists."""
    pools: dict[str, list[str]] = {
        "two_player": [],
        "three_four_player": [],
        "all_maps_rigged": [],
    }
    for m in _LIST_BLOCK.finditer(gameinit_src):
        block_start = m.start()
        i = block_start - 1
        while i >= 0 and gameinit_src[i] in " \t":
            i -= 1
        if i < 0:
            continue
        line_end = i
        while i >= 0 and gameinit_src[i] != "\n":
            i -= 1
        line_start = i + 1
        preceding_line = gameinit_src[line_start:line_end + 1]
        literals = STRING_LITERAL.findall(m.group(1))

        lc = preceding_line.lower()
        if "2-player" in lc or "two player" in lc or "two-player" in lc:
            pools["two_player"].extend(literals)
        elif (
            "3-4 player" in lc
            or "3, 4 player" in lc
            or "3,4 player" in lc
            or "three-four player" in lc
            or "three or four" in lc
        ):
            pools["three_four_player"].extend(literals)

    # The rigged-map find-list is structured differently (no preceding comment
    # about player count). Find `val allMaps = listOf(...)` by name.
    for m in re.finditer(
        r"val\s+allMaps\s*=\s*listOf\s*\((.*?)\)",
        gameinit_src,
        re.DOTALL,
    ):
        pools["all_maps_rigged"].extend(STRING_LITERAL.findall(m.group(1)))

    return pools


def has_negative_pin_for(test_src: str, map_path: str) -> bool:
    """Confirm the negative-path assertion is present in MapResourceRegistryTest.kt.

    The assertion shape is:
      maps.none { it.equals("maps/<Name>.map", ignoreCase = true) }
    """
    needle = f'maps.none {{ it.equals("{map_path}", ignoreCase = true) }}'
    return needle in test_src


def find_other_references(workspace: Path, map_name: str) -> list[str]:
    """grep for <MapName> in server/src/ excluding the intentional negative-pin
    reference in MapResourceRegistryTest.kt. Returns list of file:line strings."""
    try:
        result = subprocess.run(
            ["grep", "-rn", map_name, "server/src/"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return ["TIMEOUT: grep took >10s (large repo)"]

    if result.returncode != 0 and not result.stdout.strip():
        return []

    refs: list[str] = []
    for line in result.stdout.splitlines():
        # The negative-pin in MapResourceRegistryTest.kt is the intentional one;
        # filter those out as "expected".
        if "MapResourceRegistryTest.kt" in line and "none" in line:
            continue
        # Also filter test-source references that just describe the absent file
        # in plain prose (the "Expected maps/<Name>.map to be ABSENT" message).
        if "MapResourceRegistryTest.kt" in line and "ABSENT" in line:
            continue
        refs.append(line)
    return refs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "map_name",
        help="map filename WITHOUT the 'maps/' prefix and without '.map' "
             "extension (e.g. 'fixedUSamerica')",
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
    reg_test = ws / "server/src/test/kotlin/org/ttt/autogenesis/server/maps/MapResourceRegistryTest.kt"
    resource = ws / "server/src/main/resources/maps" / f"{args.map_name}.map"

    checks: list[tuple[str, bool, str]] = []
    passed = 0

    def add(label: str, ok: bool, detail: str = "") -> None:
        nonlocal passed
        checks.append((label, ok, detail))
        if ok:
            passed += 1

    print(f"=== verify-map-removal: {target_path} ===")
    print(f"  workspace: {ws}\n")

    # [1] File deleted from disk
    add(
        f"[1] resource removed: server/src/main/resources/maps/{args.map_name}.map",
        not resource.exists(),
        f"absent (OK)" if not resource.exists() else f"still on disk (FAIL: {resource})",
    )

    # [2-4] GameInit.kt pool lists
    if not gameinit.is_file():
        add(f"[2-4] GameInit.kt found", False, f"not found at {gameinit}")
    else:
        src = gameinit.read_text()
        pools = extract_pool_lists(src)
        for k in pools:
            pools[k] = sorted(set(pools[k]))

        two_p = pools["two_player"]
        three_four = pools["three_four_player"]
        all_maps = pools["all_maps_rigged"]

        add(
            f"[2] GameInit.kt 2-player pool excludes '{target_path}'",
            target_path not in two_p,
            f"two_player pool: {two_p}" if two_p else "(no 2-player pool detected)",
        )
        add(
            f"[3] GameInit.kt 3-4 player pool excludes '{target_path}'",
            target_path not in three_four,
            f"three_four_player pool: {three_four}" if three_four else "(no 3-4 player pool detected)",
        )
        add(
            f"[4] GameInit.kt rigged-map 'allMaps' list excludes '{target_path}'",
            target_path not in all_maps,
            f"all_maps list: {all_maps}" if all_maps else "(allMaps list not detected — manual inspection needed)",
        )

    # [5] Negative-path pin in MapResourceRegistryTest.kt
    if not reg_test.is_file():
        add(f"[5] MapResourceRegistryTest.kt found", False, f"not found at {reg_test}")
    else:
        test_src = reg_test.read_text()
        add(
            f"[5] MapResourceRegistryTest.kt has maps.none { ... {target_path} } negative pin",
            has_negative_pin_for(test_src, target_path),
            f"if missing, add the assertTrue block: maps.none {{ it.equals(\"{target_path}\", ignoreCase = true) }}",
        )

    # [6] No other code references
    other_refs = find_other_references(ws, args.map_name)
    add(
        f"[6] no other code references '{args.map_name}' in server/src/",
        len(other_refs) == 0,
        f"residue: {other_refs}" if other_refs else "no residue (OK)",
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
                print(f"    - {label}")
                print(f"        {detail}")
        return 1
    print(f"  all 4 purge sites are consistent on disk.")
    print(f"  next: run ./gradlew :server:test --tests \"*MapResourceRegistryTest\" "
          f"--console=plain --offline --rerun-tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
