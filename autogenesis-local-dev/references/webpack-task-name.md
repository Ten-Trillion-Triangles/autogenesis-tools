# Webpack Dev Server Task Name

## Pitfall — `:kvisionApp:runKvisionNoHotReload` does not exist

If you reach for the task `runKvisionNoHotReload` (mentioned in some older notes), gradle will fail with:

```
* What went wrong:
Cannot locate tasks that match ':kvisionApp:runKvisionNoHotReload' as task
'runKvisionNoHotReload' not found in project ':kvisionApp'.
```

The actual task in this project is `:kvisionApp:jsBrowserDevelopmentRun`. It binds webpack-dev-server to port 8080 with hot reload enabled.

## Correct commands

```bash
# Start server-extend first (port 7070)
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./gradlew :server-extend:run &

# Wait for it to bind
until ss -tlnp 2>/dev/null | grep -q ":7070 "; do sleep 5; done

# Then game-server (port 9080)
./gradlew :server:run &
until ss -tlnp 2>/dev/null | grep -q ":9080 "; do sleep 5; done

# Then webpack (port 8080)
./gradlew :kvisionApp:jsBrowserDevelopmentRun &

# Wait for first compile to finish — bundle size ~25 MiB
until curl -sf -o /dev/null --max-time 3 http://127.0.0.1:8080/kvisionApp.js; do sleep 4; done
```

## How to discover the right task if uncertain

```bash
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./gradlew :kvisionApp:tasks --all 2>&1 | grep -iE "run|serve|browser|webpack|dev"
```

The relevant tasks in this project are:

| Task | What it does |
|---|---|
| `jsBrowserDevelopmentRun` | Start webpack-dev-server with HMR (port 8080) |
| `jsBrowserDevelopmentWebpack` | Build dev bundle (no server) |
| `jsBrowserProductionRun` | Start webpack-dev-server for production bundle |
| `jsBrowserProductionWebpack` | Build production bundle |
| `jsBrowserTest` | Run JS tests in karma + webpack |

## Don't run server-extend and server in the same gradle invocation

Running `./gradlew :server-extend:run :server:run` silently breaks server-extend's port bind — the gradle daemon serializes them and server-extend's port ends up taken by the second process before the first binds. Always run them in separate terminals / separate background processes.

## UUID v4 without hyphen format for playerId

When using `?playerId=...` in testMode or skipLogin, the userId must be a valid UUID v4 WITHOUT hyphens (32 hex characters, version nibble `4` at position 12, variant nibble `8|9|a|b` at position 16). Generate one with:

```bash
python3 -c "import uuid; print(uuid.uuid4().hex)"
```

Custom strings like `8c4e1a2b3d4f5a6b7c8d9e0f1a2b3c4d` (no version `4` at position 12) get rejected by AccelByte CloudVFS:

```
AccelByte API error: 400 - errorCode: 20002, errorMessage:
"unable to process request: validation error, userId : 8c4e1a2b3d4f5a6b7c8d9e0f1a2b3c4d
is not valid uuid v4 without hyphen format"
```

The `registeredPlayers` list on the server is empty for fresh connections — `Lord Maple Tree`, `Shitty Bob`, etc. only appear after a player has actually played a game in this session.