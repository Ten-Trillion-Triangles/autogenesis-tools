# ArkVcs RPC Fix: Closure Serialization → Name-Registry Dispatch

**Session:** 2026-07-11, ArkVcs project (`/home/cage/Desktop/Workspaces/ArkVcs`)

**Problem:** ArkVcs tried to send Kotlin function references over the network by embedding them in a `Request` data class:

```kotlin
// ArkVcs/src/main/kotlin/Structs/Api/Request.kt:13
data class Request(var cinit: Boolean = false) {
    var function: (suspend (json: String, user: UserSettings) -> String)? = null
    var json: String = ""
}
```

`kotlinx.serialization` cannot serialize function references. They contain JVM classloader pointers, bound receivers, and internal state with no portable binary representation. The serialization fails at runtime, blocking all RPC calls.

**Same flaw appears in:** `VoidResponse` and `VoidParamResponse` (Response.kt:14, 24) — both carry `() -> Unit` / `(String) -> Unit` function fields that are equally unserializable.

## PCP's Solution: Name-Based Registry Dispatch

PCP never transmits function references. Instead:

1. Server registers functions in a `FunctionRegistry` at startup with a string name
2. Client sends a **name + args** (both as plain strings) — serializable, crosses any transport
3. Server receives the name, looks up the actual function in `FunctionRegistry`, invokes it

```
Client                                  Server
  |                                        |
  |  { "functionName": "runFileTransfer",  |
  |    "args": "{\"action\":\"upload\",..."}"|  
  |  ─────────────────────────────────────>|
  |                                        | FunctionInvoker.invoke()
  |                                        |   → FunctionRegistry.get("runFileTransfer")
  |                                        |   → TypeConverter converts String→Native
  |                                        |   → KotlinFunction.invoke(params)
  |                                        |
  |  { "success": true, "result": "..." } |
  |<───────────────────────────────────────|
```

**The serialized payload is pure data — no closures, no JVM references.**

## ArkVcs Fix: Apply PCP's Pattern

### 1. Replace `Request` with a name-based request

```kotlin
// New: ArkRpcRequest.kt — serializable, no function field
@kotlinx.serialization.Serializable
data class ArkRpcRequest(
    val functionName: String,
    val args: String  // serialized JSON args
)
```

### 2. Create a function registry

```kotlin
// ArkFunctionRegistry.kt
object ArkFunctionRegistry {
    private val functions = ConcurrentHashMap<String, ArkRpcFunction>()
    
    fun register(name: String, fn: ArkRpcFunction) {
        functions[name] = ArkRpcFunction(name, fn)
    }
    
    fun get(name: String): ArkRpcFunction? = functions[name]
    fun getNames(): Set<String> = functions.keys.toSet()
}

typealias ArkRpcFunction = suspend (json: String, user: UserSettings) -> String

data class ArkRpcFunction(
    val name: String,
    val function: ArkRpcFunction_
)

data class ArkRpcFunction_(
    val name: String,
    val function: ArkRpcFunction
)
```

*(Note: the data class naming above is illustrative — the actual implementation should use a concrete `FunctionSignature` pattern like PCP's `FunctionSignature` in `FunctionRegistry.kt`.)*

### 3. Register existing runners at startup

```kotlin
// At application boot
ArkFunctionRegistry.register("runPortableKeyTask",    ::runPortableKeyTask)
ArkFunctionRegistry.register("runLockedKeyTask",      ::runLockedKeyTask)
ArkFunctionRegistry.register("runFileTransferTask",   ::runFileTransferTask)
```

### 4. Change dispatch in ApiRoutes.kt

```kotlin
// Before (line 91):
val apiResult = requestAsObject.function!!(requestAsObject.json, arkUser)

// After:
val sig = ArkFunctionRegistry.get(requestAsObject.functionName)
    ?: throw IllegalArgumentException("Unknown function: ${requestAsObject.functionName}")
val apiResult = sig.function(requestAsObject.args, arkUser)
```

### 5. Client-side changes

```kotlin
// Before: Request with captured closure (BROKEN)
fun createUploadRequest(...): Request {
    val request = Request()
    request.function = ::handleFileTransferRequest  // closure — not serializable
    return request
}

// After: ArkRpcRequest with name (WORKS)
fun createUploadRequest(...): ArkRpcRequest {
    val fileRequest = FileTransferRequest(action = "upload", ...)
    return ArkRpcRequest(
        functionName = "runFileTransferTask",
        args = serialize(fileRequest)
    )
}
```

## Key Lesson

| | Broken (closure) | Fixed (registry) |
|---|---|---|
| Transmitted | `(suspend (String, UserSettings) → String)?` closure | `String` function name + `String` args |
| Serialization | **FAILS** — closures aren't serializable | **WORKS** — just text |
| Dispatch | Direct closure invocation | Registry lookup by name |
| Server binding | Implicit (closure captured at call site) | Explicit (`registerFunction(name, fn)`) |
| Both sides need | Same JVM reference | Agree on string name only |

**The rule:** If you want to invoke a function across a serialization boundary (network, persistence, IPC), the function must be identified by name, not by reference. The name crosses the boundary. The function lives server-side in a registry and is looked up by that name.

## PCP Files to Reference

| File | What it demonstrates |
|---|---|
| `TPipe/src/main/kotlin/PipeContextProtocol/FunctionRegistry.kt` | ConcurrentHashMap registry, `registerFunction`, `getFunction` |
| `TPipe/src/main/kotlin/PipeContextProtocol/FunctionInvoker.kt` | Lookup + TypeConverter + invoke pattern |
| `TPipe/src/main/kotlin/PipeContextProtocol/FunctionSignature.kt` | Serializable function metadata (name, params, return type) |
| `TPipe/src/main/kotlin/PipeContextProtocol/FunctionWrapper.kt` | `NativeFunction` abstract base, `KotlinFunction` / `LambdaFunction` concrete implementations |

## Related Pitfalls

- **ArkVcs `VoidResponse` / `VoidParamResponse`** — same closure-in-data-class flaw. Apply identical fix: replace function field with `functionName: String`, register handlers in `ArkFunctionRegistry`, dispatch by name.
- **Don't try to serialize the closure** — no amount of `encodeDefaults` or custom serializer on the function field will help. The fundamental problem is that JVM function objects carry non-serializable internal state. The only fix is name-based dispatch.
