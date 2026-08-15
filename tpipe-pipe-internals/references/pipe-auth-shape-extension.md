# Extending a Pipe Subclass with a New Auth Shape

Recipe for adding a non-bearer, non-x-api-key auth shape to a TPipe Pipe
subclass without breaking the existing `getAuthHeaders()` switch on
`apiMode`. Captured from the Bedrock Mantle integration on
`TPipe-GenericOpenAI/GenericOpenAIPipe` (2026-07-29).

## When this recipe applies

Any Pipe subclass that has an existing `getAuthHeaders()` dispatch
table — typically:

```kotlin
private fun getAuthHeaders(): Map<String, String> = when(apiMode) {
    is ApiMode.OpenAI -> mapOf("Authorization" to "Bearer $apiKey")
    is ApiMode.Anthropic -> mapOf("x-api-key" to apiKey, ...)
    ...
}
```

…and needs to add a new auth surface that:

- Computes auth headers PER REQUEST (not just at init time) — typical
  for body-hash-based signing like AWS SigV4, where the signature
  depends on the request body bytes
- Has its own credential resolution (env vars, system properties,
  programmatic overrides) that doesn't fit the existing `apiKey` field
- May need to be DISABLED at runtime (caller may want to fall back to
  the existing bearer mode)

The Bedrock Mantle integration is the canonical worked example:
Mantle accepts both Bedrock API keys (bearer) and AWS SigV4 auth, and
TPipe users want both paths available depending on whether they're
using IAM-tied credentials or a long-lived API key.

## Recipe (5 steps)

### Step 1: Define the auth shape as a sealed type

Create a sealed class hierarchy that represents the auth shape's two
modes. Each variant implements a `authHeaders(method, url, body,
headers)` method that returns the full set of headers to attach.

```kotlin
// genericOpenAIPipe/mantle/BedrockMantleAuth.kt
sealed class BedrockMantleAuth {
    abstract fun authHeaders(
        method: String,
        url: String,
        body: ByteArray,
        headers: Map<String, String>,
    ): Map<String, String>

    data class Bearer(val apiKey: String) : BedrockMantleAuth() { ... }
    data class SigV4(val signer: SigV4Signer) : BedrockMantleAuth() { ... }

    companion object {
        fun bearer(apiKey: String): Bearer = Bearer(apiKey)
        fun sigV4(...): SigV4 = SigV4(SigV4Signer(...))
        fun sigV4FromEnv(regionOverride: String? = null): SigV4? { ... }
    }
}
```

The `sigV4FromEnv()` null-fallback pattern is the right idiom for "try
to use IAM auth, fall back to bearer if creds are missing." Returning
`null` (not throwing) lets the caller distinguish "no creds" from
"creds but wrong format."

### Step 2: Add an optional override field on the Pipe

Add a `@kotlinx.serialization.Transient` field on the Pipe subclass
holding the auth override. `Transient` because auth state is
runtime-only — it should not survive serialization round-trips (the
parent `Pipe.toPipeSettings()` / `applyPipeSettings()` cycle).

```kotlin
// GenericOpenAIPipe.kt (inside the class body)
@kotlinx.serialization.Transient
private var bedrockMantleAuth: BedrockMantleAuth? = null
```

### Step 3: Refactor `getAuthHeaders()` to accept `(method, url, body)`

The existing `getAuthHeaders(): Map<String, String>` signature is
insufficient when the auth depends on the body bytes. SigV4 requires
the SHA-256 hash of the payload to compute the canonical request, so
the body has to flow through. Update the signature:

```kotlin
private fun getAuthHeaders(
    method: String,
    url: String,
    body: ByteArray,
): Map<String, String> {
    bedrockMantleAuth?.let { auth ->
        return auth.authHeaders(method, url, body, emptyMap())
    }
    return when(apiMode) {
        is ApiMode.OpenAI -> mapOf("Authorization" to "Bearer $apiKey")
        is ApiMode.OpenAIResponses -> mapOf("Authorization" to "Bearer $apiKey")
        is ApiMode.Anthropic -> mapOf("x-api-key" to apiKey, "anthropic-version" to "2023-06-01")
    }
}
```

This is a signature change to a `private` function — it should not
break any external API. But it WILL break any in-module callers (every
`getAuthHeaders().forEach { ... }` site becomes
`getAuthHeaders(method, url, body).forEach { ... }`). The Mantle
integration had three call sites:

```bash
grep -nE 'getAuthHeaders\(\)' src/main/kotlin/GenericOpenAIPipe.kt
# Three sites: two in Ktor POST request blocks, one in streaming-direct
# HttpURLConnection builder. Each gets the body byte array via
# jsonRequest.toByteArray(Charsets.UTF_8).
```

Update each call site to pass the body bytes. For the streaming-direct
path, the body is already in scope at the call site; for the Ktor
POST blocks, the body is `jsonRequest` (the serialized request body
string) — pass `jsonRequest.toByteArray(Charsets.UTF_8)`.

### Step 4: Add builder methods that wire the override

The convention is `set{AuthShape}(...)` builders that take the same
parameters as the underlying auth. They wire `baseUrl`, `apiMode`, the
auth shape, and any model-id or region settings in one fluent call.

```kotlin
fun setBedrockMantle(region: String, modelId: String): GenericOpenAIPipe {
    val config = BedrockMantleConfiguration.forRegion(region, modelId)
    configureBedrockMantle(config)
    return this
}

fun setBedrockMantleWithResponses(region: String, modelId: String): GenericOpenAIPipe {
    val config = BedrockMantleConfiguration.forRegionWithResponses(region, modelId)
    configureBedrockMantle(config)
    return this
}

fun setBedrockMantleAuth(auth: BedrockMantleAuth?): GenericOpenAIPipe {
    bedrockMantleAuth = auth
    return this
}
```

The two convenience setters (`setBedrockMantle`, `setBedrockMantleWithResponses`)
delegate to a private `configureBedrockMantle(config)` helper that:

1. Calls `setBaseUrl(config.endpoint())` (regional endpoint URL)
2. Calls `setApiMode(config.apiMode)` (selects the right wire format)
3. Calls `setModel(config.modelId)` (existing Pipe setter)
4. Resolves credentials via the env resolver (`sigV4FromEnv(regionOverride = ...)`)
5. Sets `bedrockMantleAuth` to the SigV4 auth shape, OR falls back to bearer if no IAM creds

### Step 5: Update the test-only accessor

If the Pipe exposes an `internalGetAuthHeadersForTest()` for unit
tests, update it to provide default args for the new parameters:

```kotlin
fun internalGetAuthHeadersForTest(): Map<String, String> =
    getAuthHeaders(method = "GET", url = baseUrl, body = ByteArray(0))
```

Defaults are safe — empty body and a placeholder URL mean the auth
shape's per-request logic is not exercised, but the auth TYPE
selection still works (Bearer vs SigV4 vs no-override).

## Why this shape

**Why a sealed class for the auth shape, not a single class with a
nullable field?** A sealed class makes the per-variant auth header
generation type-safe — `BedrockMantleAuth.SigV4` carries the signer,
`BedrockMantleAuth.Bearer` carries the key, no field is ever null.
The sealed `authHeaders()` method dispatches on the variant at runtime
without `if (signer != null) ... else ...` chains.

**Why a per-request auth-headers call, not a cached map?** SigV4's
Authorization header changes per request because the signature
depends on `X-Amz-Date`, the payload hash, and the canonical-request
hash. A cached map would produce a single signature used for every
request — AWS would reject all but the first. The per-request call is
the only safe pattern.

**Why a separate env resolver, not just System.getenv() inline?**
Tests need to override the resolver to inject deterministic values.
The singleton object with programmatic setters (`setAccessKeyId(...)`,
`clearAccessKeyId()`, etc.) follows the same pattern as
`GenericOpenAIEnv` (the existing Bearer-key resolver). The
test teardown is `@AfterTest { clearAccessKeyId(); clearSecretAccessKey(); ... }`.

**Why preserve the existing `apiMode` dispatch as the fallback?**
Caller code that uses `setBaseUrl(...)` + `setApiKey(...)` (the
existing OpenAI/Anthropic paths) without calling any of the new
`setBedrockMantle*` setters MUST keep working unchanged. The
`bedrockMantleAuth?.let { ... } ?: when(apiMode) { ... }` shape
preserves the existing dispatch as the no-override default. The
Mantle integration added 35 new tests (signer + config + env + live)
and produced ZERO regressions on the existing 243-test suite, which
is the proof this recipe preserves the existing surface.

## Pitfalls

### Don't add `x-amz-content-sha256` to the request headers

For body-hash-based signing like SigV4, the payload hash goes INTO
the canonical request (as the last line) but is NOT emitted as an
on-the-wire header by reference SDKs (verified against aws-sdk-go
v1.55.8 `v4_test.go:202`). Adding it to the SignedHeaders list will
silently mismatch the AWS server's signature computation. The hash is
canonical-only, not transport-level.

### Don't re-encode the canonical URI

`URL.getPath()` already returns the percent-encoded form. If your
caller passes a path string, you may want to encode it — but if the
caller passes a fully-formed URL, the path is already encoded and
re-encoding will double-encode characters, producing a signature
mismatch. Default to passing the path through unmodified, and require
the caller to opt into encoding with an explicit flag.

### Preserve casing for the Authorization header

The existing test
`OpenAIResponsesPipeDispatchTest.testGetAuthHeadersReturnsBearer()`
asserts `headers["Authorization"]` (uppercase `A`). When adding a new
auth shape, return `"Authorization"` (uppercase), NOT `"authorization"`
(lowercase). Ktor's `header()` call normalizes header names to
lowercase internally, but the test reads the map directly, so the
key must match.

### Don't let the new auth shape accidentally lock apiMode

If your new auth shape sets `apiMode = ...`, remember the existing
`apiModeLocked: Boolean` guard that prevents further changes after
the first request. The Mantle setter calls `setApiMode(...)` which
goes through the guard — which is fine because Mantle is typically
called before the first request. But if the pipe's lifecycle lets
the new setter run AFTER the first request, you'll hit the
`IllegalStateException("apiMode cannot be changed after the first API
request")` guard. Either fail loudly with a clear message, or
document the ordering constraint.

### Use a Clock injection for deterministic timestamps in the signer

If your new auth shape uses time-based signing (SigV4 uses
`X-Amz-Date`; OAuth2 uses request timestamps), inject a `Clock`
abstraction rather than calling `System.currentTimeMillis()`
directly. Tests asserting signature byte-equality need a fixed
clock so the timestamp is reproducible. The Mantle integration
implemented a `fun interface Clock` with a `SystemClock` default
production implementation, and tests supplied `Clock { <fixedEpochMs> }`.

## Live test gating pattern

The Mantle live integration test follows this recipe (canonical for
all "real network, gated" tests in TPipe):

```kotlin
@EnabledIfEnvironmentVariable(named = "BEDROCK_MANTLE_LIVE_TEST", matches = "true")
class BedrockMantleLiveTest {
    @Test
    fun testMantleChatCompletions() = runBlocking {
        // Skip cleanly when AWS creds are missing — don't fail.
        assumeTrue(
            (System.getenv("AWS_ACCESS_KEY_ID") ?: "").isNotBlank() &&
                (System.getenv("AWS_SECRET_ACCESS_KEY") ?: "").isNotBlank(),
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY env vars must be set"
        )
        // ... test body
    }
}
```

Two-gate pattern: `@EnabledIfEnvironmentVariable` skips the class when
the flag is absent; `assumeTrue(...)` skips the individual test when
the creds are absent (avoids the live test failing with NPE on the
first env lookup). Matches the JUnit 5 idiom.

**The pre-existing `MiniMaxLiveTest` and `AnthropicStreamingLiveTest`
in this same module use `assertTrue(env.isNotBlank(), "must be set")`
which FAILS rather than SKIPS — that's a bug. The Mantle live test
demonstrates the correct pattern.**

## Worked example reference

- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/BedrockMantleAuth.kt`
  — the sealed auth shape
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/SigV4Signer.kt`
  — pure-Java HMAC SigV4 with Clock injection
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/mantle/BedrockMantleConfiguration.kt`
  — typed configuration record (region, modelId, apiMode)
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/env/BedrockMantleEnv.kt`
  — credential resolver (programmatic > system property > env > AWS default chain)
- `TPipe-GenericOpenAI/src/main/kotlin/genericOpenAIPipe/GenericOpenAIPipe.kt`
  — the modified Pipe subclass (lines added for Mantle: ~144 lines, 7 removed)
- `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/mantle/SigV4SignerTest.kt`
  — 17 unit tests including aws-sdk-go structural-parity checks
- `TPipe-GenericOpenAI/src/test/kotlin/genericOpenAIPipe/BedrockMantleLiveTest.kt`
  — gated live integration test