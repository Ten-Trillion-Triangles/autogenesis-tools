# session.ready Detection Fix

**Problem:** `session.ready` arrives during the SSE init drain phase, but the subsequent polling loop calls `_msg_q.get_nowait()` and finds nothing. The loop then polls `_msg_q.get(timeout=30)` which waits 30s each time. After 60 attempts, it aborts even though the game already started.

**Root cause:** The SSE reader puts `session.ready` on the queue during drain, but the drain loop also consumes it correctly. However, the drain loop exits and the main polling loop starts fresh — and since no *new* `session.ready` event arrives after drain, 60 subsequent "no event" polls happen.

**Evidence from session log (2026-05-08):**
```
[SSE] session.ready          ← received during init drain
  attempt 1/60 – no event
  attempt 2/60 – no event
  ...
  attempt 60/60 – no event
[MAIN] ERROR: no session.ready – aborting
```
The game was LIVE — `ui.agentWorkStream` chunks were streaming on the WS channel. The session was ready. The detection logic failed.

**Fix:** Use a `threading.Event` — set it in the SSE reader when `session.ready` is seen, and wait on it in main instead of polling the queue.

```python
import threading

# Shared state
session_ready_event = threading.Event()

def sse_thread_func(url, stop_event):
    proc = subprocess.Popen(
        ["stdbuf", "-oL", "curl", "-s", "-N",
         "--max-time", "240", url,
         "-H", "Accept: text/event-stream",
         "-H", f"playerId: {PLAYER_ID}"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    try:
        import fcntl, os
        fd = proc.stdout.fileno()
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)
        while not stop_event.is_set():
            readable, _, _ = select.select([proc.stdout], [], [], 1.0)
            if readable:
                raw_line = proc.stdout.readline()
                if raw_line:
                    line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                    # Skip blank SSE lines and empty data: prefixes
                    if line.startswith("data: "):
                        content = line[6:].strip()
                        if not content:
                            continue  # skip blank data: lines
                        _msg_q.put(("sse", content))
                    elif line.startswith("data:"):
                        # no space after colon
                        content = line[5:].strip()
                        if not content:
                            continue
                        _msg_q.put(("sse", content))
        proc.terminate()
        proc.wait()
    except Exception as e:
        print(f"[SSE] Error: {e}", flush=True)
        proc.terminate()
        proc.wait()
```

And in `kotlin_response`/`pong handling` in the SSE reader, check for `session.ready`:

```python
# In sse_thread_func — check for session.ready BEFORE putting on queue
if content.startswith("{"):
    try:
        obj = json.loads(content)
        method = obj.get("method", "")
        if method == "session.ready":
            session_ready_event.set()
            print(f"  [SSE] session.ready SET", flush=True)
    except json.JSONDecodeError:
        pass

# ALWAYS put on queue for main's monitoring loop
_msg_q.put(("sse", content))
```

In main, replace the polling loop with event-based wait:

```python
# OLD (broken — polls queue, misses session.ready):
# print("[Main] Waiting for session.ready...", flush=True)
# while True:
#     src, data = _msg_q.get(timeout=30)
#     ...

# NEW (event-based — reliable):
print("[Main] Waiting for session.ready...", flush=True)
if not session_ready_event.wait(timeout=60):
    print("[Main] ERROR: no session.ready within 60s", flush=True)
    stop_event.set()
    return
print("[Main] session.ready!\n", flush=True)

# Drain remaining SSE/WS init messages
while True:
    try:
        src, data = _msg_q.get_nowait()
        if src == "sse":
            obj = json.loads(data)
            print(f"  [SSE-drain] {obj.get('method','')}", flush=True)
        elif src == "ws":
            print(f"  [WS-drain] {data.get('type','')} {data.get('method','')}", flush=True)
    except queue.Empty:
        break
```

**Blank SSE lines also flood the queue** — the SSE stream sends `data: ` (blank) lines between events. Each gets parsed as `{}` by `json.loads("")`. Skip any `data: ` line where the content after `data: ` is empty.

**Summary of SSE reader fixes:**
1. Strip `data: ` prefix, skip if content is empty
2. Set `session_ready_event` when `session.ready` arrives (before putting on queue)
3. Main waits on the event, not the queue

## Timeout Fix

**480s is too short.** BG's AI turn alone ran 5+ minutes. With 4 opponents taking 4-10 min each, a full round can exceed 30 minutes.

```python
# OLD — TOO SHORT:
deadline = time.time() + 480

# NEW:
deadline = time.time() + 2400  # 40 minutes — survives a full round
```

The game server and TPipe run independently. As long as Python's WS is connected and pongs are being sent, the player stays reachable even if Python's main loop is blocked waiting for the next turn event.
