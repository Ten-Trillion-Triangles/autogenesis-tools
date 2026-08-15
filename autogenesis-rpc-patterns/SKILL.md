---
name: autogenesis-rpc-patterns
description: Autogenesis RPC patterns — @RpcMethod handler authoring (KSP constraints, RpcDirection, signature rules), transport-specific invoker objects for calling RPCs from server / server-extend / kvisionApp, the server-extend ↔ main-server WebSocket bridge, REST+SSE-vs-WebSocket transport split, and Kotlin 2.2 + KVision/JS launch parser quirks. Use when adding a new RPC method, debugging KSP "First parameter must be RpcCallContext" errors, deciding RpcDirection, obtaining an RpcInvoker from a specific module, wiring a server-extend bridge, calling an RPC from server or kvisionApp, or debugging Kotlin 2.2 "Function invocation 'launch(...)' expected" errors. NOT for LLM prompt debugging (autogenesis-prompt-debugging) or trace analysis (autogenesis-trace-analysis) or local-dev startup (autogenesis-local-dev).
version: 1.13.0
author: Hermes Agent (extracted from interactive-plan session 2026-06-22)
created: 2026-06-22
updated: 2026-08-12
tags: [autogenesis, kotlin, ksp, rpc, kvision, server, resume-game, sse, push, tpipe, pipe-failure, singleton-injection, visibility, integration-test, harness]
changelog:
  - "1.14.0 (2026-08-12): Added the verification-gap pitfall that produced the recurring 'manual register' regression. The class of failure: the skill already documents the auto-registration contract with a detection heuristic (above), but the agent kept shipping manual `ServerExtendBridge.registerHandlers { ... }` blocks in `Main.kt` as a 'belt-and-suspenders' fix on the premise that 'JS module lazy-load' meant auto-registration might not fire. The user pushed back TWICE in 10 days with the same shape ('Rpc methods are supposed to auto register and not need those manual registers wtf is going on?' 2026-08-10; 'Was the RPC system not designed to handle all annotations being auto registered? I believe that it is and yet you cowboy code' 2026-08-12). The fix is: (a) the existing detection heuristic is now percussive and the skill is the load-bearing guard — every `MapUpload*ClientHandlers`-type wiring MUST be read through the 1.11.0 / 1.13.0 four-step shape before any registration code is written; (b) the new pitfall 'Code-graph inspection is not runtime verification' is added to the umbrella, and references/rpc-auto-registration-verification.md ships a re-runnable Playwright console-capture probe that proves (or fails to prove) the auto-registration chain executed against the live bundle without the manual block; (c) noted that AGENTS.md's claim about `localStorage['autogenesis_logs']` persistence for the JS log writer is stale — `sharedModel/.../LogWriter.js.kt:34-43` says 'localStorage persistence removed for performance.' Verification probes must capture `console.log` via Playwright, not read localStorage. Load before: any session wiring RPC client listeners, any session that needs runtime confirmation that auto-registration fired."
  - "1.13.0 (2026-08-12): Added the Kotlin/JS UI-side companion via references/kvision-js-ui-rpc-wiring.md. The umbrella documents the call-site API surface; this support file captures the 9 Kotlin/JS compile-time gotchas that fire when wiring a UI widget to call into a server-extend RPC (typed-invoke does NOT return the typed payload, MessageBox constructor is positional+legacy-named not KVision-default, Uint8Array indexed access needs asDynamic()[i] as Byte, @JvmStatic unresolved, err::class.js.name not javaClass.simpleName, KEnv/AccelByteEnv/structs.* are top-level packages not nested under org.ttt.autogenesis.*, RpcJson is a top-level val). Also documents the companion-object dispatch hook pattern (Pattern A) for UI to singleton-client-handler decoupling — the only pattern that worked cleanly in the MapUploadModal wiring session for KVision 9.1.1 + Kotlin/JS 2.2.20. Includes the production webpack bundle symbol-probe recipe (HermesDesktop end-to-end pitfall pattern). Trigger for the next session: load this file BEFORE writing any UI widget that calls ServerExtendBridge.rpcInvoker.invoke()."
  - "1.12.0 (2026-08-11): Added the End-to-end integration harness for RPC handlers section. Five things worth pinning from the MapUploadGateEndToEndTest work: (1) seam orchestration — real at the wire boundary (pack/unpack, outgoingFlow drain), fake at the cost boundary (Bedrock/LLM, AGS/HTTP) so tests run without network or money; (2) when a test seam is a non-suspend lambda but the underlying factory is suspend, pre-compute outside the seam and capture the result in a closure so the harness can still exercise the real wire format; (3) trace emission must fire on BOTH the real and fake seam branches — if the surface is hoisted inside the `if` conditional, the fake branch's audit trail goes silent and the integration test cannot assert on the on-disk receipt; (4) for assertions on string-shaped on-disk files (the gate's `gate-call.json`), the production writer's whitespace matters — `trimIndent()` preserves the space after `:` so the test must mirror `\"key\": \"value\"` not `\"key\":\"value\"`; (5) `internal` types from the same module can be reconstructed in test fixtures only via Pair-shaped fixtures (return the public components, reconstruct the internal wrapper at the call site) to avoid `'public' function exposes its 'internal' return type` compile errors. Companion: references/map-upload-gate-harness-recipe.md."
  - "1.11.0 (2026-08-10): Rewrote the Client-side listener registration (kvisionApp) section to remove the manual-register escape hatch that 1.7.0 had documented. Captured the 2026-08-10 operator correction: the Map.Upload.Error channel was hand-rolled with a manual register call at Main.kt, bypassing the KSP-generated contract that every other client handler (UiSignalClientHandlers, ActionHistoryClientHandlers, AudioClientHandlers) used. The fix is a four-step shape -- new AreaClientHandlers.kt file with a typed @RpcMethod suspend fun, KSP regenerates the binding, the generated register call goes into WebSocketRpcBridge.registerHandlers, the DTO import in Main.kt is dropped. Worked example from this session with file:line evidence. Added a detection heuristic: any manual register block in Main.kt that does RpcJson.decodeFromJsonElement against a DTO is bypassing the auto-registration contract and must be replaced."
  - 1.10.0 (2026-08-10): Added the pre-edit baseline-compile gate to the singleton-injection workflow. When a pipe-builder failure lambda will call into an injected notification singleton whose `register` method crosses a module-internal type (the v1.6.0 visibility trap), baseline-compile BEFORE writing either edit -- the compile blocker lives in the singleton file, not the caller, and the IDE red you see in the builder file is downstream ripple from a failure in shared infrastructure. Added the method-name-must-not-be-fabricated rule with the `server-extend.mapUpload.error` vs `Map.Upload.Error` wrong-string anti-pattern. Added the do-the-work-not-the-lecture operator framing for `setOnFailure` completion tasks -- a 1-line diagnosis, the patch, and the compile is the entire response, no system-design tangent. Patched the operator-pushback receipt with verbatim framing for this session.
  - 1.9.0 (2026-08-10): Added the server-extend notification singleton pattern subsection under the pipe-failure section. MapUploadErrorHandlers (server-extend/MapUploadErrorHandlers.kt) is the canonical mirror of UiSignalRpcHandlers.sendTurnTimerUpdate for the server-extend side. Shape is typed DTO in sharedModel, then encodeToJsonElement, then RpcMessage.Notification, then manager.findSession(playerId)?.sendRpcMessage(notification). The singleton owns a nullable RestPlayerConnectionManager injected once at startup in ServerExtend.kt:292; WARN logs when the manager is null OR the player has no live SSE session. The pitfall to encode -- when a pipe failure lambda captures both the playerId and the connection manager as constructor arguments, the pipe setOnFailure already has everything it needs. Do NOT sketch a "create the notification object inside the lambda and queue it somewhere" shape, the call into the singleton is synchronous and lands the SSE frame immediately.
  - 1.8.0 (2026-08-10): Added the "Extending the RPC surface" section. RpcRegistry is declared plain class at sharedModel/.../network/RpcRuntime.kt:137, not `open class` -- literal Kotlin subclassing is not possible. The actual extension mechanism is the RpcRegistrationProvider fun-interface that takes a single `RpcRegistry` and registers handlers via `register`/`registerTyped`/`registerStream`, plus a top-level `_starProvider` val that calls `RpcRegistrationCollector.registerProvider(it)` at class-load time. Documented the three-piece shape (register function + provider class + top-level val) using `GeneratedSystemProbeHandlersRpcBindings.kt:16-37` as the canonical example. Also added the broadcast-helper per-session try/catch pitfall after the user pasted `UiSignalRpcHandlers.sendAgentStreamPayload` -- `sessions.forEach { it.sendRpcMessage(notification) }` with no per-call try/catch means a single half-closed WebSocket throws, the iteration aborts, and the remaining sessions in the list miss the chunk.
  - 1.7.0 (2026-08-10): Added the server-extend to main server call shape subsection under Calling an RPC and the do-not-fabricate call-site-patterns pitfall. When a user asks how to invoke an RPC from a specific module, the answer must cite a production call site (grep the bridge name in server-extend/src/main/kotlin/) -- never sketch a capture-the-bridge-rpcInvoker-into-a-private-val pattern that has no analog in the codebase. The right shape for server-extend to main server is `RestRpcBridge.rpcInvoker?.invoke(method, payload)` at the call site, exactly the way `RestRpcExample.kt:18` and `ResumeAvailabilityPushService.kt:400,448` do it. Also clarified that there is no JVM-side analog of `ServerExtendBridge` today -- only `accounting/Billing.kt:302` uses it.
  - 1.6.0 (2026-08-10): Added the TPipe pipe failure to RPC push section. `setOnFailure` only receives `(original, processed)` -- no session, no connection, no playerId -- so pushing an RPC out of a pipe failure requires either closure-capture at agent-build time or a ContextBank round-trip. The two paths trade clarity for cross-pipe-stage reachability. Also added the `internal`-visibility-trap pitfall (a `public fun` whose parameter type is `internal` won't compile; flip the function to `internal`) and the no-op `setOnFailure { _, _ -> MultimodalContent() }` smell that silently masks real failures upstream.
  - 1.5.0 (2026-08-10): Filled in the "Calling an RPC" section that 1.4.0 added as a stub. Documents the three call-site patterns — server-side ServerExtendConnection.getInvoker() (lazy gRPC client, Billing.kt:302), browser-side ServerExtendBridge facade (transport-aware REST+SSE/gRPC switch), and WebSocketRpcBridge for the always-on main-server WS link. Covers the three RpcInvoker.invoke() overloads, the null-skip idiom for bridge-side callers, the notification-vs-invoke split on the server, and the anti-pattern of trying to share one invoker across transports. Removed a near-duplicate "## Calling an RPC — invoker objects and transport shortcuts" section that had been left over from the 1.4.0 edit (different title, same content).
  - 1.4.0 (2026-08-10): Added "Calling an RPC — invoker objects and transport shortcuts" section — the call-site side was documented nowhere. (Section was a stub at first; filled in by 1.5.0.)
  - 1.3.0 (2026-07-07): Added two KSP gotchas from the server-extend cost-tracking plan. (a) RpcMethod handlers MUST live inside a class, object, or companion object — KSP rejects top-level suspend functions with Rpc-handlers-must-live-inside-a-class-or-object. Fix is to wrap in object or companion object. (b) RpcCallContext field is metadata, not connectionMetadata — the wrong name compiles but fails at runtime when the auth-gate handler reads the header.
  - 1.2.0 (2026-06-24): Corrected the SSE accelbyteId plumbing claim (the previous wording was wrong — RestRpcBridgeAccelbyteIdTest only pins the signature, not the wire-level URL). Added class-level Wrapper-chain-params-need-wire-level-tests pitfall derived from the accelbyteId bug fix (commit f16987684). Embedded reference to the fix commit and the RestRpcClientConfigUrlTest that now pins the wire contract.
  - 1.1.0 (2026-06-24): Added resume-game SSE-push architecture section (single-player snapshot capture → server-extend SSE check → client resume dialog → rehydrated gameplay). Embeds the full A→F trace with file:line evidence from the 2026-06-24 audit. Bumped version.
---

# Autogenesis RPC Patterns

The Autogenesis codebase uses a project-specific RPC framework built on KSP (Kotlin Symbol Processing). The framework is invisible from the call site — `@RpcMethod` annotations on suspend functions trigger KSP codegen that registers the handler in the project's RPC runtime, and `RpcInvoker.invoke()` calls route through it. But the framework has several non-obvious constraints that the Kotlin compiler and KSP enforce silently with cryptic error messages.

This skill is the gotcha list — read it before adding any new RPC method or wiring any new server-extend bridge.

## The 30-second mental model

- **Main server** (`:server`, JVM, port 9080, WebSocket) — the always-on game server. Handles `@RpcMethod("server.X", RpcDirection.SERVER)` invocations. Has `connectionManager` / `playerStats` for routing. Pushes notifications to clients via `RpcMessage.Notification` with method names like `client.X` or `ui.X`.
- **Server-extend** (`:server-extend`, JVM, port 7070 REST + 9092 gRPC, REST+SSE) — auxiliary matchmaking/CloudSave proxy. The bridge from the browser to the main server. Receives `@RpcMethod("server.extend.X", RpcDirection.SERVER)` invocations from the client and proxies through match2 / AMS. Calls back into the main server by opening a short-lived WebSocket and using `client.rpcInvoker.invoke(...)`.
- **Browser client** (`:kvisionApp`, Kotlin/JS 2.2.20 + KVision 9.1.1) — speaks to both transports. The `WebSocketRpcBridge` is the always-on WS to the main server. The `RestRpcBridge` / `ServerExtendBridge` is the REST+SSE link to server-extend.

`RpcDirection` is the receiver side, NOT the caller's side:
- `RpcDirection.SERVER` — only the server can handle this method. Used for `server.X` methods invoked by clients/server-extend, AND for `client.X` methods invoked by the main server (where the "server" receiver is the main server itself).
- `RpcDirection.CLIENT` — only the client can handle this method. Used for `client.X` methods invoked by the main server and received by the browser.
- `RpcDirection.BOTH` — either side can handle. Rare.

## `@RpcMethod` constraints (KSP-enforced)

KSP refuses to register a handler unless the function signature follows a strict shape. The error messages are misleading:

| KSP error | What it actually means |
|---|---|
| `First parameter must be RpcCallContext` | The function signature is `(userId: String, payload: Foo)`. Wrap it as `(ctx: RpcCallContext, userId: String, payload: Foo)` and read connection metadata from `ctx.metadata["accelbyteId"]` instead of as a positional parameter. |
| `Rpc handler can only accept RpcCallContext plus one payload parameter` | The function has `(ctx, userId, payload)` (two extra params). Bundle the extras into the payload struct or pull them from `ctx.metadata`/`WorldManager`. One parameter beyond `RpcCallContext` is the cap. |

**Anti-pattern** (from the plan I wrote that KSP rejected twice):
```kotlin
// WRONG: two non-ctx params
suspend fun notifyResumeAvailable(userId: String, payload: ResumeAvailabilityNotification)

// WRONG: ctx + two non-ctx params
suspend fun notifyResumeAvailable(ctx: RpcCallContext, userId: String, payload: ResumeAvailabilityNotification)

// RIGHT: ctx + one payload param; userId lives inside the payload
suspend fun notifyResumeAvailable(ctx: RpcCallContext, payload: ResumeAvailabilityNotification) {
    val userId = payload.userId   // or ctx.metadata["accelbyteId"]
}
```

**Anti-pattern** (RpcDirection backwards):
```kotlin
// WRONG: a server-handler invoked by server-extend cannot be RpcDirection.CLIENT
@RpcMethod("client.resumeAvailable", RpcDirection.CLIENT)
suspend fun notifyResumeAvailable(...)

// RIGHT: server-extend invokes it, so the main server is the receiver → SERVER
@RpcMethod("client.resumeAvailable", RpcDirection.SERVER)
suspend fun notifyResumeAvailable(...)
```

The method NAME (`client.X`) reflects what the notification is named when the client receives it — not who is calling.

**KSP fails on top-level `@RpcMethod` suspend functions (2026-07-07)** — the handler MUST live inside a `class`, `object`, or `companion object`. A top-level `suspend fun handler(...)` annotated `@RpcMethod` produces the cryptic KSP error `Rpc handlers must live inside a class or object` at `:kspKotlin` build time. The fix is wrapping the handler in the smallest enclosing type — usually an `object` if the handler is logically a singleton (no per-instance state), or a `companion object` inside an existing class if the handler is conceptually a member. **Real case (2026-07-07, server-extend cost-tracking Phase 3):** the `server.extend.getStatus` handler was originally a top-level suspend function; KSP rejected it at `:server-extend:kspKotlin`. Moving it into `object StatusRpcHandler { @RpcMethod(...) suspend fun getStatus(...) }` fixed the error with no other changes to the handler body.

**`RpcCallContext` field is `metadata`, not `connectionMetadata` (2026-07-07)** — when reading per-call metadata (e.g. an `X-Admin-Token` header plumbed from the REST bridge through to an RPC handler), the field name is `ctx.metadata: Map<String, String>`. Spelling it `ctx.connectionMetadata` or `ctx.headers` compiles in the production code path because both names resolve through type inference, but fails at KSP processing or at runtime when the header is missing. Pin the field name in any auth-gate handler that reads metadata — the build doesn't catch it because Kotlin's flexible typing defers the member lookup until first read.

## The `client.X` notification flow (server-extend → main server → browser)

To push something from server-extend down to the browser through the main server, the flow is:

1. **Define a `@Serializable` struct** in `sharedModel/src/commonMain/kotlin/structs/<area>/` for the payload. Build both JVM and JS targets (`./gradlew :sharedModel:compileKotlinJvm :sharedModel:compileKotlinJs`).
2. **Add an `@RpcMethod("client.X", RpcDirection.SERVER)` handler** to the main server (typically in `UiSignalRpcHandlers.kt` — that's where all the existing server→client push logic lives). The handler looks up the user's WS connection via `WorldManager.playerStats.firstOrNull { it.accelByteUserId == userId }?.playerID`, finds the session via `connectionManager?.findAllSessions(connectionId)`, iterates `sendRpcMessage(RpcMessage.Notification("client.X", payloadElement))`, and logs at WARN if no session is found.
3. **In server-extend**, open a short-lived `WebSocketRpcClient(WebSocketRpcClientConfig("ws://127.0.0.1:9080", "server-extend-<purpose>"), RpcRegistry(RpcDirection.CLIENT).also { registerRpcSystem() })`. Wait up to 5s for `onConnected`. Call `client.rpcInvoker.invoke("client.X", payloadElement)`. Close the client in a `finally` block with a 500ms delay to let the dispatch flush.

The bridge call shape (from `ServerConnector.notifyGameServer` at `server-extend/src/main/kotlin/matchmaking/ServerConnector.kt:560-624`):
```kotlin
val registry = RpcRegistry(RpcDirection.CLIENT).also { registerRpcSystem() }
val client = WebSocketRpcClient(
    WebSocketRpcClientConfig(baseUrl = baseUrl, playerId = connectorPlayerId),
    registry
)
val readySignal = CompletableDeferred<Unit>()
client.onConnected { if (!readySignal.isCompleted) readySignal.complete(Unit) }
try {
    client.connect()
    if (withTimeoutOrNull(5_000) { readySignal.await() } == null) return false
    val response: RpcMessage.Response = client.rpcInvoker.invoke(methodName, payload)
    // handle response.error
} finally {
    kotlinx.coroutines.delay(500)
    client.close()
}
```

## Client-side listener registration (kvisionApp) — KSP-generated ONLY

`Main.kt` registers every client handler in a single block like:
```kotlin
WebSocketRpcBridge.registerHandlers {
    ui.gameplay.networking.registerUiSignalClientHandlersRpcHandlers(
        this,
        UiSignalClientHandlers
    )
    ui.gameplay.networking.registerActionHistoryClientHandlersRpcHandlers(
        this,
        ActionHistoryClientHandlers
    )
    org.ttt.autogenesis.kvisionapp.audio.registerAudioClientHandlersRpcHandlers(
        this,
        AudioClientHandlers
    )
    org.ttt.autogenesis.kvisionapp.mapUpload.registerMapUploadErrorClientHandlersRpcHandlers(
        this,
        MapUploadErrorClientHandlers
    )
    org.ttt.autogenesis.kvisionapp.mapUpload.registerMapUploadSuccessClientHandlersRpcHandlers(
        this,
        MapUploadSuccessClientHandlers
    )
}
```

Every `register<Name>ClientHandlersRpcHandlers(this, <Name>)` call is **KSP-generated** by the `rpc-ksp` KSP processor (`rpc-ksp/src/main/kotlin/org/ttt/autogenesis/ksp/RpcProcessor.kt:104`) at compile time. The generated function iterates the `@RpcMethod`-annotated suspend functions on the target object and calls `rpcRegistry.registerTyped(...)` for each. The KSP output is visible after a build at `kvisionApp/build/generated/ksp/js/jsMain/kotlin/org/ttt/autogenesis/<package>/Generated<Name>ClientHandlersRpcBindings.kt` — `internal fun registerMapUploadErrorClientHandlersRpcHandlers(rpcRegistry, target)`, plus the matching `<Name>ClientHandlersRpcHandlersRegistrationProvider` that wires `RpcRegistrationCollector.registerProvider(it)` so the handlers are registered against every `RpcRegistry` instance at construction time.

**There is no manual-`register` exception for kvisionApp listeners.** Every client-side notification channel goes through a typed `@RpcMethod`-annotated object. To add a new client listener, follow the four-step shape:

1. **Create the handler file** under `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/<area>/<Name>ClientHandlers.kt` (or extend the existing package if the area already has one — `ui.gameplay.networking` for `UiSignalClientHandlers.kt` and `ActionHistoryClientHandlers.kt`, `audio/` for `AudioClientHandlers.kt`, `mapUpload/` for the new map-upload handlers). The file is a singleton `object` with one `@RpcMethod`-annotated `suspend fun` per channel:

   ```kotlin
   package org.ttt.autogenesis.kvisionapp.<area>

   object <Name>ClientHandlers
   {
       @RpcMethod(name = "<Channel.Name>", direction = RpcDirection.CLIENT)
       suspend fun handle<Channel>(_ctx: RpcCallContext, data: <Channel>Data)
       {
           // body — log, route to UI, dispatch to a state store, whatever the
           // notification's contract requires
       }
   }
   ```

2. **Run `./gradlew :kvisionApp:compileKotlinJs`** to trigger the KSP step. The generated `register<Name>ClientHandlersRpcHandlers(this, <Name>)` function appears in the `kvisionApp/build/generated/ksp/...` tree on success.

3. **Wire the call into the `WebSocketRpcBridge.registerHandlers { ... }` block in `Main.kt`** — the import for the new handler class goes into the existing import block (alphabetical position), and the `register<Name>ClientHandlersRpcHandlers(this, <Name>)` call goes into the `WebSocketRpcBridge.registerHandlers { ... }` block, one line per handler class. Use the fully-qualified package name as the qualifier (e.g. `org.ttt.autogenesis.kvisionapp.mapUpload.registerMapUploadErrorClientHandlersRpcHandlers(...)`) — matches the style of the existing `AudioClientHandlers` line at `Main.kt:588`.

4. **Drop the DTO import from `Main.kt`** if it was only there for the manual decode. The auto-generated `registerTyped(...)` handles the `RpcJson.decodeFromJsonElement(...)` against `MapUploadErrorData.serializer()` (or whichever DTO) for you — the handler signature is typed.

**Why no manual `register(...)` block for clients (anti-pattern, captured 2026-08-10):** the prior version of this skill documented a "manual `register("client.X", RpcDirection.CLIENT) { ctx, payload -> ... }` block inside `WebSocketRpcBridge.registerHandlers`" escape hatch for the case where no generated client handler class exists. That escape hatch was wrong. The correct answer is always "add a `<Name>ClientHandlers` object, let KSP generate the binding." Real failure case (2026-08-10): the `Map.Upload.Error` notification on kvisionApp was hand-rolled with `register("Map.Upload.Error", RpcDirection.CLIENT) { _, params -> RpcJson.decodeFromJsonElement(MapUploadErrorData.serializer(), it)?.reason ?: "Map upload rejected"; Logger.warn(...); null }` at `Main.kt:597-605`, bypassing the KSP-generated contract that every other client handler (`UiSignalClientHandlers`, `ActionHistoryClientHandlers`, `AudioClientHandlers`) used. The operator called this out directly: *"Rpc methods are supposed to auto register and not need those manual registers wtf is going on? What did you do?"* The fix was to add `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/mapUpload/MapUploadErrorClientHandlers.kt` (and the matching success one), let KSP generate the bindings (verified at `kvisionApp/build/generated/ksp/js/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/mapUpload/GeneratedMapUploadErrorClientHandlersRpcBindings.kt` and `GeneratedMapUploadSuccessClientHandlersRpcBindings.kt`), and replace the manual block with `org.ttt.autogenesis.kvisionapp.mapUpload.registerMapUploadErrorClientHandlersRpcHandlers(this, MapUploadErrorClientHandlers)` and the matching success call. The two `Map.Upload.{Error,Success}` channels are now on the same auto-registration contract as UiSignal/ActionHistory/Audio.

**Detection heuristic**: any time you find yourself writing a `register("client.X" or "ui.X" or "Map.Upload.X", RpcDirection.CLIENT) { _, params -> RpcJson.decodeFromJsonElement(<DtoType>.serializer(), it) ?: ...; <side effect>; null }` block in `Main.kt`, you have bypassed the auto-registration contract. Delete the block, create a `<Name>ClientHandlers.kt` file with the typed `@RpcMethod`-annotated suspend function, let KSP regenerate, and replace the manual call with the auto-generated `register<Name>ClientHandlersRpcHandlers(...)` call. The DTO import in `Main.kt` should also be removed (it is no longer referenced there).

## Kotlin 2.2 + KVision/JS launch parser quirk

**`MainScope().launch\n{` (brace on new line) FAILS** with "Function invocation 'launch(...)' expected" on the Kotlin/JS target (Kotlin 2.2.20, KVision 9.1.1). The same code with the brace on the SAME line works. This is a parser quirk that wasted ~15 minutes of debugging because the error message points at `.launch` as if the extension function doesn't exist, when it does — the issue is the trailing-lambda shape.

**Always use single-line `MainScope().launch {` form in `:kvisionApp` Kotlin/JS files**, even for multi-statement lambda bodies. Same-line brace is the universal TTT Kotlin style anyway, so this is consistent with the rest of the codebase.

The companion quirk for server-extend JVM: `private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())` + `scope.launch { ... }` with multi-line lambda body also fails the same way in this build. The fix that worked is the explicit form: `kotlinx.coroutines.GlobalScope.launch(context) { ... }` with the lambda inside the parentheses, plus `@file:OptIn(kotlinx.coroutines.DelicateCoroutinesApi::class)`. The same single-line `CoroutineScope(Dispatchers.Default).launch { ... }` form works in `Server.kt` and `GameRestoreRpcHandlers.kt` (those files are written with the same-line form).

## Resume-Game SSE-Push Architecture (single-player snapshot → server-extend → client rehydrate)

Single-player resume-game is a state-restore pipeline that fires when the user logs back in and the server still has a snapshot from their previous session. The architecture is fully wired across 5 modules — capture → VFS write → SSE-attached push → dialog → dual-mode restore (dev + live). File:line evidence below verified by direct reads on 2026-06-24.

**Trigger:** SSE `/events` connection with `accelbyteId` query parameter (NOT a literal login hook — the SSE open is what fires the check). User-observable behavior is similar to a login hook (both fire shortly after auth), but the mechanism is SSE-driven. See `ServerExtend.kt:283-300` for the `/events` endpoint.

**Architecture (A→F trace):**

1. **A. Single-player snapshot capture** — `TurnHarness.serializeCurrentWorldSnapshotToUserRecord` (server/src/main/kotlin/.../TurnHarness.kt:1759) writes the current world + history to the user's VFS record under the `running-game` key. Triggered by `TurnHarness.clearRunningGameForUser` (line 2015) or `invalidateRunningGameRecord` (line 2064).
2. **B. server-extend polls on SSE connect** — `ResumeAvailabilityPushService.checkAndPush(accelbyteId)` (server-extend/src/main/kotlin/.../ResumeAvailabilityPushService.kt) reads the user's `running-game` record from VFS via `vfs.fetchUserRecord`. If non-null, builds a `ResumeAvailabilityNotification` and pushes it down. Fires via the SSE handler in `ServerExtend.kt:283-300`.
3. **C. client.resumeAvailable push** — server-extend opens a short-lived WS to `127.0.0.1:9080` (the main server's WS endpoint) and calls `client.rpcInvoker.invoke("client.resumeAvailable", payloadElement)` (RPC bridge pattern documented above).
4. **D. main server routes the push** — `UiSignalRpcHandlers.notifyResumeAvailable` (server/src/main/kotlin/.../UiSignalRpcHandlers.kt:642) receives the `client.resumeAvailable` notification. Looks up the user's WS connection via `WorldManager.playerStats.firstOrNull { it.accelByteUserId == userId }`. Iterates `sendRpcMessage(RpcMessage.Notification("client.resumeAvailable", payload))`.
5. **E. client mounts ResumeOrNewDialog** — `ResumeAvailabilityListener.kt:153-160` (`kvisionApp/src/jsMain/kotlin/.../`) subscribes to `client.resumeAvailable` and mounts `ResumeOrNewDialog` (a 3-button widget: Resume / New Game / Cancel).
6. **F. resume session begins** — `MainMenu.beginResumeSession()` (lines 382-441) branches:
   - **Dev mode:** `MatchmakingClient.requestResume()` returns a local GameTicket with `serverUrl="127.0.0.1:9080"` and `resumeFromVfs=true`. Client connects via `connectToGameServer()`.
   - **Live mode:** `MatchmakingClient.requestResumeLive()` builds a match2 ticket via `SINGLEPLAYER_RESUME_POOL = "singleplayer-resume"` (`ServerConnector.kt:113`). The match2 ticket carries `resumeFromVfs=true` and `resumeUserId=accelByteId`. The DS receives `setGameMode(resumeFromVfs=true)` and calls `GameRestoreRpcHandlers.restoreRunningGameForUser(resumeUserId)` BEFORE the fresh-state reset.

**Critical implementation details:**

- **Rehydrate ordering** — `GameInit.defineGameRules()` (server/src/main/kotlin/gameInit/GameInit.kt:46-58) calls `restoreRunningGameForUser(resumeUserId)` BEFORE `TurnHarness.resetState()` at line 62. The rehydrate must complete before the fresh-state reset; otherwise the snapshot is lost. Pinned by `GameInitDefineGameRulesResumeTest` (4 cases).
- **World emptiness check** — `WorldManager.isWorldEmpty()` (server/src/main/kotlin/gameState/WorldManager.kt:85-88) returns `world.roundNumber <= 1 && history.isEmpty()`. Deliberately does NOT inspect `activePlayers` — this is the seed-player fix that allows auto-restore on a fresh DS without false negatives. Used in `Server.kt:321` to decide whether to auto-restore.
- **Map pack compatibility** — saved snapshots store map name as `resource:maps/IO-map.map`; `MapSelectionService.loadBytesByName` (server/src/main/kotlin/gameInit/MapSelectionService.kt:154) calls `stripResourcePrefix` (lines 193-196) to strip the `resource:` prefix on lookup. Without this, restored snapshots fail with map-not-found.
- **Race recovery** — when `AdminDeletePlayerRecord` fails with action-code 20013 (admin lacks CloudSave delete permission), `invalidateRunningGameRecord` writes a `{consumed:true, consumedAt:...}` sentinel instead of deleting. `GameRestoreRpcHandlers.hasRunningGame` recognizes the sentinel and returns False (treating it as "no live save"). This is the workaround for the AccelByte IAM 20013 permission gap; the operator runbook is at `docs/OPERATIONS.md:8-50`.
- **`notifyResumeAvailable` must guard against mid-game re-pushes (2026-06-27)** — every SSE reconnect (page reload, network blip, post-skipLogin rebind) fires `server-extend`'s `triggerSseResumePush(accelbyteId)` which pushes a modal to the user's WS session. Without a guard, the modal pops up on every reconnect mid-game, forcing the user to dismiss it repeatedly. The fix at `UiSignalRpcHandlers.kt:660` adds an `isGameActive && playerStats populated && lastRehydratedAccelByteUserId != userId` check; if the user is mid-game, the push is silently dropped. The `&& !worldJustRehydratedForThisUser` exception preserves the documented race-recovery path: when the user IS mid-resume, the push fires right after the auto-restore's initial sync, and the modal there lets the user choose to start fresh or reload to re-resume. Only the mid-game case (user joined, world rehydrated some time ago) is dropped. Without this guard, the user reported "the popup randomly keeps appearing after the player is back in the game."

- **`shouldPersistOnDisconnect` MUST gate by `historySize > 0` (2026-06-27)** — companion fix to the consumed-sentinel removal. The save-on-disconnect path at `Server.kt:1144` was previously writing a `round=1, turnIndex=0, historyEntries=0` snapshot to VFS for every user who opened-but-didn't-play a game. The next login offered that phantom as a Resume, the Resume faithfully rehydrated the empty world, and the user saw the "no data, no player, nothing" GameplayUI. The fix added a `historySize: Int = 0` parameter (with default) to `shouldPersistOnDisconnect`; the gate now returns false when no turn was submitted. **Order of operations rule:** fix the producer gate (`historySize > 0` in `shouldPersistOnDisconnect`) BEFORE removing the consumer side-effect (consumed-sentinel on resume). Removing the sentinel exposes the gate weakness; the two fixes ship together. The user reported "Regression. Now it just does htis. No data, nno player no nothiing." — this was the exact symptom. Test the user-visible behavior: the regression test `SaveOnDisconnectGateTest.shouldPersistOnDisconnect_returns_false_when_history_is_empty` passes, but a live e2e probe that opens a game, disconnects immediately, and clicks Resume should also assert that the Resume dialog DOES NOT appear (or that a "fresh game" path is taken).

- **SSE `accelbyteId` is the load-bearing parameter** — if absent, the resume push is silently skipped (no error, just absent). The bridge `RestRpcBridge.connect(accelbyteId=globals.AccelByteEnv.userId)` (Main.kt:124-125) propagates the parameter into `RestRpcBridgeJs.connect`, which STORES it for idempotency but DOES NOT forward it to `RestRpcClientConfig(...)` — `RestRpcClientConfig` has no `accelbyteId` field at all and `buildEndpointUrl` does not append `?accelbyteId=...` to the SSE URL. End-to-end fix landed in commit `f16987684` (2026-06-24): added `internal val accelbyteId: String? = null` to `RestRpcClientConfig`, appended `accelbyteId` in `buildEndpointUrl` (only when non-blank), and forwarded the param in both `RestRpcBridgeJs.connect` and `RestRpcBridgeJvm.connect`. **Pinned by `RestRpcClientConfigUrlTest` (6 cases) which constructs the lowest-level `RestRpcClientConfig` and asserts on the wire-level URL string** — local-layer signature tests like `RestRpcBridgeAccelbyteIdTest` are NOT sufficient for wrapper-chain code; see "Wrapper-chain params need wire-level tests" pitfall below.
- **`_fire_pre_llm_call` dispatch** — in hermes-agent's `run_agent.py`, the `pre_llm_call` hook must be invoked explicitly via `invoke_hook("pre_llm_call", ...)` and the returned `{"context": ...}` entries must be merged into the LLM context. Without this, the plugin's hook is registered but never fires (DEAD CODE). Pinned by `test_hook_return_mechanism_verified`.

**Test pinning contract (Tasks 17, 18 closed 2026-06-24):**

| File | Tests | What it pins |
|------|-------|--------------|
| `server/src/test/kotlin/gameInit/GameInitDefineGameRulesResumeTest.kt` | 4 | Rehydrate ordering + sentinel handling + blank-userId skip |
| `server-extend/src/test/kotlin/.../ServerExtendSseAccelbyteIdTest.kt` | 4 | SSE-attached accelbyteId gate (the trigger) |
| `server-extend/src/test/kotlin/.../ServerConnectorRequestResumeTest.kt` | 4 | Live-mode `requestResume` GameTicket shape + blank-userId early reject + timeout empty ticket + dev mode 127.0.0.1:9080 |
| `server/src/test/kotlin/.../GameRestoreRpcHandlersTest.kt` + `*RaceTest.kt` + `*HasRunningGameRaceTest.kt` | 18 | The VFS save/restore race-recovery matrix |
| `server/src/test/kotlin/.../TurnHarnessRunningGameTest.kt` | 7 | Snapshot roundtrip + invalidate-after-apply |
| `kvisionApp/src/jsTest/kotlin/.../ResumeAvailabilityListenerTest.kt` | 3 | Listener mounts dialog + null-safe callback |
| `kvisionApp/src/jsTest/kotlin/.../RestRpcBridgeAccelbyteIdTest.kt` | 1 | `connect(accelbyteId=...)` signature guard |

Total: 41 tests pinning the resume-game contract. 1 known test pollution failure (testSessionLog.py's `importlib` reload contaminating `HOOK_BASE`) is unrelated to production code.

**Operators must provide (NOT code territory):**

- AccelByte admin client role must have `CLOUDSAVE:RECORD [DELETE]` permission (or per-user form). Without it, `AdminDeletePlayerRecordHandlerV1` returns 403 with action-code 8 denied. Sentinel fallback handles this gracefully.
- AccelByte matchmaker must have a `singleplayer-resume` pool provisioned, with `resume: true` attribute scoring. The pool name is hardcoded at `ServerConnector.kt:113`.
- Production deployment needs `run_agent.py:_fire_pre_llm_call` to actually fire (NOT optional — this is the only path the plugin's hook reaches the LLM context).

## Calling an RPC (the call-site side)

The handler side is documented above. The **caller** side — how do you actually invoke an RPC from your code — is documented nowhere else in the codebase and was the question that triggered this session's iteration (2026-08-10).

**The mental model**: there is no single global `invoke()` because `RpcInvoker` is stateful (it owns a `pending` map of in-flight requests with completable-deferreds). You can't share one invoker across two transports — each transport owns its own invoker behind a bridge object. There are exactly three call-site patterns, one per side of the wire:

### 1. Server → server-extend (JVM, gRPC on 9092)

`ServerExtendConnection` is a `private object` singleton in `server/src/main/kotlin/accounting/Billing.kt:302-376` that **lazily boots the gRPC client on first call and returns its invoker**. This is the one-step entry point the operator remembers:

```kotlin
// server/src/main/kotlin/accounting/Billing.kt:302
private object ServerExtendConnection {
    private const val SERVER_EXTEND_ENDPOINT = "127.0.0.1:9092"
    private const val PLAYER_ID = "billing-service"
    private var grpcClient: GrpcRpcClient? = null

    suspend fun getInvoker(): RpcInvoker? {
        testInvoker?.let { return it }   // test seam — see BillingTest
        val existing = grpcClient
        if (existing != null && existing.isConnected()) return existing.rpcInvoker
        // ...connectionMutex.withLock { lazy connect() }
    }
}

// Usage (real call site, Billing.kt:656):
val invoker = ServerExtendConnection.getInvoker()
val response = invoker.invoke("server.extend.getUsageLedger", request)
```

The endpoint is hardcoded to `127.0.0.1:9092` and the playerId to `billing-service` — this is intentional, server-extend is local to the host. The `testInvoker` / `setTestInvoker` seam at lines 315-328 is how unit tests inject canned `RpcInvoker` responses without booting a real gRPC stack; production code never sets it.

**There is no equivalent `ServerExtendConnection` in other server modules** — only `accounting/Billing.kt` uses server-extend's gRPC. If a new server-side caller needs the same pattern, the cleanest path is to lift this object to `org.ttt.autogenesis.server.ServerExtendConnection` (sharedModel or server root) rather than copy-paste it. As of 2026-08-10 nobody has done that lift.

### 2. Browser → server-extend (JS, REST+SSE or gRPC)

`ServerExtendBridge` is a transport-aware facade in `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/ServerExtendBridge.kt:21-31`. It hides the REST-vs-gRPC transport switch behind a single `rpcInvoker` getter:

```kotlin
object ServerExtendBridge {
    val rpcInvoker: RpcInvoker?
        get() = when (activeTransport()) {
            ServerExtendTransport.REST_SSE   -> SharedRestRpcBridge.rpcInvoker
            ServerExtendTransport.GRPC_BIDI,
            ServerExtendTransport.GRPC_WEB   -> SharedGrpcRpcBridge.rpcInvoker
        }
    // ...isConnected, isSessionReady, registerHandlers
}

// Usage (real call site, kvisionApp Main.kt:688):
val response = ServerExtendBridge.rpcInvoker?.invoke("server.extend.invokeMatchMaking", null)
```

The transport mode is configurable (REST+SSE is the default; gRPC bidi/gRPC-web are switchable per deployment). The facade exists precisely so call sites don't have to branch on transport — they read `ServerExtendBridge.rpcInvoker` and call `invoke()` on whatever comes back.

### 3. Browser → main server (JS, WebSocket on 9080)

The always-on WebSocket bridge. Same pattern as the server-extend facade but transport-fixed to WS:

```kotlin
// Usage (real call sites, kvisionApp AgentWorkStreamManager.kt:121,
// MatchmakingClient.kt:646/697/747/812, NeuralLinkWindow.kt:195):
WebSocketRpcBridge.rpcInvoker?.invoke("server.someMethod", payload)
```

The `rpcInvoker` is null while disconnected — always `?.invoke(...)`, never bare `.invoke(...)`. A null-skip pattern is the idiom across the browser codebase.

### 4. server-extend -> main server (JVM, REST + SSE on 9080/7070)

The long-lived server-extend bridge. Same shape as the bridge-facade pattern on the JS side, but on the JVM. The call sites are direct reads of `RestRpcBridge.rpcInvoker` at the point of call -- NOT a captured private val on a class:

```kotlin
// Real call site: server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/RestRpcExample.kt:18
val response = RestRpcBridge.rpcInvoker?.invoke("main.server.status", null)

// Real call site: server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ResumeAvailabilityPushService.kt:400
val response: RpcMessage.Response = client.rpcInvoker.invoke("client.resumeAvailable", payload)
```

`RestRpcBridge` is connected once at server-extend boot (see `RestRpcExample.kt:13-15` -- `RestRpcBridge.connect(baseUrl = RestRpcBridgeConfig.development(8080))`). The `rpcInvoker` is a nullable singleton property; read it at the call site with `?.invoke(...)` or unwrap locally if you have already checked.

**This is the answer to the recurring 'how do I call main server from server-extend?' question.** The wrong pattern is capturing it into a `private val invoker = checkNotNull(RestRpcBridge.rpcInvoker) { ... }` on a class -- no production code does this, and the operator will reject the example because the bridge is a nullable singleton that the user wants to access at the call site, not a one-time-checked constructor dependency. If the bridge is not connected when the call fires, `invoke()` never runs -- which is the correct behavior.

There is **no JVM-side analog of `ServerExtendBridge` today**. Only `accounting/Billing.kt:302` (`ServerExtendConnection`) opens a cross-bridge on the server side. If a new caller on the server side needs the same lazy-connect pattern, lift `ServerExtendConnection` to `sharedModel` or `server/src/main/kotlin/org/ttt/autogenesis/server/ServerExtendConnection.kt` rather than copy-paste it. As of 2026-08-10 nobody has done that lift.

### The three `invoke()` overloads

`RpcInvoker` (`sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/RpcRuntime.kt:446, 575, 587`) has three call shapes:

```kotlin
// Raw JSON element + optional timeout
suspend fun invoke(method: String, params: JsonElement?, timeoutMillis: Long? = null): RpcMessage.Response

// Typed with explicit serializer
suspend fun <P> invoke(method: String, params: P, serializer: KSerializer<P>): RpcMessage.Response

// Typed reified (most common — no serializer passed at call site)
suspend inline fun <reified P> invoke(method: String, params: P): RpcMessage.Response =
    invoke(method, params, serializer())
```

The reified overload is the idiomatic shape for typed payloads. For notifications (no response expected), use `RpcMessage.Notification(...)` directly through the server-side `connectionManager.broadcast(...)` path — invoke() always round-trips a Response.

### Server-side push to clients (notifications, not invoke)

Server-to-client notifications do NOT go through `invoke()`. Use `connectionManager.broadcast(RpcMessage.Notification("ui.X", payload))` or iterate a specific session via `sendRpcMessage(...)`. The pattern is documented in `server/src/main/kotlin/org/ttt/autogenesis/server/audio/AudioManager.kt:134/161/193/216/287` (broadcast shape) and `UiSignalRpcHandlers.kt:74-79` (per-session shape).

### Anti-pattern: trying to share one invoker across transports

A future maintainer might be tempted to introduce a "global RpcInvoker singleton" to make call sites one-liners. Don't. Each transport connection has its own pending-request map; collapsing them would lose the per-connection lifecycle (cancellation on close, timeout on a specific transport's event loop, drain on swap). The bridge-facade pattern is the correct shape.

### Anti-pattern: fabricating a call-site pattern that isn't in the production code (2026-08-10)

When the user asks "how do I call X from Y" the answer must come from how the codebase actually does it -- not from how the API surface would naturally compose if you wrote the pattern from scratch. The most common failure is sketching a `private val invoker = checkNotNull(SomeBridge.rpcInvoker) { ... }` capture on a class that takes the bridge singleton at construction time and stashes it for use in a method body. The bridge-facade pattern is a `null`-skip property read at the call site (or an `?.invoke(...)` chained read), not a checked-then-stashed constructor dependency.

**Operator pushback from this session (2026-08-10), verbatim:** *"this does not look right to me and I'm getting fed up if I don't like what I see you're going to fix this system exactly as I demand"*. The offending pattern was a `checkNotNull(RestRpcBridge.rpcInvoker)` capture in `setOnFailure`. The right shape was `RestRpcBridge.rpcInvoker?.invoke(method, payload)` at the call site, exactly as `RestRpcExample.kt:18`, `ResumeAvailabilityPushService.kt:400,448`, `Main.kt:704`, and `CommanderCreationDialog.kt:286` do it.

**Operator pushback from a second session the same day (2026-08-10, `mapSafetyBuilder.kt`):** *"that needs to be constructed though. So that means I need to find where it's single objectt ref is saved to where is that?"* followed by *"why the fuck is this rpc system like this? THIS IS DOGSHIT"* and *"Whatever you figure itt out finish the functionnn inn map safety so i cann move onn with my flie and if you fuck it up you're deleted"*. The pattern here was different -- the operator did NOT need a system-design writeup, they needed the singleton object's method called. `MapUploadErrorHandlers.sendMapUploadError(playerId, reason)` is the entire answer. The "where is the singleton ref saved" question has the answer "Kotlin `object` is a singleton by language -- there is no instance reference to save." Answered that, then did NOT pivot into a refactor pitch. Patched the function, dropped a 3-line receipt, moved on. Lesson: when the operator rants about the system shape mid-task, the rant is a separate thread, not the current task. Solve the current task.

**Recipe for 'how do I call X from Y' answers**:

1. **Run `grep -rn 'Bridge\.rpcInvoker\?\?\.invoke\|Bridge\.rpcInvoker\.invoke\|invoker\.invoke' <module>/src/main/kotlin/`** to find every existing call site in the target module. This is your evidence base.
2. **Pick the call site that best matches the user's situation** (same bridge, same direction, same payload shape). Cite the file:line.
3. **If the user is asking about a bridge they don't yet have wired**, show the connect step first (`RestRpcBridge.connect(...)`), then the `rpcInvoker?.invoke(...)` read at the call site. Do not show a check-then-stash class constructor.
4. **Verify the connection.** If the bridge might not be connected at call time, the bridge property is nullable and you read it with `?.`. If the bridge is guaranteed (e.g. the per-session `WebSocketRpcClient.rpcInvoker` because the caller owns the client lifecycle), read it as `.invoke(...)` without the safe-call.
5. **If the requested pattern would require new infrastructure that doesn't exist** (e.g. a per-session invoker accessible from inside a TPipe `setOnFailure` closure when no such session is in scope), say so plainly. Don't bridge the gap with a fabricated injection pattern -- the operator's next move will be to find that the pattern doesn't work, and the trust hit is the real cost.

**Anti-patterns**:

- `private val invoker = checkNotNull(Bridge.rpcInvoker) { ... }` in a class constructor. The bridge is a `null`-skip singleton, not a required-injection dependency. Production code reads it at the call site.
- Sketching a three-layer "transport-aware facade" in code when the user asked a one-bridge question. The answer is the one bridge, not an abstracted version of all bridges.
- Inventing a `Bridge.rpcInvoker(...)` factory call when the singleton is a property. The bridge uses a `val rpcInvoker: RpcInvoker?` getter (or a `getInvoker()` suspend method like `ServerExtendConnection`), not a factory.
- Pattern-matching on `Main.kt:688` (the server-extend bridge facade on the JS side) and applying it to the JVM side. The JVM side does not have that facade today; it reads `RestRpcBridge.rpcInvoker` directly.

**Detection heuristic**: if your answer to "how do I call X from Y" includes an explicit `checkNotNull` or `!!` against a `Bridge.rpcInvoker` or similar bridge-singleton property, you have fabricated a pattern. Production code skips past nulls at the call site with `?.invoke(...)` rather than crashing with an error message about the bridge not being connected.

## TPipe pipe failure → RPC push (closing the loop from inside `setOnFailure`)

The Autogenesis agent builders (`server-extend/src/main/kotlin/agent/builders/*.kt`, `server/src/main/kotlin/agent/builders/*`) are TPipe pipelines. When a Bedrock model call fails validation or the JSON output is rejected, `setOnFailure { original, processed -> ... }` fires on the pipe that owns the failure. The natural follow-up is often "tell the client this failed" — but the lambda's only parameters are `(original: MultimodalContent, processed: MultimodalContent)`. **No session, no connection, no playerId is reachable from inside that lambda unless the agent factory threaded it in.**

The signature on TPipe's `Pipe` base class (verified 2026-08-10, `TPipe/src/main/kotlin/Pipe/Pipe.kt:4838`):

```kotlin
fun setOnFailure(func: suspend (original: MultimodalContent, processed: MultimodalContent) -> MultimodalContent): Pipe
```

Two valid patterns for pushing an RPC out of the failure:

### Pattern A — Closure-capture at agent-build time (preferred when scope is single-request)

Take the `playerId` (and any other session/connection) as constructor parameters to `buildXxxAgent(...)`. Capture them in `val` locals before the `.apply { ... }` block and reference them directly inside `setOnFailure`:

```kotlin
internal fun buildMapSafetyAgent(
    playerId: String,                            // captured
    connectionManager: RestPlayerConnectionManager // captured
): Pipeline {
    val safePlayerId = playerId                   // hoist for setOnFailure closure
    val manager = connectionManager
    val imageChecker = BedrockMultimodalPipe().apply {
        // ... config ...
        setOnFailure { _, processed ->
            val safety = extractJson<mapSafetyCheck>(processed.text) ?: mapSafetyCheck()
            if (!safety.isAllowed) {
                val notification = RpcMessage.Notification(
                    method = "Map.Upload.Error",
                    params = RpcJson.encodeToJsonElement(...)
                )
                manager.findSession(safePlayerId)?.sendRpcMessage(notification)
            }
            MultimodalContent()
        }
    }
    return Pipeline()
}
```

**Pros:** zero indirection, the lambda body reads exactly what you'd expect. **Cons:** the agent is single-use — re-using the same `Pipeline` for a different `playerId` requires rebuilding it. Acceptable when one agent instance = one player's request.

### Pattern B — ContextBank round-trip (when the agent is shared across requests)

When the agent factory is called once at module init and the same `Pipeline` instance services many players across many requests, there's no closure to capture. The TPipe-idiomatic persistence surface is the ContextBank:

```kotlin
// Stash before pipe execution (e.g. in a wrapping Pipeline.runWith call,
// or in the caller that knows the playerId at dispatch time):
ContextBank.emplaceWithMutex(
    key = "<scope>.activePlayer",                  // e.g. "mapSafetyActivePlayer"
    window = ContextWindow().apply { contextElements.add(playerId) },
    mode = StorageMode.MEMORY_ONLY
)

// Fetch inside setOnFailure:
val stored = ContextBank.getContextFromBank("<scope>.activePlayer")
val playerId = stored.contextElements.firstOrNull() ?: return@setOnFailure MultimodalContent()
```

`ContextWindow.contextElements` is `MutableList<String>` (`TPipe/src/main/kotlin/Context/ContextWindow.kt:29`), perfect for a single string or a small bag of key:value pairs. The `emplaceWithMutex` variant is the suspend-safe choice — `emplace(key, window, mode)` is synchronous and can deadlock if called from a coroutine. The bank key is the only coordination surface you need; pick a name that's unique enough not to collide with adjacent agents running in the same JVM (e.g. `mapSafetyActivePlayer`, not `player`).

**Pros:** agent is reusable, no closure-over-constructor-arg coupling. **Cons:** two extra suspending calls per failure, plus the discipline of remembering to clear the key on success so the next request doesn't see a stale playerId.

**Anti-pattern**: the no-op `setOnFailure` that swallows the failure

```kotlin
// BAD -- silently masks the failure from upstream
setOnFailure { _, processed ->
    return@setOnFailure MultimodalContent()  // the JSON-parse failure? the safety-reject? who knows
}
```

This shape compiles cleanly and the pipe still returns a value, but **upstream consumers of the pipeline have no way to learn that anything went wrong**. If you find yourself writing this in a new agent, the question to ask is "what does the consumer of this pipe expect to learn from the failure?" If the answer is "nothing -- keep going" then the no-op is correct. If the answer is "the player needs to see a rejection" or "we need to log the cause" then you're missing the RPC push (Pattern A or B above) or a `Logger.error(LogCategory.LLM, ...)` call. The pre-existing `setOnFailure` in `server-extend/.../mapSafetyBuilder.kt:54-63` (pre-2026-08-10) was exactly this anti-pattern: it swallowed the safety rejection and returned an empty `MultimodalContent`, so the client never learned the upload had been blocked.

### Server-extend notification singleton pattern (the canonical pipe-failure -> client push)

The pipe-failure patterns above cover the call shape from inside `setOnFailure`, but they don't address the broader question: *how does a server-extend backend piece (pipe failure, command handler, async job) push a typed notification down to a specific player's kvisionApp tab?* The canonical answer is a notification-singleton, mirroring the `UiSignalRpcHandlers.sendTurnTimerUpdate` shape on the main server side.

The reference implementation is `MapUploadErrorHandlers` (`server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/MapUploadErrorHandlers.kt`). Five pieces, all required:

1. **A typed DTO in `sharedModel`** -- `MapUploadErrorData(val reason: String)` at `sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/UiSignalDtos.kt:340`. `@Serializable` so the JSON path round-trips cleanly.
2. **A notification method name constant** -- `"Map.Upload.Error"`. Convention is `<Area>.<Event>.<Outcome>` in PascalCase. The same string is the lookup key the kvisionApp listener registers against.
3. **A singleton (`object`) that owns a nullable `RestPlayerConnectionManager`** -- injected once at startup with `MapUploadErrorHandlers.registerConnectionManager(connectionManager)` at `ServerExtend.kt:292`. The injection site is one line in the module wiring; the singleton's `connectionManager` field is `var` so `resetForTest()` can clear it between cases.
4. **The send method resolves manager -> session -> typed payload -> notification -> send**:

   ```kotlin
   suspend fun sendMapUploadError(playerId: String, reason: String) {
       val manager = connectionManager
       if (manager == null) {
           Logger.warn(LogCategory.NETWORK, "MapUploadErrorHandlers: sendMapUploadError() called before registerConnectionManager() -- dropping notification for playerId=$playerId")
           return
       }
       val session = manager.findSession(playerId)
       if (session == null) {
           Logger.warn(LogCategory.NETWORK, "MapUploadErrorHandlers: Cannot send map upload error, session '$playerId' not found")
           return
       }
       val data = MapUploadErrorData(reason = reason)
       val payload = RpcJson.encodeToJsonElement(MapUploadErrorData.serializer(), data)
       val notification = RpcMessage.Notification("Map.Upload.Error", payload)
       Logger.info(LogCategory.NETWORK, "MapUploadErrorHandlers: Dispatching 'Map.Upload.Error' to $playerId (reason='$reason')")
       session.sendRpcMessage(notification)
   }
   ```

5. **A matching client-side handler** -- in `kvisionApp/src/jsMain/kotlin/.../Main.kt`, registered against `RpcDirection.CLIENT` for `"Map.Upload.Error"`. The handler deserializes `MapUploadErrorData` from the `params: JsonElement` and surfaces the rejection in the upload UI.

The full shape -- typed DTO, named method, registered handler, manager-injected singleton -- is the contract. **Pitfall**: a partial implementation that constructs the `RpcMessage.Notification` inside a pipe `setOnFailure` lambda and then doesn't send it (the pre-2026-08-10 `mapSafetyBuilder.kt:100-104` state) builds the payload and drops it on the floor. Even if the lambda has access to the `connectionManager`, the right shape is `manager.findSession(playerId)?.sendRpcMessage(notification)` -- NOT a queue, NOT a callback registration, NOT a deferred dispatch. The SSE channel is hot, `sendRpcMessage` is `suspend Unit`, and it lands the frame immediately.

**Anti-pattern**: building the `RpcMessage.Notification` inside the lambda and then forgetting to call `session.sendRpcMessage(...)` on it. The notification is a value object -- it doesn't transport itself. The error message at `mapSafetyBuilder.kt:101` (`val message = RpcMessage.Notification("server-extend.mapUpload.error", payload)`) without a trailing `session.sendRpcMessage(message)` is a silent bug class: the LLM correctly rejected the upload, the JSON shape was correct, the manager and session were both resolvable, but the player never saw the toast because the notification was never written to the SSE channel.

**Anti-pattern**: inventing the notification method name. The singleton file (`MapUploadErrorHandlers.kt`) is the canonical owner of the method name string (`"Map.Upload.Error"`, PascalCase, `<Area>.<Event>.<Outcome>`). When the caller (pipe builder, command handler, async job) builds or wraps the notification, it MUST read or use the singleton's exact string -- NOT a parallel convention invented at the call site. Real failure case (2026-08-10, `mapSafetyBuilder.kt`): the builder had `RpcMessage.Notification("server-extend.mapUpload.error", payload)` -- a `server-extend` prefix and lowercase `mapUpload.error`, neither of which matched the singleton's `"Map.Upload.Error"`. The two strings both serialize, both parse, both are valid `RpcMessage.Notification` values -- but the listener in `kvisionApp/Main.kt` is registered against `"Map.Upload.Error"`. The wrong-string notification travels the SSE channel unmolested and the client listener never fires. Fix: replace the local `Notification(...)` construction with `MapUploadErrorHandlers.sendMapUploadError(playerId, reason)` -- the singleton owns the string. Detection heuristic: any caller-side construction of `RpcMessage.Notification(...)` for a domain event that already has a singleton handler is wrong-shaped; delete the construction and call the singleton method.

**Pre-edit baseline-compile gate (2026-08-10)**: when the patch touches a pipe-builder `setOnFailure` lambda AND the singleton it will call into, baseline-compile BEFORE writing either edit. The compile blocker (`'public' function exposes its 'internal' parameter type ...`) lives in the singleton file (where the `register` method's visibility has to match its `internal`-typed parameter), not in the builder. If the singleton file has a pre-existing visibility trap, every edit to the builder -- even correct ones -- surfaces as a red IDE underline in the builder. The agent (this one included) wastes a turn chasing phantom bugs in the builder, then a second turn chasing the real one in the singleton, with a hostile operator steer between turns ("red error", "you fucekd up the compiler") for the lost time. The fix order is: (1) compile clean from the start of the task; (2) make the builder edit; (3) make the singleton edit only if the singleton's pre-existing `public fun register...` shape actually fails; (4) re-compile to confirm green. The build command (`./gradlew :server-extend:compileKotlin --no-daemon -q`) returns in ~25s on this host; the time saved on the second-pass hunt is much larger.

**Do-the-work framing for `setOnFailure` completion tasks (2026-08-10)**: when the operator asks "finish the function in <builder>.kt so I can move on with my file", the response is: 1-line diagnosis + the patch (add import + delete dead construction + add the singleton call) + the compile output + a receipt. It is NOT a system-design tangent about why the RPC framework as a whole is poorly shaped, even if the operator separately ranted about the framework shape in the same conversation. The two requests are different conversations: the immediate task is the function; the system critique is a separate "later" task that the operator will pick up if and when they want to. Mixing them loses the operator's time on the immediate task AND makes the system critique land weaker because it's framed as "I had to clean this up before I could do your work." Operator framing verbatim: *"finish the functionnn inn map safety so i cann move onn with my flie and if you fuck it up you're deleted"*. Read it as "land the patch, do not lecture."

**When to extract a new singleton vs call an existing one**: if the notification is a domain event that multiple backend pieces might emit (map-upload rejections, commander-creation failures, billing alerts), prefer one singleton per domain. If it's a one-off that only one pipe ever fires, inline the five pieces into the pipe file -- the singleton overhead isn't worth it. `MapUploadErrorHandlers` is the former (map upload has many failure modes); a hypothetical `BattleOutcomeHandlers` for a single pipe's resolution notification would be the latter.

## Extending the RPC surface (`RpcRegistry` is `final`; `RpcRegistrationProvider` is the seam)

This is the canonical "how do I add a child of that registry" question, and the answer is NOT literal Kotlin subclassing. Verified 2026-08-10 against `sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/RpcRuntime.kt:137` -- the declaration is `class RpcRegistry(private val localDirection : RpcDirection)`, plain `class`, not `open class`. Kotlin subclassing won't compile.

There are exactly two extension mechanisms, both of which feed handlers into every existing `RpcRegistry` instance:

1. **KSP-generated providers (the `@RpcMethod` route)** -- `@RpcMethod`-annotated functions on a class produce `_<RegistrationName>RpcHandlersProvider` accessors (e.g. `_extendCommanderRunnerRpcHandlersProvider`, `_serverConnectorRpcHandlersProvider`, `_cloudSaveProxyRpcHandlersProvider` referenced at `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt:81-83`). The KSP processor (`rpc-ksp/src/main/kotlin/org/ttt/autogenesis/ksp/RpcProcessor.kt:111-120`) generates an `internal class $providerClassName(private val target : $targetType) : RpcRegistrationProvider` whose `register()` calls into a generated `register<Name>RpcHandlers(this, target)` function. The collector-registration call lives on the same module-startup line: `RpcRegistrationCollector.registerProvider(it)`. This is the path you want for any handler whose signature follows KSP's `(ctx, payload)` rules.

2. **Manual providers (the `registerSystemProbeHandlers` route)** -- when the handler does NOT fit KSP's shape (e.g. uses `Map<String, String>` instead of a single payload struct, or needs to read an env var at registration time), write the bindings by hand using the same three pieces. The canonical example is `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/GeneratedSystemProbeHandlersRpcBindings.kt:16-37` -- it's name-aliased as "Generated" because it was extracted from an earlier KSP-managed file, and the file's own KDoc (line 13) says it follows "the same pattern as the KSP-generated bindings so that `RpcRegistrationCollector` discovers and registers the handler at startup." The three required pieces, in this exact order:

    ```kotlin
    // 1. A register function taking RpcRegistry and calling rpcRegistry.register(...)
    internal fun registerFooHandlers(rpcRegistry: RpcRegistry)
    {
        rpcRegistry.register("foo.methodName", RpcDirection.SERVER) { ctx, _ ->
            val response = FooHandlers.handle(ctx)
            RpcJson.encodeToJsonElement(FooResponse.serializer(), response)
        }
    }

    // 2. A provider class implementing RpcRegistrationProvider (the fun-interface in
    //    sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/RpcRegistrationProvider.kt:6).
    internal class FooRegistrationProvider : RpcRegistrationProvider
    {
        override fun register(rpcRegistry: RpcRegistry)
        {
            registerFooHandlers(rpcRegistry)
        }
    }

    // 3. A top-level val that fires registerProvider(it) at class-load time.
    internal val _fooProvider = FooRegistrationProvider().also {
        RpcRegistrationCollector.registerProvider(it)
    }
    ```

The collector then re-runs the provider against every new `RpcRegistry`. From `RpcRegistry.<init>` at `RpcRuntime.kt:141-149` -- `init { initializeRpcRegistrations(); RpcRegistrationCollector.registerAll(this); Logger.info(...) }`. Every `RpcRegistry` instance picks up every registered provider at construction time, so you do not need to wire anything yourself beyond the top-level val.

**Critical gotcha**: The top-level val must fire at class-load, not inside a function body. If you put `_fooProvider` inside a function or behind an `if`, the global collector never learns about it and the handlers are dead. The whole-module init in `ServerExtend.kt:81-83` (`agent.runners._extendCommanderRunnerRpcHandlersProvider`, `matchmaking._serverConnectorRpcHandlersProvider`, `proxy._cloudSaveProxyRpcHandlersProvider`) is a separate touch-point for KSP-generated providers; manual ones should not duplicate this list -- the top-level val covers them.

**Anti-pattern**: writing `class MyCustomRegistry(...) : RpcRegistry(...)` and expecting it to inherit handler registration. Kotlin won't compile `RpcRegistry` as a parent because it's `final`, and even if you rewrote the seam, the global `RpcRegistrationCollector.registerAll(this)` only fires inside the existing `RpcRegistry` init block -- a subclass would need its own contract to participate. Use the provider interface, not inheritance.

**Operator framing (2026-08-10, verbatim)**: *"...So are there a bunch more regristires like that? ... Ok so we neeed a child of that registry, adn then I can proceed. This is startinng to make more sense"*. The user was thinking OOP subclassing. The right answer is composition via `RpcRegistrationProvider`, not inheritance, and the canonical answer is the three-piece shape above using `GeneratedSystemProbeHandlersRpcBindings.kt:16-37` as the template.

## Where to find the framework code

- `@RpcMethod` annotation, `RpcDirection` enum, `RpcCallContext`, `RpcInvoker`, `RpcRegistry`, `RpcMessage` sealed class: `sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/RpcRuntime.kt` and `RpcModels.kt`
- KSP codegen: `rpc-ksp/` module
- Main server's existing RPC handlers: search for `@RpcMethod` in `server/src/main/kotlin/`. The list of generated client-handler bindings is in `kvisionApp/build/generated/ksp/main/kotlin/` after a build.
- Server-extend's existing bridge example: `server-extend/src/main/kotlin/matchmaking/ServerConnector.kt:560-624` (`notifyGameServer`)
- Server → server-extend lazy gRPC client: `server/src/main/kotlin/accounting/Billing.kt:302-376` (`ServerExtendConnection`)
- Browser → server-extend transport-aware facade: `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/ServerExtendBridge.kt:21`
- Browser → main server WebSocket bridge: `kvisionApp/src/jsMain/kotlin/ui/gameplay/...` (call sites) backed by the expect-object `WebSocketRpcBridge` in `sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/`

## Wrapper-chain params need wire-level tests (class-level pitfall, 2026-06-24)

When a parameter flows through multiple wrapper layers (e.g. a config object through bridge → wrapper → URL builder → HTTP query string), a class of bug can hide between layers: every layer's local test passes ("the bridge accepts the parameter") but no test verifies the parameter reaches the final wire format. Each layer's test sees the parameter at its local boundary and is satisfied.

**Real case (2026-06-24, resume-game audit)**: `accelbyteId` flowed through `RestRpcBridge.connect → SharedRestRpcBridge.connect → RestRpcBridgeJs.connect → RestRpcClientConfig(...) → buildEndpointUrl → HTTP query string`. Each layer's test passed:
- `RestRpcBridgeAccelbyteIdTest` (kvisionApp) — signature guard on the KVision wrapper
- `ServerExtendSseAccelbyteIdTest` (server-extend) — server-extend handler reads the query param correctly
- All other resume-game test suites

**But the bug was**: `RestRpcClientConfig` had no `accelbyteId` field, `buildEndpointUrl` never appended it, so the SSE URL on the wire did NOT include `accelbyteId=...`. Server-extend always saw `accelbyteId=""` and silently skipped the resume push. User-observed symptom: "just treats like a brand new game, makes zero attempt to even offer resuming at all."

**The fix (commit `f16987684`)** added `internal val accelbyteId: String? = null` to `RestRpcClientConfig`, appended the param in `buildEndpointUrl` (only when non-blank), forwarded in both JS and JVM bridges. **The test that caught it (`RestRpcClientConfigUrlTest`)** constructs the lowest-level `RestRpcClientConfig` and asserts on the wire-level URL string directly.

**The lesson — encode in any new RPC plumbing:**

For any parameter that flows through 2+ wrapper layers, require at least one test that pins the wire-level end-to-end contract. For URL builders this usually means `internal`-ifying the builder so the test can construct a config object and assert on the produced URL string. The seam cost is one visibility change; the test catches a whole class of bugs.

**Anti-pattern in test design**: writing only signature-guard tests at the highest layer ("does this method accept the param?"). These tests pass locally but tell you nothing about whether the param reaches the wire. They're useful for documentation but not for catching the bug class above.

**When writing tests for new plumbing** (a parameter that crosses 2+ layers), the test suite MUST include at least one wire-level assertion. Local-layer tests are a useful supplement, never a substitute.

## No manual `register(...)` blocks for client-side notification listeners (kvisionApp anti-pattern, 2026-08-10)

Every client-side notification channel on kvisionApp goes through a typed `@RpcMethod`-annotated singleton `object` (e.g. `MapUploadErrorClientHandlers`, `MapUploadSuccessClientHandlers`, `UiSignalClientHandlers`, `ActionHistoryClientHandlers`, `AudioClientHandlers`). The KSP processor at `rpc-ksp/src/main/kotlin/org/ttt/autogenesis/ksp/RpcProcessor.kt:104` generates the matching `register<Name>ClientHandlersRpcHandlers(rpcRegistry, target)` function plus the `<Name>ClientHandlersRpcHandlersRegistrationProvider` that wires `RpcRegistrationCollector.registerProvider(it)`. The Main.kt wiring block looks like:

```kotlin
WebSocketRpcBridge.registerHandlers {
    ui.gameplay.networking.registerUiSignalClientHandlersRpcHandlers(this, UiSignalClientHandlers)
    ui.gameplay.networking.registerActionHistoryClientHandlersRpcHandlers(this, ActionHistoryClientHandlers)
    org.ttt.autogenesis.kvisionapp.audio.registerAudioClientHandlersRpcHandlers(this, AudioClientHandlers)
    org.ttt.autogenesis.kvisionapp.mapUpload.registerMapUploadErrorClientHandlersRpcHandlers(this, MapUploadErrorClientHandlers)
    org.ttt.autogenesis.kvisionapp.mapUpload.registerMapUploadSuccessClientHandlersRpcHandlers(this, MapUploadSuccessClientHandlers)
}
```

There is **no manual-`register` exception** for the kvisionApp listener block. A hand-rolled `register("client.X", RpcDirection.CLIENT) { _, params -> RpcJson.decodeFromJsonElement(<DtoType>.serializer(), it) ?: ...; <side effect>; null }` call in `Main.kt` bypasses the auto-registration contract that every other client handler uses. The fix is always: (1) create `<Name>ClientHandlers.kt` with a typed `@RpcMethod(name, RpcDirection.CLIENT) suspend fun handle...(_ctx, data)`, (2) let KSP regenerate the binding via `:kvisionApp:compileKotlinJs`, (3) replace the manual call with the auto-generated `register<Name>ClientHandlersRpcHandlers(this, <Name>)`, (4) drop the DTO import in `Main.kt` since `registerTyped` handles the decode.

**Detection heuristic**: any time the agent is about to write a manual `register("client.X" or "ui.X" or "Map.Upload.X", RpcDirection.CLIENT) { _, params -> RpcJson.decodeFromJsonElement(<DtoType>.serializer(), it) ... }` block in `Main.kt`, the correct move is the four-step shape above. The operator's verbatim 2026-08-10 steer when this anti-pattern was reproduced: *"Rpc methods are supposed to auto register and not need those manual registers wtf is going on? What did you do?"* Real failure case: the `Map.Upload.Error` notification was hand-rolled at `Main.kt:597-605` while every other client handler in the same file was using the KSP-generated contract, creating an inconsistency the operator caught on the next turn. Verbatim 2026-08-12 follow-up after the agent reintroduced the same shape via a `ServerExtendBridge.registerHandlers { ... }` block: *"Was the RPC system not designed to handle all annotations being auto registered? I believe that it is and yet you cowboy code and that's very troublesome."* The second incident is the one this skill update patches — it is structurally identical to the first and the skill's prior defense (the heuristic + the 1.11.0 four-step shape) was not load-bearing enough to stop the recurrence. **Mandatory pre-write check** when wiring any client handler: grep `Main.kt` for `registerHandlers` blocks — if the new listener isn't going through a generated `register<Name>ClientHandlersRpcHandlers(...)` call inside an EXISTING `registerHandlers { ... }` block (and the listener isn't a JsonElement-decode-and-route shape that the auto-registration already covers), don't add a second `registerHandlers` block; add a `<Name>ClientHandlers.kt` file and a generated `register<Name>ClientHandlersRpcHandlers(this, <Name>)` call inside the existing block. The block-as-listener-registration-surface is the design; `ServerExtendBridge.registerHandlers { ... }` is not a separate listener bus.

## Code-graph inspection is not runtime verification (the verification-gap pitfall)

This pitfall is the structural cousin of the no-manual-register rule above. The system DOES auto-register — the KSP-generated `_<Name>RpcHandlersProvider` vals self-register into `RpcRegistrationCollector`, and every `RpcRegistry.init` runs `RpcRegistrationCollector.registerAll(this)`. Code-graph inspection proves this. **Code-graph inspection does NOT prove that the registration actually fired against a live bundle in the running JVM/JS runtime.** The two verifications are different:

- **Static** (cheap, fast, lies sometimes): "I traced `GeneratedRpcMasterRegistration.kt`'s `run { ... }` block, I see every provider declared, the master module is reachable via JS `require(MODULE_PATH)`, the `RpcRegistry.init` block calls `registerAll(this)`." → proves the code path exists. Does not prove the path executed.
- **Runtime** (the only thing that matters): drive a live boot, capture console events from the running browser, grep for `RpcRegistrationCollector: Registering provider <X>` and `RpcRegistry initialized with N handlers from M providers`. If `N >= 5` (UiSignal + ActionHistory + Audio + MapUploadSuccess + MapUploadError), the chain fired. If `N = 0`, it didn't, and the add-manual-block instinct is wrong (the real fix is to find WHY the auto path is broken in JS module load, not to bypass it).

Real failure mode (2026-08-12, this session): after reverting the cowboy `ServerExtendBridge.registerHandlers { ... }` block, the agent reported "the auto-registration flow exists; I have not observed it executing on your machine. That's a Class 8 hole." The user immediately responded *"use your local dev skills for autogenisis and build a harness to verify. Run the harness and get the answer to this question."* The Playwright probe that landed (kvisionApp-e2e/probes/rpc-auto-reg.mjs) proved the chain IS firing — `RpcRegistry initialized with 40 handlers from 5 providers` at runtime, with all 5 providers including `MapUploadSuccessClientHandlersRegistrationProvider` and `MapUploadErrorClientHandlersRegistrationProvider` self-registering at the DEBUG level via `console.log`. The 5-source-replay run produced the receipt: yes, the auto-registration works; no, the manual block was never needed; yes, the second operator pushback was correct.

**Recipe for the verification probe** (re-runnable, works against a live stack):

1. Stack must be live — `./debugger/scripts/start_servers.sh` boots server-extend (7070), game server (9080), webpack (8080). Confirmed running via `ss -tlnp | grep -E ':(7070|8080|9080)'` showing Java + webpack pids.
2. Playwright opens `http://localhost:8080/?skipLogin=true` with `waitUntil: 'load'`. Wait 30s for the JS bundle to complete its app boot. (skipLogin avoids the AccelByte OAuth path and goes straight to MainMenu.)
3. **Capture console events, not localStorage** — AGENTS.md's claim about `localStorage['autogenesis_logs']` persistence is stale; `sharedModel/.../LogWriter.js.kt:34-43` says 'localStorage persistence removed for performance.' The JS log writer (DEBUG priority on the JS target) writes to `console.log`/`info`/`warn`/`error`. Playwright's `page.on('console', msg => captured.push(\`[${msg.type()}] ${msg.text()}\`))` is the only sink that captures all entries in this build.
4. **Grep for the chain evidence** — `RpcRegistrationCollector: Registering provider` (one per @RpcMethod-bearing object class, fired when its `_<Name>RpcHandlersProvider` initialises), `RpcRegistrationCollector: Running N providers` (fired when `registerAll` runs from `RpcRegistry.init`), `RpcRegistry initialized with N handlers from M providers` (the summary line). Expected: `M >= 5` (the KSP-generated master initializer has 5 client-listener classes for kvisionApp: UiSignal, ActionHistory, Audio, MapUploadSuccess, MapUploadError). For server-extend module, the count is different — check the master initializer's `run { _serverConnectorRpcHandlersProvider; _extendCommanderRunnerRpcHandlersProvider; _cloudSaveProxyRpcHandlersProvider; ... }` block for the expected count.
5. **Snapshot-format caveat** — the entries are formatted as `"${timestamp} [${priority}] [${category}]: ${message}"` so case-sensitive `[DEBUG]`/`[INFO]`/`[WARN]`/`[ERROR]` brackets are real. Match on `[SYSTEM]` for registration logs and `[NETWORK]` for registry init.

The full probe (with assertions) is at `kvisionApp-e2e/probes/rpc-auto-reg.mjs` + the diagnostic variant at `probes/dump-rpc-logs.mjs`. Both pass against the live bundle as of 2026-08-12.

**Anti-pattern**: shipping a "fix" that is a code-graph justification without runtime evidence. The user's verify-before-deliver norm is documented in INTERPLAY:PLAYGROUND SOUL.md (Class 8) — the operator's machine is the verification, not the call graph. The same norm applies here: any claim that auto-registration "should work" without a Playwright console-capture probe is unverified.

## AGENTS.md staleness note: JS log writer does NOT persist to localStorage

## `internal`-visibility trap on agent factory functions (2026-08-10)

A function whose parameter type is `internal class X` cannot itself be `public fun`. The compiler enforces this strictly:

```
e: server-extend/src/main/kotlin/agent/builders/mapSafetyBuilder.kt:54:5
   'public' function exposes its 'internal' parameter type 'RestPlayerConnectionManager'.
```

**Real case (2026-08-10, server-extend `mapSafetyBuilder.kt`)**: `RestPlayerConnectionManager` (`server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/RestPlayerConnectionManager.kt:164`) is `internal class` — it's not part of server-extend's public API surface. The agent factory was originally `fun buildMapSafetyAgent(playerId: String, connectionManager: RestPlayerConnectionManager)` and the build failed with the message above. The fix is to flip the factory to `internal fun buildMapSafetyAgent(...)` so the visibility aligns with its parameter type. No other change is needed — `internal` functions are still callable from anywhere in the same module, which is what an agent factory always wants.

**When you'll hit this:**
- Agent factories in `server-extend/.../agent/builders/` that take a `RestPlayerConnectionManager` (always `internal`)
- Server-side handlers that take `WorldManager` (also `internal` in some modules) — though `WorldManager` is usually `internal object` so the same trap fires
- Anything returning a `RestPlayerSession` (also `internal`)

**The shape that's always safe:**
- `internal fun buildXxxAgent(...): Pipeline` — fine even when all params are public, since `internal fun` only restricts export-out-of-module
- `public fun buildXxxAgent(...): Pipeline` — fine ONLY when every parameter type is `public`
- The moment you add an `internal`-typed parameter, the function MUST become `internal` — there is no `internal`-exporting-public-function escape hatch

**Anti-pattern**: leaving the function `public` and "working around" the visibility error by changing the parameter type's visibility. The parameter type's visibility is the correct one (it reflects the module's actual public API surface); the factory's visibility should follow.

## Per-session `sendRpcMessage` in a `forEach` needs per-call try/catch (2026-08-10)

`PlayerSession.sendRpcMessage(notification)` is `suspend Unit` over a WebSocket. It can throw if the connection is half-closed, the user's tab suspended the WS, or the peer socket timed out. When that happens inside `sessions.forEach { it.sendRpcMessage(notification) }`, the throw aborts the iteration -- the remaining sessions in the list never see the notification.

**Real case (2026-08-10, `server/src/main/kotlin/org/ttt/autogenesis/server/UiSignalRpcHandlers.kt:313-329`)**: `sendAgentStreamPayload` iterates `connectionManager?.findAllSessions(connectionId) ?: emptyList()` and calls `it.sendRpcMessage(notification)` per session. No try/catch wraps each call. The same shape repeats in `sendCommandClassification` at lines 297-311 of the same file, `broadcastNotification` (line 79), `broadcastLoadMapPack` (line 133), `broadcastWorldUpdate` (line 141), `broadcastTurnComplete` (line 149), and `broadcastAudioSyncState` (line 157). Every one of these will silently drop chunks to any session whose WS is half-closed at the moment the broadcast fires. The user-visible symptom is "the player occasionally misses a UI update after a network blip."

**Fix pattern**: wrap each call. Either per-call try/catch:

```kotlin
sessions.forEach { session ->
    try
    {
        session.sendRpcMessage(notification)
    }
    catch (e: Throwable)
    {
        Logger.warn(LogCategory.NETWORK, "<helper>: dead WS for session ${session.id}: ${e.message}")
    }
}
```

or, if you want to keep the body terse, an `inline fun runCatchingRpc` helper that swallows + logs. The KEY thing is that the per-iteration throw is caught -- one dead session must not abort the broadcast.

**Related smell to watch for**: the `else` branch that fires when `sessions.isEmpty()` because no matching `connectionId` was found. Production code is inconsistent about this -- `broadcastCommandInteractive`/`broadcastWorldUpdate`/`broadcastNotification` take the silent-drop path (just iterate the empty list), while `sendAgentStreamPayload` and `sendCommandClassification` log a WARN at `LogCategory.NETWORK`. The policy isn't documented anywhere. Pick one: either always log (so disconnect-during-stream produces a noisy log you can grep for "no session"), or never log (treat it as expected during the disconnect window). Mixing the two produces inconsistent log volume across helpers that look identical to a reader.

## Reference Files

- `references/kvision-js-launch-pitfall.md` — the Kotlin 2.2 + KVision/JS multi-line `launch` failure mode, with the exact error message and the single-line fix pattern. Load this before writing any Kotlin/JS code in `:kvisionApp` that uses coroutines.
- `references/kvision-js-ui-rpc-wiring.md` — the Kotlin/JS UI-side companion to this umbrella. Covers the 9 compile-time gotchas (typed-invoke returns `RpcMessage.Response` not `<R>`, `MessageBox` constructor positional-vs-named trap, `Uint8Array.asDynamic()[i] as Byte` indexed access, `@JvmStatic` unresolved, `err::class.js.name` over `javaClass.simpleName`, top-level-package paths for `KEnv`/`AccelByteEnv`/`structs.*`, `RpcJson` is a top-level `val`), the companion-object dispatch hook pattern for UI ↔ singleton-client-handler decoupling, and the production webpack bundle symbol probe recipe. Load this before wiring any UI widget to call into a server-extend RPC.
- `references/rpc-auto-registration-verification.md` — the Playwright console-capture probe that proves (or fails to prove) `RpcRegistrationCollector` auto-registered every provider against the live bundle without needing manual `registerHandlers` blocks. The 5-ingredient recipe: live stack up, navigate to `?skipLogin=true`, capture console events (NOT localStorage — that's stale per `LogWriter.js.kt:34-43`), grep for `Registering provider` and `RpcRegistry initialized with N handlers from M providers`, expect `M=5` for kvisionApp. **Mandatory before claiming an RPC registration "fix" is needed** — if the runtime probe shows `M >= 5` you don't need a fix; if it shows `M=0` the problem is the JS module loader, not the registration shape.
- `references/stall-fingerprint-recipe.md` — diagnostic recipe for "user reports the page froze for N seconds/minutes" reports. Maps the `RestPlayerConnectionManager reconnecting playerId=...` log fingerprint to the client-side `connectToGameServer` WS tear-down + `ResumeAvailabilityPushService` snapshot-poll cycle. Read-only grep commands + file:line evidence for the server (`RestPlayerConnectionManager.kt:246-256`) and client (`MatchmakingClient.kt:380-420`, `MainMenu.kt:466`, `MainMenu.kt:601`) code paths. Use before assuming a server-side stall or GC pause.
- `references/tpipe-bedrock-pipe-setup.md` — the four TPipe pipe-setup footguns that surface in Bedrock multimodal safety agents: (1) `setJsonOutput(::Foo)` is the WRONG call shape — the right shape is `setJsonOutput(Foo::class)` because the parameter is `KClass<*>`, not a function reference; the wrong shape compiles but crashes at runtime with `Serializer for class 'KFunction' is not found`. (2) `Pipeline.execute(...)` returns `MultimodalContent`; the pass/fail signal is `result.shouldTerminate()` (which is true when `setOnFailure` flipped the `processed.terminatePipeline = true` flag). (3) The trace event field is `pipeName` (`TPipe/src/main/kotlin/Debug/TraceEvent.kt:21`), NOT `name` — regex-based trace inspectors will miss every event if they target the wrong field. (4) The map pack format is a zip with two entries — `map.json` (MapPackData) plus the image entry referenced by `MapPackData.imageName` — not a binary blob. Load before wiring any new Bedrock multimodal pipe, before extracting pipe names from a TPipe trace, or before constructing `MapData` for a unit test (the `pins` and `connections` fields have no default).

## Quick checklist for adding a new RPC method

1. Decide direction: who receives it? → `RpcDirection.SERVER` for main server, `.CLIENT` for browser.
2. Pick the method name: prefix with the receiver's namespace (`server.X` for main-server handlers, `client.X` for browser handlers, `server.extend.X` for server-extend handlers). Avoid mixing namespaces — it's a soft convention but reading mixed prefixes is confusing.
3. Define the payload struct in `sharedModel/src/commonMain/kotlin/structs/<area>/` if it's new. `@Serializable` required.
4. Write the handler with `(ctx: RpcCallContext, payload: Foo)` signature — exactly one payload param beyond `ctx`.
5. Run `./gradlew :<module>:compileKotlin` — if KSP rejects, the error will point at the line of the `@RpcMethod` annotation.
6. Verify the handler appears in `server/build/generated/ksp/main/kotlin/org/ttt/autogenesis/network/generated/GeneratedRpcMasterRegistration.kt` after build.

## Replacing the matchmaker's vendored proto with the upstream matchFunction.proto (2026-07-01)

The Autogenesis `matchmaker/` module originally shipped with a vendored sketch of the match2 contract: a 2-RPC `Service { Validate, MakeMatches }` in package `accelbyte.matchmaker` (java_package `net.accelbyte.matchmaker.proto`). The real upstream contract is a 5-RPC `MatchFunction { GetStatCodes, ValidateTicket, EnrichTicket, MakeMatches, BackfillMatches }` in package `accelbyte.matchmaking.matchfunction` (java_package `net.accelbyte.matchmakingv2.matchfunction`). The vendored sketch would have been wire-incompatible with match2 — the deployed matchmaker would never have been invoked.

**The fix (commit history; full TDD discipline in the `tdd-protoc-grpc-mcp` skill):**

1. Replaced `matchmaker/src/main/proto/accelbyte_matchmaker.proto` with the upstream copy from `AccelByte/matchmaking-function-grpc-plugin-server-java:main/src/main/proto/matchFunction.proto` (185 lines, v1.1.0).
2. Old impl `MatchmakerGrpcService.kt` extended `ServiceGrpcKt.ServiceCoroutineImplBase` (old package) — replaced with `MatchFunctionGrpcKt.MatchFunctionCoroutineImplBase` (upstream package) and implemented all 5 RPCs.
3. Old test `MatchmakerServiceGrpcImplTest.kt` asserted on removed internal types (`ApiMatchTicket`, `AttributeValue.stringValue`) — **deleted**. Pin-the-implementation tests have no value when the implementation shape changes.
4. New test `MatchmakerUpstreamContractTest.kt` (10 tests) drives the production code through the upstream gRPC stub layer via `InProcessServerBuilder`. The package assertion `assertEquals("net.accelbyte.matchmakingv2.matchfunction", MatchFunctionGrpcKt.MatchFunctionCoroutineStub::class.java.package.name)` is a compile-time guard that catches any future reversion to the legacy package.
5. **Algorithm contract change**: `MatchmakingAlgorithm.propose()` used `require(tickets.size >= targetPlayers)` which threw `IllegalArgumentException`. Throw surfaces as gRPC `UNKNOWN` status which match2 treats as fatal. Changed to `if (tickets.size < targetPlayers) return emptyList()` (empty list = "no proposal this tick" signal on the match2 stream). Updated the corresponding test assertion.
6. **Proto oneof trap**: upstream `MakeMatchesRequest` has `oneof request_type { MakeMatchesParameters parameters = 1; Ticket ticket = 2; }`. Each ticket must be its own frame on the bidi stream — `flowOf(paramsFrame, ticket1, ticket2, ticket3, ticket4)`, NOT `flowOf(paramsFrame, builderWithFourSetTicketCalls)`. The naive impl sends 4 setTicket calls on one builder, but the oneof keeps only the last — silent ticket loss.

**The lesson for any future proto swap:** the RED signal for a `.proto` swap is compile errors, not test failures. The TDD discipline still applies (write failing test → watch it fail → implement → watch it pass) but the failure shape is "this test class doesn't even load" rather than "this test fails its assertion." For the full 6-step discipline including `uint64` → `Long` trap, see the `tdd-protoc-grpc-mcp` skill.

**The pre-existing flaky test caveat:** when the matchmaker tests went GREEN but `agent.builders.writingAgent.SelectRulesFromCategoriesTest.zeroPercentCategoryNeverFires` failed with `expected: <empty> but was: <Should never appear>`, the clean-HEAD verification (git stash → run on HEAD → git stash pop) showed it fails on HEAD too. Pre-existing flake in a module my changes don't touch. Document it, don't fix it.