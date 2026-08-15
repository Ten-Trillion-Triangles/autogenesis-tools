# PCP System Prompt Injection & PcpInstructionGenerator

Source: `Pipe.kt:1596` (`setSystemPrompt()`) and `PcpInstructionGenerator.kt` — read 2026-05-21.

---

## How PCP Schema Reaches the LLM

The schema is injected via `Pipe.setSystemPrompt()` at Pipe.kt:1615 (PCP-only mode) and Pipe.kt:1659 (merged mode with JSON output):

```kotlin
val pcpAsJson = serialize(pcpContext, false)
systemPrompt += "You may take actions using the Pipe Context Protocol.\n${pcpAsJson}\n..."
```

`PcpContext` is the container. `TPipeContextOptions` carries function schemas inside it. `ContextOptionParameter` carries per-parameter schema (type, description, enumValues, isRequired) within each `params` entry.

The `PcpInstructionGenerator` output is appended AFTER the raw JSON, giving the LLM human-readable runtime guidance alongside machine-readable schema.

---

## PCP Tool Detection (Pipe.kt:1602)

```kotlin
val hasPcpTools = !pcpContext.tpipeOptions.isEmpty() ||
                  !pcpContext.httpOptions.isEmpty() ||
                  !pcpContext.stdioOptions.isEmpty() ||
                  pcpContext.pythonOptions.availablePackages.isNotEmpty()
```

This flag gates whether the PCP instruction block is injected at all.

---

## PcpInstructionGenerator

Located at `src/main/kotlin/PipeContextProtocol/PcpInstructionGenerator.kt`.

### Kotlin instructions

```kotlin
PcpInstructionGenerator.generateKotlinInstructions(kotlinOptions: KotlinContext, pcpContext: PcpContext): String
PcpInstructionGenerator.generateCodeExecutionGuide(kotlinOptions: KotlinContext): String
```

Generates sections for: memory access, file system access, imports/packages, capabilities. `generateCodeExecutionGuide()` produces the JSON example for `argumentsOrFunctionParams`:

```kotlin
"""
KOTLIN SCRIPT EXECUTION:
- Put Kotlin code in argumentsOrFunctionParams array
- Each element is a line or block of code
- Use println() to return output
- Code runs in JVM via script engine
- Example:
  {
    "kotlinContextOptions": {},
    "argumentsOrFunctionParams": ["val x = 10", "val y = 20", "println(x + y)"]
  }
"""
```

### Python instructions

```kotlin
PcpInstructionGenerator.generatePythonInstructions(pythonOptions: PythonContext, pcpContext: PcpContext): String
PcpInstructionGenerator.generatePythonCodeExecutionGuide(): String
```

### JavaScript instructions

```kotlin
PcpInstructionGenerator.generateJavaScriptInstructions(javascriptOptions: JavaScriptContext, pcpContext: PcpContext): String
PcpInstructionGenerator.generateJavaScriptCodeExecutionGuide(): String
```

---

## Where It's Called in Pipe.kt

The `PcpInstructionGenerator` output is conditionally appended at Pipe.kt:1969-2002 after the raw `PcpContext` JSON — only when the respective runtime options are non-empty:

```kotlin
if(pcpContext.kotlinOptions.allowTpipeIntrospection ||
   pcpContext.kotlinOptions.allowHostApplicationAccess ||
   pcpContext.kotlinOptions.allowedImports.isNotEmpty() ||
   pcpContext.kotlinOptions.blockedImports.isNotEmpty()) {
    pcpContext.kotlinOptions,
    pcpContext,
    // → appends Kotlin instruction sections + code execution guide
}

if(pcpContext.pythonOptions.availablePackages.isNotEmpty() ||
   pcpContext.pythonOptions.workingDirectory.isNotEmpty() ||
   pcpContext.pythonOptions.permissions.isNotEmpty()) {
    pcpContext.pythonOptions,
    pcpContext,
    // → appends Python instruction sections + code execution guide
}

if(pcpContext.javascriptOptions.allowedModules.isNotEmpty() ||
   pcpContext.javascriptOptions.workingDirectory.isNotEmpty() ||
   pcpContext.javascriptOptions.permissions.isNotEmpty()) {
    pcpContext.javascriptOptions,
    pcpContext,
    // → appends JavaScript instruction sections + code execution guide
}
```

---

## The Full Instruction Block the LLM Receives

The complete instruction text appended to the system prompt for PCP-only mode (Pipe.kt:1662-1686):

```
You may take actions to carry out your task using the Pipe Context Protocol.
The Pipe Context Protocol is a standardized way to communicate with user's machine. The protocol is as follows:
${pcpAsJson}

The above Pipe Context Protocol json defines each tool you can call and what it can do. Each tool's parameters
include an "isRequired" field - you MUST provide all parameters where isRequired is true, while parameters
where isRequired is false are optional and may be omitted.

If you wish to call or use any tools provided to you return an array of the following json for each tool you wish to call:
${pcpRequestAsJson}

When returning any json requests for tools. You must always follow the json schema exactly.

IMPORTANT - How to pass arguments when calling tools:
The 'params' field inside each tool definition describes the function's expected parameters (names, types, descriptions).
It is for reference only. Do NOT place argument values inside 'params' when making a call.

To call a TPipe function, set 'tPipeContextOptions.functionName' to the function name and pass argument values using one of:
  - 'callParams': A map of named arguments. Example: {"paramName": "value", "otherParam": "value2"}
  - 'argumentsOrFunctionParams': A list of positional arguments in the order defined by the function signature.
'callParams' is preferred. If both are provided, 'callParams' values override positional arguments.

To call a stdio command, populate 'stdioContextOptions' with the command and arguments.
To call an HTTP endpoint, populate 'httpContextOptions' with the URL, method, and request body.
To execute Python, Kotlin, or JavaScript code, populate the respective context options.
```

Then the `PcpInstructionGenerator` output is appended, adding runtime-specific human-readable guidance for whatever language contexts are configured.