#!/usr/bin/env python3
"""
Diff line extractor for TTT-style commit audits.

Extracts the new lines (+ hunks) from each .kt file in a commit, with their
post-commit line numbers. Lets you cross-reference style violations back to
the file for git blame or patching.

Usage:
    python3 diff_line_extractor.py <repo_dir> <base> <commit>

Example:
    python3 diff_line_extractor.py /home/cage/Desktop/Workspaces/TPipe/TPipe HEAD~1 HEAD

Output:
    Prints to stdout. Format: VIOLATION_TYPE  file:line  snippet
    Prints "OK" line if no violations found.

Patterns checked (mirrors the violation greps in SKILL.md):
    - if/for/while/when with same-line brace
    - fun declaration with same-line brace
    - catch with same-line brace
    - if with space after keyword
    - snake_case identifier in val/var/fun
"""
import subprocess
import re
import sys


def extract_new_lines(repo_dir: str, commit: str, file_path: str) -> list:
    """
    Return list of (post_commit_line_number, content) for every '+' line in
    the diff of `file_path` between (commit^1, commit].
    """
    diff = subprocess.run(
        ['git', 'show', commit, '--', file_path],
        cwd=repo_dir, capture_output=True, text=True
    )
    lines = diff.stdout.split('\n')

    new_line_num = 0
    result = []
    in_hunk = False
    for line in lines:
        if line.startswith('@@'):
            m = re.search(r'\+(\d+)', line)
            if m:
                new_line_num = int(m.group(1))
            in_hunk = True
            continue
        if line.startswith('+++') or line.startswith('---'):
            continue
        if not in_hunk:
            continue
        if line.startswith('+') and not line.startswith('+++'):
            content = line[1:]
            result.append((new_line_num, content))
            new_line_num += 1
        elif line.startswith('-'):
            pass
        else:
            new_line_num += 1
    return result


PATTERNS = {
    'if_same_line_brace':    re.compile(r'^\s*if\s*\([^)]*\)\s*\{'),
    'for_same_line_brace':   re.compile(r'^\s*for\s*\([^)]*\)\s*\{'),
    'while_same_line_brace': re.compile(r'^\s*while\s*\([^)]*\)\s*\{'),
    'when_same_line_brace':  re.compile(r'^\s*when\s*\([^)]*\)\s*\{'),
    'fun_same_line_brace':   re.compile(r'^\s*(override|private|internal|suspend)?\s*(suspend\s+)?fun\s+.+\)\s*\{'),
    'catch_same_line_brace': re.compile(r'^\s*\}\s*catch\s*\([^)]*\)\s*\{'),
    'if_with_space':         re.compile(r'^\s*if\s+\('),
    'snake_case_ident':      re.compile(r'\b(val|var|fun)\s+[a-z]+_[a-z_0-9]+'),
}


def audit_commit(repo_dir: str, base: str, commit: str) -> int:
    files_proc = subprocess.run(
        ['git', 'diff', '--name-only', base, commit],
        cwd=repo_dir, capture_output=True, text=True
    )
    files = [f for f in files_proc.stdout.strip().split('\n') if f.endswith('.kt')]

    violations = []
    for f in files:
        for ln, content in extract_new_lines(repo_dir, commit, f):
            for name, pat in PATTERNS.items():
                if pat.search(content):
                    violations.append((name, f, ln, content.rstrip()[:120]))

    if not violations:
        print(f"OK: {len(files)} .kt files changed, 0 violations in NEW code ({base}..{commit})")
        return 0

    print(f"FAIL: {len(violations)} violations in NEW code ({base}..{commit}):")
    for name, f, ln, snippet in violations:
        print(f"  [{name}] {f}:{ln}  {snippet}")
    return 1


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    repo_dir, base, commit = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.exit(audit_commit(repo_dir, base, commit))
