# Capture-mode probes — screenshot reference + mobile-adaptation

Reference for using Playwright to capture the Autogenesis KVision/JS UI as
it actually renders. The verification-mode probes (login-flow-e2e.mjs etc.
in `kvisionApp-e2e/probes/`) live in JavaScript and target specific
behavioral contracts; this reference is for the inverse problem: *load
the real game UI in a headless Chromium, render it as a real player
would see it, and write PNGs of the result.*

This file complements the resume-flow probes above — same dev stack
(server on :9080, server-extend on :7070, static-server on :8080),
same testMode hooks, but the goals are visual ground-truth, not
behavioral assertion.

## When to use this

- The user asks to "evaluate the mobile adaptation of the gameplay UI"
  or "capture screenshots of how it renders in desktop vs mobile" or
  "load the real map into the map viewer for reference".
- The user asks to verify a widget change by rendering before/after
  PNGs.
- The user asks to populate demo data into a widget that is normally
  only populated by server-sent UI signals (then the `demoMode=FULL`
  path is the way).
- The user wants to drive the game UI from a script (Playwright,
  Puppeteer, etc.) and needs to know which testMode hooks are
  available, which methods survive minification, and how to bypass
  server-sent "showTurnResolution" flips.

## The desktop-first workflow rule (USER CORRECTION 2026-07-17)

The user explicitly said:

> "you need to learn how the desktop ui is laid out because the design of
> mobile will be directly affected by it"
> "moreover, you need to see how it all renders in desktop mode too, so
> you can learn how the ui looks and is designed"

**Workflow:** before evaluating mobile adaptation, capture desktop
ground-truth first. The desktop layout is the design intent; mobile
rendering only makes sense relative to it. Do NOT skip this step.

**Sequence:**
1. Bare MapViewer at desktop + mobile (reference of the map in isolation).
2. Full GameplayUI at desktop + mobile (with map loaded, all widgets in
   their initial layout).
3. Full GameplayUI at desktop + mobile with `demoMode=FULL` (populated
   state — sample turn entries, `Commander Juno` local player,
   resource counters with real numbers).
4. Compare mobile against desktop to find layout that does not adapt.

## URL params that drive the boot path

| Param | Effect |
|---|---|
| `?skipLogin=true` | Bypass AccelByte login, set `accelbyteId="guest-user"`. |
| `?testMode=true` | Expose `window.mapViewer`, `window.loadMapForTest`, `window.gameplayUI`. Also auto-mounts MapViewer directly into the stack when `skipLogin=true`. |
| `?bootWidget=MapViewer\|GameplayUI\|MainMenu\|DebugConsole\|CollectionOverlay\|ResumeOrNewDialog\|CommanderSelectionDialog` | Direct-mount that widget at startup, bypassing login + MainMenu + bridge rebinds. |
| `?demoMode=FULL` | Bypass WebSocket + REST + ServerExtend bridge connects. Seed `World.localPlayer = Commander Juno` from `DemoFixtures`. |
| `?demoMode=WIDGETS` | Keep bridges alive, drive widgets in demo mode (different from FULL). |

These compose. The capture combinations that work end-to-end:

- `?skipLogin=true&testMode=true` → bare MapViewer (testMode branch in Main.kt:228–287)
- `?skipLogin=true&testMode=true&bootWidget=GameplayUI` → full GameplayUI on real bridge
- `?demoMode=FULL&skipLogin=true&testMode=true&bootWidget=GameplayUI` → full GameplayUI, populated demo state, no server UI signals

## The five load-bearing shims (verified 2026-07-17)

Without these, the page either never leaves LoadingScreen, never mounts
the map, or the map is hidden behind the TurnResolutionWidget.

### 1. Route-asset fallback for the static-server

The static-server at :8080 ships only `index.html`, `kvisionApp.js`,
and `night-mode.css`. Audio, images, fonts, etc. all 404. LoadingScreen's
`Mp3AssetLoader` then sits in `withTimeoutOrNull(30_000)` for 30 s
before the asset is reported failed, the LoadingScreen never clears,
and the target widget never mounts.

Fix: install a `ctx.route("**/*", handler)` that intercepts requests
for `.mp3/.png/.jpg/.css/.webmanifest/etc.` and serves them from on-disk
roots:

```python
ROOTS = [
    "<repo>/kvisionApp/build/processedResources/js/main",  # webpack output
    "<repo>/kvisionApp/src/jsMain/resources",
    "<repo>/server/src/main/resources",
]
def handle(route, request):
    path = urlparse(request.url).path
    if not any(path.endswith(suf) for suf in (".mp3", ".png", ".jpg", ".css", ".webmanifest")):
        return route.continue_()
    rel = unquote(path.lstrip("/"))  # url-decode (%20 -> space)
    for root in ROOTS:
        full = os.path.join(root, rel)
        if os.path.isfile(full):
            with open(full, "rb") as f: body = f.read()
            ctype, _ = mimetypes.guess_type(full)
            return route.fulfill(status=200,
                                 headers={"content-type": ctype or "application/octet-stream"},
                                 body=body)
    return route.continue_()
context.route("**/*", handle)
```

**Pitfall:** `request.url` is the FULL URL (scheme + host + path +
query). `path = urlparse(request.url).path` is correct. `path.lstrip("/")`
gives the relative-on-disk key. URLs with `%20` etc. MUST be
`urllib.parse.unquote`'d before filesystem lookup — autogenesis audio
files have spaces in their names ("Xilaron and Eleuryiyidict wet final.mp3").

### 2. LoadingScreen CTA dismiss

LoadingScreen is gated on a user click for browser autoplay policy
(AudioContext.state must be `running` before any sound). The button
has `data-testid="loading-screen-cta"` and text "CLICK TO ENTER".

```python
btn = page.locator('[data-testid="loading-screen-cta"]')
if btn.count() > 0 and btn.is_visible():
    btn.click(force=True)
# Then poll until the loading-screen-root element is gone.
```

### 3. testMode `loadMapForTest(bytes)` map injection

`Main.kt:287` installs the test hook at app boot:

```kotlin
window.loadMapForTest = { bytes: Array<Number> ->
    val ba = ByteArray(bytes.size)
    for (i in 0 until bytes.size) { ba[i] = bytes[i].toByte() }
    MainScope().launch { testViewer.loadMapPack(ba) }
}
```

The function returns immediately (fire-and-forget launch). Wait for
the side-channel completion signal:

- A `<img>` element with `src.startsWith("blob:")` (the map background)
- 30+ emoji-marker `<span>`s inside the map (one per territory
  icon) — these come from MapViewer's `addTerritoryIcon` loop,
  which only runs after `MapPackManager.unpack` completes.

The bundle is minified — `mapViewer.isMapLoaded` is also minified away,
so polling the Kotlin field does NOT work. Polling the DOM
side-channel does.

```python
# Encode the .map bytes as base64 in Python, ship to JS, decode,
# convert to a plain Array<Number> (matches Kotlin's Array<Number>).
b64 = base64.b64encode(map_bytes).decode("ascii")
# Then in JS:
#   const bin = atob(b64);
#   const arr = new Array(bin.length);
#   for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
#   window.loadMapForTest(arr);
#   // Then poll document.querySelectorAll('img') for blob: URLs
#   // and document.querySelectorAll('span, div') for emoji markers
#   // until blobImgs >= 1 AND emojiTerritories >= 30.
```

`San_Martello.map` is on disk at
`<repo>/server/src/main/resources/maps/San_Martello.map` and is also
referenced in the guest running-game snapshot at
`~/.autogenesis/player-records/guest-user/running-game.json` (the
`mapPackName` field). 2.2 MB ZIP.

### 4. The minified-name `gameplayUI.lha()` shim

**This is the most non-obvious trick and was the difference between
"GameplayUI shell but TurnResolutionWidget overlays everything" and
"GameplayUI with the map mounted in the dockPanel centerStackPanel."**

The GameplayUI's dockPanel center cell contains a `StackPanel`
(`centerStackPanel`) with two children: index 0 = `MapViewer`,
index 1 = `TurnResolutionWidget`. KVision mounts StackPanel children
**lazily** — only the active index gets a DOM subtree. Default
`activeIndex` is 0 = MapViewer, but server-sent UI signals
(`ui.setCommandInteractive`, `ui.turnComplete`, etc.) repeatedly call
`gameplayUI.showTurnResolution()` which flips activeIndex to 1 and
mounts TurnResolutionWidget instead. By the time the capture script
runs, the MapViewer's `<img>` is not in the DOM and never gets a blob
URL.

The production fix is `gameplayUI.showMap()`. After Kotlin/JS
minification, the method ends up at `protoOf(GameplayUI).lha`:

```js
protoOf(GameplayUI).lha = function(){
    Logger_getInstance().n5p(LogCategory_UI_getInstance(),"GameplayUI.showMap() called"),
    this.sg3_1=!0;
    var t = this.hg3_1;  // centerStackPanel field
    null==t||t.zk3();   // activeIndex = 0 setter
    ...
}
```

So in JS:
- `window.gameplayUI.showMap()` returns `undefined` (it's not on the
  JS-accessible instance path — Kotlin/JS keeps it on `__proto__`
  with a mangled name).
- `window.gameplayUI.lha()` works.

To find the mangled name for a Kotlin/JS method:

```bash
curl -s http://localhost:8080/kvisionApp.js | \
  grep -oE 'GameplayUI\$[a-zA-Z_$]+\(\)' | head
# Or search by the JS log message:
curl -s http://localhost:8080/kvisionApp.js | \
  grep -oE 'protoOf\(GameplayUI\)\.\w+[^{]*"GameplayUI.showMap\(\) called"'
```

After you call `lha()` once, KVision mounts the MapViewer subtree
(lazy mount). Subsequent server-side `showTurnResolution` flips will
re-flip activeIndex back to 1. The fix is an enforcer:

```js
window.__autogenesisShowMapEnforcer = setInterval(() => {
    try {
        if (window.gameplayUI && typeof window.gameplayUI.lha === 'function') {
            window.gameplayUI.lha();
        }
    } catch (_e) {}
}, 200);
```

200 ms is the right cadence — fast enough that the screenshot is
always taken with the map visible, slow enough that it doesn't
fight KVision's own state machine.

### 5. The `demoMode=FULL` populated-state path

When the user wants to see the GameplayUI in its "designed" populated
state (without depending on a live server that may or may not be in
the right phase of the turn cycle), use `demoMode=FULL`:

```python
url = "http://localhost:8080/?demoMode=FULL&skipLogin=true&testMode=true&bootWidget=GameplayUI"
```

`Main.kt:451` reads `demoMode=FULL` and bypasses both the WebSocket
bridge connect AND the ServerExtend bridge connect. `GameplayUI.kt:113`
seeds `World.localPlayer = DemoFixtures.buildDemoLocalPlayer()`
(Commander Juno: 34 VP, 12 military, 2 diplomatic, 3 research,
1 summit). Game History window is shown with demo entries populated
from `DemoFixtures.buildDemoWorld()`.

With this path:
- No server UI signals fire (no WS connected).
- The MapViewer's `<img>` mounts at the default activeIndex 0
  automatically.
- The Game History panel populates with sample turns — visible
  ground-truth of "this is what the design looks like with real data".
- Score bar shows `0` for all four resource counters (Commander Juno
  has them in `Player.militaryPoints` etc. but the score bar updates
  only via `updateWorldState`/`updateResources`, which is normally
  driven by server signals — in FULL demo mode those signals don't
  fire, so the score stays at 0).

## End-to-end capture script (Python)

The full script lives at `/tmp/autogenesis-screenshots/capture.py`
(outside the repo). It captures 6 screenshots:

| File | What it shows |
|---|---|
| `01_mapviewer_{desktop,mobile}.png` | Bare MapViewer with San_Martello loaded |
| `02_gameplay_{desktop,mobile}.png` | Full GameplayUI with map loaded (real bridge) |
| `03_demo_full_{desktop,mobile}.png` | Full GameplayUI demo state with map loaded |

The script is self-contained. To re-run:

```bash
python3 /tmp/autogenesis-screenshots/capture.py
```

It takes ~60 s for 6 captures, prints diagnostic logs for each
playwright operation, and writes PNGs to `/tmp/autogenesis-screenshots/`.

## Subagent vision dispatch fails with HTTP 401 (verified 2026-07-19)

The `mcp__MiniMax__understand_image` tool works in the main agent session but
**fails with `HTTP 401: unauthorized: AuthenticateToken authentication failed`
when dispatched from a subagent** (verified twice with claude-opus-4.8 in
2026-07-19 mobile-defect-chart sessions — same tool, same image, same prompt,
same model; works in main, fails in subagent). The root cause is that
subagents inherit an MCP credential context that doesn't include the vision
provider's token.

**Pattern for vision audits:** do the work in the main session, NOT via
`delegate_task`. The first subagent dispatch in a chain will fail with 401,
the second will also fail with 401, and the time saved by parallelism is
wasted on the failed dispatch + result-rejection cycle. Vision calls in the
main session are fast enough that 30+ serial calls is cheaper than 1 subagent
dispatch + recovery.

If you absolutely must batch vision (e.g. 100+ PNGs), do it as multiple
sequential parallel groups in the main session (8 vision calls per
assistant turn), not as a subagent.

## md5-grouped dedup pattern for capture audits (verified 2026-07-19)

When the capture batch is large (48+ PNGs), many will be byte-identical
siblings (modal stubs that fell through the same code path write the same
image buffer). Group by md5 BEFORE running vision — this cuts 48 vision
calls to ~23 in the typical Autogenesis capture.

```bash
cd /tmp/autogenesis-screenshots && md5sum *.png | awk '{print $1}' | sort | uniq -c | sort -rn
```

Example output from 2026-07-19:
```
   13 245bb7b3...   shell_landscape + 12 modal landscape stubs (byte-identical)
   11 ef265976...   11 modal portrait stubs (visually identical but different md5
                       from shell_portrait — different render frame)
    3 b4144532...   player_territory/prompt_status/world_stats desktop (byte-identical)
    2 d0b2d077...   player_info/turn_resolution desktop (byte-identical)
   20 (unique)      shell_*, map_bare_*, player_resources_*, settings_*, etc.
```

Rule: vision each unique md5 ONCE. For byte-identical siblings (count > 1),
list them by reference in the chart with `// same image as <sample>`. For
visually-identical-but-different-bytes (md5 group count > 1 where the
deltas are small), still vision a 1-2 sample to confirm the visual match
before skipping the rest.

## What actually renders on `bootWidget=MapViewer` (verified 2026-07-19)

The 2026-07-19 capture's `map_bare_{desktop,portrait,landscape}.png` files
all show the AUTOGENESIS title/loading splash — **not** the San_Martello map.
The "Map" label visible in the top-left is a broken `<img>` placeholder.

Why: even with `bootWidget=MapViewer`, the MapViewer mounts lazily via KVision.
`window.loadMapForTest(bytes)` is fire-and-forget; if the call lands before
the `<img>` element exists in the DOM, the bytes are dropped silently and
the map never renders. The completion-side-channel signals (blob `<img>`
URL + 30+ emoji marker spans) never appear.

Fix (not yet verified in capture — to be added next run):

```python
# Wait for the MapViewer's <img> element to exist in the DOM BEFORE
# calling loadMapForTest. The widget may take 200-800ms to mount after
# the page loads.
page.wait_for_function(
    "() => document.querySelector('img.map-background') || "
    "document.querySelector('img[src*=\"map\"]')",
    timeout=5000
)
# THEN inject the bytes.
page.evaluate("""(b64) => {
    const bin = atob(b64);
    const arr = new Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    window.loadMapForTest(arr);
}""", b64)
```

The 2026-07-17 capture used `lha()` + 200ms enforcer for the **GameplayUI**
path (StackPanel flip), but the **MapViewer-direct** boot path has a
different race: MapViewer's own init. The two paths require different
injection code. The bare-MapViewer success at 2026-07-17 was probably a
timing fluke, not a verified pattern.

## Modal widgets don't open via `window.gameplayUI.<field>.show()` (verified 2026-07-19)

The 9 sub-widget modals (world_stats, player_resources, player_territory,
player_info, stats, prompt_status, game_end, delegate, territory_desc,
turn_resolution, neural_link, agent_work) all fail to open in capture.
The two root causes:

1. **Webpack minifies field names.** `worldStatsWidget`,
   `playerResourcesWidget`, etc. become single letters after production
   build. `window.gameplayUI.worldStatsWidget` returns `undefined`.

2. **Click fallback hits the wrong buttons on mobile portrait.** The HUD
   quick-action 2x2 grid (RESOURCES / STATS / WORLD / SETTINGS) is anchored
   to the right side of the desktop layout. On portrait (390px wide), the
   grid clips off the right edge — Playwright's `page.click('button:has-text("STATS")')`
   either times out or lands on the demo/simulate buttons visible at that
   x,y coordinate.

Fix options (to be implemented in next capture run):

```javascript
// (a) Use @JsName annotations on the 12 widget fields in GameplayUI.kt
//     to force stable names in the production bundle:
//     @JsName("worldStatsWidget") val worldStatsWidget: WorldStatsWidget = ...
//
// (b) Expose a single dispatcher on window.gameplayUI:
//     window.gameplayUI.openWidgetByName = (name) => { ... }
//     and call it from capture script as:
//     page.evaluate('window.gameplayUI.openWidgetByName("worldStatsWidget")')
//
// (c) For mobile click fallback: use force=True click + offset, OR
//     scroll the 2x2 grid into view first via page.evaluate.
```

**The "Your Turn To Act" text in the desktop shell is NOT a modal** — it's
the TurnResolutionWidget's empty-state placeholder (always visible when the
game is in idle state). Don't get fooled by it when assessing which modal
"opened" in a capture. The actual modal opening is detectable by:
- A new centered dialog with `position: fixed; top: 50%; left: 50%` and
  a backdrop dimming the game world
- A unique modal title string ("My Resources", "Game Settings", etc.)

## Per-image vision audit pattern (verified 2026-07-19)

For mobile-defect chart audits, the per-image vision prompt should ask
specifically for:

1. Right-edge clipping (resource labels truncated to "Di…/Re…/Su…")
2. Bottom-edge clipping (2x2 grid bottom row clipped at viewport boundary)
3. Top-edge clipping (HUD score bar partial visibility)
4. Text truncation ("DE…" DELEGATE button, "00:…" timer)
5. Element overlap / collision (DELEGATE + timer pill colliding on right)
6. Touch target sizing (iOS HIG: <44px is a violation; measure visually)
7. Map render completion (broken `<img>` placeholder vs actual map)
8. Score bar visibility (Main Score + 4 sub-scores at top)
9. DELEGATE button visibility (the blue button with scroll icon)
10. Turn timer visibility ("00:00" pill or similar)
11. Command box visibility (SEND button + text input + char counter)
12. 2x2 quick-action grid visibility (RESOURCES / STATS / WORLD / SETTINGS)
13. Modal/overlay presence (is the requested widget actually opened?)
14. Game History sidebar visibility (left rail, tabs)
15. Empty/dead space (large unused viewport regions)
16. Z-index / layering issues
17. Border-radius / styling inconsistencies

For the desktop capture prompt, swap (1) → (4) emphasis to:
- 1920x1080 desktop reference
- Is the requested widget/modal open? (dialog vs shell)
- List every visible major UI element with approximate position
- Any clipping, truncation, overlap, or layout issues?

**Reference template:** see `/tmp/autogenesis-screenshots/MOBILE_DEFECT_CHART.md`
in the 2026-07-19 capture for the canonical per-image audit output (48 rows,
all PNGs covered with vision-grounded defects, severity P0/P1/P2, cross-cutting
patterns, top-N fixes by impact).

## Stitch design-token lookup (verified 2026-07-19)

Before writing any mobile-adaptation code, check if the user already has a
Google Stitch design project for the mobile version. The design system
specifies color tokens, typography, spacing, and component styles that
should drive the KVision/Kotlin port.

```python
from mcp_stitch import list_projects, get_project, list_design_systems

# Find the project (title usually contains "Mobile" + game name)
projects = mcp.list_projects()
target = next(p for p in projects if "Autogenesis" in p.title and "Mobile" in p.title)

# Pull the full design system (namedColors + designMd + typography)
project = mcp.get_project(name=target.name)
design_md = project.designTheme.designMd  # full markdown spec
named_colors = project.designTheme.namedColors

# List screens (may be empty if project was scaffolded but not generated)
screens = mcp.list_screens(projectId=target.name.split("/")[-1])

# Pull the project thumbnail if list_screens returns empty — the thumbnail
# usually shows the design intent even when no screens are enumerated.
# thumbnail URL is at project.thumbnailScreenshot.downloadUrl
```

The 2026-07-19 Stitch project `projects/10219611715979180962` ("Autogenesis
Mobile Adaptation — Concept Sketches") had **0 screens** but a 4-frame
thumbnail showing the mobile design intent: hex-tile map filling 70% of the
viewport, slim tactical HUD at top with faction flags + timer + VP pill,
bottom-sheet command box with Story/Details/Geopolitics/Work Stream tabs.
The thumbnail is the design source of truth when list_screens is empty.

**Mapping design tokens to KVision code:**
- `primary: "#00f2ff"` → CSS `--kv-primary: #00f2ff` and Bootstrap override
- `namedColors.surface_container: "#122131"` → night-mode.css panel bg
- `typography.body_lg.fontFamily: "Inter"` → `<link href="...Inter...">`
- `spacing.unit: "4px"` → Bootstrap `$spacer: 0.25rem` already in KVision

## Common pitfalls (verified 2026-07-17, all bit me at least once)

1. **DON'T poll `window.mapViewer.isMapLoaded`** — that Kotlin field
   is also minified. After minification, reading
   `window.mapViewer.isMapLoaded` returns `undefined` even after
   `loadMapPack` completes. Use the DOM side-channel (blob `<img>` +
   emoji-marker count) instead.

2. **DON'T call `window.gameplayUI.showMap()`** — same minification
   reason. Use `window.gameplayUI.lha()` (or whatever the mangled
   name is for your build). To find the name, grep the bundle for
   `"<method-name>() called"` and look at the surrounding
   `protoOf(GameplayUI).<name> = function...`.

3. **DON'T assume a non-bare-MapViewer capture will have a working
   MapViewer's `<img>` after `loadMapForTest`** — the
   TurnResolutionWidget overlay covers the MapViewer's slot by
   default. Without the lha() + 200ms enforcer, the map never mounts
   and your screenshot shows "Your Turn To Act / GO TO MAP" instead
   of the map.

4. **DON'T trust bare-MapViewer success as proof that GameplayUI
   capture will work.** Bare MapViewer is `activeIndex 0` by default
   with no TurnResolutionWidget to flip away. GameplayUI's
   centerStackPanel starts hidden and is re-flipped by every server
   signal. The two paths require different injection code.

5. **DON'T load the map bytes BEFORE flipping to the map view.** When
   KVision's centerStackPanel activeIndex is 1 (TurnResolutionWidget
   visible), `loadMapForTest` runs but the MapViewer's `<img>` is
   not yet in the DOM, so the blob URL gets attached to a 0-sized
   `<img>`. Always call `lha()` first and wait for the `<img>` to
   appear, THEN call `loadMapForTest`.

6. **DON'T skip the route-asset fallback.** Without it, the
   LoadingScreen's Mp3AssetLoader hits the static-server's 404 on
   `audio/music/Xilaron*.mp3` and times out after 30 s. The page
   never mounts anything. The static-server doesn't ship audio.

7. **DO URL-decode filenames before filesystem lookup.** Autogenesis
   audio files have spaces in their names. The browser sends
   `Xilaron%20and%20Eleuryiyidict%20wet%20final.mp3`. Decode to
   `Xilaron and Eleuryiyidict wet final.mp3` before joining with
   the on-disk root.

8. **DO click the LoadingScreen CTA via Playwright BEFORE waiting
   for testMode hooks.** The button click satisfies the autoplay
   policy. Without it, audio context never runs and the page sits
   on the loading screen indefinitely.

9. **DO respect the desktop-first workflow rule.** Mobile adaptation
   evaluation without desktop reference is guesswork. Capture
   desktop first, then mobile, then compare.

## What mobile-portrait actually breaks (verified 2026-07-17)

The GameplayUI is designed for desktop. On mobile portrait (390 CSS
px wide), the following all break:

- **Game History panel** — `minWidth = 400.px` in
  `GameplayUI.kt:202` is wider than the entire mobile viewport,
  consuming it and covering the centerStackPanel (the map is in the
  DOM but obscured).
- **Score bar** — single row across the top overflows off the right
  edge; the turn-timer circle (DELEGATE button + 00:00) is the only
  thing still on-screen.
- **Turn-progression chips** (Start / Action / Planning / Writing /
  Judging / Dispatch / NPCs / World / Counter) — 9 chips in a row
  overflow; last 4 are clipped off-screen.
- **Command box** — single row with SEND + textarea + 0/500 char
  counter. SEND is `56 px` wide, textarea is squashed to 0 width,
  counter wraps below.
- **Quicks** (RESOURCES / STATS / WORLD / SETTINGS) — fine at
  mobile size, 2×2 bottom-right grid.

The map itself is in the DOM and rendering correctly — it's just
hidden behind the Game History panel that consumes the viewport.

## What desktop looks like with `demoMode=FULL` (verified 2026-07-17)

This is the closest thing to "real game session, no live server" that
also bypasses server UI signals. Use it as the layout reference.

- **Game History panel (left, 400px wide)** — tabs Story / Details /
  Geopolitics / Work Stream; populated with sample turn entries:
  - `Turn 1 – DemoPlayer: The automated systems successfully executed
    Plan Alpha. Initial parameters exceeded expectations. Result:
    Success (Yield +15%)`
  - `Turn 2 – DemoPlayer: The automated systems are preparing for...
    [Planning]`
- **Main Score bar (top)** — `Main Score: 0`, Military / Diplomatic /
  Research / Summit counters all 0 (not auto-populated in FULL demo
  mode), DELEGATE button, 00:00 turn timer.
- **Center dockPanel cell** — San_Martello map with all 98
  territories at percent positions.
- **Command box (bottom)** — SEND button, "Waiting for turn..."
  input, 0/500 character counter.
- **Quicks (bottom-right)** — 2×2 grid: RESOURCES / STATS / WORLD
  / SETTINGS.

## Reproduction

The pattern in `/tmp/autogenesis-screenshots/capture.py` is
self-contained. Adapt the paths (map bytes, asset roots) to your
checkout and re-run. Total wall clock: ~60 s on a recent Mac/Linux
workstation.