# Runtime verification of RPC auto-registration (Playwright recipe)

The 2026-08-12 incident produced this recipe. **Document your assumption is wrong** if your fix for an RPC registration problem is a manual call in `Main.kt` — the running bundle almost certainly auto-registers everything via `RpcRegistrationCollector`, and the real problem is elsewhere. This file ships the re-runnable probe that proves it.

## Why static analysis is not enough

The auto-registration chain:

1. `rpc-ksp` generates a `_rpcRegistrationInitializer = run { ... }` block in `sharedModel/build/generated/ksp/<target>/kotlin/org/ttt/autogenesis/network/generated/GeneratedRpcMasterRegistration.kt` that references every `_<Name>RpcHandlersProvider` val by name.
2. `sharedModel/src/jsMain/.../RpcRegistrationPlatform.kt` is the JS entry point — its `actual fun initializeRpcRegistrationsPlatform()` does `requireFunc?.invoke("./org/ttt/autogenesis/network/generated/GeneratedRpcMasterRegistrationKt")` to force the JS module loader to evaluate the master initializer.
3. `RpcRegistry.<init>` (sharedModel/src/commonMain/.../RpcRuntime.kt:141-149) calls `initializeRpcRegistrationsPlatform()` then `RpcRegistrationCollector.registerAll(this)` then a log line of the form `RpcRegistry initialized with N handlers from M providers`.
4. Each `_<Name>RpcHandlersProvider` is a top-level val whose `init { ... }` calls `RpcRegistrationCollector.registerProvider(it)`. Reaching the val via the master initializer's `run { ... }` block triggers the registration.

Static analysis proves the chain EXISTS. The chain runs at runtime — `require(MODULE_PATH)` only fires when JS actually evaluates the script, and webpack's tree-shaking can drop the master initializer if no one references it. The only way to prove the chain executed is to capture the console output and grep for the log lines.

## How the JS log writer works (2026-08-12 reality)

`sharedModel/src/jsMain/kotlin/org/ttt/autogenesis/logging/LogWriter.js.kt` writes every log to `console.log` (DEBUG), `console.info` (INFO), `console.warn` (WARN), `console.error` (ERROR) at line 60-66:

```kotlin
when (entry.priority) {
    LogPriority.DEBUG -> console.log(formattedMessage)
    LogPriority.INFO  -> console.info(formattedMessage)
    LogPriority.WARN  -> console.warn(formattedMessage)
    LogPriority.ERROR -> console.error(formattedMessage)
}
```

The buffer (in DEBUG mode) is sent to `http://127.0.0.1:9080/api/browser-log` via `window.fetch(...)` every 3s. **There is no localStorage persistence** — the `configure()` function's KDoc at line 30 says "saveToDisk Ignored in browser (localStorage persistence removed for performance)." AGENTS.md:72 is wrong on this point.

**Verification probe must use Playwright's `page.on('console', ...)` listener**, NOT `localStorage.getItem("autogenesis_logs")`. The console-event-format is `"${entry.timestamp} [${entry.priority}] [${entry.category}]: ${entry.message}"`. Priority tokens are uppercase (`[DEBUG]`, `[INFO]`, `[WARN]`, `[ERROR]`) — case-sensitive in the regex.

## The probe (saved as `kvisionApp-e2e/probes/rpc-auto-reg.mjs`)

```javascript
// kvisionApp-e2e/probes/rpc-auto-reg.mjs
import { chromium } from 'playwright';

const URL = 'http://localhost:8080/?skipLogin=true';

const REQUIRED = [
    { name: 'MapUploadSuccess',  re: /RpcRegistrationCollector:\s*Registering provider\s+MapUploadSuccessClientHandlersRegistrationProvider/i, mustMatch: true },
    { name: 'MapUploadError',    re: /RpcRegistrationCollector:\s*Registering provider\s+MapUploadErrorClientHandlersRegistrationProvider/i,   mustMatch: true },
    { name: 'UiSignal',          re: /RpcRegistrationCollector:\s*Registering provider\s+UiSignalClientHandlersRegistrationProvider/i,         mustMatch: true },
    { name: 'Audio',             re: /RpcRegistrationCollector:\s*Registering provider\s+AudioClientHandlersRegistrationProvider/i,             mustMatch: true },
    { name: 'ActionHistory',     re: /RpcRegistrationCollector:\s*Registering provider\s+ActionHistoryClientHandlersRegistrationProvider/i,   mustMatch: true },
];

async function main() {
    const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
    const page = await ctx.newPage();
    const captured = [];
    page.on('console', msg => captured.push(`[${msg.type()}] ${msg.text()}`));
    page.on('pageerror', err => captured.push(`[pageerror] ${err.message}`));

    await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
    await page.waitForTimeout(30000); // generous boot window for the bridges to construct their registries

    await ctx.close();
    await browser.close();

    const all = captured.join('\n');
    let pass = true;
    for (const check of REQUIRED) {
        const matches = [...all.matchAll(new RegExp(check.re.source, 'gi'))];
        if (matches.length === 0 && check.mustMatch) {
            console.error(`FAIL: ${check.name}`);
            pass = false;
        } else if (matches.length > 0) {
            console.log(`OK ${check.name}: ${matches.length}x`);
        }
    }

    const initMatches = [...all.matchAll(/RpcRegistry initialized with (\d+) handlers from (\d+) providers/gi)];
    if (initMatches.length < 2) {
        console.error(`FAIL: expected >=2 RpcRegistry init lines, got ${initMatches.length}`);
        pass = false;
    } else {
        for (const m of initMatches) {
            console.log(`registry-init: ${m[1]} handlers from ${m[2]} providers`);
        }
    }
    if (!pass) process.exit(1);
}
main().catch(e => { console.error(e); process.exit(1); });
```

Diagnostic variant that just dumps captured console output: `kvisionApp-e2e/probes/dump-rpc-logs.mjs`.

## Recipe: read it out of context

1. **Pre-flight**: stack is up (`ss -tlnp | grep -E ':(7070|8080|9080)'` shows java + webpack pids).
2. `node kvisionApp-e2e/probes/rpc-auto-reg.mjs 2>&1 | head -30`
3. **Expected output (autogenesis-kvisionApp, 5 client-listener classes):**
   ```
   registry-init: 0 handlers from 0 providers      <- WebSocketRpcBridge.rpcRegistry first read (may be empty if nothing registered yet)
   registry-init: 40 handlers from 5 providers    <- SharedRestRpcBridge.rpcRegistry after auto-reg via REST/SSE bridge
   OK MapUploadSuccess: 1x
   OK MapUploadError: 1x
   OK UiSignal: 1x
   OK Audio: 1x
   OK ActionHistory: 1x
   ```
4. **Failure modes**:
   - `0 handlers from 0 providers` on BOTH registries → master initializer wasn't loaded. Check `RpcRegistrationPlatform.js` — JS path is `requireFunc?.invoke(...)`. If `require` is undefined (webpack without CommonJS shim), the require silently no-ops.
   - `Ok X: 0x` for some class → its provider val wasn't reachable. Check whether the class is annotated with `@RpcMethod` (otherwise KSP doesn't generate the provider). Check whether the file is imported somewhere reachable from the boot path.
   - Tests fail with `main-menu` never mounting → the bundle is stale (HMR didn't pick up the source change). Reload the webpack server: `pkill -f jsBrowserDevelopmentRun && nohup ./gradlew :kvisionApp:jsBrowserDevelopmentRun > /tmp/kvision.log 2>&1 &`.

## Server-extend module variant

The probe above is kvisionApp-shaped. For server-extend module, the same pattern applies but the expected provider count comes from `server-extend/build/generated/ksp/main/kotlin/org/ttt/autogenesis/serverextend/GeneratedServerExtendRpcMasterRegistration.kt` (or wherever the generated master lives — same directory structure as kvisionApp). Common server-extend providers include `ServerConnectorRpcHandlers`, `ExtendCommanderRunnerRpcHandlers`, `CloudSaveProxyRpcHandlers`, `MapUploadGateRpcHandlers`, `BinaryRecordProxyRpcHandlers`. Replace the `REQUIRED` array with the actual class names.

## Other JS-debug pitfalls that the same probe surfaces

- The `Main.kt:425` `Logger.configure(LogPriority.DEBUG, true)` call uses `minPriority=DEBUG` — without that, DEBUG entries are dropped at the log writer gate at `LogWriter.js.kt:55` (`if (entry.priority.level < minPriority.level) return`).
- The webpack-dev-server hot-reload can race with Playwright's `waitForTimeout(30000)` — if your probe sees boot logs but misses the registration logs, the script may have hit a stale bundle. Confirm via `grep -c 'via its own SSE' /path/to/bundle` (which is a stable commit-marker for the cowboy block; should be 0 to verify the bundle reflects the revert).
- The `Map.Upload.Error` log entry fires through `Logger.warn(LogCategory.NETWORK, ...)` at `MapUploadErrorClientHandlers.kt:30`. Test the channel: trigger an upload via the modal with a known-bad file (large enough to trip the AGS 3 MB cap, or with a name that matches an existing entry), then grep for the `Map.Upload.Error` notification in the console.
