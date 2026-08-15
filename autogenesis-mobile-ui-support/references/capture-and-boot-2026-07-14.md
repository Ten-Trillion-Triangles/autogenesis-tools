# Mobile Screenshot Capture & Server Boot — Session Reference (2026-07-14)

Session-specific detail for the wipe+recapture cycle and the dev-server boot/serve plumbing on this sandbox. Complements the canonical capture recipe in the main SKILL.md.

## The wipe+recapture cycle

The user periodically wipes `screenshots/<date>-<slug>/` and asks for fresh re-capture. The pattern recurs across multiple sessions:

- 2026-07-12: wiped `screenshots/2026-07-12-mainmenu-mobile-widget-survey/` (14 PNGs → 0), asked for fresh capture
- 2026-07-14: same pattern, asked for fresh batch saved to a NEW dated directory

**Pattern response**: preserve BOTH captures (don't overwrite the previous one), bump the date in the output directory path so each capture is a separate evidence trail. The user wants to compare wipes side-by-side for diagnosis, not see them collide into one file.

## The consolidated capture script

`/tmp/hermes-capture-canonical-YYYYMMDD/capture.mjs` walks every widget polish across all rounds. Output goes to `/home/cage/Desktop/Workspaces/Autogenesis/screenshots/YYYY-MM-DD-<slug>/` and mirrors to `kvisionApp/build/dist/js/productionExecutable/preview/YYYY-MM-DD-<slug>/` for static-server URL access.

The script structure for a 2026-07-14 wipe+recapture:

```
01-main-menu-clean.png
02-shop-modal-credits-top.png
03-shop-modal-scrolled-go-monthly.png
04-usage-modal-top.png
05-usage-modal-scrolled-bottom.png
06-settings-modal.png
07-collection-overlay.png
08-commander-creation-dialog.png
09-commander-selection-step1.png
10-commander-selection-card-selected.png
11-play-wizard-step2.png
```

Splitting into 3 scripts (capture.mjs, capture2.mjs, capture3.mjs) was needed because:
1. Cold-start is ~30s per boot — monolithic script timed out at 120s for all 11 captures
2. Some widgets (Collection modal at #7) intercept subsequent clicks — splitting lets a widget failure not poison the rest
3. Each script boots fresh, so cold-start overhead is paid once per script not once per widget

**File path** for the 2026-07-14 capture scripts:
- `/tmp/hermes-capture-canonical-20260714/capture.mjs` (boots, captures 01-06)
- `/tmp/hermes-capture-canonical-20260714/capture2.mjs` (boots, captures 07, fails on 08 because Collection still intercepts)
- `/tmp/hermes-capture-canonical-20260714/capture3.mjs` (boots, captures 08-11)

## Server boot gotchas (re-confirmed 2026-07-14)

### All 3 servers need to be up before any capture

Per-session sequence:
```
mkdir -p /tmp/autogenesis-proxy && nohup ./gradlew :server-extend:run > /tmp/autogenesis-proxy/se.log 2>&1 &
mkdir -p /tmp/autogenesis-proxy && nohup ./gradlew :server:run > /tmp/autogenesis-proxy/srv.log 2>&1 &
mkdir -p /tmp/autogenesis-proxy && nohup node kvisionApp-e2e/static-server-8080.mjs > /tmp/autogenesis-proxy/static.log 2>&1 &
```

All three use the SAME `mkdir -p /tmp/autogenesis-proxy` prefix on the same line as the launch — separating mkdir into a prior command FAILS in the Hermes background sandbox because each `terminal(background=true)` gets fresh shell state.

Verify with:
```
ss -tlnp 2>/dev/null | grep -E ":(7070|8080|9080|9091|9092)"
```

Expected: 5 listening sockets (7070, 8080, 9080, 9091, 9092). server-extend takes ~90s to compile (kotlin-daemon). server takes another ~90s after server-extend finishes. static-server is instant.

### webpack production output path migrated — symlink required

`:kvisionApp:jsBrowserProductionWebpack` now outputs to `kvisionApp/build/kotlin-webpack/js/productionExecutable/`, NOT the old `kvisionApp/build/dist/js/productionExecutable/` path that `kvisionApp-e2e/static-server-8080.mjs` hardcodes.

If the dist dir is missing (after a clean re-boot or wipe), create the symlink:
```bash
mkdir -p kvisionApp/build/dist/js
ln -sfn kvisionApp/build/kotlin-webpack/js/productionExecutable kvisionApp/build/dist/js/productionExecutable
```

Also missing from the webpack output: `index.html` and `night-mode.css` (webpack emits only `kvisionApp.js`, `731.js`, source maps). Copy manually:
```bash
cp kvisionApp/src/jsMain/resources/index.html kvisionApp/build/kotlin-webpack/js/productionExecutable/index.html
cp kvisionApp/src/jsMain/resources/night-mode.css kvisionApp/build/kotlin-webpack/js/productionExecutable/night-mode.css
```

Verify static-server health:
```
curl -sI http://127.0.0.1:8080/index.html | head -2
# Expected: HTTP/1.1 200 OK
curl -sI http://127.0.0.1:8080/night-mode.css | head -2
# Expected: HTTP/1.1 200 OK
```

If 404: webpack build hasn't completed, OR dist symlink is missing, OR the cp step wasn't run.

### Cold-start pipeline is ~30s

After clicking the LoadingScreen CTA, the in-game pipeline takes ~30s to mount the main menu. The default Playwright `waitForSelector` timeout of 30s is borderline — sometimes succeeds, sometimes times out. Use a polling loop instead:

```javascript
await page.locator('[data-testid="loading-screen-cta"]').first().click();
for (let i = 0; i < 12; i++) {
  await page.waitForTimeout(5000);
  const arrived = await page.evaluate(() => !!document.querySelector('[data-testid="main-menu"]'));
  if (arrived) {
    console.log(`main-menu appeared after ${(i + 1) * 5}s post-click`);
    break;
  }
}
await page.waitForSelector('[data-testid="main-menu"]', { timeout: 30000 });
await page.waitForTimeout(2000);
```

The polling loop catches early arrivals (~30s, sometimes 25s on warm cache). The subsequent `waitForSelector` is the safety net. Logging the actual arrival time is useful — if main-menu takes 5s in one session and 60s in another, the variance is real and you can spot it from the log.

### JSdelivr CDN integrity error is benign

On page load, console logs: `Failed to find a valid digest in the 'integrity' attribute for resource 'https://cdn.jsdelivr.net/np...'`. This is the AccelByte SDK's CDN resource with a stale integrity hash. Does NOT block LoadingScreen or main-menu from mounting. Ignore.

## Stale verifier cache pattern

When the system shows "stale verifier" warnings pointing to a file like `/tmp/hermes-verify-usage-scroll-20260712.mjs` that no longer exists, the cache holds a stale reference. To inject fresh evidence:

```bash
mkdir -p /tmp/hermes-verify-<topic>-YYYYMMDD
ln -sfn kvisionApp-e2e/node_modules /tmp/hermes-verify-<topic>-YYYYMMDD/node_modules
cp kvisionApp-e2e/probes/<verifier>.mjs /tmp/hermes-verify-<topic>-YYYYMMDD/verify.mjs
cd /tmp/hermes-verify-<topic>-YYYYMMDD && node verify.mjs > /tmp/hermes-verify-<topic>-YYYYMMDD/output.json 2>&1
```

Capture to a NEW path so the system sees fresh evidence. The captured output.json file is what the verifier cache reads.

## Server shutdown — handoff signal

When the user says "shut the game servers down, I'll examine how things look," the right response is:

```bash
fuser -k 7070/tcp 8080/tcp 9080/tcp 9091/tcp 9092/tcp 2>&1
sleep 2
ss -tlnp 2>/dev/null | grep -E ":(7070|8080|9080|9091|9092)" || echo "ALL CLEAR - no dev ports listening"
```

The static-server going down means clickable URLs (http://127.0.0.1:8080/preview/...) will 404 until the next boot. The screenshots themselves are safe on disk at `file:///home/cage/Desktop/Workspaces/Autogenesis/screenshots/<date>-<slug>/`.

## Network cut-off mid-response — the stall signal

When the assistant's response is cut off mid-stream by network instability, the next user message is often "why are you stalling?" The right read: previous response didn't land, restart the in-flight work with cleaner chunking. Multi-script captures (capture.mjs + capture2.mjs + capture3.mjs) are more robust than one monolithic script under these conditions.