# Kotlin Wire-Format Bump Recipe — Standalone Compiler + kotlinx-serialization

When you bump a wire-format field on a TPipe `TracePayload` (or any other
`@Serializable` data class on the v1 ↔ v2 boundary between TPipe client and TPipe-TraceServer,
or any other TPipe wire contract), the test surface is small but the risk is wire-compat.
`./gradlew :test --tests ...` works fine when the build is healthy, but when you need a
FAST independent check — e.g. you want to confirm "does encoding with the new optional
field produce JSON byte-identical to the v1 form?" — the gradle round trip is overkill.
This recipe shows how to compile a small Kotlin verifier with `kotlinc` directly,
run it, and inspect the wire bytes in seconds.

## When to use this recipe (vs. gradle test)

Use this recipe when:
- You are verifying a wire-format property (default-null handling, omit-vs-explicit-null,
  unknown-key tolerance, version-field shape) and want sub-second feedback.
- The full gradle build is slow or failing for unrelated reasons (daemon crash, etc.)
  and you need to prove a wire change in isolation.
- You want to capture the exact bytes that hit the wire and inspect them.

Do NOT use this recipe for:
- Anything that touches the full TPipe runtime (no `PipeTracer`, no `dispatchTrace` —
  those require gradle test).
- Live harness runs (`PumpStationMiniMaxLiveTest`, etc.). Still use gradle.

## The recipe (5 steps)

### Step 1 — Locate the runtime jars on disk

```bash
KOTLINX_JSON=$(find ~/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlinx/kotlinx-serialization-json-jvm -name "*.jar" ! -name "*-sources.jar" 2>/dev/null | head -1)
KOTLINX_CORE=$(find ~/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlinx/kotlinx-serialization-core-jvm -name "*.jar" ! -name "*-sources.jar" 2>/dev/null | head -1)
KOTLIN_SERIAL_PLUGIN=/home/linuxbrew/.linuxbrew/Cellar/kotlin/2.3.21/libexec/lib/kotlinx-serialization-compiler-plugin.jar
```

The plugin path assumes linuxbrew-managed `kotlinc 2.3.21`. If yours is elsewhere:

```bash
find / -name "kotlinx-serialization-compiler-plugin.jar" 2>/dev/null
```

(`kotlin-serialization-compiler-plugin-embeddable-X.Y.Z.jar` from the gradle caches
also works with `-Xplugin=`, but the linuxbrew-installed variant requires no `-Xplugin`
tweaks because it bundles the right `@Serializable` runtime handler.)

### Step 2 — Author the verifier at `/tmp/hermes-verify-<feature>/main.kt`

The package MUST match the production `TracePayload` package so the serializer
resolution matches. Mirror the production data class shape exactly — do not copy from
a stale memory; read the file.

```kotlin
package com.TTT.Debug

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

// Mirror of production data class — verify against RemoteTraceDispatcher.kt:14
@Serializable
data class TracePayload(
    val pipelineId: String,
    val htmlContent: String,
    val name: String,
    val status: String,
    val kind: String? = null,  // the new optional field
)

fun main() {
    // v1-shape decode test, v2 round-trip test, omitted-vs-null test, etc.
    // See "Checklist for a wire bump" below.
}
```

### Step 3 — Compile

```bash
cd /tmp/hermes-verify-<feature> && \
kotlinc -Xplugin="$KOTLIN_SERIAL_PLUGIN" \
  -classpath "$KOTLINX_JSON:$KOTLINX_CORE" \
  main.kt -include-runtime -d verifier.jar 2>&1 | tail -10
```

If `serializer()` is "unresolved" in your driver, you forgot `-Xplugin` — the
`@Serializable` annotation is a compile-time transformation that requires the
plugin. Re-run with the plugin path set.

If the verifier JAR was emitted and `ls verifier.jar` shows the file size > 100KB,
compile succeeded.

### Step 4 — Run

```bash
java -classpath "verifier.jar:$KOTLINX_JSON:$KOTLINX_CORE" com.TTT.Debug.MainKt
```

Exit code is the test result: `0` for all-pass, `1` for any fail. Each check should
print `PASS: <label>` or `FAIL: <label>` followed by the count summary.

### Step 5 — Cleanup

Delete `/tmp/hermes-verify-<feature>/` when done. Note: the verification
sandbox may gate `rm -rf /tmp/...` operations. If it does, leave the directory in
place — it's outside the repo, untracked, and harmless. Document the leftover in your
session summary so the operator knows.

## Checklist for a wire bump

Minimum checks for any nullable-additive wire change:

1. **v1 decode** — feed the OLD JSON shape (without the new field) and assert the
   decoder returns `newField == null` (or whatever the documented default is).
2. **v2 round-trip** — encode a value with the new field set, decode, assert equal.
3. **Default-null encode** — encode a value with the new field = null (default) and
   capture the bytes. Confirm whether the encoder OMITS the key or writes
   `"newField":null` explicitly. **See "kotlinx-serialization null behavior" below** —
   the result is "key omitted," which is the v1-compatible form and is what you want.
4. **Round-trip with null** — decode the bytes from check (3) and assert
   `newField == null`.
5. **Arbitrary-string round-trip** — encode with a non-default value (`"pumpstation"`,
   `"manifold"`, etc.) to confirm the field isn't accidentally constrained to an enum.

Keep checks 1-2 only if you need minimal proof the bump compiles. Run all 5 when you
want wire-compat verification, which is what v1 ↔ v2 contracts deserve.

## kotlinx-serialization null behavior (empirically verified 2026-07-11)

When a `@Serializable` field is a nullable type (`String?`, `Int?`, etc.) and the
value is `null` at encoding time, **kotlinx-serialization OMITS the key entirely** by
default. The encoded JSON does NOT contain the key at all (not `"key":null`).

Empirical proof from the wire-bump recipe verifier for `TracePayload` with
`val kind: String? = null`:

```
// Encoded: kind = null (the default)
// Output: {"pipelineId":"p-3","htmlContent":"<html/>","name":"x","status":"FAILURE"}
//                                                    ^ no "kind" key at all
```

The decoder, in turn, treats a missing key on a nullable field as `null` (the type's
default), so the round-trip is identity.

**Why this matters for wire compat**: a v1 client that doesn't know about `kind` will
encode without the key. A v2 server that adds `val kind: String? = null` will ALSO
encode without the key when the value is null. The two encoded payloads are
**byte-identical**. Backward compat holds at the byte level, not just the type level —
which is what the wire bump wants.

**Caveat**: if you explicitly call `Json.encodeToString` with `encodeDefaults = true`,
the encoder writes `"kind":null` explicitly instead of omitting. This is NOT v1-compatible
(v1 decoders may or may not tolerate explicit null, depending on how they were
written). Stick with the default behavior.

## When v1 is missing a field but v2's default is non-null

If the new v2 field has a non-null default (e.g. `val kind: String = "generic"`) and
you want v1 payloads to decode as `"generic"`, you cannot use the "omit key = default"
trick — kotlinx will fill the missing-key slot with the Kotlin default value as
defined on the data class. Verify this by feeding the v1 JSON shape into the decoder
and checking the decoded field equals the Kotlin default. The behavior is not
documented uniformly across kotlinx-serialization versions.

## Pairing with the existing gradle test

Always write a JUnit test alongside the standalone verifier recipe. The gradle test
catches behavior over the full TPipe runtime (e.g. the actual `dispatchTrace(...)`
call site, `PipeTracer.exportTrace()`, etc.); the standalone recipe catches
**wire-format shape details** fast. Keep both green.

The reference verifier from this session passed 7/7 ad-hoc checks AND the gradle
suite was 8/8 green; this is the shape to aim for.

## Failure modes the recipe catches

| Failure | Symptom | What the recipe catches |
|---------|---------|------------------------|
| Field declared but no default | Compile error: `No parameter with name 'kind' found` in the test | Recipe Step 5 always asserts `kind = null` is decodable |
| Default supplied but key always written | v1 decoder (which might be strict) rejects `"kind":null` on receive | Recipe Step 3 observes the omit-vs-explicit-null output, asserts the omit behavior |
| Round-trip on a non-string kind | Compile or runtime error | Recipe Step 5 covers arbitrary strings |
| Forgot the serialization plugin | `Unresolved reference 'serializer'` at compile | Recipe Step 3 prints the error and stops; retry with `-Xplugin` |

## Companion pitfall — Kotlin gradle daemon crash (`Daemon compilation failed: null`)

When TPipe's multi-module gradle build (`./gradlew :test ...`) intermittently fails
with `e: Daemon compilation failed: null` and a `Compilation error. See log for
details` cause, **retry with `--no-daemon`**:

```bash
./gradlew :test --tests "..." --rerun-tasks --no-daemon
```

The crash produces no line number, no source file pointer — it looks like the build
is fundamentally broken when in fact only the Kotlin compiler daemon crashed. The
`--no-daemon` flag bypasses the failing daemon and uses a fresh JVM per build. Build
time roughly doubles but reliability approaches 100%. This is a known intermittent
bug in Kotlin 2.2.x / 2.3.x; not a TPipe bug.

If you see this crash, prefer the standalone `kotlinc` recipe (this file) over
retrying gradle repeatedly — the standalone recipe has no daemon to crash.

## Captured

Captured 2026-07-11 during the `kind` discriminator addition to
`RemoteTraceDispatcher.TracePayload` (client-side v1→v2 wire bump for
TPipe-TraceServer). The standalone verifier (`/tmp/hermes-verify-tracepayload-wire/main.kt`)
caught a developer mistake in the FIRST iteration: the verifier checked for
`"kind":null` literal in the encoded output and the check FAILED because kotlinx
omits the key entirely. That failure surfaced the right behavior to encode in the
recipe's "kotlinx-serialization null behavior" section. Without the verifier, this
property would have stayed implicit in the JUnit test (which only checked round-trip
with kind = null, not the encoded bytes).
