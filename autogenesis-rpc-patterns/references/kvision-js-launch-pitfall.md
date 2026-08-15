# Kotlin 2.2 + KVision/JS multi-line `launch` failure

## Symptom

In Kotlin/JS files under `kvisionApp/src/jsMain/kotlin/`, this pattern FAILS to compile with the misleading error:

```
e: file:///.../MyFile.kt:60:15 Function invocation 'launch(...)' expected.
e: file:///.../MyFile.kt:62:17 Suspend function 'suspend fun mySuspend(): Unit' can only be called from a coroutine or another suspend function.
```

```kotlin
MainScope().launch
{
    try
    {
        mySuspend()
    }
    catch (e: Throwable)
    {
        logger.warn(...)
    }
}
```

Same code with the brace on the SAME LINE works:

```kotlin
MainScope().launch {
    try
    {
        mySuspend()
    }
    catch (e: Throwable)
    {
        logger.warn(...)
    }
}
```

## Root cause

Kotlin 2.2.20 + KVision 9.1.1 (the toolchain pinned in the Autogenesis build) has a parser quirk where the trailing-lambda form `launch\n{` on a separate line is not recognised as an extension function call on the `CoroutineScope` returned by `MainScope()`. The error message points at `.launch` as if the extension doesn't exist, but the issue is the lambda placement, not the function resolution.

The existing code in `kvisionApp/src/jsMain/kotlin/ui/MainMenu.kt:349`, `LoginWidgets.kt:809`, `MapViewer.kt:165` all uses the same-line form, presumably because someone hit this exact issue before and the pattern propagated.

## The fix

**Always use single-line `MainScope().launch { ... }` form in `:kvisionApp` Kotlin/JS files.** Even for multi-statement lambda bodies — keep the brace on the same line as `launch`.

If the body is genuinely too long for a single line, use one of these workarounds:

### Option A — Same-line brace, body on subsequent lines (the standard TTT fix)

```kotlin
MainScope().launch {
    try
    {
        mySuspend()
    }
    catch (e: Throwable)
    {
        logger.warn(...)
    }
}
```

### Option B — Assign to a variable first, then launch on a fresh line

```kotlin
val myScope = MainScope()
myScope.launch {
    mySuspend()
}
```

### Option C — Explicit `GlobalScope.launch(context) { ... }` (only when other options fail)

```kotlin
@file:OptIn(kotlinx.coroutines.DelicateCoroutinesApi::class)
...
kotlinx.coroutines.GlobalScope.launch(kotlinx.coroutines.Dispatchers.Main + kotlinx.coroutines.Job()) {
    mySuspend()
}
```

Option C was needed once in `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ResumeAvailabilityPushService.kt:60` when both Option A and B failed against a fresh `CoroutineScope(Dispatchers.Default + SupervisorJob())` instance. The exact failure mode there was different (the JVM target) — the JVM-only `private val scope` + `scope.launch\n{` form also fails in this build, but `GlobalScope.launch(context) { ... }` with explicit context arg works.

## Companion quirk for server-extend JVM

```kotlin
// FAILS — same Kotlin 2.2 parser quirk on JVM with a member-style scope field
private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
scope.launch
{
    mySuspend()
}

// WORKS — same-line brace
private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())
scope.launch {
    mySuspend()
}

// WORKS — fresh scope inline
CoroutineScope(Dispatchers.Default + SupervisorJob()).launch {
    mySuspend()
}
```

## When in doubt

- Search for `MainScope().launch {` in `kvisionApp/src/jsMain/kotlin/` to find every existing instance — they all use the same-line form. Match the pattern.
- Search for `CoroutineScope(Dispatchers.IO).launch {` in `server/src/main/kotlin/` — those files use the same-line form too.
- If the build fails with "Function invocation 'launch(...)' expected", the first thing to try is collapsing the brace onto the same line.