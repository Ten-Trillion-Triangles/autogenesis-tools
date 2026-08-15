# Commit Audit Procedure — Read-Only Style Review

When a user asks "is commit X TTT-style compliant?", the right answer requires scoping the
violation greps to **only the lines added in that commit**, not the whole post-commit file. This
reference gives the complete recipe with copy-pasteable scripts.

---

## The Core Gotcha

A file's **post-commit state** is not the same as **what the commit added**. Running
`grep -nE '^\s*if\s*\(...\)\s*\{' file.kt` on a modified file will flag pre-existing
same-line braces from earlier commits as if the current commit introduced them. False positives
confuse the user and waste cycles.

**Always scope to the diff** for any "is this commit compliant" question.

---

## The Audit Recipe

### Step 1 — List files changed

```bash
git diff --name-only <base>..<commit>
# e.g. git diff --name-only HEAD~1..HEAD
```

### Step 2 — Extract only the new lines from each .kt file

Use the Python script in `scripts/diff_line_extractor.py` (below) or inline:

```bash
git show <commit> -- 'src/main/kotlin/Pipeline/Foo.kt' | \
    grep -nE '^\+[^+]' | sed 's/^+//' > /tmp/new_lines.kt
```

The `-E '^\+[^+]'` excludes `+++ b/...` headers and stops at any `+` that is the start of a
hunk header.

### Step 3 — Run violation greps against the new-lines file

```bash
# Type 1 control-flow brace violations
grep -nE '^\s*(if|for|while|when)\s*\([^)]*\)\s*\{\s*$' /tmp/new_lines.kt

# Function-declaration brace violations
grep -nE '^\s*(override|private|internal|suspend)?\s*(suspend\s+)?fun\s+.+\)\s*\{\s*$' /tmp/new_lines.kt

# Kotlin catch same-line-brace (Kotlin uses NEXT-line)
grep -nE '^\s*\}\s*catch\s*\([^)]*\)\s*\{\s*$' /tmp/new_lines.kt

# Space-after-keyword or space-inside-parens
grep -nE '^\s*if\s+\(' /tmp/new_lines.kt
grep -nE 'if\s*\([^)]*\s\)' /tmp/new_lines.kt

# snake_case identifiers in val/var/fun
grep -nE '\b(val|var|fun)\s+[a-z]+_[a-z_0-9]+' /tmp/new_lines.kt
```

### Step 4 — Verify any post-commit violation is really in the commit

If a grep on the post-commit file flags something that didn't appear in step 3, confirm it was
pre-existing with `git blame`:

```bash
git blame -L 350,350 src/main/kotlin/Pipeline/Pipeline.kt
# Output: 2981242eb (EchoOfMaridia 2026-04-16 ...) if(tracingEnabled) {
# The SHA is older than <commit> → pre-existing, not in this commit.
```

### Step 5 — Build check

```bash
./gradlew :compileKotlin 2>&1 | tail -5
# BUILD SUCCESSFUL means at least the compiler is happy
```

### Step 6 — Report

Structure the report as:
- "Code added in this commit: N files, M lines. Audit results: 0 violations."
- "Pre-existing violations in modified files (NOT in this commit): list with file:line and blame SHA"
- "Build: PASS/FAIL"

Don't conflate the two. The user typically wants to know "did the commit break style?" — answer
that cleanly first, then offer to fix pre-existing issues as a drive-by.

---

## Python Diff Line Extractor

This script extracts the new lines from a commit diff along with the post-commit file line numbers
they appear on. This lets you cross-reference violations back to the file for blame or patching.

```python
import subprocess
import re
import os
import sys


def extract_new_lines(repo_dir: str, commit: str, file_path: str) -> list[tuple[int, str]]:
    """
    Return list of (post_commit_line_number, content) for every '+' line in
    the diff of `file_path` between (commit^1, commit].

    Skips the '+++' file header. Tracks new-file line numbers via the '@@' hunk header.
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
            # Removed line: don't advance new_line_num (line is gone in new file)
            pass
        else:
            # Context line (unchanged): advance new_line_num
            new_line_num += 1
    return result


# --- example usage ---
REPO = '/home/cage/Desktop/Workspaces/TPipe/TPipe'
COMMIT = 'HEAD'
BASE = f'{COMMIT}~1'

# Get changed files
files_proc = subprocess.run(
    ['git', 'diff', '--name-only', BASE, COMMIT],
    cwd=REPO, capture_output=True, text=True
)
files = [f for f in files_proc.stdout.strip().split('\n') if f.endswith('.kt')]

# Patterns to flag
patterns = {
    'if_same_line_brace':   re.compile(r'^\s*if\s*\([^)]*\)\s*\{'),
    'for_same_line_brace':  re.compile(r'^\s*for\s*\([^)]*\)\s*\{'),
    'while_same_line_brace':re.compile(r'^\s*while\s*\([^)]*\)\s*\{'),
    'when_same_line_brace': re.compile(r'^\s*when\s*\([^)]*\)\s*\{'),
    'fun_same_line_brace':  re.compile(r'^\s*(override|private|internal|suspend)?\s*(suspend\s+)?fun\s+.+\)\s*\{'),
    'catch_same_line_brace':re.compile(r'^\s*\}\s*catch\s*\([^)]*\)\s*\{'),
    'if_with_space':        re.compile(r'^\s*if\s+\('),
    'snake_case_ident':     re.compile(r'\b(val|var|fun)\s+[a-z]+_[a-z_0-9]+'),
}

violations = []
for f in files:
    for ln, content in extract_new_lines(REPO, COMMIT, f):
        for name, pat in patterns.items():
            if pat.search(content):
                violations.append((name, f, ln, content.rstrip()[:120]))

if not violations:
    print(f"OK: {len(files)} .kt files changed, 0 violations in NEW code")
else:
    print(f"FAIL: {len(violations)} violations in NEW code:")
    for name, f, ln, snippet in violations:
        print(f"  [{name}] {f}:{ln}  {snippet}")
```

---

## When to Use This

Use this audit recipe when:
- User says "audit commit X" / "check this PR for style" / "is this commit TTT-compliant?"
- User reports "I see style violations" after a commit and you need to verify whether they're new
- Reviewing a Claude Code / Codex / Gemini-generated commit before merging
- Running CI-style style gate on a specific commit (vs the whole branch)

Do NOT use this recipe when:
- User wants the whole codebase scanned (just run the violation greps against all .kt files)
- User is fixing known violations and wants the patches applied (use the "How to Find Violations
  in New Code" / "Applying Formatting Fixes" sections of the parent SKILL.md instead)

---

## Cross-Reference

For the violation patterns themselves (what counts as a violation), see the parent SKILL.md.
For the post-commit verification with `git blame`, see the "Fixing Formatter Damage" section
of the parent SKILL.md for the SHA-isolation pattern.
