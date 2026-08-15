# PCP security managers — per-manager threat model and validation gates

Reference for the four `*SecurityManager` classes in `TPipe/src/main/kotlin/PipeContextProtocol/`. Each has a different threat model and a different defense pattern. This file documents the actual gates, the defaults, and the override knobs — everything you need to audit a PCP context config without re-reading source.

---

## `PythonSecurityManager.kt` — file path: same directory

### Threat model

Untrusted Python script running as a subprocess of the JVM. The OS process model is the primary sandbox (the subprocess can't reach the host JVM's memory). The security manager exists to:

1. Block dangerous Python idioms (`os.system`, `subprocess.run`, dynamic imports via `__import__`)
2. Limit blast radius of long-running / large-output scripts
3. Enforce developer-set package and import allowlists
4. Require explicit `Permissions` for operations that touch the filesystem or network

### Layered defense

The Python security manager runs **two** validation passes per script and requires **both** to pass:

1. **AST validation (defense-in-depth, robust)**
   `performAstValidation()` writes the script + blocked-imports/blocked-functions list to a Python subprocess running `ast_validator.py` (loaded from `src/main/resources/ast_validator.py`, cached to temp file with `deleteOnExit()`), runs with a 10-second timeout, parses JSON `{isValid, errors, warnings}`.
   - Catches: dynamic imports (`__import__("os".replace("o","s"))`), nested function definitions calling blocked names, conditional imports
   - **Misses**: things the AST can't see but runtime can (e.g., string-based `eval` of a hex-encoded `os.system`)
2. **Regex validation (legacy, defense-in-depth)**
   Three checks per script:
   - Blocked imports — three patterns per blocked import covering `import x`, `from x import`, `import x as y`
   - Blocked functions — two patterns per function, the second being `getattr(... , 'name')` to catch indirect access
   - Blocked patterns (`eval(`, `exec(`, `__import__(`)

### Per-level defaults (`PythonSecurityLevel`)

| Level | maxTimeoutMs | maxScriptSize | requirePermissions |
|---|---|---|---|
| STRICT | 60,000 (1 min) | 1,048,576 (1 MB) | true |
| BALANCED | 300,000 (5 min) | 1,048,576 (1 MB) | true |
| PERMISSIVE | 1,800,000 (30 min) | 10,485,760 (10 MB) | true |
| DISABLED | Long.MAX_VALUE | Int.MAX_VALUE | false |

### Per-level blocked sets

| Level | Blocked imports (added) | Blocked functions (added) | Blocked patterns |
|---|---|---|---|
| STRICT | `DANGEROUS_IMPORTS + {sys, importlib, ctypes}` | `DANGEROUS_FUNCTIONS + {eval, exec, compile, __import__}` | `DANGEROUS_PATTERNS` |
| BALANCED | `DANGEROUS_IMPORTS` (= `{os, subprocess}`) | `DANGEROUS_FUNCTIONS` (= `{os.system, subprocess.call, subprocess.run, subprocess.Popen}`) | `{eval\s*\(, exec\s*\(` |
| PERMISSIVE | empty | empty | empty |
| DISABLED | empty | empty | empty |

### Permission gates

`requirePermissions = true` (default at all levels except DISABLED) triggers:
- `containsFileOperations(script)` → requires `Permissions.Write` if matched
  - Patterns: `open\(`, `.write\(`, `with open`, `pathlib`, `shutil`
- `containsNetworkOperations(script)` → requires `Permissions.Read` if matched
  - Patterns: `requests.`, `urllib.`, `http.`, `socket.`, `ssl.`

### Developer overrides

The executor exposes three fluent overrides:

```kotlin
pythonExecutor.allowImports("os", "subprocess")           // subtract from blocked set
pythonExecutor.allowFunctions("os.system")
pythonExecutor.allowPatterns("eval\\s*\\(")
```

Each adds to the `allowedImports` / `allowedFunctions` / `allowedPatterns` set on `PythonSecurityConfig`. Matches against allowed items surface as **warnings** rather than errors.

### Package allowlist (separate from import blocks)

`PythonExecutor.validatePackageImports()` parses `import` and `from ... import` statements, then checks each module name against `context.availablePackages`. If the context specifies packages, anything not in the list is rejected with `"Import 'X' not in allowed packages list"`. If the list is empty, all imports pass.

### The `captureOutput` dead-config bug

`PythonContext.captureOutput: Boolean = true` is set on the context, merged into the request, but **never read at the capture site**. The executor always reads stdout and stderr regardless. Setting `captureOutput = false` does nothing — reserved state, not behavior. See `references/executor-output-capture.md`.

---

## `KotlinSecurityManager.kt` — file path: same directory

### Threat model

Untrusted Kotlin script running **inside the JVM** via JSR-223 (`kotlin-scripting-jsr223`). No subprocess — the script shares memory with the host JVM, can call into TPipe, can read environment variables, can fork processes via `ProcessBuilder` if not blocked. The security manager exists because there is no OS boundary.

This is the most conservative of the four — all six capability flags default to false.

### Capability flags

| Flag | Default | Blocklist when false |
|---|---|---|
| `allowReflection` | false | `::class`, `KClass`, `java.lang.reflect`, `kotlin.reflect` |
| `allowClassLoaderAccess` | false | `ClassLoader`, `getClassLoader` |
| `allowTpipeIntrospection` | false | `PcpRegistry`, `PcpContext` |
| `allowFileRead` | false | (joined with Write/Delete — see below) |
| `allowFileWrite` | false | (joined with Read/Delete — see below) |
| `allowFileDelete` | false | (joined with Read/Write — see below) |
| `allowNetworkAccess` | false | `Socket`, `URL(`, `HttpURLConnection`, `ServerSocket`, `java.net` |
| `allowProcessExecution` | false | `ProcessBuilder`, `Runtime.getRuntime`, `exec(`, `java.lang.Process` |
| `allowHostApplicationAccess` | false | (separate opt-in — requires `exposedBindings` map) |

### File access — special case

If **all three** of `allowFileRead`, `allowFileWrite`, `allowFileDelete` are false, the script is scanned for any file access pattern:

```kotlin
val filePatterns = listOf("File(", "FileInputStream", "FileOutputStream",
                          "FileReader", "FileWriter", "readText", "readLine", "readBytes")
```

Setting any one of the three to true loosens this check — but you have to opt in explicitly to each capability.

### Imports and packages

`KotlinContext` has four import/package lists:

- `allowedImports: MutableList<String>` — if non-empty, only these allowed (allowlist mode)
- `blockedImports: MutableList<String>` — if `allowedImports` is empty, these are blocked (blocklist mode)
- `allowedPackages: MutableList<String>` — package-level allowlist (substring match on `import x.y.z` → package `x.y`)
- `blockedPackages: MutableList<String>` — package-level blocklist

Wildcards supported: `import java.io.*` matches `java.io.*` blocklist entries.

### Dangerous items scan

After import validation, `validateGeneralSecurity()` runs:

```kotlin
val dangerousItems = KotlinConstants.DANGEROUS_FUNCTIONS + KotlinConstants.DANGEROUS_IMPORTS
dangerousItems.forEach { item ->
    val itemPattern = Regex("\\b${item.replace(".", "\\.")}\\b")
    if(itemPattern.containsMatchIn(script)) errors.add("Potentially dangerous usage of '$item'")
}
KotlinConstants.DANGEROUS_PATTERNS.forEach { pattern ->
    if(Regex(pattern).containsMatchIn(script)) errors.add("Dangerous pattern found: '$pattern'")
}
```

This is **substring scan**, not AST. Catches `java.io.File`, `Runtime.getRuntime`, etc. Misses obfuscated references (string concatenation, `KClass.simpleName`).

### Host bindings — the opt-in escape hatch

`KotlinContext.allowHostApplicationAccess = false` (default). When true, the `exposedBindings: MutableMap<String, String>` map (name → description) tells the executor which `customBindings` to inject:

```kotlin
if(mergedOptions.allowHostApplicationAccess) {
    mergedOptions.exposedBindings.keys.forEach { bindingName ->
        customBindings[bindingName]?.let { bindings[bindingName] = it }
    }
}
```

You have to register bindings via `executor.registerBinding(name, obj, description)` first. The map only declares what's exposed; the binding itself lives in the executor's `customBindings: MutableMap<String, Any>`.

### The timeout gap

`KotlinContext.timeoutMs` is read by the executor's merge step but **not** enforced at the `engine.eval()` site. See `references/executor-output-capture.md`. Wrap untrusted scripts in `withTimeoutOrNull` at the caller layer.

---

## `HttpSecurityManager.kt` — file path: same directory

### Threat model

Outbound HTTP. The only transport where the sandbox boundary is "did the request reach an internal IP we shouldn't be allowed to call?" — i.e., SSRF. The executor uses TPipe's `com.TTT.Util.httpRequest` (Ktor-based) under the hood. The security manager is the **strictest** of the four because blast radius is highest (data exfiltration, internal network access).

### Per-level defaults (`HttpSecurityLevel`)

| Level | maxTimeoutMs | maxRequestBodySize | maxHeaders | requireExplicitHosts | requireExplicitMethods | requirePermissions | allowPrivateNetworks |
|---|---|---|---|---|---|---|---|
| STRICT | 30,000 (30s) | 65,536 (64KB) | 10 | true | true | true | **false** |
| BALANCED | 300,000 (5min) | 1,048,576 (1MB) | 50 | true | true | true | **false** |
| PERMISSIVE | 1,800,000 (30min) | 10,485,760 (10MB) | 100 | false | false | true | **false** |
| DISABLED | Long.MAX_VALUE | Int.MAX_VALUE | Int.MAX_VALUE | false | false | false | **true** |

### SSRF protection — fail-closed

```kotlin
private val privateNetworkRanges = listOf(
    "127.0.0.0/8",      // Loopback (localhost, 127.0.0.1, etc.)
    "10.0.0.0/8",       // Private Class A (10.x.x.x)
    "172.16.0.0/12",    // Private Class B (172.16-31.x.x)
    "192.168.0.0/16",   // Private Class C (192.168.x.x)
    "169.254.0.0/16",   // Link-local (AWS/GCP/Azure metadata services)
    "::1/128",          // IPv6 loopback
    "fc00::/7",         // IPv6 unique local
    "fe80::/10"         // IPv6 link-local
)
```

`checkSsrfProtection()` resolves the URL's host via `InetAddress.getByName()` and tests against these ranges. **Fail-closed on resolution failure**:

```kotlin
catch(e: Exception) {
    // If we can't resolve, we MUST assume it's unsafe (fail-closed)
    return SsrfCheckResult(true, null)
}
```

Comment is explicit: "an attacker might use a non-resolvable host that resolves to a private IP during the actual request window." DNS rebinding mitigation by failing closed.

The resolved IP is returned and used by `HttpExecutor` to construct the actual request URL (`httpExecutor.kt:230-248`), with the `Host` header manually set to the original hostname (`httpExecutor.kt:271-274`). This prevents DNS rebinding during the actual request.

### Host allowlist

- If `allowedHosts` is set, the URL host must match (exact or subdomain via `host.endsWith(".$allowed")`)
- Wildcard `*` is rejected: `if(options.allowedHosts.any { it.trim() == "*" }) errors.add("Wildcard host '*' is not permitted in allowed hosts")`
- Port-specific entries (`host:port`) matched as-is

### Method allowlist + permission gates

`HttpConstants.READ_METHODS = {GET, HEAD}` require `Permissions.Read`.
`HttpConstants.WRITE_METHODS = {POST, PUT, PATCH, DELETE}` require `Permissions.Write`.

If `requireExplicitMethods = true` and `allowedMethods` is empty → error.
If `allowedMethods` is non-empty, the request's method must be in it.

### Endpoint sanitization

Rejects endpoints that:
- Start with `http` or `//` (absolute URL or protocol-relative — must be relative)
- Contain `..` (path traversal)
- Contain `\` (backslash)

### Header validation

Warns on (does not block):
- `authorization`
- `cookie`
- `x-forwarded-for`
- `x-real-ip`
- `host`

Errors on:
- `\r` or `\n` in header value (header injection)
- Header value length > 8,192 chars

### Resource caps

- `timeoutMs` ≤ `securityConfig.maxTimeoutMs`
- `requestBody.length` ≤ `securityConfig.maxRequestBodySize`
- `headers.size` ≤ `securityConfig.maxHeaders`

---

## `CommandSecurityManager.kt` — file path: same directory

### Threat model

Shell command execution via `ProcessBuilder`. No SSRF concern (no network), no host-app concern (subprocess is its own process), but high local-system reach: `rm -rf`, `chmod`, `shutdown`, etc. The defense is **command-name allowlist + 4-tier classification + injection regex**.

### Command classification (`SecurityLevel`)

| Level | Meaning | Default action |
|---|---|---|
| `SAFE` | Always allowed | Read-only info commands: `ls`, `cat`, `echo`, `head`, `tail`, `wc`, `pwd`, `whoami`, `grep`, `sort`, `awk`, `sed` |
| `RESTRICTED` | Requires explicit permission | System info + network: `ps`, `top`, `netstat`, `ping`, `traceroute`, `nslookup`, `find`, `tar`, `gzip`, `unzip` |
| `DANGEROUS` | Requires elevated permission | File mutation + permissions + users + network mutation: `mv`, `cp`, `chmod`, `chown`, `kill`, `systemctl`, `service`, `passwd`, `iptables`, `ufw` |
| `FORBIDDEN` | Never allowed | Destructive + system control + security bypass: `rm`, `shred`, `dd`, `mkfs`, `shutdown`, `reboot`, `insmod`, `chroot`, `unshare` |

### Platform split

Same commands, different classification depending on `Platform.{WINDOWS, LINUX, MACOS, UNIX_LIKE}`. The default database has separate maps for Windows (`dir`, `type`, `tasklist`, `netstat`, `reg`, `del`, `format`, `diskpart`, `bcdedit`, etc.) and Unix-like (`ls`, `cat`, `rm`, `chmod`, `iptables`, etc.).

### Validation

`validateCommand(command, allowedCommands, maxSecurityLevel)`:

1. If `allowedCommands` non-empty: must be in the list exactly. **Highest priority.**
2. Otherwise: get classification (custom override → platform-specific match → `null` for unknown)
3. Unknown commands default to `RESTRICTED`
4. Check if command level ≤ max level:
   - `SAFE` → only `SAFE` allowed
   - `RESTRICTED` → `SAFE` or `RESTRICTED`
   - `DANGEROUS` → anything except `FORBIDDEN`
   - `FORBIDDEN` → everything (not recommended)

### Injection detection

```kotlin
private val injectionPatterns = listOf(
    Regex("[;&|`$\\(\\)]"),       // command separators and substitution
    Regex("\\.\\."),             // directory traversal
    Regex(">/dev/"),             // device access
    Regex("\\|\\s*nc\\s"),       // netcat piping
    Regex("\\|\\s*curl\\s"),     // curl piping
    Regex("\\|\\s*wget\\s")      // wget piping
)
```

`detectCommandInjection(input)` returns true if any pattern matches. `sanitizeArguments(args)` strips matched patterns from each arg, then escapes `"` and `'`.

### Path permissions

`checkPathPermissions(path, permissions)` blocks system directories:
- Windows: `c:/windows`, `c:/system32`, `c:/program files`
- Unix: `/etc`, `/sys`, `/proc`, `/dev`, `/boot`, `/root`

Access to system paths requires `Permissions.Execute`. Non-system paths always allowed.

### Session and buffer ACL

- `validateSessionAccess(sessionId, userId)` checks `StdioSessionManager.getSession(sessionId).isActive && ownerId == userId`
- `validateBufferAccess(bufferId, permissions)` checks `bufferId.isNotEmpty() && permissions.isNotEmpty()`

These are wired up via `PcpContext.enableSessionAccessControl` and `enableBufferAccessControl`.

---

## Cross-manager invariants

1. **Per-language security managers are NEVER shared.** Each language has its own. The threat models differ — Python's regex+AST is wrong for Kotlin, Kotlin's capability flags are wrong for Python, etc.
2. **Context options override request options for security settings.** Every executor's `mergeContextOptions()` makes the context win for `*Path`, `*Permissions`, `*Timeout`, `*Allowed*`.
3. **Developer overrides are subtracted from blocked sets.** `allowedImports` / `allowedFunctions` / `allowedPatterns` etc. are computed as `getBlockedX() - allowedX`. Matches against allowed items are warnings, not errors.
4. **Subprocess executors enforce timeout at the executor level; in-process executors don't.** Python and JavaScript use `ProcessBuilder.waitFor(timeoutMs)` + `destroyForcibly()`. Kotlin's `engine.eval()` has no timeout — wrap at the caller layer.

## Per-executor security manager ownership

```kotlin
class PythonExecutor     : private val securityManager = PythonSecurityManager()
class KotlinExecutor     : private val securityManager = KotlinSecurityManager()
class JavaScriptExecutor : private val securityManager = JavaScriptSecurityManager()
class StdioExecutor      : private val securityManager = CommandSecurityManager()
class HttpExecutor       : private val securityManager = HttpSecurityManager()
```

If you're auditing PCP security, start with the per-language `*SecurityManager` config, then trace through `mergeContextOptions` to confirm context options are actually being applied. The executors are the bridge between config and validation; if you find a security gap, the bug is usually in the executor's merge step or the manager's defaults, not in the validator itself.

## Key files

| File | Lines | Purpose |
|---|---|---|
| `PythonSecurityManager.kt` | 441 | AST + regex + per-level caps |
| `KotlinSecurityManager.kt` | 152 | Regex + 6 capability flags |
| `JavaScriptSecurityManager.kt` | (similar size to Kotlin) | Module allowlist |
| `CommandSecurityManager.kt` | 552 | Command classification + injection regex |
| `HttpSecurityManager.kt` | 804 | SSRF + host allowlist + header scan + caps |
| `PythonConstants.kt` | 40 | Default blocked sets + safe packages |
| `KotlinConstants.kt` | (small) | Default blocked imports/patterns |
| `HttpConstants.kt` | (small) | Method classification + auth type constants |
