# Server Lifecycle & Stale Notifications

## How Sessions Work

`server-extend` (port 7070) is a long-running process — it manages matchmaking state and persists across game sessions. It does NOT restart between games.

The **game server** (port 9080) is started per-session and exits when the Python controller disconnects after submitting an action. This is normal behavior.

```
server-extend (7070)     — stays up across games
game server (9080)        — restart each game session
webpack (8080)            — optional, only if browser needed
```

## Restart Procedure

```bash
# Check current port state (authoritative source)
ss -tlnp | grep -E "7070|9080"

# If :9080 is down (normal after controller disconnects):
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis
./gradlew :server:run --no-daemon &

# server-extend (7070) rarely needs restart — only if killed or crashed
```

## Stale Background Notifications

When starting the game server with `background=true + notify_on_complete=true` in Hermes Terminal, the notification fires when the Gradle build completes — but the build output (the Java server process) may already have been restarted with a new PID from a previous cycle. This makes the notification appear stale: it reports exit=0 for a process that is no longer the active one.

**How to verify actual server state:**
```bash
ss -tlnp | grep -E "7070|9080"   # authoritative — shows what's actually listening
tail /tmp/srv.log                # shows recent server log lines
~/.autogenesis/logs/*.log        # detailed game server logs
```

**Never rely on a background process notification alone to determine if servers are up.** The notification tells you the Gradle build finished; `ss -tlnp` tells you what's actually listening on the ports.

## Gradle Project Name

The game server project is `:server` — NOT `:game`. Running `./gradlew :game:run` fails with `project 'game' not found`. Always verify with `./gradlew projects -q | grep -E "server|kvision"`.