# Browser as Passive Game Client — Observer Architecture

> **DEPRECATED NOTE (2026-05-08):** MITM proxy mode is deprecated. `debug_session.py` and `mitm_proxy.py` assumed servers bind to 7071/9081 with proxy on 7070/9080, but servers bind directly to 7070/9080. Browser connects directly to servers. Use `browser_observer.py` directly, not through proxy.

## Core Insight

The browser IS the game client. Python drives the server via REST/SSE/WebSocket; the browser connects normally to the same servers and receives identical UI feedback. The browser has no idea it's watching a driven session.

```
Python drives                        Browser observes (passive)
────────────────                     ──────────────────────────
REST POST /rpc → server-extend       Browser WS → game server (9080)
SSE → session events                 Browser SSE → server-extend (7070)
WS → pong + game.submitAction        Browser receives same ui.* events
                                        (setLocalPlayer, turn timer, narrative chunks)
```

**The browser is never "fake" — it's a real client receiving real game state.**

## Key Architectural Point

Browser and Python both connect to the REAL servers directly. No proxy injection in the normal flow. The browser's WebSocket (kvision-ws-*) IS a real player connection registered in `WorldManager`. The game server broadcasts `ui.*` events to it just like any other client.

Python and browser can coexist — both receive the same game state broadcasts.

## What This Session Built

```
debugger/
├── proxy/
│   └── mitm_proxy.py          # MITM proxy — intercepts WS + HTTP/SSE, logs everything, forwards to real servers
├── observer/
│   └── browser_observer.py    # Playwright browser — visible Chromium + full CDP console/network capture
├── scripts/
│   └── start_servers.sh        # Quick server launcher
├── observer_session.py         # Full session orchestrator
└── README.md                   # Full documentation
```

## MITM Proxy Architecture (for observation mode)

The proxy sits between browser and real servers:
```
Browser → :7070/:9080 (proxy) → :7071/:9081 (real servers)
          ↕ logs all traffic
```

Start proxy:
```bash
/tmp/autogenesis-dev/bin/python debugger/proxy/mitm_proxy.py --start \
    --http-port 7070 --ws-port 9080 \
    --real-se-port 7071 --real-ws-port 9081
```

In observation mode:
- Browser connects to proxy (7070/9080) — traffic is logged
- Python connects directly to real servers (7071/9081) — bypasses proxy
- Both see the same game state

## Shutdown Rule — CRITICAL

User explicitly said: "shut all the servers down so I don't rack up a bill while I'm away."

When task is complete:
```bash
fuser -k 7070/tcp 9080/tcp 8080/tcp 9091/tcp 9092/tcp 2>/dev/null
./gradlew --stop  # kill gradle daemons too
```
Do NOT leave background processes running.

## Yarn Lock Fix

If `runKvisionNoHotReload` fails with `kotlinStoreYarnLock FAILED`:
```bash
./gradlew kotlinUpgradeYarnLock
./gradlew runKvisionNoHotReload
```

## KSP Build Conflict (Applied Fix)

KSP 2 + module-specific cache dirs prevent concurrent server builds from colliding:
- `gradle.properties`: `ksp.useKSP2=true`
- `server/` and `server-extend/` build.gradle.kts: `arg("ksp.cache.dir", "build/ksp-cache")`

## Controller Enhancement

controller.py now accepts `--se-port` and `--ws-port` for flexible targeting (direct or proxy mode).