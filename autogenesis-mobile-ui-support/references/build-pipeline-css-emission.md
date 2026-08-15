# Build Pipeline — night-mode.css Emission Pattern

The Autogenesis kvisionApp webpack build emits `night-mode.css` as a separate file rather than inlining CSS in the JS bundle. This affects how local development sees CSS changes.

## File Locations

Three copies of night-mode.css exist in the workspace at any time:

1. **Source** (what you edit): `kvisionApp/src/jsMain/resources/night-mode.css`
2. **Processed** (Kotlin/JS resource processing output): `kvisionApp/build/processedResources/js/main/night-mode.css`
3. **Dist** (what static-server-8080.mjs serves to e2e probes): `kvisionApp/build/dist/js/productionExecutable/night-mode.css`

The dist file is also what Amplify deploys to production.

## Refresh Sequence After CSS Edit

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp

# 1. Process the resource (copies src → processedResources)
./gradlew :kvisionApp:jsProcessResources -Pkvision.liveMode=true

# 2. Copy processedResources → dist (manual, NOT in any Gradle task)
cp build/processedResources/js/main/night-mode.css \
   build/dist/js/productionExecutable/night-mode.css
```

## Why the Manual cp Exists

`build.gradle.kts` runs `:kvisionApp:jsBrowserProductionWebpack` which regenerates `kvisionApp.js` but does NOT touch `dist/js/productionExecutable/night-mode.css`. The actual copy step lives in `amplify.yml` at the postBuild phase (lines 144-156):

```yaml
SRC=kvisionApp/build/kotlin-webpack/js/productionExecutable
DST=kvisionApp/build/dist/js/productionExecutable
mkdir -p "$DST"
cp -r "$SRC/." "$DST/"
for d in audio grpc img maps; do
  [ -d "kvisionApp/build/processedResources/js/main/$d" ] && \
    cp -r "kvisionApp/build/processedResources/js/main/$d" "$DST/"
done
for f in index.html sw.js manifest.webmanifest night-mode.css; do
  [ -f "kvisionApp/build/processedResources/js/main/$f" ] && \
    cp "kvisionApp/build/processedResources/js/main/$f" "$DST/"
done
```

This means on AWS Amplify the dist copy IS automatic (postBuild runs after webpack). But locally, no equivalent hook exists — the developer must run the `cp` themselves.

## Symptom When Stale

If you forget the cp step:

1. `grep '<selector>' kvisionApp/src/jsMain/resources/night-mode.css` returns 1 hit
2. `grep '<selector>' kvisionApp/build/processedResources/js/main/night-mode.css` returns 1 hit
3. `grep '<selector>' kvisionApp/build/dist/js/productionExecutable/night-mode.css` returns 0 hits
4. Static server keeps serving the OLD CSS
5. Playwright probes behave as if your changes don't exist

Diagnostic tells you "your CSS rule isn't firing" — but the source rule IS fine, the dist artifact is just stale.

## webpack CSS Pipeline Quirks

Confirmed quirks that affect CSS rule survival:

1. **`> div` child combinator is stripped** — `.parent > div { ... }` becomes just `.parent` in the bundle. Use `:has(...)` to anchor to a known inner element.
2. **`a, b` selector groups are preserved** as separate rules.
3. **CSS custom properties (`--var`)** survive through webpack.
4. **`@media` blocks are preserved** with their full media-query strings.
5. **CSS comments** (`/* ... */`) are stripped from the bundle but survive in processedResources.

## Detection Recipe

When a CSS fix appears to not work:

```bash
WORKSPACE=/home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
SEL="your-new-selector"

echo "Source:"
grep -c "$SEL" "$WORKSPACE/kvisionApp/src/jsMain/resources/night-mode.css"

echo "Processed:"
grep -c "$SEL" "$WORKSPACE/kvisionApp/build/processedResources/js/main/night-mode.css"

echo "Dist (served):"
grep -c "$SEL" "$WORKSPACE/kvisionApp/build/dist/js/productionExecutable/night-mode.css"
```

If source >= 1 but processed = 0, run `:kvisionApp:jsProcessResources`.
If source >= 1 AND processed >= 1 but dist = 0, run the manual `cp`.
If all three >= 1, the rule IS in the served CSS — your defect is elsewhere.

## Amplify Deploy Caveat

Once Amplify deploys, the postBuild cp fires automatically and dist matches processedResources. But local dev without Amplify needs the manual cp. For sandbox dev / e2e probe work, always:

```bash
# After every CSS edit:
./gradlew :kvisionApp:jsProcessResources -Pkvision.liveMode=true && \
  cp kvisionApp/build/processedResources/js/main/night-mode.css \
     kvisionApp/build/dist/js/productionExecutable/night-mode.css
```

Or chain into a single shell line and alias it in your shell.