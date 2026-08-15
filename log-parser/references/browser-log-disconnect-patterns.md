# Browser WebSocket Disconnect Patterns — Autogenesis

## The Problem
User reports "game server crashed" — actual cause is almost always a browser tab close or network blip, not a JVM crash.

## Diagnostic Checklist

### Step 1: Find the browser log
```bash
ls -lt ~/.autogenesis/logs/browser*.log | head -3
```

### Step 2: Check for WebSocket close events
```bash
grep -n "WebSocket connection closed\|WebSocket connection error" ~/.autogenesis/logs/browser-*.log
```
- **Single close event** → normal tab close (not a crash)
- **Multiple close events** → investigate reconnection loops

### Step 3: Check what the error says
```
WebSocket connection error: StandaloneCoroutine was cancelled
```
This is **NOT** an error — it's Kotlin coroutine cleanup when the tab closes. Normal behavior.

### Step 4: Verify server side
```bash
grep "No PRIMARY sessions remain\|Player.*disconnected\|BUILD FAILED\|exit value 143" ~/.autogenesis/logs/server*.log
```
- `exit value 143` = SIGTERM = process was killed, not crashed
- `No PRIMARY sessions remain` = server correctly shut down after last client left

### Step 5: Check for reconnection after close
```bash
grep "WebSocket connection established" ~/.autogenesis/logs/browser-*.log | wc -l
```
High count = tab was reopened multiple times (normal during development)

## Browser vs Server Log Correlation

| Browser Log Shows | Server Log Shows | Interpretation |
|------------------|-----------------|---------------|
| `StandaloneCoroutine was cancelled` + single close | `Player session deregistered` | Tab closed normally |
| Multiple close/reconnect pairs | Multiple `session deregistered` + re-registers | Network blip, client reconnected |
| No close events, log ends abruptly | Server still running | Browser tab killed, server alive |
| Close + no reconnect | Server shuts down after 15s | Client left, server timed out |

## Key Grep Patterns for Session Analysis

```bash
# Count judgement outcomes (game activity)
grep "Judgement Effect" ~/.autogenesis/logs/browser-*.log | \
  grep -oP "Success: (true|false)" | sort | uniq -c

# Extract turn timeline
grep "showActiveTurn actor=" ~/.autogenesis/logs/browser-*.log | \
  head -20

# Extract all judgement narratives
grep "turnResult = '" ~/.autogenesis/logs/browser-*.log | \
  grep -v "Planning\|Defenders\|Counter" | head -20

# Get session duration
grep "BrowserSmokeState.install" ~/.autogenesis/logs/browser-*.log | head -1
grep "WebSocket connection closed" ~/.autogenesis/logs/browser-*.log | tail -1
```

## Why "BUILD FAILED" is Misleading
Both server and server-extend Gradle tasks show `BUILD FAILED` when they exit with code 143 (SIGTERM). This is Gradle's normal reporting for any non-zero exit — SIGTERM is how the JVM is killed when the tab closes or `kill` is called. Not a crash.

## Session Duration
From `BrowserSmokeState.install` to last log entry = session length. From last log entry to `No PRIMARY sessions remain` = server grace period (15 seconds).
