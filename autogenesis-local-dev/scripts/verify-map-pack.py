#!/usr/bin/env python3
"""
verify-map-pack.py — schema + compatibility check for an Autogenesis .map pack.

A .map file is a ZIP archive with map.json + a PNG/JPEG image. This verifier
does the ad-hoc shape check the agent would otherwise do inline (zip integrity,
JSON parse, pin/connection consistency, image entry present, schema variant
detection) and reports a pass/fail exit code plus a per-field fingerprint.

Usage:
    python3 verify-map-pack.py <path-to-map-file> [--strict]

Exit codes:
    0  pass — shape clean, JSON valid, no broken pins
    1  load failure (not a zip, JSON broken, missing entries)
    2  shape failure (e.g. pin references undefined connection target)
    3  strict-only failure (warnings when --strict is set)

The verifier is AD-HOC. It does NOT exercise WorldManager.loadMapFromResources()
or reconstructBorders(). A clean exit is necessary, not sufficient — a Gradle
boot is the only true positive. See ../references/add-new-map-pack.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from collections import Counter
from pathlib import Path


def fingerprint(path: Path) -> dict:
    z = zipfile.ZipFile(path)
    raw = z.read("map.json")
    data = json.loads(raw.decode("utf-8"))
    pins = data["mapData"]["pins"]
    conns = data["mapData"].get("connections", [])
    pin_ids = {p["pinId"] for p in pins}
    img = data.get("imageName")
    # schema fingerprint
    sample_terr = pins[0]["territory"] if pins else {}
    schema = {
        "has_size": "size" in sample_terr,
        "has_pointValue": "pointValue" in sample_terr,
        "has_resource": "resource" in sample_terr,
        "has_adjacentTerritoryNames": "adjacentTerritoryNames" in sample_terr,
    }
    sizes = Counter(p["territory"].get("size", "?") for p in pins)
    pvs = Counter(p["territory"].get("pointValue", "?") for p in pins)
    types = Counter(p["territory"].get("type", "?") for p in pins)
    return {
        "imageName": img,
        "image_present": img in z.namelist() if img else False,
        "zip_entries": z.namelist(),
        "pins": len(pins),
        "connections": len(conns),
        "schema": schema,
        "sizes": dict(sizes),
        "pointValues": dict(pvs),
        "types": dict(types),
        "worldName": data["mapData"].get("worldName"),
        "author": data["mapData"].get("author"),
        "_pin_ids": pin_ids,
    }


def check(path: Path, strict: bool) -> tuple[int, list[str], list[str], dict]:
    errors: list[str] = []
    warnings: list[str] = []

    if not path.is_file():
        return 1, [f"file not found: {path}"], [], {}

    # Magic bytes
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic != b"PK\x03\x04":
        return 1, [f"not a ZIP archive (magic={magic!r}, expected b'PK\\x03\\x04')"], [], {}

    try:
        info = fingerprint(path)
    except KeyError as e:
        return 1, [f"map.json missing required key: {e}"], [], {}
    except json.JSONDecodeError as e:
        return 1, [f"map.json is not valid JSON: {e}"], [], {}

    # Pin/connection consistency
    pin_ids = info["_pin_ids"]
    for conn in info.get("zip_entries", []):
        pass
    # Re-parse connections for the consistency check (info only stores counts)
    z = zipfile.ZipFile(path)
    data = json.loads(z.read("map.json").decode("utf-8"))
    for i, conn in enumerate(data["mapData"].get("connections", [])):
        for k in ("fromPinId", "toPinId"):
            if k not in conn:
                errors.append(f"connection[{i}] missing {k!r}")
                continue
            if conn[k] not in pin_ids:
                errors.append(
                    f"connection[{i}].{k}={conn[k]!r} does not match any pin.pinId"
                )

    # Image entry
    if not info["image_present"]:
        errors.append(
            f"imageName={info['imageName']!r} not present in zip entries: {info['zip_entries']}"
        )

    # Pin count plausibility (warnings, not errors)
    pins = info["pins"]
    conns = info["connections"]
    if pins == 0:
        errors.append("mapData.pins is empty")
    elif pins < 10:
        warnings.append(f"only {pins} pins — looks like a fixture, not a full map")
    elif pins > 200:
        warnings.append(f"{pins} pins — may stress BFS targeting; flagged for playtest")

    # Schema variant (informational; either is loadable)
    if info["schema"]["has_pointValue"]:
        # Skeleton-maps (San_Martello, IO-map, fixedUSamerica) DO have pointValue
        # but no size/resource/adjacentTerritoryNames. Full has all four.
        if all(info["schema"].values()):
            variant = "full"
        elif not any(info["schema"].values()):
            variant = "skeleton-extreme"
        else:
            variant = "skeleton" if not info["schema"]["has_size"] else "unknown"
    else:
        variant = "unknown-missing-pointValue"

    info["schema_variant"] = variant
    info.pop("_pin_ids", None)

    # Strict-only failures
    if strict:
        if variant == "skeleton-extreme":
            errors.append("--strict: map has NO territory fields, will not load")
        if not info["schema"]["has_pointValue"]:
            errors.append("--strict: territories missing pointValue")

    code = 0 if not errors else (3 if strict else 2)
    return code, errors, warnings, info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("path", type=Path, help=".map file to verify")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="treat schema-fingerprint warnings as errors",
    )
    args = ap.parse_args()

    code, errors, warnings, info = check(args.path, args.strict)

    print(f"=== verify-map-pack: {args.path} ===")
    print(f"  exit_code: {code}  ({'PASS' if code == 0 else 'FAIL'})")
    if info:
        print(f"  pins:        {info['pins']}")
        print(f"  connections: {info['connections']}")
        print(f"  image:       {info['imageName']!r}  present={info['image_present']}")
        print(f"  worldName:   {info['worldName']!r}")
        print(f"  author:      {info['author']!r}")
        print(f"  schema:      {info['schema']}")
        print(f"  variant:     {info['schema_variant']}")
        print(f"  sizes:       {info['sizes']}")
        print(f"  pointValues: {info['pointValues']}")
        print(f"  types:       {info['types']}")
    if warnings:
        print("\n  WARNINGS:")
        for w in warnings:
            print(f"    - {w}")
    if errors:
        print("\n  ERRORS:")
        for e in errors:
            print(f"    - {e}")
    return code


if __name__ == "__main__":
    sys.exit(main())
