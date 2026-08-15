TPipe build / gradle / test gotchas — apply to all TPipe work, not just PCP.

## Gradle module naming

`settings.gradle.kts` declares `rootProject.name = "TPipe"`. That means:

- The repo lives at `/home/cage/Desktop/Workspaces/TPipe/` (workspace root).
- The TPipe source root is at `/home/cage/Desktop/Workspaces/TPipe/TPipe/` (one level deeper — confusingly the same name as the gradle project).
- `./gradlew :TPipe:test` is AMBIGUOUS — gradle tries to match `:TPipe:test` against the root project named `TPipe` AND against the literal `TPipe` subfolder. It fails with "Project with path ':TPipe' could not be found." Use either:
  - `./gradlew :test` (bare, from the TPipe/ dir) — runs the root project's tests, which includes the whole monorepo via subprojects.
  - `./gradlew :TPipe-MCP:test` — addresses a specific subproject by name.
- Never `cd /home/cage/Desktop/Workspaces/TPipe/TPipe && ./gradlew :TPipe:test` — the gradle wrapper reads `settings.gradle.kts` from the inner TPipe/ dir, which sets `rootProject.name = "TPipe"`, so `:TPipe:test` resolves to the root project that's literally named "TPipe". Works there but fails from anywhere else.

## JUnit 5 `Unit`-return trap

When a Kotlin test is `fun foo() = runBlocking { ... assertNotNull(x.path) }`, the function's inferred return type is whatever `assertNotNull(x.path)` returns — typically `String?`, not `Unit`. JUnit 5 silently skips `@Test` methods whose return type isn't `Unit`, with NO error in the test report.

**Symptom**: `./gradlew :test --tests "..."` reports BUILD SUCCESSFUL, the XML shows fewer tests than expected, no failure, no warning.

**Fix**: end the test with an explicit `Unit` statement:
```kotlin
@Test
fun foo() = runBlocking {
    val x = doThing()
    assertNotNull(x.path)
    Unit   // <- ensures inferred return type is Unit, JUnit picks it up
}
```

This applies to any test that uses `assertNotNull(obj.someProperty)` as the last line. Discovery trick: `javap -p build/classes/kotlin/test/<TestClass>.class` — if a `@Test` method shows `public final java.lang.String foo()` instead of `public final void foo()`, that's the bug.

## Python `python3 -c` quoting for random bytes

When a test generates random bytes and ships them as a Python `b'...'` literal via `python3 -c "<script>"`, the bytes-to-source expansion needs careful escaping. Naive `bts.toString(Charsets.UTF_8)` and friends produce broken scripts.

Bytes that MUST be escaped inside a Python bytes literal (`b'...'` or `b"..."`):

| Byte | Why |
|---|---|
| `0x27` (`'`) | terminates the literal |
| `0x5C` (`\`) | escapes the next char |
| `0x0A` (LF) | terminates the source line — Python sees `b'...\n...'` and reports `SyntaxError: unterminated string literal (detected at line 2)` |
| `0x0D` (CR) | similar source-line risk |
| `0x09` (TAB) | works as a raw byte but easy to forget — emit `\t` escape for clarity |

Other high bytes (0x80+) are fine as `\xNN` escapes. Printable ASCII (0x20-0x7E, excluding 0x5C and 0x27) can be emitted verbatim.

A correct emitter (Kotlin):
```kotlin
fun pythonBytesLiteral(bytes: ByteArray): String {
    val sb = StringBuilder("b'")
    for (b in bytes) {
        val u = b.toInt() and 0xFF
        when (u) {
            0x5C -> sb.append("\\\\")
            0x27 -> sb.append("\\'")
            0x09 -> sb.append("\\t")
            0x0A -> sb.append("\\n")
            0x0D -> sb.append("\\r")
            in 0x20..0x7E -> sb.append(b.toInt().toChar())
            else -> sb.append("\\x").append(u.toString(16).padStart(2, '0'))
        }
    }
    sb.append("'")
    return sb.toString()
}
```

## ARG_MAX limits `python3 -c`

Linux's `ARG_MAX` is typically 2 MB (check with `getconf ARG_MAX`). `python3 -c "<script>"` puts the entire script in `argv`. For random bytes that get ~4x-expanded into `\xNN` escapes, the script reaches ARG_MAX at around 500 KB of input bytes. Larger scripts via `-c` will fail with `IOException: Cannot run program "python3": error=7, Argument list too long`.

**Workarounds**:
- Write the script to a temp file (use `scriptFile.writeText(script, Charsets.UTF_8)` then pass the path as `argv[1]`). This is what `PythonExecutor.kt` does and it sidesteps ARG_MAX entirely.
- If you must use `-c` for a test, keep input <= 200 KB after escape expansion.

## Files ignored by `.gitignore` that you need to track

`TPipe/.gitignore` excludes:

- `/.github/workflows` — but the existing `gemini-*.yml` and `publish.yml` workflows ARE tracked, because they were added with `--force`. New workflow files (e.g., for a per-PR fuzz gate) need `git add --force -- <path>`.
- `**/AGENTS.md` — same situation. The module-level `AGENTS.md` files in the source tree are tracked via `--force`. Treat AGENTS.md as if it's gitignored and use `--force` when adding/updating.
- `infrastructure/.aws-sam/build/` — SAM build artifacts. Don't commit these.

## Transitive compile dependency on GenericOpenAI

Every gradle test run in the TPipe root project compiles **all** subprojects (`TPipe-OpenAI`, `TPipe-GenericOpenAI`, `TPipe-Bedrock`, etc.) before running the root project's tests. This means a compile error in any subproject blocks `gradle :test` for the root project too. The TPipe-GenericOpenAI subproject has been mid-refactor on Anthropic SSE support — pre-existing `contentOrNull`, `AnthropicSseParser.parseLine`, and duplicate `GenericOpenAIErrorResponse` errors will block every test run until repaired. When fixing TPipe-root tests, always check `gradle :TPipe-GenericOpenAI:compileKotlin` first if you see unexplained build failures.

## Tests using `subprocess` from Java vs. python3 from PATH

`ProcessBuilder("python3", ...)` on Linux uses `/usr/bin/python3` from PATH. The Linuxbrew install at `/home/linuxbrew/.linuxbrew/bin/python3` (Python 3.14) is what gets picked up. For Python tests:
- `print(...)` works.
- `import sys; sys.stdout.buffer.write(b'...')` works for byte-level output.
- The default `kotlin-scripting-jsr223` host does NOT expose `kotlin.io` — so `println("text")` inside `engine.eval()` fails with `ERROR Symbol is declared in module 'io.github.oshai.kotlinlogging' which does not export package 'kotlin.io'`. For Kotlin-executor tests, return the value as the script's last expression instead of using `println`.

## Pre-existing failing tests (not regressions from your work)

`PcpStandaloneTest.testPcPRequestSerialization` has been failing on master before any hardening work. Confirmed by `git stash` then re-run. Don't treat this as a regression you caused.

## CI conventions

`TPipe/.github/workflows/publish.yml` builds and publishes on tag push. There is no per-PR test workflow — the repo currently relies on the developer running `./gradlew :test` locally before push. When adding test gates, add them as new workflow files (use `--force` to track) and remember the per-PR workflow budget: ~15 min on ubuntu-latest, so don't put slow stress tests there. Manual-dispatch workflows with `workflow_dispatch` inputs work well for slow harnesses.