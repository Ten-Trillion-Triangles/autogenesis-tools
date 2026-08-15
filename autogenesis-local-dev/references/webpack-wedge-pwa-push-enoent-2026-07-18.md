# webpack-dev-server wedge root cause: pwa-push.js afterEmit ENOENT

Captured 2026-07-18 from the cold-boot gray-screen session where the user pushed back on "treat webpack as systemically broken — use static-server fallback" and demanded the actual root cause + fix.

## What the user observed

`./gradlew :kvisionApp:jsBrowserDevelopmentRun` boots successfully. Port :8080 accepts connections. Browser loads `http://localhost:8080/` but the page renders a gray screen with "Waiting for localhost..." in the corner (that's webpack-dev-middleware's loader overlay — the bundle never finished compiling). `curl -m 3 http://localhost:8080/` returns 0 bytes (HTTP 000) — accept succeeds, response never arrives. The gradle log shows:

```
[i] [webpack-dev-server] Project is running at: ...
[i] [webpack-dev-server] Loopback: http://localhost:8080/, ...
[i] [webpack-dev-middleware] Content not from webpack is served from 'kotlin, ../../../../kvisionApp/build/processedResources/js/main, ../../../..' directory
[i] [webpack-dev-middleware] wait until bundle finished: /
[i] [webpack-dev-middleware] wait until bundle finished: /sw.js
[i] [webpack-dev-middleware] wait until bundle finished: /
[i] [webpack-dev-middleware] wait until bundle finished: /kvisionApp.js
```

…and nothing else. webpack-dev-middleware is in its permanent "wait until bundle finished" state — all incoming requests are queued behind the never-marked-done first compile.

## Why prior sessions classified this as "systemically broken"

v1.21.0 (2026-07-18) logged: "webpack-dev-server has wedged THREE TIMES in the same session with the identical log pattern. Treat it as systemically broken in this sandbox — static-server + manual `:server:run` / `:server-extend:run` is the PRIMARY path, not the recovery fallback."

That was a hypothesis, not a diagnosis. The session transcript shows we killed the webpack process each time after 5-10+ minutes of `curl -m 30` timeouts and never read the gradle daemon log to look for the actual error. The 2026-07-18 session did read the daemon log and found the error.

## The actual error

The live gradle daemon log (find via `ls -t /home/cage/.gradle/daemon/8.14.4/*.out.log | head -1`) contains, after the `wait until bundle finished: /index.html` lines:

```
<e> [webpack-dev-middleware] Error: ENOENT: no such file or directory, copyfile
    '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp/build/processedResources/js/main/vapid_public.json'
    -> '/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/build/js/packages/Autogenesis-kvisionApp/dist/vapid_public.json'
<e>     at /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/build/js/packages/Autogenesis-kvisionApp/webpack.config.js:478:24
<e>     at /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/build/js/packages/Autogenesis-kvisionApp/webpack.config.js:474:25
<e>     at /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/build/js/node_modules/webpack/lib/Compiler.js:1028:27
```

webpack.config.js:478 is inside the `pwa-push.js` webpack plugin (the kotlin-js plugin concatenates all `webpack.config.d/*.js` files into a single scope at config-generation time). The plugin's afterEmit hook is failing because the destination's parent directory doesn't exist.

## Why the destination dir doesn't exist on cold boot

The kotlin-js plugin wires `jsBrowserDevelopmentRun` to invoke `node webpack/bin/webpack.js serve --config <generated webpack.config.js>` (verified via daemon log: `Starting process 'command '...node''... Working directory: .../build/js/packages/Autogenesis-kvisionApp Command: ...node .../webpack/bin/webpack.js serve --config .../webpack.config.js`). webpack's `serve` mode runs webpack-dev-server in-process — webpack compiles and serves in one Node process. webpack-dev-server uses webpack-dev-middleware internally; the middleware queues all incoming HTTP requests behind the first compile's "done" event.

On the FIRST compile of a cold boot, webpack only auto-creates the output directory (`dist/`) if it emits at least one asset. If the compile produces zero assets — a transient module-resolution race on the very first compile, a watcher-inotify race, an unlucky timing of the kotlin-webpack plugin copying files — webpack never creates `dist/`. But afterEmit still fires (webpack fires afterEmit on every compilation regardless of success).

The `pwa-push.js` afterEmit hook at `kvisionApp/webpack.config.d/pwa-push.js:74-91` runs on every compile:

```js
compiler.hooks.afterEmit.tap('VapidPublicJsonCopier', function (compilation) {
    const outDir = compilation.outputOptions.path;
    const srcDir = processedResourcesDir;
    const filesToCopy = [
        'vapid_public.json',
        'kvision-iam.local.properties',
        'kvision-global.local.properties'
    ];
    filesToCopy.forEach(function (filename) {
        const src = pathModule.join(srcDir, filename);
        const dst = pathModule.join(outDir, filename);
        if (fs.existsSync(src)) {
            fs.copyFileSync(src, dst);   // <-- THROWS ENOENT when outDir doesn't exist
        }
    });
});
```

`fs.copyFileSync(src, dst)` requires dst's parent directory to exist. If `outDir` (= `compilation.outputOptions.path` = `dist/`) is missing, the throw happens. webpack-dev-middleware captures the error and logs it but does NOT mark the bundle as done — all subsequent requests sit in the wait queue forever.

## How to find this if you suspect it

The diagnosis recipe — three commands, <30 seconds:

```bash
# 1. Confirm port :8080 has a webpack process and connections hang
ss -ltnp 2>/dev/null | grep ':8080'     # should show pid="webpack", users:((...,pid=N))
curl -sS --max-time 3 -o /dev/null -w 'HTTP %{http_code} size=%{size_download}\n' http://localhost:8080/
# -> HTTP 000 size=0 (NOT connection-refused)

# 2. Find the live gradle daemon log
LATEST=$(ls -t /home/cage/.gradle/daemon/8.14.4/*.out.log 2>/dev/null | head -1)
[ -z "$LATEST" ] && LATEST=$(ls -t ~/.gradle/daemon/*/*.out.log | head -1)
echo "log: $LATEST"

# 3. Grep for the actual error
grep -E 'webpack-dev-middleware.*Error' "$LATEST"
# -> ENOENT copyfile '...vapid_public.json' -> '.../dist/vapid_public.json' at webpack.config.js:478:24
```

The line number will be inside the pwa-push.js plugin code (the kotlin-js plugin concatenates webpack.config.d/*.js files in alphabetical order — pwa-push.js is late enough that its lines are at higher line numbers, typically 470-490 in the generated config).

## The fix

At `kvisionApp/webpack.config.d/pwa-push.js:74`, add `mkdirSync(outDir, {recursive: true})` BEFORE the copy loop. Idempotent (no-op if dir exists), best-effort (warns on failure rather than swallowing):

```js
compiler.hooks.afterEmit.tap('VapidPublicJsonCopier', function (compilation) {
    const outDir = compilation.outputOptions.path;
    const srcDir = processedResourcesDir;
    // webpack only auto-creates the output dir when it has at least
    // one asset to emit. If the compile produces zero assets (e.g.
    // a transient module-resolution failure during the first dev
    // run after a clean), afterEmit still fires but the dir is
    // missing, and `fs.copyFileSync` below throws ENOENT on the
    // destination's parent. Create it explicitly so the copy is
    // idempotent across cold-boot and warm-recompile scenarios.
    // `recursive: true` makes this a no-op when the dir already
    // exists.
    if (outDir) {
        try {
            fs.mkdirSync(outDir, { recursive: true });
        } catch (e) {
            // Best-effort: if mkdir fails the copyFileSync below
            // will throw and webpack-dev-middleware will surface
            // the underlying cause. Don't swallow silently.
            console.warn('PwaPushPlugin: mkdirSync(' + outDir + ') failed: ' + e.message);
        }
    }
    const filesToCopy = [
        'vapid_public.json',
        'kvision-iam.local.properties',
        'kvision-global.local.properties'
    ];
    filesToCopy.forEach(function (filename) {
        const src = pathModule.join(srcDir, filename);
        const dst = pathModule.join(outDir, filename);
        if (fs.existsSync(src)) {
            fs.copyFileSync(src, dst);
        }
    });
});
```

This is the change shipped in this session. Cold-boot `:kvisionApp:jsBrowserDevelopmentRun` now serves the bundle on the first compile, no workaround needed.

## The workaround (use when the fix isn't applied yet)

Pre-compile webpack once from the npm project dir to create `dist/` + the 3 copied files before starting `jsBrowserDevelopmentRun`:

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/build/js/packages/Autogenesis-kvisionApp
node ../../node_modules/webpack/bin/webpack.js --config webpack.config.js --mode development
# Exits when done (~3s with warm cache). Now dist/ exists with the 3 copied files.
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./gradlew :kvisionApp:jsBrowserDevelopmentRun
```

The pre-compile writes the bundle AND populates `dist/`, so when webpack-dev-server's first in-process compile fires its afterEmit hook, `dist/` already exists and the copy succeeds. webpack-dev-middleware marks the bundle ready and the dev server serves normally.

## Verification (after fix or workaround)

The same 5-asset curl probe should serve cleanly:

```bash
for p in / /kvisionApp.js /sw.js /night-mode.css /vapid_public.json /manifest.webmanifest; do
  curl -sS --max-time 5 -o /dev/null -w "$p: HTTP %{http_code} size=%{size_download}\n" "http://localhost:8080$p"
done
```

Expected output after fix:
```
/: HTTP 200 size=713
/kvisionApp.js: HTTP 200 size=25861750
/sw.js: HTTP 200 size=3295
/night-mode.css: HTTP 200 size=150673
/vapid_public.json: HTTP 200 size=114
/manifest.webmanifest: HTTP 200 size=341
```

If the bundle size isn't ~25.8MB, webpack didn't actually emit — re-check the gradle daemon log for the ENOENT.

## What this changes in the broader skill guidance

Prior versions of this skill recommended static-server + manual `:server:run` / `:server-extend:run` as the PRIMARY dev path because webpack-dev-server "wedges." With the pwa-push.js fix, that recommendation is reversed for the typical case: webpack-dev-server is the canonical dev path (HMR, source maps, fast iteration). Static-server is the FALLBACK when the operator needs the page running immediately and doesn't want to debug.

This is a learning worth carrying forward: "treat X as systemically broken" claims should be re-investigated when the symptom recurs. The 2026-07-18 session could have killed-and-retried again, but the operator pushed back ("get in here and take accountability for your bullshit") — that prompt is what triggered the actual root-cause investigation.

## Related

- `references/process-kill.md` — the canonical kill sequence when webpack-dev-server is hung (used as the precondition for the diagnosis above)
- `references/post-recovery-port-mirror.md` — the static-server fallback recipe for when webpack can't be made to work in the current session
- `kvisionApp/webpack.config.d/pwa-push.js:74` — the file containing the fix
- The 2026-07-18 operator feedback that motivated the investigation: "Get in here and get ready to take accountability for your bullshit and fix your work." The "your work" was specifically the v1.21-1.23 conclusion that webpack-dev-server is broken — that conclusion was wrong, and the work that needed fixing was the prior session's diagnostic laziness.
