#!/usr/bin/env python3
"""
Lord Maple Tree plays Autogenesis.
Threaded: pong thread (non-blocking recv FIRST) + SSE thread + main thread.
Key fix: POST to server-extend (7070) with server.extend.requestGame method.
"""
import json, subprocess, time, sys, uuid, urllib.request, urllib.error, queue, threading, itertools, select

try:
    import websocket as WSClient
except ImportError:
    print("ERROR: websocket-client not installed.")
    sys.exit(1)

SE_URL   = "http://127.0.0.1:7070"
GS_URL   = "ws://127.0.0.1:9080"
PLAYER_ID = f"lord-{uuid.uuid4().int % 1000000}-{int(time.time()*1000)}"
LORD_NAME = "Lord Maple Tree"
LORD_UUID = str(uuid.uuid4())

LORD_COMMANDER = {
    "id":       LORD_UUID,
    "name":     LORD_NAME,
    "description": "Supreme Ruler of the Universe, Emperor of All Canada, Duke of the Golden Forest. Master of Explosive Maple Syrup and Conqueror of Pancake Peace.",
    "empire":   "The Golden Forest Dominion",
    "type":     "Land",
    "trait":    "Researcher",
    "imageUrl": None,
    "rarity":   "LEGENDARY"
}

_rpc_counter = itertools.count(1)
def kotlin_rpc_payload(method, params=None, rid=None):
    obj = {"type": "request", "id": str(rid or next(_rpc_counter)), "method": method}
    if params is not None:
        obj["params"] = params
    return json.dumps(obj)

def kotlin_notification(method, params=None):
    obj = {"type": "notification", "method": method}
    if params is not None:
        obj["params"] = params
    return json.dumps(obj)

def kotlin_response(req_id, result=None, error=None):
    """Send a Response to a server REQUEST (e.g., client.pong)."""
    obj = {"type": "response", "id": str(req_id)}
    if result is not None:
        obj["result"] = result
    if error is not None:
        obj["error"] = error
    return json.dumps(obj)

# ── Shared queues ───────────────────────────────────────────────────────────
_outbound_q   = queue.Queue()   # main → pong thread
_msg_q        = queue.Queue()   # pong thread → main

# ── SSE thread ──────────────────────────────────────────────────────────────
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
                    if line.startswith("data: "):
                        _msg_q.put(("sse", line[6:]))
        proc.terminate()
        proc.wait()
    except Exception as e:
        print(f"[SSE] Error: {e}", flush=True)
        proc.terminate()
        proc.wait()

# ── Pong thread ─────────────────────────────────────────────────────────────
_pong_count = [0]
_ws_connected = [False]

def ws_pong_thread_func(ws_url, stop_event):
    global _ws_connected
    _pong_count[0] = 0

    for attempt in range(10):
        try:
            ws = WSClient.create_connection(ws_url, timeout=10, suppress_origin=True)
            print(f"[PongThread] Connected (attempt {attempt+1})", flush=True)
            break
        except Exception as e:
            print(f"[PongThread] Connect failed: {e}, retrying...", flush=True)
            time.sleep(1)
            if stop_event.is_set():
                return
    else:
        print("[PongThread] Could not connect", flush=True)
        return

    _ws_connected[0] = True

    # Register
    reg = kotlin_notification("client.register", {
        "playerId": PLAYER_ID, "displayName": LORD_NAME,
        "commander": LORD_COMMANDER
    })
    ws.send(reg)
    print("[PongThread] client.register sent", flush=True)
    ws.settimeout(0.5)

    while not stop_event.is_set():
        # FIRST: Check for inbound WS data
        try:
            raw = ws.recv()
            obj = json.loads(raw)
            t     = obj.get("type", "")
            mid   = obj.get("id")
            method = obj.get("method", "")
            params = obj.get("params") or {}

            if t == "request":
                if method in ("client.ping", "client.pong"):
                    rid = mid if mid is not None else str(next(_rpc_counter))
                    pong_resp = kotlin_response(rid, result={"echo": params.get("echo","")})
                    ws.send(pong_resp)
                    _pong_count[0] += 1
                    print(f"[PongThread] >>> PONG (server={method}) id={rid} total={_pong_count[0]}", flush=True)
                    continue
            # All other messages → queue for main
            if t in ("connection_state", "notification", "request", "response"):
                _msg_q.put(("ws", obj))
        except WSClient.WebSocketTimeoutException:
            pass
        except Exception as e:
            print(f"[PongThread] recv error: {e}", flush=True)
            break

        # SECOND: Check outbound queue
        try:
            msg = _outbound_q.get_nowait()
            ws.send(msg)
            print(f"[PongThread] SENT: {msg[:80]}", flush=True)
        except queue.Empty:
            pass

    ws.close()
    _ws_connected[0] = False
    print("[PongThread] Exiting", flush=True)

# ── REST via server-extend (7070) ──────────────────────────────────────────
def se_rpc(method, params=None):
    """POST to server-extend REST endpoint (7070)"""
    body = json.dumps({
        "type": "request", "id": str(next(_rpc_counter)), "method": method,
        "params": params or {}
    }).encode()
    req = urllib.request.Request(
        f"{SE_URL}/rpc?playerId={PLAYER_ID}",
        data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print(f"\n{'='*60}")
    print(f"  LORD MAPLE TREE enters the battlefield!")
    print(f"  Player ID: {PLAYER_ID}")
    print(f"{'='*60}\n", flush=True)

    stop_event = threading.Event()
    gs_url  = f"{GS_URL}/events?playerId={PLAYER_ID}&guestMode=true"
    sse_url = f"{SE_URL}/events?playerId={PLAYER_ID}&guestMode=true"

    # ── 1. Start pong thread ─────────────────────────────────────────────
    pong_thread = threading.Thread(target=ws_pong_thread_func,
                                  args=(gs_url, stop_event), daemon=True)
    pong_thread.start()
    print("[Main] Pong thread started\n", flush=True)

    for _ in range(20):
        time.sleep(0.5)
        if _ws_connected[0]:
            print("[Main] WS connected!\n", flush=True)
            break
    else:
        print("[Main] WS connection timeout", flush=True)
        stop_event.set()
        return

    time.sleep(0.5)

    # ── 2. Start SSE thread ──────────────────────────────────────────────
    print(f"[Main] SSE: {sse_url}", flush=True)
    sse_thread = threading.Thread(target=sse_thread_func,
                                  args=(sse_url, stop_event), daemon=True)
    sse_thread.start()
    print("[Main] SSE thread started\n", flush=True)

    # ── 3. Wait for session.ready ───────────────────────────────────────
    print("[Main] Waiting for session.ready...", flush=True)
    session_ready = False
    while True:
        try:
            src, data = _msg_q.get(timeout=30)
            if src == "sse":
                obj = json.loads(data)
                method = obj.get("method", "")
                print(f"  [SSE] {method}", flush=True)
                if method == "session.ready":
                    session_ready = True
            elif src == "ws":
                print(f"  [WS]  {data.get('type','')} {data.get('method','')}", flush=True)
        except queue.Empty:
            print("[Main] 30s timeout", flush=True)
            break

        if session_ready:
            try:
                while True:
                    src, data = _msg_q.get_nowait()
                    if src == "sse":
                        obj = json.loads(data)
                        print(f"  [SSE-drain] {obj.get('method','')}", flush=True)
                    elif src == "ws":
                        print(f"  [WS-drain] {data.get('type','')} {data.get('method','')}", flush=True)
            except queue.Empty:
                pass
            print("[Main] session.ready!\n", flush=True)
            break

    if not session_ready:
        print("[Main] ERROR: no session.ready", flush=True)
        stop_event.set()
        return

    # ── 4. POST requestGame to server-extend (7070) ─────────────────────
    print("[Main] Sending server.extend.requestGame to server-extend...", flush=True)
    try:
        resp = se_rpc("server.extend.requestGame", {
            "userName": LORD_NAME,
            "gameType": "SINGLEPLAYER",
            "accelByteId": PLAYER_ID,
            "websocketId": PLAYER_ID,
            "selectedCommander": LORD_COMMANDER,
            "aiOpponentCount": 3,
            "aiOnly": False,
            "matchPool": "default"
        })
        print(f"[REST] Response: {resp[:300] if resp else '(empty)'}", flush=True)
    except urllib.error.HTTPError as e:
        body = e.read()
        print(f"[REST] HTTP {e.code}: {body[:200]}", flush=True)
    except Exception as e:
        print(f"[REST] Error: {e}", flush=True)

    print("\n[Main] Matchmaking sent! Monitoring...", flush=True)

    # ── 5. Monitor loop ─────────────────────────────────────────────────
    deadline  = time.time() + 480
    turn_started = False
    game_over    = False

    while time.time() < deadline:
        try:
            src, data = _msg_q.get(timeout=30)
            last_ts = time.time()

            if src == "sse":
                obj = json.loads(data)
                method = obj.get("method", "")
                params = obj.get("params", {})
                print(f"[SSE] {method}: {str(params)[:80]}", flush=True)
                if "shutdown" in method.lower() or "game_over" in method.lower():
                    game_over = True
            elif src == "ws":
                t     = data.get("type", "")
                method = data.get("method", "")
                params = data.get("params", {})
                if t == "notification":
                    if method == "ui.activeTurn":
                        actor = params.get("actor","?")
                        rnd   = params.get("round","?")
                        print(f"\n[WS] *** {actor}'s turn (Round {rnd}) ***", flush=True)
                        if "Lord" in actor or "Maple" in actor:
                            turn_started = True
                    elif method == "ui.setResolutionStep":
                        step = params.get("step","")
                        msg  = params.get("message","")
                        print(f"  Step={step} msg={msg}", flush=True)
                        if step == "START" and "Lord Maple Tree" in msg:
                            turn_started = True
                    elif method == "ui.thinkingUpdate":
                        print(f"[WS] Thinking ({params.get('character','?')}, {params.get('thinkingLength',0)} chars)", flush=True)
                    else:
                        print(f"[WS] NOTIF {method}", flush=True)
                elif t == "request":
                    print(f"[WS] REQUEST {method}", flush=True)
                elif t == "response":
                    print(f"[WS] RESP id={data.get('id')}", flush=True)
        except queue.Empty:
            pongs = _pong_count[0]
            print(f"[Main] (timeout – pongs={pongs}, alive={pong_thread.is_alive()})", flush=True)
            if not pong_thread.is_alive():
                print("[Main] Pong thread died, restarting...", flush=True)
                pong_thread = threading.Thread(target=ws_pong_thread_func,
                                              args=(gs_url, stop_event), daemon=True)
                pong_thread.start()
            continue

        if turn_started and not game_over:
            print("\n[Main] Submitting action!", flush=True)
            _outbound_q.put(kotlin_rpc_payload("game.submitAction", {
                "action": "Photosynthetic Incursion against the Southern Coast — march the Ent army southward through the Atlantic Ocean, spreading vegetative dominion and pancake peace.",
                "playerName": LORD_NAME
            }))
            print("[Main] Action queued via game.submitAction RPC", flush=True)
            turn_started = False

        if game_over:
            break

    print(f"\n[Main] Monitor ended. game_over={game_over}", flush=True)

    # ── 6. Shutdown ──────────────────────────────────────────────────────
    print("[Main] Shutting down...", flush=True)
    stop_event.set()
    time.sleep(2)
    print(f"[PongThread] Total pongs: {_pong_count[0]}", flush=True)
    print("[Main] Done.", flush=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Main] Interrupted.", flush=True)
        sys.exit(0)
