# Kotlin/JS UI-side RPC wiring — compile-time gotchas + dispatch patterns

Captured 2026-08-12 from the `MapUploadModal` + `CollectionOverlay` + `MapDetailWindow` wiring session (six files modified, 9 of 10 wire symbols verified in the production webpack bundle).

This file is the Kotlin/JS-specific companion to the umbrella's `Calling an RPC (the call-site side)` section. The umbrella covers the API surface; this file covers the compile-time + type-system traps that fire when you actually wire a UI widget to call into a server-extend RPC.

## The "9 things the compiler complains about" cheat sheet

Every one of these fires at compile time when you write the obvious-shaped Kotlin/JS code. None of them are in the umbrella today — this list IS the gotcha surface for the JS target.

### 1. `RpcInvoker.invoke()` is NOT generic over the response type

The umbrella documents the typed overload `invoke<P>(method, params, serializer)` and the reified inline version. **Both return `RpcMessage.Response`, NOT the typed payload.** The DTO does NOT come back through type parameters. You must manually decode:

```kotlin
val response = invoker.invoke(
    "server.extend.uploadMapGate",
    MapUploadRequest(mapPackBytes = bytes, mapName = mapName),
    MapUploadRequest.serializer()
)
// response: RpcMessage.Response — NOT MapUploadGateResponse

if (response.error != null) {
    val errMsg = response.error?.message ?: response.error?.code?.toString() ?: "Unknown"
    throw RuntimeException("uploadMapGate RPC error: $errMsg")
}

val payload = response.result
    ?: throw RuntimeException("uploadMapGate returned null result")

val typed = RpcJson.decodeFromJsonElement(MapUploadGateResponse.serializer(), payload)
```

**The naive shape `invoker.invoke<UploadGateResponse>(...)` (as I wrote in the plan) does not exist.** Real call sites in the codebase confirm this pattern:
- `kvisionApp/src/jsMain/kotlin/ui/CommanderDataSync.kt:167-180` — `response.result?.let { RpcJson.decodeFromJsonElement(serializer<String>(), it) }`
- `server-extend/src/test/kotlin/proxy/MapStorageProxyLiveTest.kt` and similar

If a plan or session asserts "use the typed `invoke<R>(...)`" without acknowledging the manual decode, the plan is wrong.

### 2. `MessageBox` constructor is positional + legacy-named, NOT KVision-default

The canonical `MessageBox` in `kvisionApp/src/jsMain/kotlin/ui/MessageBox.kt:34-43` takes:

```kotlin
class MessageBox(
    var boxTitle: String = "",
    var message: String = "",        // NOT `boxMessage`
    var showThrobber: Boolean = false, // NOT `throbber`
    var showOk: Boolean = false,
    var showCancel: Boolean = false,
    var boxSize: ModalSize = ModalSize.LARGE,
    var onConfirm: (() -> Unit)? = null,
    var onCancel: (() -> Unit)? = null
)
```

The KVision-default `boxTitle = "..."` named-parameter shape from modern docs DOES compile against this signature, but the second positional parameter is named `message`, not `boxMessage`. Writing `MessageBox(boxTitle = "...", boxMessage = "...", throbber = true)` compiles only because Kotlin accepts the named parameters, but `boxMessage` and `throbber` are NOT properties on the class — they're just unused-then-discarded positional arg labels in the call. Use:

```kotlin
val msg = MessageBox(
    boxTitle = "Uploading map…",
    message = "Validating and saving. This may take up to 30 seconds.",
    showThrobber = true
)
KEnv.mainRoot?.add(msg)
```

Real call site: `kvisionApp/src/jsMain/kotlin/ui/LoginWidgets.kt:641-647`.

### 3. `Uint8Array` indexed access needs `asDynamic()[i] as Byte`

`ByteArray(u8.length) { i -> u8[i] }` does NOT compile in Kotlin/JS — the compiler complains `'operator' modifier is required on 'fun <T : Any> Any.get(): T'`. `Uint8Array.get(Int): Byte` doesn't exist as a Kotlin operator on the JS typed-array.

The fix (from `kvisionApp/src/jsMain/kotlin/ui/MapViewer.kt:900-906`):

```kotlin
val u8 = Uint8Array(arrayBuffer)
val bytes = ByteArray(u8.length)
for (i in bytes.indices) bytes[i] = u8.asDynamic()[i] as Byte
```

`u8.asDynamic()[i]` is the typed-array escape hatch that compiles and gives you a `Byte` per index.

### 4. `@JvmStatic` does not exist in Kotlin/JS

Trying to use `@JvmStatic` on companion-object members fails with `Unresolved reference 'JvmStatic'`. Drop the annotation; companion-object members on Kotlin/JS are accessible without it.

```kotlin
// WRONG (Kotlin/JS):
companion object {
    @JvmStatic
    var successCallback: ((String) -> Unit)? = null
    @JvmStatic
    fun handleUploadSuccessNotification(mapName: String) { ... }
}

// RIGHT (Kotlin/JS):
companion object {
    var successCallback: ((String) -> Unit)? = null
    fun handleUploadSuccessNotification(mapName: String) { ... }
}
```

### 5. `err.javaClass.simpleName` → `err::class.js.name`

`javaClass` is unresolved in Kotlin/JS. The substitute is `::class.js.name` (returns the JS class name, e.g. `"TypeError"`, `"Error"`). For chained null-safe error reporting:

```kotlin
"${err.message ?: err::class.js.name}"
```

### 6. `KEnv.mainRoot?.add(MessageBox(...))` is the modal mount pattern

`KEnv` is the top-level global singleton holding the KVision root. The mount pattern is identical to how `LoginWidgets.kt` mounts login flow modals:

```kotlin
KEnv.mainRoot?.add(msg)
```

If you import `ui.KEnv`, the path doesn't resolve — `KEnv` lives at `globals.KEnv` (top-level package, not under `ui`). This is the same kind of top-level-package trap as `structs.accelbyte.cloudsave` and `structs.rpcRequests` (NOT under `org.ttt.autogenesis.*`).

### 7. Top-level packages that aren't nested under `org.ttt.autogenesis.*`

The sharedModel DTOs live in top-level packages, NOT nested:

| Symbol | Full path | NOT |
|---|---|---|
| `MapUploadRequest` | `org.ttt.autogenesis.network.MapUploadRequest` | `org.ttt.autogenesis.network.structs.rpcRequests.*` |
| `MapUploadGateResponse` | `org.ttt.autogenesis.network.MapUploadGateResponse` | (under UploadGateDtos.kt, `org.ttt.autogenesis.network.*`) |
| `CloudPlayerMaps` / `CloudPlayerMapEntry` | `structs.accelbyte.cloudsave.*` | `org.ttt.autogenesis.*` |
| `ListPlayerMapsRequest` / `GetPlayerMapRequest` / `GetPlayerMapResponse` | `structs.rpcRequests.*` | `org.ttt.autogenesis.*` |
| `KEnv` / `AccelByteEnv` | `globals.*` | `org.ttt.autogenesis.kvisionapp.*` |

Real failure case: `import org.ttt.autogenesis.network.structs.rpcRequests.ListPlayerMapsRequest` returns `Unresolved reference 'structs'` — the path doesn't nest. Use `import structs.rpcRequests.ListPlayerMapsRequest`.

### 8. `RpcJson` is a top-level `val` (Json instance), not an object/companion

From `sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network/RpcModels.kt:8`:

```kotlin
val RpcJson = Json { ignoreUnknownKeys = true; ... }
```

So the call shape is `RpcJson.decodeFromJsonElement(serializer, payload)` — `RpcJson` is the instance directly. There is no `RpcJson.Json` or `RpcJson.Companion`.

### 9. `globals.AccelByteEnv.userId` is the userId singleton

The authenticated player's AccelByte user ID lives at `globals.AccelByteEnv.userId` (top-level package, again NOT under `ui.*` or `org.ttt.autogenesis.*`). Use `AccelByteEnv.userId` as the `userId` parameter for server-extend RPCs that need to scope to the current player (`listPlayerMaps`, `getPlayerMap`, etc.).

## The companion-object dispatch hook pattern (Kotlin/JS-friendly decoupling)

When a singleton `object` (e.g. `MapUploadSuccessClientHandlers`) needs to dispatch to a UI widget that lives in a separate file with no compile-time visibility into the singleton, the canonical patterns are:

### Pattern A — Static callback fields on a companion object

Use when the singleton receives notifications from the wire and needs to hand control to the UI without a constructor dependency.

```kotlin
// In the widget (kvisionApp-side):
class MapUploadModal : SimplePanel(...) {
    companion object {
        // Nullable static hooks — null when no overlay is mounted
        var successCallback: ((mapName: String) -> Unit)? = null
        var errorCallback: ((reason: String) -> Unit)? = null

        // Dispatchers called by the singleton handlers
        fun handleUploadSuccessNotification(mapName: String) {
            successCallback?.invoke(mapName)
        }
        fun handleUploadErrorNotification(reason: String) {
            errorCallback?.invoke(reason)
        }
    }
    // ...widget body
}

// In the singleton (server-side handler):
object MapUploadSuccessClientHandlers {
    @RpcMethod(name = "Map.Upload.Success", direction = RpcDirection.CLIENT)
    suspend fun handleMapUploadSuccess(_ctx: RpcCallContext, data: MapUploadSuccessData) {
        Logger.info(LogCategory.NETWORK, "Map.Upload.Success received: mapName='${data.mapName}'")
        ui.MapUploadModal.handleUploadSuccessNotification(data.mapName)
    }
}

// In the overlay that owns the modal (one-time wiring):
private val mapUploadModal = MapUploadModal().also {
    MapUploadModal.successCallback = { mapName ->
        it.dismiss()
        val msg = MessageBox(boxTitle = "Map uploaded", message = "Map '$mapName' uploaded")
        KEnv.mainRoot?.add(msg)
        MainScope().launch {
            kotlinx.coroutines.delay(3500)
            msg.hide()
        }
        refreshMapCatalogue()
    }
    MapUploadModal.errorCallback = { reason ->
        it.dismiss()
        val msg = MessageBox(boxTitle = "Upload failed", message = "Upload failed: $reason")
        KEnv.mainRoot?.add(msg)
    }
}
```

This is what shipped in the `MapUploadModal` wiring session and proved clean at runtime (success MessageBox surfaces + catalogue re-fetch fires; error MessageBox surfaces; modal dismisses).

**Why not `MapUploadModal.successCallback = { mapName -> this.showUploadSuccess(mapName) }`?** That would create a `this` reference inside the `.also { ... }` lambda body that conflicts with `MapUploadModal.successCallback`'s static-field write. The `it.dismiss()` form keeps the widget instance explicit.

### Pattern B — Global Kotlin `object` singleton with method dispatch

Use when the dispatch can be a method call on the singleton rather than a closure invocation. Doesn't work well for UI because UI widgets are stateful instances, not singletons.

**Skip Pattern B for UI**. UI widgets need instance-level state (the `currentState` enum, the `selectedFile` field, etc.) so a static-hook pattern is correct.

### Pattern C — `RpcRegistry.register` callback registration

The umbrella already documents that `RpcRegistry` accepts manual `register("method", RpcDirection.CLIENT) { ctx, params -> ... }` blocks for non-KSP-shaped handlers. **This is the wrong pattern for UI listeners** — the umbrella's anti-pattern entry says exactly this: kvisionApp client listeners MUST go through the KSP-generated `register<Name>ClientHandlersRpcHandlers(this, <Name>)` contract, never a hand-rolled `register(...)` block.

### Pattern D — Broadcast event bus

A separate `MapUploadEvents` singleton with `Flow<MapUploadSuccessData>` is overkill for two notification channels. The companion-object dispatch hook is the right shape for low-channel-count cases; an event bus pays off when 5+ UI widgets react to the same notification.

## Verifying the wire format ships to the bundle (HermesDesktop pitfall pattern)

`autogenesis-rpc-patterns` references `references/desktop-e2e-verification-without-gui.md` for the HermesDesktop case. The same discipline applies here: **verify the new symbols are actually in the production webpack bundle**, not just that the source compiles. The verification recipe:

```bash
./gradlew :kvisionApp:assemble --no-daemon
# Wait ~1m for the webpack build

# Probe the production bundle for the new symbols
bundle=/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp/build/dist/js/productionExecutable/kvisionApp.js
for sym in uploadMapGate listPlayerMaps getPlayerMap refreshMapCatalogue \
          handleUploadSuccessNotification handleUploadErrorNotification \
          MapUploadSuccess MapUploadError; do
    printf "  %s %s\n" \
        $([[ "$bundle" == *"$sym"* ]] && echo "✓" || echo "✗") \
        "$sym"
done
```

Expected: all `✓`. Companion-object fields like `successCallback` / `errorCallback` may not appear (Kotlin compiler inlines single-use lambdas), but the **dispatch methods** (`handleUploadSuccessNotification`, `handleUploadErrorNotification`) MUST be present.

## Real call-site references in this codebase

When you wire a new UI widget to call into a server-extend RPC, **grep for an existing pattern first**. The load-bearing precedents:

| What you're doing | Real call site to copy from |
|---|---|
| Calling `RpcInvoker.invoke(method, params, serializer)` and decoding the response | `kvisionApp/src/jsMain/kotlin/ui/CommanderDataSync.kt:167-180` |
| Reading `File` → `ByteArray` via `FileReader` + `Uint8Array` | `kvisionApp/src/jsMain/kotlin/ui/MapViewer.kt:900-911` (`loadMapPackFile`) |
| Mounting a `MessageBox` with throbber | `kvisionApp/src/jsMain/kotlin/ui/LoginWidgets.kt:641-647` |
| Reading per-user data from server-extend (`AccelByteEnv.userId` is the key) | `server-extend/src/test/kotlin/proxy/MapStorageProxyLiveTest.kt:134-135` (`val userId = System.getenv("AB_LIVE_TEST_USER") ?: "25a70be88881466286bc03154f5d7492"`) |
| `ServerExtendBridge.rpcInvoker` reads | `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/ServerExtendBridge.kt:26-31` |
| Registering a server-extend client listener on `ServerExtendBridge` (in addition to `WebSocketRpcBridge`) | `kvisionApp/src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/Main.kt:608-622` (the `MapUpload*ClientHandlers` block added in the wiring session) |

Use these as the template; do not invent call shapes from the API surface.