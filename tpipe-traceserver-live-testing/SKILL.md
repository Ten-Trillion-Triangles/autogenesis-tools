---
name: tpipe-traceserver-live-testing
description: Write live (real-Netty, real-port) JUnit tests for the TPipe-TraceServer module. Use when a feature requires booting the actual Ktor server and exercising it via HTTP from a real client (e.g. `RemoteTraceDispatcher` posting to `/api/traces`). Covers the startTraceServer/stopTraceServer engine-pair pattern, InMemoryTraceStore reset for test isolation, agentAuthMechanism/clientAuthMechanism reset, port-picking via `ServerSocket(0)`, the cold-start delay, and the artifact directory convention under `TPipeConfig.getTraceDir()/Library/<feature>/`. Do NOT use for in-process tests — those should use Ktor's `testApplication { }` helper and live in the existing `TraceServerApiTest`-style classes.
---

# TPipe-TraceServer Live Testing

When a TPipe-TraceServer feature needs an end-to-end test that goes through a
real HTTP client (e.g. `RemoteTraceDispatcher`, WebSocket connections, real
authentication), you must boot the real Netty engine — not Ktor's in-memory
`testApplication` host. This skill captures the canonical recipe.

## When to load this skill

- The test must verify wire-shape round-trips that depend on a real HTTP
  client (Java HttpClient, ktor-client-cio, etc.).
- The test must verify the WebSocket broadcast path or any feature that
  `testApplication` cannot faithfully reproduce.
- The plan asks for a "live test" against the trace server.
- A new feature adds a wire field (e.g. `kind`, `tags`) and you want to prove
  end-to-end it survives the encoder → POST handler → store → list mapper →
  GET handler → JSON response path. In-process tests miss the last two hops.

## Canonical recipe (8 numbered steps)

1. **Annotate the test class** with `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`
   if the test holds per-class state (server engine, base URL). For single-method
   tests, omit it.
2. **Pick a free port** via `java.net.ServerSocket(0).use { it.localPort }` —
   never hardcode a port; CI parallelism and local re-runs both break with
   fixed ports.
3. **Build a `TraceServerConfig`** with `port = pickedPort`, `host = "127.0.0.1"`,
   and an isolated `defaultTenant` (e.g. `"test"`).
4. **Reset state in `@BeforeEach`**:
   - `TraceServerRegistry.useInMemoryStore()` — avoid disk pollution.
   - `TraceServerRegistry.agentAuthMechanism = null` AND
     `clientAuthMechanism = null` — these are global vars; prior tests can
     leak auth closures that fail closed on the next test.
   - Clear sessions: `TraceServerRegistry.sessionsFor(tenant).clear()` for
     every tenant the test will touch.
   - Reset any cross-module config the test mutates (e.g.
     `RemoteTraceConfig.{remoteServerUrl, authHeader, dispatchAutomatically}`).
5. **Boot the server**: keep the engine reference in a `@Volatile var engine`
   field — `startTraceServer(config, wait = false)` returns a `Netty` engine
   you MUST pass back to `stopTraceServer(engine)` in teardown. There is **no
   no-arg `stopTraceServer()`** — calling one is a compile error that has
   shipped in plan skeletons before.

   **Tenant gotcha (cost one smoke run to discover):** the one-arg
   `TraceServerRegistry.store.put(payload)` overload inserts under
   `DEFAULT_TENANT = "default"` (defined in `store/TraceStore.kt:13`), NOT
   under `TraceServerConfig.defaultTenant`. The default-tenant GET
   (`GET /api/traces` with no `?tenant=` query) filters on the config's
   `defaultTenant` via `resolveTenant(defaultTenant)`. If your test or
   smoke main calls `store.put(payload)` then queries the default tenant,
   you will silently see an empty list. **Fix:** always call the two-arg
   overload, `store.put(payload, tenant)`, and pass an explicit tenant
   (the config's `defaultTenant` for the "main" dataset, or a per-test
   unique one for isolation). When `registerTrace` or any 1-arg write path
   is used, the trace goes to `default` and is invisible to the default
   query. This is also why the legacy demo's 3 traces never show up in
   code that builds its own `TraceServerConfig(defaultTenant="smoke")`.
6. **Settle**: `delay(1500)` after `startTraceServer(...)` for Netty cold start
   + module load + listener bind. 800ms is too tight on busy CI.
7. **Drive the wire** with the production entry point (e.g.
   `RemoteTraceDispatcher.dispatchTrace(...)`), then `delay(2500)` for the
   `GlobalScope.launch(Dispatchers.IO)` POST to land.
8. **Assert via Java `HttpClient`** (not ktor-client) so the test

## Smoke mains for browser/visual verification

The 8-step recipe above is for JUnit tests. When the verification
target is a *human-visible dashboard* (browser screenshot pass, manual
QA, design sign-off), use a **smoke main** — a standalone `fun main()`
in `src/main/kotlin/.../TraceServerSmoke<Feature>Main.kt` that boots
the real server and holds it alive for tens of seconds while an
out-of-band tool captures the UI.

### Smoke-main checklist

- `startTraceServer(cfg, wait = true)` on a worker thread; the main
  thread owns JVM lifetime via `Thread.sleep(N)`.
- Use the **two-arg `store.put(payload, tenant)`** with an explicit
  tenant equal to the config's `defaultTenant`. The one-arg
  `store.put(payload)` inserts under `DEFAULT_TENANT = "default"`, but
  the default-tenant GET routes query the config's `defaultTenant`,
  so 1-arg writes are invisible at the default query (the **tenant
  gotcha** spelled out above).
- **Auth mechanisms are NOT symmetric.** The agent POST path
  (`TraceServer.kt:670` etc.) uses a three-elvis cascade
  `agentAuthMechanism ?: P2PRegistry.globalAuthMechanism ?: true` — so
  leaving `agentAuthMechanism` null opens agent POSTs. **The dashboard
  login path does NOT have a fallback.** `TraceServer.kt:593-604`:
  ```kotlin
  val ok = if (authConfig.passwordHasherEnabled && expected != null && req.password != null)
      passwordHasher.verify(req.password, expected)
  else
      clientAuthMechanism?.invoke(raw) ?: false   // null mechanism → false → 401
  ```
  So a smoke main with both mechanisms null + the default
  `passwordHasherEnabled=true` will reject every dashboard login attempt
  with 401 "Unauthorized". The dashboard renders the auth overlay
  indefinitely. Don't assume "leaving mechanisms null makes it open."
  It opens the AGENT path; it LOCKS the DASHBOARD.

  To make the dashboard log in successfully, set EITHER:
  - `clientAuthMechanism = { _ -> true }` (accept any key), OR
  - `passwordHasherEnabled = true` + `expectedHash = Pbkdf2PasswordHasher().hash("smoke-key")`
    AND make the dashboard send `{"password":"..."}` (not `{"key":"..."}`).

- **The dashboard's default auth tab sends `{"key":"..."}`, not
  `{"password":"..."}`.** The hasher branch at `TraceServer.kt:593` only
  fires when `req.password != null`. So `{"key":"smoke-key"}` always
  falls into the lambda branch — even with the hasher enabled and a
  valid hash configured. For dashboard-tab screenshots, use the
  `clientAuthMechanism = { _ -> true }` path with `passwordHasherEnabled`
  left at its default (true) — the hasher branch is skipped because the
  request has no `password` field, so the lambda path runs and accepts
  any key.
- Don't call `stopTraceServer()` without an engine reference — there
  is no no-arg overload (compile error). The JVM exit on
  `Thread.sleep` expiry will tear down Netty via its shutdown hook,
  matching what `TraceServerDemo.kt` does (it `while(true) sleep`s
  forever and never stops).

### Overriding the application `mainClass` non-invasively

`TPipe-TraceServer/build.gradle.kts` declares
`application { mainClass.set("com.TTT.TraceServer.TraceServerDemoKt") }`.
Gradle's `-PmainClass=...` property does **not** override this; the
`application` plugin reads `mainClass` directly from the extension.
To boot a smoke main without editing `build.gradle.kts`, use a
**gradle init-script** that swaps the `:run` task's `mainClass` at
`projectsEvaluated` time. A reusable template lives in
`scripts/override-smoke-main.init.gradle.kts` — copy it, edit the
`mainClass.set(...)` line for your run. Invoke with:

```
./gradlew --init-script /path/to/override-smoke-main.init.gradle.kts \
          :TPipe-TraceServer:run --no-daemon
```

The init-script is workspace-local — no commit to the repo, no churn
in `git status`.

### Verifying a smoke main

Put the harness in `/tmp/hermes-verify-*.sh` (sandbox-namespaced),
boot with `terminal(background=true)`, poll `GET /api/health` until
2xx, sleep an extra 5–10s for the smoke main's `Thread.sleep(2000)`
plus the `store.put` chain to land, then hit the read endpoint (the
default-tenant query for the screenshot smoke) and assert the
expected items + fields.

A too-early health probe (`< 3s` after gradle says "up") reports
`uptimeMs ~1500` but `total: 0` on `/api/traces` — the smoke main's
`Thread.sleep(2000)` PLUS 4 puts take a few seconds to land. Always
sleep an extra 5–10s after first 2xx.

Kill the JVM via the background-process session. Don't rely on the
smoke main's own 120s sleep to bound the verification — 2 min of wall
time per check is wasteful.

### Jar shadows classes on the classpath trap

When running a smoke main via `java -cp` with BOTH
`TPipe-TraceServer/build/classes/kotlin/main/` AND
`TPipe-TraceServer/build/libs/TPipe-TraceServer.jar` on the classpath,
**the jar's classes shadow the directory classes**. Java's classpath
ordering puts `build/libs/*.jar` ahead of `build/classes/...` in
common classpath-assembler output (and the smoke main's verifier
script will likely include both, since both exist after the first
`./gradlew :TPipe-TraceServer:jar`). The symptom: source edits to
`TraceServerSmokeMain.kt` compile cleanly into
`build/classes/kotlin/main/`, but the running JVM (launched from the
jar) doesn't see them. `println` lines you just added don't appear.
Class-file timestamps stay stale.

**Fix:** after every `compileKotlin`, re-run `./gradlew :TPipe-TraceServer:jar`
to refresh the jar BEFORE launching the JVM. Or remove the jar entry
from the classpath and use only `build/classes/kotlin/main/`. Either
way, verify by `strings <jar_or_class> | grep <unique-new-string>` —
the new string should be present. If it's missing, the jar is stale.

### Live update vs summary broadcast — what's actually being tested

When you assert "live render update" via the dashboard's WebSocket,
the wire path is the **v1 legacy summary broadcast**, not per-event
streaming. `PumpStationLoop.kt:2986-3009` calls
`PipeTracer.exportTrace(runId, HTML)` then `dispatchTrace(..., kind=...)`
— both produce ONE POST each, and the server broadcasts a legacy
`TraceSummary` JSON to all connected WebSocket clients (the
`_upsertSummary` upsert at `dashboard.js:455-489`). The per-event
`POST /api/traces/{id}/events` endpoint exists server-side but no
container currently emits to it. So if your test asserts the
dashboard reflects a new trace "live" within ~3s of submission, you're
testing the summary-broadcast path, not the per-event path.

## Pitfalls

- **`detachedConfiguration1` snapshot-transform hiccup on first run.**
  When you invoke `:TPipe-TraceServer:test --rerun-tasks --no-daemon`
  immediately after the root `:jar` task has just rewritten
  `build/libs/TPipe-1.0.0.jar`, the
  `BuildToolsApiClasspathEntrySnapshotTransform` for
  `:TPipe-TraceServer:detachedConfiguration1` (the kotlinc classpath
  snapshotter the embedded kotlin plugin uses to compute
  incremental-compile inputs) can fail with:

  > `Index 6 out of bounds for length 0` from
  > `BuildToolsApiClasspathEntrySnapshotTransform: .../build/libs/TPipe-1.0.0.jar`

  This is a transient race between the snapshotter reading the freshly
  rewritten jar and the size/Mtime attributes Gradle's classpath cache
  recorded for it. **Fix: re-run the same `--rerun-tasks --no-daemon`
  invocation once.** The second run always succeeds. Do NOT clean the
  root build, do NOT switch daemons, do NOT retry with
  `--no-build-cache` — none of those fix it; only `--rerun-tasks` after
  the previous failure cleanly does. Symptom-to-recognition: the failure
  prints `> Task :TPipe-TraceServer:compileKotlin FAILED` immediately
  after `> Task :jar`, with the snapshot error naming `TPipe-1.0.0.jar`.
  That trio is diagnostic — don't waste turns debugging.

- **Foreground timeout cap on the full TPipe-TraceServer run is real.**
  A clean `--rerun-tasks --no-daemon` takes ~75–80s of wall time, but a
  first-run snapshot hiccup + retry can stretch past the 600s foreground
  cap. Always invoke full-suite runs via
  `terminal(background=true, notify_on_complete=true)` and
  `process(action='wait', timeout=120)` for status. Don't try to fit the
  full suite into a single foreground call. Captured on commit 02d6c15d
  during task-9 of `pumpstation-traceserver-component-aware` plan: 14
  classes / 49 tests / 0 fail-err-skip on the retry.

## Support files

- `scripts/override-smoke-main.init.gradle.kts` — gradle init-script that
  swaps `:TPipe-TraceServer:run`'s `mainClass` at `projectsEvaluated` time
  without touching `build.gradle.kts`. Copy + edit the `mainClass.set(...)`
  line for your smoke main.