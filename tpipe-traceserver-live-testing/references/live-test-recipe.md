# TPipe-TraceServer Live Test Recipe

Concrete boilerplate for writing live (real-Netty, real-port) JUnit tests
against `TPipe-TraceServer`. The canonical implementation is
`PumpStationTraceServerLiveTest.kt` (commit 8e0a47b3+ in the
pumpstation-traceserver plan).

## Minimal working skeleton

```kotlin
package com.TTT.TraceServer

import com.TTT.Config.TPipeConfig
import com.TTT.Debug.RemoteTraceConfig
import io.ktor.server.engine.*
import io.ktor.server.netty.*
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.io.File
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.time.Duration

class MyFeatureTraceServerLiveTest {

    private val traceBaseDir: File by lazy {
        File(TPipeConfig.getTraceDir(), "Library/<feature-name>")
    }
    private val client: HttpClient = HttpClient.newHttpClient()
    private var engine: EmbeddedServer<NettyApplicationEngine, NettyApplicationEngine.Configuration>? = null

    @BeforeEach
    fun setup() {
        traceBaseDir.mkdirs()
        TraceServerRegistry.useInMemoryStore()
        TraceServerRegistry.agentAuthMechanism = null
        TraceServerRegistry.clientAuthMechanism = null
        for (tenant in listOf("default", "test")) {
            runCatching { TraceServerRegistry.sessionsFor(tenant).clear() }
        }
        RemoteTraceConfig.remoteServerUrl = null
        RemoteTraceConfig.authHeader = null
        RemoteTraceConfig.dispatchAutomatically = false
        engine = null
    }

    @AfterEach
    fun teardown() {
        RemoteTraceConfig.remoteServerUrl = null
        RemoteTraceConfig.authHeader = null
        RemoteTraceConfig.dispatchAutomatically = false
        runCatching { stopTraceServer(engine!!) }
        engine = null
        TraceServerRegistry.configureStore(
            com.TTT.TraceServer.store.FileBackedTraceStore(
                java.nio.file.Paths.get(System.getProperty("user.home"), ".TPipe-Debug", "trace-server")
            )
        )
    }

    @Test
    fun myFeatureRoundTripsAcrossTheWire() = runBlocking {
        val port = pickFreePort()
        val cfg = TraceServerConfig(port = port, host = "127.0.0.1", defaultTenant = "test")
        engine = startTraceServer(cfg, wait = false)
        delay(1500) // Netty cold-start settle

        try {
            val baseUrl = "http://127.0.0.1:$port"
            RemoteTraceConfig.remoteServerUrl = baseUrl
            RemoteTraceConfig.authHeader = "Bearer test-token"
            RemoteTraceConfig.dispatchAutomatically = true

            // Drive the production entry point.
            com.TTT.Debug.RemoteTraceDispatcher.dispatchTrace(
                pipelineId = "live-test-${System.currentTimeMillis()}",
                name = "live-test",
                status = "SUCCESS",
                kind = "<feature-name>",
            )
            delay(2500) // GlobalScope.launch(Dispatchers.IO) POST settle

            val listResp = client.send(
                HttpRequest.newBuilder(URI("$baseUrl/api/traces?limit=20"))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build(),
                HttpResponse.BodyHandlers.ofString(),
            )
            assertEquals(200, listResp.statusCode(), "GET /api/traces should return 200")
            // ...assertion logic...
        } finally {
            runCatching { engine?.let { stopTraceServer(it) } }
        }
    }

    private fun pickFreePort(): Int = java.net.ServerSocket(0).use { it.localPort }
}
```

## Canonical gradle commands

```bash
# Compile-check only (fast; ~10s).
./gradlew :TPipe-TraceServer:compileTestKotlin --no-daemon

# New live test in isolation (~45s; boot + dispatch + assertions).
./gradlew :TPipe-TraceServer:test \
    --tests "com.TTT.TraceServer.MyFeatureTraceServerLiveTest" \
    --no-daemon --rerun-tasks

# Full TPipe-TraceServer suite (~60s).
./gradlew :TPipe-TraceServer:test --no-daemon --rerun-tasks
```

Always use `--no-daemon` per the parent task convention; `--rerun-tasks`
forces re-execution so you can see actual test times instead of cached UP-TO-DATE.

## Pitfalls confirmed in production

| Pitfall | Symptom | Fix |
|---|---|---|
| `stopTraceServer()` no-arg call | Compile error | Use `stopTraceServer(engine)`; keep engine in a class field |
| No port pick | `BindException` when port in use | `ServerSocket(0).use { it.localPort }` |
| Forgot `useInMemoryStore()` | `~/.TPipe-Debug/trace-server/` accumulates | Call in `@BeforeEach` |
| Forgot to null `agentAuthMechanism` | Auth fails closed after another test | Null in `@BeforeEach` |
| Cold-start delay too short (800ms) | First GET returns empty list | Use 1500ms |
| POST settle too short | GET races the async POST | Use 2500ms after `dispatchTrace` |

## Bug found by this pattern (Task 7)

The original v2 wire commit (`a06026fd`) added `kind` to `TracePayload` and
`TraceSummary`, updated the WS broadcast site at `TraceServer.kt:852`, but
**missed both store implementations' `listSummaries` mapper**. The mapper
was constructing `TraceSummary` with only `(id, timestamp, name, status)` —
the `kind` field was dropped silently.

The live test caught this on first run. Fix was one line in each store:

```kotlin
// Before
.map { (id, entry) -> TraceSummary(id, entry.insertedAt, entry.payload.name, entry.payload.status) }
// After
.map { (id, entry) -> TraceSummary(id, entry.insertedAt, entry.payload.name, entry.payload.status, entry.payload.kind) }
```

Whenever a live wire-shape test fails on the GET hop, check store mappers
first. The POST and WS broadcast paths get updated in every wire-bump
commit because they're obviously user-facing; the store mapper is the
hidden hop that misses.