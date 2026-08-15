# Hermes Test JVM Env-Var Discovery — bashrc parsing recipe

Captured 2026-07-10 from the post-goal-hook `PumpStationPostGoalLiveTest`
rollout. Pattern is generic to any Hermes test that needs an API key
defined in `~/.bashrc` but not exported to the gradle test JVM.

## Why This Exists

The standard `System.getenv("MINIMAX_API_KEY")` call returns null in the
test JVM when the test is run from a Hermes terminal session. Hermes
spawns a non-interactive bash subprocess that does NOT source `~/.bashrc`
or `~/.profile`, so the env var the user has set in their shell init file
is invisible to the JVM. The operator's out-of-band message during the
post-goal-hook rollout captured the contract:

> *"get the api key from bashrc I told you this before"*

The test JVM is on its own for env-var discovery. Read `~/.bashrc`
directly when the env var is unset.

## The Pattern

```kotlin
private fun readKeyFromBashrc(): String? {
    val home = System.getProperty("user.home") ?: return null
    val bashrc = File(home, ".bashrc")
    if (!bashrc.exists()) return null
    val line = bashrc.readLines().firstOrNull { it.startsWith("export MINIMAX_API_KEY=") }
        ?: return null
    return line.replaceFirst("export MINIMAX_API_KEY=", "")
        .trim()
        .trim('"')
        .trim('\'')
        .takeIf { it.isNotBlank() }
}
```

When the key is loaded, call the relevant env-setter for the provider:

```kotlin
genericOpenAIPipe.env.GenericOpenAIEnv.setApiKey(key)
System.setProperty("tpipe.allowInsecureBaseUrl", "true")  // required for stub-mode
```

`setApiKey` populates the static env which `GenericOpenAIPipe.init()` reads
at pipe construction time. `allowInsecureBaseUrl` is required for stub-mode
tests whose `StubOpenAIServer` runs on `http://localhost:port` — without
it, `setBaseUrl("http://...")` throws `IllegalArgumentException`.

## Which Providers Need This

The bashrc-parsing pattern works for any provider defined in `~/.bashrc`:
- `MINIMAX_API_KEY` for `PumpStationMiniMaxLiveTest` and the new
  `PumpStationPostGoalLiveTest` (post-goal feature rollout, 2026-07-10)
- `OPENROUTER_API_KEY` for `PumpStationLiveLLMTest`
- `ANTHROPIC_API_KEY` for Anthropic-backed tests
- Anything else the user has in their shell init file

The pattern is one helper per env var. Replicate `readKeyFromBashrc()`
per-variable, with the variable name substituted:

```kotlin
private fun readEnvFromBashrc(varName: String): String? {
    val home = System.getProperty("user.home") ?: return null
    val bashrc = File(home, ".bashrc") ?: return null  // handles File-not-found
    if (!bashrc.exists()) return null
    return bashrc.readLines()
        .firstOrNull { it.startsWith("export $varName=") }
        ?.replaceFirst("export $varName=", "")
        ?.trim()
        ?.trim('"')
        ?.trim('\'')
        ?.takeIf { it.isNotBlank() }
}
```

A generic version works for any env var without per-var copy-paste.

## How It Fits Into the Test Setup

The `setup()` method pattern:

```kotlin
@BeforeAll
fun setup() {
    val envKey = System.getenv("MINIMAX_API_KEY")
    val key = envKey?.takeIf { it.isNotBlank() } ?: readKeyFromBashrc()
    if (key.isNullOrBlank()) return
    genericOpenAIPipe.env.GenericOpenAIEnv.setApiKey(key)
    apiKeyCache = key
    System.setProperty("tpipe.allowInsecureBaseUrl", "true")
}

@AfterAll
fun teardown() {
    if (apiKeyCache != null) {
        genericOpenAIPipe.env.GenericOpenAIEnv.clearApiKey()
        apiKeyCache = null
    }
    System.clearProperty("tpipe.allowInsecureBaseUrl")
}
```

The key is captured to a class-level field so `teardown()` can call
`clearApiKey()` and `System.clearProperty()`. The field is also used by
the `liveGateOrSkip()` / `stubGateOrSkip()` helpers — see
`pump-station/references/live-test-suite-architecture.md` for the full
12-test pattern.

## How the Pattern Differs from the Per-Test Isolation Rule

The existing `pump-station` skill captures the `TPipeConfig.configDir`
mutation pattern in `tpipe-trace-output-conventions/SKILL.md`'s "Per-Test
Isolation" section. That pattern is for tests that **change the trace
directory** for isolation. The bashrc-parsing pattern is for tests that
**read the API key** from the user's shell init file. Different
mechanism, different problem:

- `TPipeConfig.configDir` mutation: change where trace files land.
- `~/.bashrc` parsing: discover where the API key lives.

Both are required for a complete live test setup. Combine them: parse
bashrc for the key, mutate `configDir` for trace isolation.

## When This Pattern Applies

Any Hermes test JVM that needs an env var defined in the user's
`~/.bashrc`. NOT for:

- Env vars the user already exports on the gradle CLI (use `System.getenv` directly).
- Env vars defined in `~/.zshrc` or `~/.profile` (extend the parser to try
  multiple files; pattern is identical).
- Env vars the test sets itself (use `System.setProperty`).

## Cross-References

- `pump-station/references/live-test-suite-architecture.md` — the 12-test
  suite template that uses this pattern in its `@BeforeAll setup()`.
- `tpipe-trace-output-conventions/SKILL.md` — the canonical
  `TPipeConfig.getTraceDir()` resolver rule and the
  "Per-Test Isolation" configDir-mutation pattern (companion to this one).
- The companion pitfall in the persona memory: "Declaring env vars unset
  without checking shell init files" — applies to any tool that spawns
  a non-interactive bash subprocess.
