# PCP Data Class Deep Dive

Source: `src/main/kotlin/PipeContextProtocol/` — all files read 2026-05-21.

## Core Schema Layer

### `FunctionSignature`
```kotlin
data class FunctionSignature(
    val name: String,
    val parameters: List<ParameterInfo>,
    val returnType: ReturnTypeInfo,
    val description: String = ""
)
```
Complete metadata for a callable function. Registered in `FunctionRegistry`. Drives the LLM's ability to understand what to call and how. Passed into prompt context so the model knows parameter names, types, optionality, enum constraints, and descriptions.

### `ParameterInfo`
```kotlin
data class ParameterInfo(
    val name: String,
    val type: ParamType,           // PCP type enum (String, Int, Bool, Float, Enum, List, Map, Object, Any)
    val kotlinType: String,        // Actual JVM type string ("kotlin.String", "kotlin.Int", etc.)
    val isOptional: Boolean = false,
    val defaultValue: String? = null,
    val enumValues: List<String> = emptyList(),  // Only populated for ParamType.Enum
    val description: String = ""
)
```
Full metadata for a single parameter. `type` is LLM-facing. `kotlinType` is for reflection-based invocation. `enumValues` is the key — for enum parameters, this lists every valid value so the LLM can only emit valid inputs.

### `ReturnTypeInfo`
```kotlin
data class ReturnTypeInfo(
    val type: ParamType,
    val kotlinType: String,
    val isNullable: Boolean = false,
    val description: String = ""
)
```
Same pattern as `ParameterInfo` but for return values. Used by `FunctionInvoker.convertReturnValue()` to select the right `TypeConverter` and serialize the native return value back to a string.

### `ParamType`
```kotlin
enum class ParamType { String, Int, Bool, Float, Enum, List, Map, Object, Any }
```
The LLM-facing type system for PCP. Not JVM types — simplified, normalized types designed for reliable LLM parameter filling. `FunctionRegistry.mapKotlinTypeToParamType()` bridges JVM types to these at registration time.

---

## The Execution Layer

### `NativeFunction` (abstract base)
```kotlin
abstract class NativeFunction {
    abstract val signature: FunctionSignature
    abstract suspend fun invoke(parameters: Map<String, Any?>): Any?
    abstract fun validate(): Boolean
}
```
Abstract base for all function wrappers. Two concrete implementations:

**`KotlinFunction`** — wraps `KFunction<*>` via reflection. Calls `callBy()` for regular functions, `callSuspendBy()` for suspend functions. Rejects unbound member references and extension functions at invoke time.

**`LambdaFunction`** — wraps lambda/function objects. Uses reflection to find the `invoke()` method and calls it with ordered parameters extracted from the signature.

### `FunctionInvoker`
```kotlin
class FunctionInvoker {
    suspend fun invoke(functionName: String, parameters: Map<String, String>): InvocationResult
    fun validateParameters(signature: FunctionSignature, parameters: Map<String, String>): ValidationResult
}
```
The execution engine. Flow:
1. Lookup in `FunctionRegistry`
2. Validate parameters against signature (required presence, type convertibility)
3. Convert strings → native types via `TypeConverter` chain
4. Call `nativeFunction.invoke(convertedParams)`
5. Convert return value back to string via `TypeConverter`
6. Wrap in `InvocationResult`

### `InvocationResult`
```kotlin
data class InvocationResult(
    val success: Boolean,
    val returnValue: Any? = null,
    val returnValueAsString: String,
    val executionTimeMs: Long,
    val error: String? = null
)
```
Result of function invocation. Returned from `FunctionInvoker.invoke()`. `PcpFunctionResponse` wraps this with a `returnValueKey` for storage retrieval.

### `ValidationResult`
```kotlin
data class ValidationResult(
    val isValid: Boolean,
    val errors: List<String>
)
```
Parameter pre-flight check. If validation fails, `invoke()` returns immediately with `success=false` — no conversion attempt, no invocation.

---

## Type Conversion Layer

### `TypeConverter` (interface)
```kotlin
interface TypeConverter {
    fun canConvert(from: ParamType, to: String): Boolean
    fun convert(value: Any?, targetType: String): Any?
    fun convertBack(value: Any?, sourceType: ParamType): String
}
```
Pluggable type conversion. Converter chain in order:

**`PrimitiveConverter`** — String, Int, Boolean, Float, Double, Enum. Uses `toInt()`, `toBoolean()`, etc. `Enum.valueOf()` with multi-classloader enum resolution.

**`CollectionConverter`** — List, Map, Array, Set. Uses `kotlinx.serialization.json.Json` to decode JSON strings to collection types.

**`ObjectConverter`** — fallback for `ParamType.Object` and `ParamType.Any`. Decodes JSON to `Map<String, Any>`. Falls back to `toString()` if parsing fails.

---

## Context and Request Layer

### `PcpContext`
```kotlin
data class PcpContext(
    var transport: Transport = Transport.Auto,
    var stdioOptions: MutableList<StdioContextOptions> = mutableListOf(),
    var tpipeOptions: MutableList<TPipeContextOptions> = mutableListOf(),  // Registered native functions
    var httpOptions: MutableList<HttpContextOptions> = mutableListOf(),
    var pythonOptions: PythonContext = PythonContext(),
    var kotlinOptions: KotlinContext = KotlinContext(),
    var javascriptOptions: JavaScriptContext = JavaScriptContext(),
    var allowedDirectoryPaths: MutableList<String> = mutableListOf(),
    var forbiddenDirectoryPaths: MutableList<String> = mutableListOf(),
    var allowedFiles: MutableList<String> = mutableListOf(),
    var forbiddenFiles: MutableList<String> = mutableListOf(),
    var enableSessionAccessControl: Boolean = false,
    var enableBufferAccessControl: Boolean = false,
    var currentUserId: String = System.getProperty("user.name")
)
```
Security and capability boundary for a PCP execution session. `transport = Auto` is open; specific transport restricts to that mode only. `tpipeOptions` is the whitelist of allowed native functions.

### `TPipeContextOptions`
```kotlin
data class TPipeContextOptions(
    var functionName: String = "",
    var description: String = "",
    var params: MutableMap<String, ContextOptionParameter> = mutableMapOf()
)
```
LLM-facing function description for native function calls. `functionName` is the lookup key in `FunctionRegistry`. `params` maps parameter names to their metadata. `PcpFunctionHandler` validates that `functionName` is in `context.tpipeOptions` whitelist.

### `ContextOptionParameter`
```kotlin
data class ContextOptionParameter(
    val type: ParamType,
    val description: String,
    val enumValues: List<String> = emptyList(),
    val isRequired: Boolean = false
)
```
LLM-facing parameter descriptor. The LLM sees this in its prompt when deciding what to emit for a function call.

### `PcPRequest`
```kotlin
data class PcPRequest(
    var stdioContextOptions: StdioContextOptions = StdioContextOptions(),
    var tPipeContextOptions: TPipeContextOptions = TPipeContextOptions(),
    var httpContextOptions: HttpContextOptions = HttpContextOptions(),
    var argumentsOrFunctionParams: List<String> = emptyList(),  // Positional arguments
    var callParams: Map<String, String> = emptyMap()           // Named parameters
)
```
The LLM's output format when calling a PCP function. `argumentsOrFunctionParams` is positional (legacy). `callParams` is named parameters — the current pattern.

### `PcpFunctionResponse`
```kotlin
data class PcpFunctionResponse(
    val success: Boolean,
    val result: String,
    val returnValueKey: String = "",
    val executionTimeMs: Long = 0,
    val error: String? = null
)
```
Result returned from `PcpFunctionHandler.handleFunctionRequest()`. `returnValueKey` allows the LLM to retrieve large/complex return values from `ReturnValueHandler` by key later.

---

## Storage Layer

### `ReturnValueHandler`
```kotlin
class ReturnValueHandler {
    fun storeReturnValue(key: String = "", value: Any?): String
    fun getReturnValue(key: String): Any?
    fun toContextEntry(key: String, value: Any?): Pair<String, String>
    fun getAllAsContextEntries(): Map<String, String>
    fun clearReturnValue(key: String): Boolean
    fun clearAll()
    fun hasReturnValue(key: String): Boolean
    fun getStoredKeys(): Set<String>
}
```
In-memory return value storage with optional key generation. Stores native return values (not serialized strings). `getAllAsContextEntries()` generates a map suitable for `ContextWindow` injection.

---

## Dispatch Layer

### `PcpExecutionDispatcher`
```kotlin
class PcpExecutionDispatcher {
    private val functionHandler = PcpFunctionHandler()
    private val stdioExecutor = StdioExecutor()
    private val httpExecutor = HttpExecutor()
    private val pythonExecutor = PythonExecutor()
    private val kotlinExecutor = KotlinExecutor()
    private val javaScriptExecutor = JavaScriptExecutor()
    private val responseParser = PcpResponseParser()

    suspend fun executeRequest(request: PcPRequest, context: PcpContext): PcpRequestResult
    suspend fun executeRequests(requests: List<PcPRequest>, context: PcpContext): PcpExecutionResult
}
```
Central routing engine. Determines transport type via `PcpResponseParser.determineTransport()`, validates against context, routes to appropriate executor. For batch, runs requests in parallel via `async`.

### `PcpRequestResult` / `PcpExecutionResult`
```kotlin
data class PcpRequestResult(
    val success: Boolean, val output: String, val executionTimeMs: Long,
    val transport: Transport, val error: String? = null
)
data class PcpExecutionResult(
    val success: Boolean, val results: List<PcpRequestResult>,
    val executionTimeMs: Long, val errors: List<String>
)
```
Final output envelope. `PcpRequestResult` is single request. `PcpExecutionResult` aggregates multiple with overall success flag.

---

## Registry Layer

### `FunctionRegistry`
```kotlin
object FunctionRegistry {
    private val functions = ConcurrentHashMap<String, NativeFunction>()
    private val typeConverters = mutableListOf<TypeConverter>()

    fun registerFunction(name: String, function: KFunction<*>): FunctionSignature
    fun <T> registerLambda(name: String, lambda: T, signature: FunctionSignature): FunctionSignature
    fun getFunction(name: String): NativeFunction?
    fun getSignature(name: String): FunctionSignature?
    fun getFunctionNames(): Set<String>
    fun validateAll(): List<String>
    fun getTypeConverters(): List<TypeConverter>
    fun listFunctions(): List<FunctionDescriptor>
    fun clear()
}
```
Thread-safe singleton registry for native functions. At init registers three type converters: `PrimitiveConverter`, `CollectionConverter`, `ObjectConverter`. MCP server's tools/list endpoint calls `listFunctions()` to enumerate all available tools.

---

## Execution Flow

```
LLM Output (PcPRequest)
    │
    ▼
PcpExecutionDispatcher.executeRequest()
    │ determines transport via PcpResponseParser
    │ validates transport against PcpContext
    ▼
PcpFunctionHandler.execute()   [for Transport.Tpipe]
    │ validates functionName is in context.tpipeOptions whitelist
    ▼
PcpFunctionHandler.handleFunctionRequest()
    │ converts arguments to parameter map
    │ validates parameters against FunctionSignature
    ▼
FunctionInvoker.invoke(functionName, parameters)
    │ validates parameters
    │ converts string → native types via TypeConverter chain
    │ calls NativeFunction.invoke(convertedParams)
    │ converts return value to string via TypeConverter
    ▼
InvocationResult
    │
    ├── success=true: returnValueHandler.storeReturnValue() → PcpFunctionResponse(returnValueKey)
    │
    └── success=false: PcpFunctionResponse(error)
    │
    ▼
PcpRequestResult(transport=Transport.Tpipe)
    │
    ▼
PcpExecutionResult (for batch)
    │
    ▼
PcpRegistry.executeRequest() → caller
```

## Key Insight for PathObject Schema Design

PCP's schema system (`FunctionSignature` / `ParameterInfo`) is what makes LLM-to-function calling reliable. The LLM needs machine-readable type information to fill parameters correctly. PCP's contribution is the `ParamType` enum, `enumValues` lists on parameters, and the `TypeConverter` chain for bidirectional string ↔ native conversion.

For PathObject dispatch, the same problem exists — the dispatcher LLM must produce a path invocation that the harness can validate and execute. PCP's schema insight applies directly. But PCP as a protocol is overkill because:
- Paths are always internal to a harness (not distributed across network)
- PCP's polyglot sandbox, streaming, and multi-language support is unnecessary
- PCP's `PcpContext` security model (whitelists, file system restrictions) is irrelevant for in-process path dispatch

The correct design: a `PathSchema` data class that carries the PCP insight (description, input schema with types/enums, output description) without the protocol overhead. See `pump-station` SKILL.md §PathObject Schema Contract.
