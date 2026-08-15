# TTT Multi-Language Styling Rules Reference

Canonical TTT coding standards adapted for C-family languages: TypeScript, JavaScript, C, C++, C#, Java, Kotlin.

---

## Bracing Rules

### Type 1: Constructs WITH Control Keyword → Brace on NEXT Line

Applies to: `if`, `for`, `while`, `do-while`, `switch`, **`when`** (Kotlin), `function`, `class`, `struct`, `interface`, `enum`, `namespace`, `else`, `else if`

> ⚠️ **`when` is the most-frequently missed Type 1 construct in Kotlin.** Claude Code consistently produces `when(value) {` with same-line brace in Kotlin DSL code. Always include `when` in violation scans.

### Type 2: Lambdas, Initializers, Scope Functions → Brace on SAME Line

Applies to: lambda expressions, object/struct initializers, `finally`, scope functions, `static` blocks, `init` blocks, `companion object`

**Kotlin `try` and `catch` → NEXT line brace** (unlike Java/C# where `} catch(...) {` is idiomatic)

---

## Spacing Rules

### No Space After Control Keyword, No Space Inside Parentheses

### Space After Colon in Type Declarations Only

---

## Naming Conventions

### camelCase for Identifiers (Variables, Functions, Methods)
### PascalCase for Types (Classes, Structs, Interfaces, Enums, Type Aliases)
### UPPER_SNAKE_CASE for Constants Only

---

## Block Spacing: Two Blank Lines Between Top-Level Blocks

---

## Doc Comments

| Language | Format | Example |
|----------|--------|---------|
| TypeScript/JavaScript | JSDoc `/** */` | `/** Gets player name. */` |
| C | Doxygen `/** */` | `/** Initialize player. */` |
| C++ | Doxygen `/** */` | `/** Initialize player. */` |
| C# | XML Doc `///` | `/// Gets player name.` |
| Java | Javadoc `/** */` | `/** Gets player name. */` |
| Kotlin | KDoc `/** */` | `/** Gets player name. */` |

---

## Anti-Patterns

| Rule | Language | Reason |
|------|----------|--------|
| No `as any` / `as unknown` | TS/JS | Type safety violation |
| No `as Any` / `as!` | Kotlin | Type safety violation |
| No `goto` | C/C++ | Structured flow only |
| No silent exception swallow | C#/Java/Kotlin | Error visibility |
| No magic numbers | All | Use named constants |
| No broken code left behind | All | Quality requirement |

---

## Language-Specific Notes

### TypeScript/JavaScript
- Use `const` by default, `let` only when reassignment needed, never `var`
- Prefer interfaces over type aliases for object shapes
- Use `undefined` not `null` for optional values (unless interop requires)
- Arrow functions for callbacks: `() => {}` style

### C
- Function names: `snake_case` (per C convention) OR `camelCase` (TTT style) — snake_case accepted
- Typedef structs for opaque types: `typedef struct {} Player;`
- Always initialize pointers to `NULL`
- Use `const` for read-only parameters

### C++
- Use `std::string` over raw `char*`
- Use `nullptr` not `NULL`
- RAII for resource management
- Use `const` and `constexpr` aggressively

### C#
- Property names: PascalCase
- Method parameters: camelCase
- Use `string` not `String`, `int` not `Int32` (aliases preferred)
- `async`/`await` for async operations
- Use expression-bodied members where clear: `int Count => items.Count;`

### Java
- Use `final` for immutability
- Use `@Override` annotation when overriding methods
- Package-private is acceptable for internal classes
- Use diamond operator `<>` where type is clear

### Kotlin
- Use `val` by default, `var` only when needed
- Prefer `data class` for DTOs
- Use `when` over switch
- No semicolons
- `?.` and `?:` for null safety
- **`try` → NEXT line brace** (unlike Java `try { }`)
- **`catch` → NEXT line brace** (unlike Java `} catch(...) {`)
- **`when` → brace on next line of the `when` keyword itself**, not on each `->` branch

---

## Known Formatter Pitfalls

### TPipe: Bad Formatter Commit Recovery

A formatter applied to all 115 `.kt` files in TPipe produced incorrect output:
- Braces for `if/for/while` moved to the next line but at column 0 (no indentation)
- The diff showed `{` at the left margin inside nested blocks

**Detection**: `git show <commit> --stat` showing 80+ `.kt` files changed in one "Code formatting changes" commit.

**Fix**: Reset to the commit before the bad formatter commit. Do not attempt to patch individual files across 115 files.

```bash
git reset --soft <bad-commit>^1
# Verify with: cat -n src/main/kotlin/Pipeline/Manifold.kt | sed -n '727,732p' | cat -A
./gradlew build -x test
```

### Gradle Cache Corruption Fix

When `./gradlew :compileKotlin` fails with `Could not read workspace metadata from .../metadata.bin` errors across multiple cache directories, the caches are corrupted. Fix:

```bash
./gradlew --stop
rm -rf ~/.gradle/caches/8.14.3/dependencies-accessors
./gradlew :compileKotlin --no-daemon
```

If that still fails, nuke the whole version cache:
```bash
rm -rf ~/.gradle/caches/8.14.3
./gradlew :compileKotlin --no-daemon
```

Build must pass cleanly before declaring formatting fixes done.

### `when` — Most-Frequently Missed Type 1 Construct in Kotlin

Kotlin's `when` keyword is a Type 1 construct (brace on NEXT line) alongside `if/for/while/switch`. It is consistently missed in violation scans and is the most common Claude Code damage in Kotlin DSL code. Always include `when` in grep patterns:

```bash
# Correct pattern — includes when
grep -nE '^\s+(if|for|while|when)\s*\([^)]+\)\s*\{\s*$' <file>
```

The `when` keyword also appears in `when { branches }` (expression form) — same rule applies, brace goes on next line of the `when` keyword itself.

### Patch Tool Indentation Corruption

The patch tool can silently re-indent KDoc comment lines when replacing a function declaration that has a KDoc block. After a patch that modifies a function with a KDoc comment, always verify the doc comment indentation is still correct (3 spaces in Kotlin). If the patch caused doc comments to be re-indented to 5 spaces, immediately apply a second targeted patch to restore the correct 3-space indentation.

**Pattern**: `fun setInternalAgent(...) {` → patch replaces with next-line form → KDoc comment gets 5-space indent → second patch fixes KDoc back to 3 spaces.

### Using `cat -A` to Detect Invisible Characters

`grep` only shows text content — it cannot reveal tabs vs spaces or confirm brace indentation. After formatting fixes, always verify with:

```bash
sed -n 'N,Np' file.kt | cat -A
```

A properly indented brace at 4 spaces will show as `    {$` (4 spaces then brace then `$` for end-of-line). A tab will show as `→` (the tab character renders as `→` in `cat -A`). A brace at column 0 will show as `{$` with nothing before it.

### Nested `if` Inside `for` — Patch Inner First

When patching nested blocks, always fix the innermost `if` first, then the outer `for`. Patching outer `for` first can cause the inner `if`'s closing `}` to be consumed by the wrong pattern match.

### Claude Code Damage Pattern in Kotlin DSL Files

Claude Code consistently produces `fun path(...) {` with same-line brace on function declarations in TPipe Kotlin DSL files (PumpStationDsl.kt, JunctionDsl.kt, ManifoldDsl.kt, etc.). This is the single most common formatting violation in new TPipe code. The damage appears in "Phase 1" style commits that touch 507+ lines simultaneously.

Detection for new commits:
```bash
# Scan all new .kt files for function declaration violations
git diff --name-only <commit> | grep '\.kt$' | while read f; do
  grep -nE '^\s+(override|private|internal|suspend)?\s*fun .+\)\s*\{\s*$' "$f" && echo "VIOLATION in $f"
done
```

### TPipe Branch Contamination Pattern

Commits intended for `startup-license` branch (startup license swap, README warning banner additions) can contaminate `main` and other branches via merge commits. The contamination chain typically looks like:
- `42fcad0f` — "implement new startup license" (AGPL → Startup License)
- `cb1e288d` — "update main readme" (adds warning banner)
- `70109eb2` — "adjust for startup branch"
- `371c9ab6` — "Update LICENSE"

These commits should only exist on `startup-license` branch. If `main` shows Startup License and the warning banner, contamination has occurred. Recovery: pull the correct LICENSE and README from a pre-contamination commit (e.g. `a8157e5a` on `main`) and commit directly without history rewrite.

---

## Quick Reference Card

| Construct | Brace Placement |
|-----------|----------------|
| `if()` / `for()` / `while()` / `when` / `switch` | **NEXT** line |
| `else` / `else if` | **NEXT** line |
| Lambda `() => {}` / `{ }` as value | **SAME** line |
| Kotlin `try` | **NEXT** line |
| Kotlin `catch` | **NEXT** line |
| Object/Block initializer `{ }` | **SAME** line |
| Scope functions (`apply`, `also`, etc.) | **SAME** line |
| Kotlin DSL `fun build() { }` (lambda param) | **NEXT** line (function declaration) |