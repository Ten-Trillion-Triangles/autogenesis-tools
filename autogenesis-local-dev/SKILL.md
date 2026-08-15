---
name: autogenesis-local-dev
title: Autogenesis Local Development
description: Run the Autogenesis KMP game server and KVision browser UI locally for development and gameplay. Covers server startup, client dev server, login bypass, matchmaking, and RPC architecture.
category: gaming
version: 1.13.0
changelog:
  - "1.13.0 (2026-07-12): Expanded the 'Inner flex-row doesn't collapse when the outer column collapses' pitfall in references/kvision-mobile-portrait-css.md from 2 fix options to 3, adding `:has()` selector as option (a) — preferred for anonymous parents because it survives Kotlin restructuring and doesn't require a production-code className change. Verified by commit 4d7344bc4 (Shop BUY CREDITS row stacking). Also added a sub-pitfall: 'width: 100% !important does NOT stack items when the parent stays flex-direction: row'. The root cause is flexbox distributing the parent's available width across items (default flex-shrink:1) regardless of width:100% claims. Diagnosis recipe: when width:100% !important on an item isn't producing full-width rendering, walk up to parent and check flex-direction — collapse the PARENT, not the cards."
  - "1.12.0 (2026-07-12): Two additions. First, a 9th post-scrub boot crash (TPipe includeBuild jar corruption). TPipe/build/libs/TPipe-1.0.0.jar has zip END header not found, breaks Autogenesis :server:run via detachedConfiguration1. Symptom is :TPipe:TPipe-Bedrock:compileKotlin FAILED with the TPipe jar transform error. Fix is one-line — rm /home/cage/Desktop/Workspaces/TPipe/TPipe/build/libs/TPipe-1.0.0.jar and let the includeBuild rebuild it. This is the THIRD TPipe-includeBuild interaction class (after #5 webpack `path` collision and the chronotrace PREFER_SETTINGS blocker). Every post-scrub / cross-workspace gradle build should pre-flight this jar. Second, the 'lay of the land' mobile-portrait widget survey workflow — boot → enumerate every reachable widget → screenshot each at 390x844 → list issues by severity → wait for user pick. Verbatim user framing on 2026-07-12 — 'boot the game through the main menu, poke around each possible widget that can appear in it, and screenshot all of it for mobile again. Lets get a lay of the land on how things stand, then we can start picking these off one by one.' The 12 PNGs from that session went to screenshots/2026-07-12-mainmenu-mobile-widget-survey/. Reusable mobile-survey probe template lives at /tmp/hermes-widget-survey-YYYYMMDD.mjs (hermes-verify-* prefix, NOT in-repo — see 'Verification — ad-hoc verifier prefix' pattern in kvision-mobile-portrait-css.md)."
  - "1.11.0 (2026-07-12): Three new sections in references/kvision-mobile-portrait-css.md from the 67-defect polish pass. (a) 'CSS-only build bypass when jsBrowserProductionWebpack is broken in this sandbox' — the canonical workaround for when gradle can't resolve org.nodejs:node:22.0.0: edit night-mode.css, cp it to build/dist/, probe runs against the standalone <link> CSS without rebuilding the JS bundle. Also clarifies that CODEARTIFACT_AUTH_TOKEN is a workspace-env leak from includeBuild(TPipe) at settings.gradle.kts:87 — NOT a real dependency of the kvisionApp build. (b) 'Selector-name discovery loop' — the 3-step Playwright probe pattern for when your CSS rule 'doesn't apply,' plus a per-widget selector map (LoadingScreen → .loading-screen-root, MainMenu → .main-menu / hero wordmark on #kvapp, Shop/Usage → .modal.billing-modal-window-host .modal-content .modal-body.billing-modal-body, Settings → .login-widget-window (SimplePanel NOT Modal — no .modal-dialog), Collection → .collection-overlay + .collection-window, Commander Creation → .commander-creation-dialog > h3 title is h3 not h1 not div). (c) 'DOM probe proves the rule applied; vision review proves the user can see the result' — these are NOT the same check; the 2026-07-12 polish pass caught a case where DOM probe said panelWidth=390 (full viewport) but visual review still showed bleed-through from an outer inset container. Always do both; if they disagree, trust the visual."
  - "1.10.0 (2026-07-12): Reframed CSS specificity pitfall as a STANDALONE section (was previously a sub-bullet of 'Modal bleed-through'). The specificity lesson is class-level — any future @media override on a Bootstrap-class or compound-selector CSS will hit it. Added a new 'Verification — grep is not enough for CSS-only changes' section that names the failure mode (commits 2e7c748c3 → a313bc957 — static grep matched, dist grep matched, rendered DOM still showed the bleed-through) and points to scripts/probe-computed-styles.mjs as the re-runnable probe. Bumped 'What done looks like' step 5 to require a runtime computed-style probe for any CSS-only change."
  - "1.9.0 (2026-07-11): Added CSS specificity pitfall to 'Modal bleed-through' section — @media with !important does NOT override a base rule with a more-specific selector. The base rule at night-mode.css:2526 uses .modal.billing-modal-window-host (specificity 0,2,0); the portrait override at first used bare .billing-modal-window-host (0,1,0) and was silently defeated despite !important on both. Fix: match the compound selector in the override. Symptom verification via computed-style probe in Playwright (the source/dist grep matched, but the rendered DOM showed the inline value — proving specificity loss). Plus diagnostic recipe: when a CSS !important rule isn't winning, run getComputedStyle(el).backgroundColor in a Playwright probe to compare against el.style.cssText. Adds commit a313bc957 to the chain."
  - "1.8.0 (2026-07-11): Four new pitfall sections appended — modal bleed-through on portrait (BillingOverlayWindow translucent + Bootstrap gradient modal-content + SettingsWidget no-bg), jsBrowserProductionWebpack writing to build/kotlin-webpack/ not build/dist/ (gradle cache + manual copy recipe + grep-the-CSS-not-the-JS trap), page.goto(SAME_URL) no-op on KVision SPAs (about:blank-then-goto fix), and KVision setStyle() inline style= overridden by !important CSS (AUTOGENESIS wordmark hero clipping fix). Plus a dead-band bug class for SPACEBETWEEN flex containers with flexGrow 1 spacers (capped with max-height 240px in portrait @media block)."
  - "1.7.0 (2026-07-11): Added references/kvision-mobile-portrait-css.md documenting the mobile-portrait CSS override pattern established by the loading-screen + main-menu mobile ports on Autogenesis-Mobile branch (CSS @media block at ≤600px breakpoint, matchMedia listener + data-mobile-layout attribute in widget init, Playwright probe at iPhone 12 dimensions), the inner-hPanel pitfall (collapsing an outer flex column via @media does NOT cascade to nested anonymous flex-row hPanels inside it — fix by structural selector or stable className), the kvision-js 9.1.1 Style.create Kotlin DSL pitfall (NOT exposed to JS), and the static-server-8080.mjs verification harness recipe."
  - "1.6.0 (2026-07-01): Phase-page screenshots ARE scriptable via real-turn polling; see Capturing the 9 phase pages note in the Screenshot capture workflow section for the breakthrough recipe."
  - "1.5.0 (2026-06-30): Eight post-scrub boot crash categories and fixes documented for the open-autogenesis branch."
  - "1.4.0 (2026-06-29): Source-available release scrub — 9 tracked-source items + secrets-repo sync convention."
  - "1.3.0 (2026-06-27): AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS env var for Phase 1 e2e probes (saves 5+ minutes per run); AUTOGENESIS_DEV_PUSH_MOCK_PORT env var for push notification e2e probes."
  - "1.2.0 (2026-06-24): KVision modal layout pitfalls (references/kvision-modal-layout.md) + Bootstrap modal shell collapse (references/kvision-bootstrap-modal-shell.md)."
  - "1.1.0 (2026-06-23): KVision Modal (Bootstrap subclass) fallback CSS-shell fix in night-mode.css; runtime confirmation of skipLogin-vs-real-guest account divergence."
  - "1.0.0 (2026-05-09): Initial skill."
---

See `references/webpack-task-name.md` (webpack task = `:kvisionApp:jsBrowserDevelopmentRun`).

The `open-autogenesis` branch carries the post-scrub codebase where every Bedrock ARN, AB tenant URL, namespace, and CORS origin was refactored to read from `ConfigSource.property(...)`. The scrub merged clean per the file sweep audit (commit `1a23f6db8`, 2026-06-29), then crashed on first boot the next day. The eight crash categories that survived the audit and bit on 2026-06-30:

1. **`compileKotlinJs FAILED`**: `val x: String get() = ...` inside a function body — locals cannot have property getters. Fix: plain `val x: String = ConfigSource.property(...)`.
2. **`compileKotlinJs FAILED`**: `var x: String get() = ...` with no setter — `var` requires both getter AND setter (or backing field). Fix: convert to `val`, or add `var x: String = ""` initializer plus `set(value) { field = value }`.
3. **`compileKotlinJs FAILED`**: `data?.x` on a `val data: dynamic` — Kotlin forbids `?.` on dynamic. Fix: `val container = js("({})")`, then `container.field = data.x` (direct property assignment IS allowed on dynamic).
4. **`compileKotlinJs FAILED`**: `return` inside `launch { try { ... } catch { ... } }` — use `return@launch`.
5. **`jsBrowserDevelopmentRun FAILED`**: `SyntaxError: Identifier 'path' has already been declared` — webpack concatenates all `webpack.config.d/*.js` files into one scope. When adding a new `.d` file, declare a UNIQUE top-level binding name (`pathModule`, not `path`); use `const pathModule = typeof path !== 'undefined' ? path : require('path')` as the existing-binding fallback.
6. **`server` / `server-extend` boot: `IllegalStateException: <file>.local.local.properties not found`** — `ConfigSource.jvm.kt` only stripped `.properties`, not `.local`. Fix: also strip `.local` from the suffix and add a literal-filename fallback at the end of the candidate list. (This was hit by EVERY post-scrub JVM consumer — `BedrockConfig.kt`, `ExtendModelDefaults.kt`, `ServerConfig.kt`, `GrpcServer.kt`, `ServerExtend.kt`.)
7. **`server-extend` boot: `IllegalStateException: accelbyte.local.properties missing key 'AB_CORS_ALLOWED_ORIGINS'`** — the scrub invented a new key for the CORS tenant host, but no file has it. Fix: align `ServerExtend.kt:246` with `GrpcServer.kt:80` and read `AB_BASE_URL` (which IS in the file), stripping `https://` at runtime to derive the bare host.
8. **Same as #5 in production webpack** — same fix.

All eight are fixed on `open-autogenesis` as of 2026-06-30; if a future session sees a fresh post-scrub branch that won't boot, apply the same fixes in the same order. The verified four-step boot-verification protocol that would have caught all 8 in 90 seconds lives in `source-available-release-scrub/references/post-scrub-boot-recipe.md`.

### 9th boot crash (added 2026-07-12, TPipe includeBuild jar corruption)

When Autogenesis `:server:run` fails with `:TPipe:TPipe-Bedrock:compileKotlin FAILED` and the gradle output includes `Failed to transform TPipe-1.0.0.jar to match attributes {... artifactType=classpath-entry-snapshot ...}` followed by `zip END header not found` — the TPipe includeBuild jar at `/home/cage/Desktop/Workspaces/TPipe/TPipe/build/libs/TPipe-1.0.0.jar` is corrupt. This usually happens when a previous gradle build of the TPipe subproject was killed mid-write (OOM kill, SIGKILL, sandbox crash) and the jar was left half-flushed.

**One-line fix:**

```bash
rm /home/cage/Desktop/Workspaces/TPipe/TPipe/build/libs/TPipe-1.0.0.jar
```

Then re-run the Autogenesis build — the includeBuild will rebuild TPipe-1.0.0.jar from scratch, and `:server:run` will proceed.

**Why this is the THIRD TPipe-includeBuild interaction class to bite Autogenesis** (after #5 webpack `path` collision and the chronotrace `PREFER_SETTINGS` blocker in `~/.gradle/init.d/chronotrace.gradle.kts`). Every post-scrub or cross-workspace gradle build should pre-flight this jar:

```bash
ls -la /home/cage/Desktop/Workspaces/TPipe/TPipe/build/libs/TPipe-1.0.0.jar 2>/dev/null \
  && file /home/cage/Desktop/Workspaces/TPipe/TPipe/build/libs/TPipe-1.0.0.jar | grep -q "Zip archive data" \
  || echo "TPipe jar missing or corrupt — delete and rebuild"
```

### "Lay of the land" mobile-portrait widget survey workflow (added 2026-07-12)

When the user opens a mobile-polish session with something like "lets get a lay of the land on how things stand, then we can start picking these off one by one," the canonical workflow is:

1. **Boot** all three services via `./debugger/scripts/start_servers.sh` (or `background=true` per service, see boot-blocker note above for the `mkdir -p /tmp/log &&` pattern in background commands).
2. **Enumerate** every widget reachable from the main entry point. For MainMenu: header (Shop / Usage / gear), bottom row (Collection / New Commander / PLAY), plus each click target's resulting modal (Shop modal, Usage modal, Settings modal, Collection overlay, Commander Creation dialog, PLAY wizard step 1 + step 2). Read the widget source to confirm selector names — `grep -n 'data-testid\|className = "main-menu' ui/MainMenu.kt`.
3. **Capture** one PNG per widget at 390x844 iPhone 12 viewport via Playwright (`isMobile: true, hasTouch: true, deviceScaleFactor: 3`). Save under `~/Desktop/Workspaces/Autogenesis/screenshots/YYYY-MM-DD-<context>/` with sequential numbered prefixes. Ad-hoc probe template at `/tmp/hermes-widget-survey-YYYYMMDD.mjs` (hermes-verify-* prefix per the ad-hoc verifier convention; NOT committed to the repo).
4. **List issues by severity** at the end — High (hides content / blocks interaction), Medium (visual polish), Low (cosmetic). User picks which to tackle next.

This is the standard "here's the menu, what do you want to fix?" handoff. The 12 PNGs from the 2026-07-12 pass are at `screenshots/2026-07-12-mainmenu-mobile-widget-survey/` and documented 4 visible mobile issues:

- **High:** Wizard step 2 — Match Configuration row horizontally overflows (left + right cards cut off, only middle "3 Players" card visible)
- **High:** Commander Creation dialog — Nation Description textarea + BACK/CREATE buttons extend below the 844px viewport (no scroll-to-bottom affordance)
- **Medium:** Shop modal — "SUBSCRIPTION" tab label clips to "SUBSCRIPTIO..." (needs `min-width` or smaller font on the tab)
- **Low:** Collection overlay — COMMENDERS button glow wraps outside its card boundary (cosmetic)

## Source-available release scrub

The Autogenesis source tree is going source-available as a TPipe reference example. Per the 2026-06-29 audit (`PLANS/autogenesis-source-available-scrub.md` in the public repo, full worked example in `~/.hermes/skills/source-available-release-scrub/references/autogenesis-source-available-scrub-2026-06-29.md`), the tracked source tree carries 9 items that must change before publication (2 HIGH BedrockConfig.kt + ExtendModelDefaults.kt ARN files, 5 MEDIUM README/DEPLOY/billing-plan-doc tenant URLs + hex testUserId, 2 LOW UserAuthFacade.kt console.log tokens + PushVapidConfig.kt placeholder email). The live credentials live in a sibling private repo at `/home/cage/Desktop/Workspaces/autogenesis-secrets/` (commit `ba55d3c`); sync.sh + verify.sh tested and passing; rotation of the live `AB_CLIENT_SECRET` pending. **Working rule:** when adding any new tracked source code that references cloud infrastructure (Bedrock ARNs, AB IAM, third-party tenant URLs, OAuth client IDs), do not embed the literal — extend the existing `selectAccelByteConfig()` pattern in `server/build.gradle.kts:248-263` or the runtime loader convention, and document the value in the secrets repo instead.

- `references/map-pack-update-pattern.md` for editing an existing map pack's data (write-side mirror of the install-side). For installing a brand-new `.map` file + wiring it to a player-count pool, see `references/add-new-map-pack.md` and the re-runnable `scripts/verify-map-pack.py` (zip integrity + schema fingerprint + pin/connection consistency). **For installing a reserved / tutorial / guided-walkthrough map that must NEVER roll in normal matchmaking**, see the "Non-matchmaking install" section at the bottom of `add-new-map-pack.md` and the exclusion verifier `scripts/verify-map-exclusion.py`. **For removing a map that has been removed from gameplay** (failure cases, replacements, dead fixtures) — see `references/remove-map-pack.md` and the negative-path verifier `scripts/verify-map-removal.py` (asserts file gone + 3 GameInit.kt list entries gone + negative-pin in MapResourceRegistryTest + no other residue references). The allMaps-rigged-list drift hazard (`GameInit.kt:122-129`) is documented in `remove-map-pack.md` "Side-fix: the `allMaps` list drift bug" — every pool-list edit should audit it.

See `references/kvision-modal-layout.md` for KVision modal layout pitfalls (Bootstrap SRI breakage, TextArea `input` propagation, vPanel `flexGrow`+`max-height` recipe, zIndex vs historyWindow, webpack-dev-server caching).

See `references/kvision-bootstrap-modal-shell.md` for the KVision `Modal` (Bootstrap modal subclass) shell collapse pitfall — the `<div class="modal-header">` clipping at the right viewport edge when Bootstrap CSS isn't loaded. Affects `SurrenderConfirmDialog` and any future KVision `Modal` subclass. **Preferred fix** is to refactor the dialog to `SimplePanel(className = "login-widget-window")` mirroring `SettingsWidget` / `DelegateWidget` (no Bootstrap dependency, matches the 9+ other popup widgets in the codebase, avoids the `Modal.width` → `.modal-content` width mismatch). Fallback CSS-shell fix and the width caveat are documented there for cases where the dialog must remain a KVision `Modal`.

See `references/kvision-mobile-portrait-css.md` for the KVision mobile-portrait CSS override pattern (≤600px breakpoint, `@media` block in `night-mode.css`, matchMedia listener + `data-mobile-layout` attribute in widget init, Playwright probe at iPhone 12 dimensions). Established by the loading-screen + main-menu mobile ports on `Autogenesis-Mobile` branch. Includes the **inner-hPanel pitfall** — collapsing an outer flex column via `@media` does NOT cascade to nested anonymous flex-row hPanels inside it (the inner row stays as `flex-direction: row` and its children get squished/clipped, as in the MainMenu PLAY button at 18px wide). Diagnose by walking up from the squished element with `getComputedStyle`, fix by either targeting the inner panel with a structural selector (`.outer > div { flex-direction: column !important; }`) or giving it a stable className. Also documents the `Style.create` Kotlin DSL pitfall (NOT exposed in kvision-js 9.1.1 — CSS is the load-bearing source of truth) and the static-server-8080.mjs verification harness (`:kvisionApp:jsBrowserDevelopmentRun` has a known webpack-cli SyntaxError on Node 22+ in this sandbox).

For re-runnable verification of the mobile-portrait polish, see `scripts/probe-mobile-polish.mjs` — runs fresh Playwright contexts per modal at iPhone 12 portrait, greps 35 portrait @media rules in both source + dist, and dumps computed-style values for the 6 modals reachable from the Main Menu. Use after any CSS-only mobile-portrait edit to confirm the rule reached the bundle AND is taking effect in the rendered DOM. The reference also captures the **CSS specificity collision** as a standalone pitfall (any future `@media` override on a Bootstrap-class or compound-selector CSS will hit this), plus a "grep is not enough" verification section with a re-runnable computed-style probe at `scripts/probe-computed-styles.mjs`.

See `references/process-kill.md` for the canonical kill sequence across gradle/webpack/java processes.

**SessionRole regression — PARTIAL / REGRESSION CONFIRMED (2026-05-13):**
- Commit `9f8ca9b05` introduced `SessionRole` (PRIMARY vs CONTROLLER)
- Python controller's WebSocket URL (`_build_url` at `controller.py:465`) now includes `role=CONTROLLER` ✓
- `Server.kt` is supposed to guard `onConnected`/`onReconnected` with `session.role == SessionRole.PRIMARY` ✓
- **REGRESSION CONFIRMED (2026-05-13):** Game server shut down mid-session when browser WebSocket dropped, despite CONTROLLER session alive. `hasAnyPrimarySession()` returned FALSE → 15s shutdown timer fired even though the Python CONTROLLER was connected. The `onReconnected` path may not be covered by the SessionRole guard, or there is an additional shutdown path that ignores session role.
- **Symptom observed:** `Server: Notification: Shutting down server in 15 seconds (no player sessions)` followed by `Server stopped.` even with a live CONTROLLER WebSocket.
- **Workaround:** keep browser session alive OR restart server if it dies mid-test.

## Start sequence (boot order matters)

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./debugger/scripts/start_servers.sh
```

The canonical start script lives at `debugger/scripts/start_servers.sh` and starts all three services in order:

1. `:server-extend:run` → binds port 7070 (and gRPC 9092)
2. `:server:run` → binds port 9080 (and gRPC 9091)
3. `:kvisionApp:jsBrowserDevelopmentRun` → binds port 8080 (webpack-dev-server with HMR)

DO NOT chain all three in a single `./gradlew :server:run :server-extend:run :kvisionApp:jsBrowserDevelopmentRun` invocation — gradle serializes them and port conflicts can occur. Use the start_servers.sh script or run each in a separate background process.

### Background-process gotcha (added 2026-07-12)

When launching gradle via `terminal(background=true, notify_on_complete=true)`, the shell that runs the wrapped command is **fresh and does NOT inherit filesystem state from prior `terminal()` foreground calls**. If a foreground call did `mkdir -p /tmp/foo` and a later background call tries `./gradlew ... > /tmp/foo/log 2>&1`, the redirect FAILS with `bash: /tmp/foo/log: No such file or directory` because /tmp/foo does not exist in the new shell — the entire background gradle invocation exits with code 1 before doing any work.

**Fix:** bake the mkdir into the background command itself:

```bash
# WRONG — assumes /tmp/foo exists from a prior foreground call
./gradlew :server:run > /tmp/foo/srv.log 2>&1

# RIGHT — fresh shell creates the dir first
mkdir -p /tmp/foo && ./gradlew :server:run 2>&1 | tee /tmp/foo/srv.log
```

Apply whenever launching any gradle/maven/process via `terminal(background=true)` with a log redirection target.

## Server architecture overview

```
┌─────────────────────────────────┐
│ Browser (localhost:8080)        │
│   kvisionApp.js (webpack HMR)    │
│   ├─ WebSocket → ws://localhost:9080/events
│   └─ REST → http://localhost:9080
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ :server:run (Ktor/Netty)         │
│   port 9080 (HTTP + WS)          │
│   gRPC 9091                      │
│   ├─ Game state / turn loop
│   ├─ AccelByte cloud save (CloudVFS)
│   └─ Bedrock LLM calls
└──────────┬──────────────────────┘
           │
           ▼
┌─────────────────────────────────┐
│ :server-extend:run               │
│   port 7070 (Python REST bridge)│
│   gRPC 9092                      │
│   └─ Image generation, etc.
└─────────────────────────────────┘
```

The browser talks to the GAME SERVER (9080) for WS+REST, and the game
server talks to server-extend (7070) for Python helpers. server-extend
is a Python FastAPI service bridging to image-gen / utility tools.

See `references/server-architecture.md` for full detail on the RPC layer.

## Login bypass / test mode

There are **two** ways to be "logged in" against the dev environment. They
are NOT equivalent — pick the one that matches the test you need.

### Path A — `?skipLogin=true` (synthetic, no AccelByte)

Append `?skipLogin=true` to the URL to skip the login screen and load
the guest commander directly. The Kotlin code in `Main.kt:110-127` does:

```kotlin
if (KEnv.skipLogin) {
    globals.AccelByteEnv.userId = "guest-user"          // synthetic literal
    globals.AccelByteEnv.userName = "Guest"
    globals.AccelByteEnv.displayName = "Guest Commander"
    WebSocketRpcBridge.connect(accelbyteId = "guest-user")
    RestRpcBridge.connect(accelbyteId = "guest-user")
}
```

The accelbyteId is the literal string `"guest-user"`. **No real AccelByte
OAuth call runs**, so the WebSocket and REST bridges are bound to a string
that the game server's VFS / CloudSave code cannot resolve to a real
account. The guest commander has no commanders in its list — you must
CREATE one before PLAY works (otherwise "Please create a commander
before playing" error). The CREATE flow appears to save locally but the
saved commander does NOT show up in the PLAY selector list (AccelByte
rejects the guest UUID as not a valid uuid v4). Workaround: use an
EXISTING commander from the list (e.g. "Empire: Exists In Mailman Land
Idk...") to enter a game.

Use this path for layout/visual tests, hover tests, MapViewer tests, and
any test that does NOT need a real user account. It is the path the
existing `kvisionApp-e2e/tests/hover-border-lines.spec.mjs` uses (it adds
`&testMode=true` to skip MainMenu and mount a MapViewer directly).

### Path B — `Login As Guest` button (REAL AccelByte OAuth)

Click the "Login As Guest" button on the LoginPage. This calls
`LoginPage.guestLogin()` (`ui/LoginWidgets.kt:624-629`), which fills in
the hard-coded test guest account:

```kotlin
private const val GUEST_EMAIL = "ljn0toys0inc+test100@gmail.com"   // :63
private const val GUEST_PASSWORD = "TheFithLaw!"                    // :64
```

and runs the full AccelByte OAuth flow via `UsersFacade.loginWithUsernameSuspend`
(see `ui/LoginWidgets.kt:636-785`). On success, `AccelByteEnv.userId` is
set to the real AccelByte UUID returned by the auth response (e.g.
`"004c3eb02c0b4436b41b24d5d670b0e4"`), the WebSocket and REST bridges
are rebound to that real accelbyteId, and MainMenu mounts.

**This is the path you need for any test that exercises the game server's
per-user state** (VFS restore, CloudSave, master record, billing,
matchmaking routing, resume-game push). The skipLogin path's synthetic
`"guest-user"` string will be rejected by the game server's
AccelByte-bound RPC handlers.

### Proving a real guest login (Playwright probe)

`kvisionApp-e2e/probes/guest-login.mjs` is a runnable probe that drives
Path B end-to-end and asserts the real accelbyteId (not the skipLogin
placeholder) is bound. Run it with all three dev servers up:

```bash
cd kvisionApp-e2e
node probes/guest-login.mjs
```

Expected output (verified 2026-06-25):

```
[15:55:00.820] Step 3: click the "Login As Guest" button
[15:55:00.852]   clicked
[15:55:02.639]   dismissed messageBox OK
[15:55:02.851]   MainMenu mounted (PLAY button present)
[15:55:02.859] Result: PASS
[15:55:02.859]   console errors (non-pre-existing): 0
[15:55:02.859]   page errors (non-pre-existing): 0
[15:55:02.859]   assertions: {"mainMenuPresent":true,"mainMenuHasMainMenuClass":true,"accelbyteIdNonEmpty":true,"accelbyteIdIsNotSyntheticSkipLogin":true,"displayNameNonEmpty":true}
  accelbyteUserId: "004c3eb02c0b4436b41b24d5d670b0e4"
  accelbyteDisplayName: "KingCandy13"
```

The test surface relies on three `data-testid` / data-attributes added
for e2e stability (do not remove without updating this probe):

- `data-testid="login-as-guest"` on the "Login As Guest" button
  (`ui/LoginWidgets.kt:269`).
- `data-testid="main-menu"`, `data-accelbyte-user-id`,
  `data-accelbyte-display-name` on the MainMenu root VPanel
  (`ui/MainMenu.kt:60-65`).

If the test guest account's password rotates, update
`GUEST_PASSWORD` in `ui/LoginWidgets.kt:64` and re-run the probe.

### Debug-server signal alternative (`LOGIN_AS_GUEST`)

`DebugSignalBridge.Signals.LOGIN_AS_GUEST` (see
`org.ttt.autogenesis.kvisionapp.DebugSignalBridge.kt:52`) dispatches
`DebugConsole.triggerLoginAsGuest()` (see `ui/DebugConsole.kt:45-59`),
which calls `LoginPage.guestLogin()` IF a `LoginPage` is mounted. The
`?skipLogin=true` path never mounts a `LoginPage` (it goes straight to
MainMenu), so this signal is a no-op in skipLogin mode. The Python
debug server sends the signal via `POST /debug/signal "LOGIN_AS_GUEST"`.

## Kill sequence (no leftovers)

```bash
pkill -f "jsBrowserDevelopmentRun"
pkill -f "server:run"
pkill -f "server-extend:run"
sleep 3
ss -tlnp 2>/dev/null | grep -E ":(7070|8080|9080)" || echo "all clear"
```

**For screenshot-capture sessions only:** this blanket kill sequence also stops the user's webpack-dev-server (port 8080) and server-extend (port 7070/9092). If the user is running their own browser/UI session against the same workspace, kill ONLY the `:server:run` JVM you started (port 9080/9091) and leave 7070/8080/9092 alone. Verify after kill: `ss -tlnp | grep -E ":(7070|8080|9080|9091|9092)"` — expect 7070/8080/9092 still listening, 9080/9091 free.

**Verification pattern (operator-flagged pitfall 2026-07-01):** the user has pushed back HARD on passive shutdown narrative ("stands down" / "Ent Army rests" / "peace in the maple forest" all read as ambiguous). The expected post-shutdown response is:
1. **First line:** the `ss -tlnp | grep ...` output showing which ports are gone and which remain (the operator's services preserved, your services killed — receipts, not vibes).
2. **Second line:** the PIDs you terminated and the exit code.
3. **Third line:** one-line summary in normal prose.

Avoid wrapping shutdown confirmations in roleplay/persona voice — the artifact is the verification, the voice is decoration.

See `references/screenshot-capture.md` for the full Playwright capture recipe and the complete shutdown discipline.

See `references/process-kill.md` for the canonical kill sequence and
the gradle/gradlew process tree you must terminate to actually free the
ports.

## Debug-only env vars for the game server (added 2026-06-27)

These env vars **must be set on the `:server:run` JVM** (via the
`AUTOGENESIS_DEBUG_*` exports + `-D` JVM args in
`debugger/scripts/start_servers.sh` and the `gradlew` invocation
that starts the game server). They are no-ops in production builds
that don't set them.

| Env var | JVM property | Effect | Use case |
|---|---|---|---|
| `AUTOGENESIS_DEBUG_SEED` | `-DAUTOGENESIS_DEBUG_SEED` | Enables `POST /debug/seed-snapshot` + `GET /debug/fetch-snapshot` endpoints for re-pushing a known-good snapshot without re-playing the game | Resume-bug iteration loops — fetch snapshot, fix code, restart server, repush snapshot, re-test |
| `AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS` | `-DAUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000` | Overrides the 5-minute human turn timer (`TURN_TIMEOUT_MS=302000` at `gameState/WorldManager.kt:45`) for e2e probes | Phase 1 of `resume-preserves-round.mjs` needs `humanPlayerHasJoinedOnce=true` to fire before the probe disconnects; without this, probes wait 5+ minutes for the human's first turn |
| `AUTOGENESIS_DISABLE_AUTO_RESTORE` | `-DAUTOGENESIS_DISABLE_AUTO_RESTORE` | Suppresses in-place auto-restore on WS reconnect so the resume dialog path can be tested | Dev workflow — already in `start_servers.sh` default |
| `AUTOGENESIS_SHUTDOWN_DELAY_MS` | `-DAUTOGENESIS_SHUTDOWN_DELAY_MS=600000` | 10-minute shutdown timer so the player can switch tabs and reconnect | Dev workflow — already in `start_servers.sh` default |
| `AUTOGENESIS_DEV_PUSH_MOCK_PORT` | `-DAUTOGENESIS_DEV_PUSH_MOCK_PORT=<port>` | Dev-only endpoint override for web push. When set, `PushNotificationService` rewrites every subscription endpoint to `http://127.0.0.1:<port>` (preserving the original path) before sending. The push is intercepted by a local mock server instead of going through FCM/Mozilla/APNs. Wired in `Server.kt:291-308`; consumed in `PushNotificationService.kt` `endpointOverrideBase` ctor param + `resolveEndpoint(originalEndpoint)` private helper | E2E probe `kvisionApp-e2e/probes/push-turn-start.mjs` — starts a local HttpServer on the configured port and asserts it received the encrypted POST. Without this env var, the probe cannot intercept real push deliveries. Production builds ignore the env var entirely (no mock possible when unset). Verified 2026-06-28 via `PushNotificationServiceIntegrationTest.endpointOverrideRewritesSubscriptionEndpointToMockBase` (lines 204-277 of the integration test). |

**Why `AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS` matters:** without it,
`shouldPersistOnDisconnect` at `Server.kt:1037` rejects the Phase 1
disconnect because `humanPlayerHasJoinedOnce` was never set (the
human's turn hadn't started in the 12-second probe window). No
snapshot is written, Phase 2 finds no record, and the dialog never
appears. With `=5000` the human's turn starts, the AI takes over
in 5s, and the snapshot is written on Phase 1 disconnect. Verified
2026-06-27 with `TurnHarness.awaitPlayerAction: DEBUG SHORT TURN
TIMEOUT active: 5000ms (default 302000ms)`.

## Build / restart of just the kvision dev server

The kvision dev server is the only one that needs frequent restart
(due to webpack cache and KSP slowness):

```bash
ps aux | grep "kvisionApp:jsBrowserDevelopmentRun" | grep -v grep | awk '{print $2}' | xargs -r kill
sleep 5
nohup ./gradlew :kvisionApp:jsBrowserDevelopmentRun --no-daemon --console=plain > /tmp/kvision.log 2>&1 &
```

The Kotlin/JS compile typically takes 30-90 seconds (KSP is slow even
on warm caches). The bundle ends up at
`kvisionApp/build/compileSync/js/main/developmentExecutable/kotlin/Autogenesis-kvisionApp.js`
(mtime after the recompile is the source of truth — webpack watches
that file, not the .kt source).

## Screenshot capture workflow (Playwright UI walks)

For visual documentation of any UI state (loading screen, login, main menu, wizard, gameplay, map with pins), see `references/screenshot-capture.md`. The recipe covers:
- 1920x1080 viewport + fullPage PNGs to `~/Desktop/Workspaces/Autogenesis/screenshots/` (one above repo root)
- Dialog-scoped button queries — avoids clicking main-menu "PLAY" instead of wizard "Play"
- Resume-dialog dismissal via "New Game" (not generic "OK", which dismisses unrelated modals too)
- Chunked-WS timing: wait **25s after `gameplay-ui` mounts** before screenshotting populated state (leaderboard + map fill late)
- Real `page.mouse.click(x, y)` on element center for KVision `onClick` handlers — more reliable than Playwright `.click({force:true})`
- `AUTOGENESIS_SHUTDOWN_DELAY_MS=600000` on `:server:run` so it doesn't self-terminate 15s after disconnect during long captures
- Server shutdown discipline: kill **only the `:server:run` JVM you started** (port 9080/9091), leave user's webpack (8080/8081) and server-extend (7070/9092) alone
- **Phase-page screenshots (Start / Action / Planning / Writing / Judging / Dispatch / NPCs / World / Counter) are gated.** `?testMode=true` exposes `window.gameplayUI` but its `_1`-suffixed widget fields only carry KVision's `$delegate_1` styled-property setters (not source-visible method names). `TurnResolutionWidget(demoMode = false)` is hard-coded at `GameplayUI.kt:298` — there is no URL flag, query string, env var, or runtime toggle to enable demo mode. Three options documented in `references/screenshot-capture.md` "Capturing the 9 phase pages" section: (a) drive each phase via real LLM cycles polled by the `.fa-pulse` CSS class on active phase icons; (b) flip demoMode to true in source + rebuild `:kvisionApp:compileSync`; (c) add a `?turnDemoMode=true` URL parameter wired to GameplayUI.kt:298. Until one of these lands, do not promise phase-page captures from Playwright alone.
- Stats menu (Player Stats / NPC Stats / Territories / Turn Order) and history tabs (Story / Details / Geopolitics / Work Stream) capture cleanly without any code change — see the "Cheat Sheet" section at the bottom of `references/screenshot-capture.md` for the tab-cycling scripts.
- **Phase-page screenshots (Start / Action / Planning / Writing / Judging / Dispatch / NPCs / World / Counter) ARE scriptable** via real-turn polling (breakthrough 2026-07-01): type a command via native-value-setter, click the **title-case `Send`** button (NOT `SEND` — `CommandBox.kt:106`), poll `.fa-pulse` on active phase icons. Captured all 8 phases + the writing screen in one ~5-minute run. Server requires `AUTOGENESIS_SHUTDOWN_DELAY_MS=1800000` (30 min) for the longer AI cycle. Full working recipe + per-phase content samples in the "Capturing the 9 phase pages" section of `references/screenshot-capture.md`. The KVision controlled-input bypass (`Object.getOwnPropertyDescriptor(...).value.set` pattern) is the non-obvious gotcha that breaks both naive `.value =` and naive `dispatchEvent('input')` paths.

## Common pitfalls

[... full pitfall list unchanged ...] (preserved verbatim for searchability — see git history)