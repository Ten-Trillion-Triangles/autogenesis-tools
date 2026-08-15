"""Safe same-line-brace fix for Kotlin (and other TTT-style C-family code).

CRITICAL PITFALLS this script avoids (learned the hard way):

1. **Don't pin { to the left margin when moving it below.** The new `{` line
   must use the EXACT same indent as the original `if`/`catch` line. User
   correction: "don't pin { to the left margin, it must go exactly below when
   you move it below." A naive script that hardcodes a brace column will
   mangle nested code at deeper indents.

2. **Don't replace `if ` (3 chars) with `if(` (3 chars).** Same length does
   not mean safe transform. The input `if (x) {` has 4 chars between `if`
   and the original `{` (space + paren + content + close paren). If you
   replace the `if ` (3 chars) with `if(` (3 chars), the original `(` at
   position 3 stays, producing `if((x) {` -- a double-paren syntax error.
   The compiler will catch it, but only if you run a build between
   scripting and committing.

3. **Don't use patch tool's `replace_all` with a hardcoded indent string.**
   If a file has the same pattern at multiple indent levels (e.g.
   `if(tracingEnabled) {` at 8-space, 16-space, and 24-space indents in
   the same file), a single `replace_all` with a hardcoded new_string
   will mangle every occurrence except the one matching the hardcoded
   indent. Use a script that captures the original indent via a regex
   group and backreferences it in the replacement.

Usage:
    python3 scripts/safe_same_line_brace_fix.py <file.kt> [<file.kt> ...]

Or programmatically:
    from safe_same_line_brace_fix import fix_file
    count = fix_file("src/main/kotlin/Foo.kt")
    print(f"Applied {count} fixes")

The script is intentionally narrow: it only handles the structural same-line
brace violation (`if(cond) {` and `} catch(e) {`). It does NOT touch:
- if/while/for/when statements where the brace is already on the next line
- `if (cond) return x` (no brace at all)
- `if (cond) expr else expr` (if as expression)
- `} else {` (same-line `else` is correct; the brace goes on the next line)

The regex used is:
    ^([ \t]*)(if|catch)[ \t]*\(([^)]*)\)[ \t]*\{$

The `[^)]*` for the condition is intentionally restrictive -- it does NOT
match nested parens. If a condition has nested parens (rare in practice;
the TPipe codebase had zero such cases in the violations audited), the
script will skip the line and you must patch it manually.

ALWAYS run `./gradlew :compileKotlin` after this script. The build is your
final safety net -- it caught the double-paren bug the first time around.
"""

import os
import re
import sys

# Indent + control keyword + optional space + ( + non-paren content + ) + optional space + { + EOL
PATTERN = re.compile(r'^([ \t]*)(if)[ \t]*\(([^)]*)\)[ \t]*\{$')

# } + optional space + catch + ( + non-paren content + ) + optional space + { + EOL
CATCH_PATTERN = re.compile(r'^([ \t]*)\}[ \t]*catch[ \t]*\(([^)]*)\)[ \t]*\{$')


def fix_line(line):
    """Apply the same-line-brace fix to a single line.

    Returns (new_line, fix_count). fix_count is 1 if a fix was applied,
    0 otherwise. Lines that don't match the violation pattern are returned
    unchanged.
    """
    if not line.endswith('\n'):
        return line, 0
    content = line[:-1]
    m = PATTERN.match(content)
    if m:
        indent, kw, cond = m.group(1), m.group(2), m.group(3)
        # CRITICAL: the new '{' line MUST use indent (the original if's
        # indent). Not a hardcoded column. This is the user's explicit
        # requirement: "{ must go exactly below when you move it below".
        return f"{indent}{kw}({cond})\n{indent}{{\n", 1
    m = CATCH_PATTERN.match(content)
    if m:
        indent, cond = m.group(1), m.group(2)
        return f"{indent}}}catch({cond})\n{indent}{{\n", 1
    return line, 0


def fix_file(path):
    """Apply the fix to all lines in a file. Returns total fix count."""
    with open(path) as fp:
        lines = fp.readlines()
    new_lines = []
    total = 0
    for line in lines:
        fixed, count = fix_line(line)
        new_lines.append(fixed)
        total += count
    if total > 0:
        with open(path, 'w') as fp:
            fp.writelines(new_lines)
    return total


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: safe_same_line_brace_fix.py <file.kt> [<file.kt> ...]")
        sys.exit(1)
    grand_total = 0
    for path in sys.argv[1:]:
        if not os.path.isfile(path):
            print(f"  {path}: not found")
            continue
        count = fix_file(path)
        if count:
            print(f"  {path}: {count} fixes")
            grand_total += count
        else:
            print(f"  {path}: no changes")
    print(f"\nTotal: {grand_total} fixes")
