#!/usr/bin/env python3
"""Convert local source-code path citations in a markdown file to GitHub blob URLs.

This is the canonical converter for TTT blog posts that cite TPipe / Autogenesis
source code. The user has been clear: never ship `/home/cage/Desktop/...`
absolute paths in published blog content. The public reader has the open-source
repo, not the author's drive.

Usage:
    python3 scripts/local-paths-to-github-blobs.py <markdown-file> \\
        --repo https://github.com/Ten-Trillion-Triangles/Open-Autogenesis \\
        --path-prefix Autogenesis/server/src/main/kotlin

Default repo/path-prefix pair matches the canonical Open-Autogenesis layout
verified 2026-07-10: Autogenesis source lives at
    <repo>/blob/main/Autogenesis/server/src/main/kotlin/<rest>
For TPipe core, override --repo and --path-prefix accordingly.

The converter rewrites backtick-wrapped `path/to/file.kt:LINE` and
`path/to/file.kt:LINE-LINE` citations. It does NOT touch bare paths in
prose, code blocks, or URLs — those are out of scope.

Audit pattern after running:
    grep -c "/home/cage" dist/client/blog/<slug>/index.html   # must be 0
    grep -c "github.com/Ten-Trillion-Triangles/Open-Autogenesis" \\
        src/content/blog/<slug>.md                          # must match citation count

The 2026-07-10 orchestration-matters-more-than-model-intelligence post was
the first blog post to ship with this conversion applied. 18 inline citations
were rewritten; static build verified clean.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Citation patterns this converter handles (inside backticks only):
#   `validator.kt:97`
#   `identifyPlayAgent.kt:128-133`
#   `globals/BedrockConfig.kt:436`
# Bare paths in prose (e.g. "see the validator.kt file") are NOT touched —
# those are user-facing wording and need a manual pass.
#
# Each (file, line-range) tuple becomes a markdown link to
# <repo>/blob/main/<path-prefix>/<file>#L<first-line>
#
# File-to-repo-relative-path mapping is per project. Override --path-prefix
# for non-Autogenesis repos. For Open-Autogenesis, files live at
#   <path-prefix>/agent/builders/.../<file>
#   <path-prefix>/globals/<file>
#   <path-prefix>/<other>/<file>

# Canonical file-path-to-repo-relative-path map for the Autogenesis repo.
# Add entries here as new files get cited across posts.
AUTOGENESIS_FILE_TO_REPO_PATH: dict[str, str] = {
    "validator.kt": "agent/builders/validateAction/validator.kt",
    "identifyPlayAgent.kt": "agent/builders/validateAction/identifyPlayAgent.kt",
    "BedrockConfig.kt": "globals/BedrockConfig.kt",
    # Add more as the codebase and blog surface grows.
}

DEFAULT_REPO = "https://github.com/Ten-Trillion-Triangles/Open-Autogenesis"
DEFAULT_PATH_PREFIX = "Autogenesis/server/src/main/kotlin"


def github_url(repo: str, path_prefix: str, file: str, line: int | None) -> str:
    base = f"{repo.rstrip('/')}/blob/main/{path_prefix.strip('/')}/{file}"
    if line is not None:
        return f"{base}#L{line}"
    return base


def resolve_repo_path(file: str, file_map: dict[str, str]) -> str | None:
    """Return repo-relative path for a known file, or None if unmapped."""
    return file_map.get(file)


def convert_file(
    md_path: Path,
    repo: str,
    path_prefix: str,
    file_map: dict[str, str],
) -> tuple[int, list[str]]:
    """Rewrite citations in md_path. Returns (rewrite_count, unmapped_files).

    A citation is a backtick-wrapped `file.kt:LINE` or `file.kt:LINE-LINE`.
    Bare prose paths are untouched.
    """
    text = md_path.read_text()
    unmapped: set[str] = set()
    rewrites = 0

    # Match backtick-wrapped `file.kt:LINE` or `file.kt:LINE-LINE` citations.
    # Filename is alphanumeric + dots + slashes; line is digits or digits-digits.
    citation_re = re.compile(
        r"`(?P<file>(?:[a-zA-Z][\w./-]*\.kt)):(?P<line>\d+(?:-\d+)?)`"
    )

    def replace(match: re.Match[str]) -> str:
        nonlocal rewrites
        file = match.group("file")
        line_part = match.group("line")
        first_line = int(line_part.split("-")[0])

        # If file isn't a bare .kt (e.g. globals/BedrockConfig.kt), strip prefix.
        basename = file.rsplit("/", 1)[-1]
        repo_path = resolve_repo_path(basename, file_map)
        if repo_path is None:
            unmapped.add(file)
            return match.group(0)  # leave untouched; manual fix needed

        url = github_url(repo, path_prefix, repo_path, first_line)
        rewrites += 1
        return f"[`{file}:{line_part}`]({url})"

    new_text = citation_re.sub(replace, text)
    if new_text != text:
        md_path.write_text(new_text)

    return rewrites, sorted(unmapped)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "markdown",
        type=Path,
        help="Path to the markdown file to rewrite (modified in place).",
    )
    parser.add_argument(
        "--repo",
        default=DEFAULT_REPO,
        help=f"Canonical repo URL (default: {DEFAULT_REPO}).",
    )
    parser.add_argument(
        "--path-prefix",
        default=DEFAULT_PATH_PREFIX,
        help=(
            "Path under repo root where source files live "
            f"(default: {DEFAULT_PATH_PREFIX}). "
            "For TPipe core, use 'TPipe/src/main/kotlin'."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print rewrites without modifying the file.",
    )
    args = parser.parse_args()

    if not args.markdown.exists():
        print(f"error: {args.markdown} does not exist", file=sys.stderr)
        return 1

    if args.dry_run:
        original = args.markdown.read_text()
        # Run convert against a temp file to surface what would change.
        tmp = args.markdown.with_suffix(args.markdown.suffix + ".dryrun")
        tmp.write_text(original)
        rewrites, unmapped = convert_file(tmp, args.repo, args.path_prefix, AUTOGENESIS_FILE_TO_REPO_PATH)
        dry_text = tmp.read_text()
        tmp.unlink()
        # Print the diff outline.
        for i, (orig_line, new_line) in enumerate(
            zip(original.splitlines(), dry_text.splitlines()), 1
        ):
            if orig_line != new_line:
                print(f"L{i}: {new_line[:160]}")
        print(f"\nwould rewrite {rewrites} citation(s)")
        if unmapped:
            print(f"unmapped files (manual fix needed): {unmapped}")
        return 0

    rewrites, unmapped = convert_file(
        args.markdown, args.repo, args.path_prefix, AUTOGENESIS_FILE_TO_REPO_PATH
    )
    print(f"rewrote {rewrites} citation(s) in {args.markdown}")
    if unmapped:
        print(f"unmapped files (manual fix needed): {unmapped}")
        print(
            "Add entries to AUTOGENESIS_FILE_TO_REPO_PATH in this script "
            "and re-run, or fix manually."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())