#!/usr/bin/env python3
"""
Lord Maple Tree's Autogenesis Campaign - End-to-End Gameplay Script
Connects to server-extend (7070) for matchmaking via SSE + REST, then to game server (9080)
for turn submission. Uses 660s timeout to handle TPipe's ~4min/turn processing.

IMPORTANT PREREQUISITES:
    - All servers running: :server:run (9080), :server-extend:run (7070), runKvisionNoHotReload (8080)
    - Browser open at http://127.0.0.1:8080/?skipLogin=true — THIS IS REQUIRED for session binding
    - Lord Maple Tree commander created in collection

CRITICAL: PLAYER_ID must be the browser's kvision-ws-client-* ID (from server logs), NOT self-generated.
The WorldManager.playerStats entry is keyed by the browser's WS connection ID. A self-generated
ID means TurnHarness.awaitPlayerAction will never find the player and the turn will hang.

gameType must be "SINGLEPLAYER" (no underscore) — "SINGLE_PLAYER" is silently rejected.

Turn submission uses game.submitAction (NOT server.sendPrompt — that's for in-game prompts).

Architecture:
    - SSE connection to server-extend: receives MatchFoundNotification
    - REST call to server-extend: triggers server.extend.requestGame
    - WS connection to game server: receives game state (if session-bound) and submits turns
"""
import asyncio
import json
import websockets
import urllib.request
import urllib.error
import time
import signal
import sys
import os

# === CONFIGURATION ===
PLAYER_ID = f"lord-{os.getpid()}"
GAME_WS = "ws://127.0.0.1:9080"
SERVER_EXTEND = "http://127.0.0.1:7070"
TURN_TIMEOUT = 660  # 11 minutes — TPipe needs 4-5 min per turn

# Lord Maple Tree's march order
ORDER = (
    "I launch a full military offensive! My Ents march from Washington into Oregon "
    "while my air forces secure the skies. The Slave Lake Ent Army advances with "
    "terrifying coordination, crushing any resistance. We call upon the ancient "
    "pancake-firing artillery and deploy EXPLOSIVE MAPLE SYRUP (nitroglycerine + syrup) "
    "to detonate enemy positions into delicious caramelized rubble. "
    "Canada shall be pancakes. The world shall be pancakes. Submit or be consumed."
)

print(f"Lord Maple Tree enters the battlefield. Player ID: {PLAYER_ID}")

all_messages = []
ui_messages = []
turn_submitted = False
game_started = False
ws_connection_id = None

async def ws_game_channel():
    """Connect to game server (9080) as player channel. Receives game state if session-bound."""
    global ws_connection_id, game_started

    uri = f"{GAME_WS}/events?playerId={PLAYER_ID}&guestMode=true"
    print(f"[WS] Connecting to game server: {uri}")

    try:
        async with websockets.connect(uri, open_timeout=15, close_timeout=5) as ws:
            print("[WS] Connected to game server!")

            # Receive initial messages
            msg = await ws.recv()
            all_messages.append(msg)
            obj = json.loads(msg)

            # Respond to ping
            if obj.get('method') == 'client.ping':
                ws_connection_id = obj.get('params', {}).get('echo', PLAYER_ID)
                print(f"[WS] Pong sent, server assigned ID: {ws_connection_id}")
                await ws.send(json.dumps({
                    "type": "request", "id": obj.get('id'), "method": "client.pong",
                    "params": obj.get('params', {})
                }))

            # Listen for game state / turn events
            start_time = time.time()
            while time.time() - start_time < TURN_TIMEOUT:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    all_messages.append(msg)
                    obj = json.loads(msg)
                    t = obj.get('type', '')
                    m = obj.get('method', '')

                    if t == 'connection_state':
                        evt = obj.get('event', {})
                        print(f"[WS] CONN: {evt.get('playerId')} -> {evt.get('status')}")
                        if evt.get('status') == 'CONNECTED' and not game_started:
                            game_started = True
                            print("[WS] Game channel active!")

                    elif t == 'notification':
                        print(f"[WS] NOTIF {m}: {str(obj)[:200]}")
                        ui_messages.append(obj)

                        # Turn resolution received
                        if m == 'ui.forceShowTurnResolution':
                            print(f"[WS] TURN RESOLVED! Params: {str(obj.get('params',''))[:500]}")
                            return obj

                        # Map/player state received
                        elif m == 'ui.setLocalPlayer':
                            print(f"[WS] LOCAL PLAYER: {str(obj.get('params',''))[:300]}")
                        elif m == 'ui.updateProgressBar':
                            print(f"[WS] PROGRESS: {str(obj.get('params',''))[:200]}")
                        elif m == 'ui.agentWorkStream':
                            chunk = str(obj.get('params', {}).get('content', ''))[:100]
                            if chunk:
                                print(f"[WS] AGENT: {chunk}")
                        elif m == 'ui.thinkingUpdate':
                            print(f"[WS] THINKING: {str(obj.get('params',''))[:200]}")

                    elif t == 'response' and obj.get('id') == 'submit-turn':
                        print(f"[WS] TURN RESPONSE: {str(obj)[:500]}")

                except asyncio.TimeoutError:
                    # Send ping to keep alive
                    try:
                        await ws.ping()
                    except:
                        break
                    print(f"[WS] Still alive... ({(time.time()-start_time)/60:.1f} min in)")

    except asyncio.exceptions.WebSocketTimeoutError:
        print(f"[WS] Timeout after {TURN_TIMEOUT}s")
    except Exception as e:
        print(f"[WS] Error: {e}")

    return None

async def submit_turn():
    """Submit Lord Maple Tree's march order via game server WebSocket."""
    global turn_submitted

    if not ws_connection_id:
        ws_connection_id = PLAYER_ID

    uri = f"{GAME_WS}/events?playerId={PLAYER_ID}&guestMode=true"
    try:
        async with websockets.connect(uri, open_timeout=15, close_timeout=5) as ws:
            # Get ping and respond
            msg = await ws.recv()
            obj = json.loads(msg)
            if obj.get('method') == 'client.ping':
                await ws.send(json.dumps({
                    "type": "request", "id": obj.get('id'), "method": "client.pong",
                    "params": obj.get('params', {})
                }))

            await asyncio.sleep(1)

            # Submit turn
            submit_id = f"submit-{int(time.time())}"
            submit_msg = {
                "type": "request",
                "id": submit_id,
                "method": "game.submitAction",
                "params": {
                    "action": ORDER,
                    "playerName": "LordMapleTree"
                }
            }
            print(f"[WS] Submitting turn: {ORDER[:80]}...")
            await ws.send(json.dumps(submit_msg))
            turn_submitted = True
            print(f"[WS] Turn submitted (id={submit_id}), waiting for TPipe processing...")

            # Wait for resolution (up to 10 min)
            for _ in range(40):
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=15)
                    obj = json.loads(msg)
                    t = obj.get('type', '')
                    m = obj.get('method', '')

                    if t == 'notification' and m == 'ui.forceShowTurnResolution':
                        print(f"[WS] TURN RESOLVED!")
                        return obj
                    elif t == 'response' and obj.get('id') == submit_id:
                        print(f"[WS] Submit confirmed: {str(obj)[:300]}")
                except asyncio.TimeoutError:
                    await ws.ping()
                    print("[WS] Waiting for resolution...")

            return None

    except Exception as e:
        print(f"[WS] Submit error: {e}")
        return None

async def sse_matchmaking():
    """Connect to server-extend (7070) SSE for matchmaking events."""
    uri = f"{SERVER_EXTEND}/events?playerId={PLAYER_ID}&guestMode=true"
    print(f"[SSE] Connecting to server-extend: {uri}")

    req = urllib.request.Request(uri)
    try:
        with urllib.request.urlopen(req, timeout=TURN_TIMEOUT + 30) as resp:
            print("[SSE] Connected to server-extend!")
            for line in resp:
                line = line.decode().strip()
                if line.startswith('data: '):
                    data = json.loads(line[6:])
                    t = data.get('type', '')
                    m = data.get('method', '')
                    print(f"[SSE] {t} {m}: {str(data.get('params',''))[:200]}")
                    if m == 'MatchFoundNotification':
                        print(f"[SSE] *** MATCH FOUND! sessionId={data.get('params',{}).get('sessionId')}")
    except Exception as e:
        print(f"[SSE] Error: {e}")

async def main():
    print("=" * 60)
    print("LORD MAPLE TREE'S AUTOGENESIS CAMPAIGN - ROUND 3")
    print("=" * 60)

    # Start SSE matchmaking listener in background
    sse_task = asyncio.create_task(sse_matchmaking())
    await asyncio.sleep(1)

    # Send REST matchmaking request
    url = f"{SERVER_EXTEND}/rpc?playerId={PLAYER_ID}&guestMode=true"
    payload = json.dumps({
        "method": "server.extend.requestGame",
        "params": {
            "userName": "LordMapleTree",
            "gameType": "SINGLEPLAYER",
            "websocketId": PLAYER_ID,
            "aiOpponentCount": 1,
            "aiOnly": False,
            "selectedCommander": {
                "name": "Lord Maple Tree",
                "description": "Emperor of All Canada, Duke of the Golden Forest...",
                "type": "Land",
                "trait": "Researcher"
            }
        }
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read()
            print(f"[REST] HTTP {resp.status}: {body[:300] if body else '(empty)'}")
    except Exception as e:
        print(f"[REST] Error: {e}")

    # Wait for match
    print("\nWaiting for match to form...")
    try:
        await asyncio.wait_for(sse_task, timeout=60)
    except asyncio.TimeoutError:
        print("[SSE] Timeout waiting for match")

    await asyncio.sleep(5)

    # Connect to game server and submit turn
    print("\nConnecting to game server...")
    result = await submit_turn()

    if result:
        print("\n" + "=" * 60)
        print("TURN RESOLUTION RECEIVED!")
        print("=" * 60)
        print(json.dumps(result.get('params', {}), indent=2)[:2000])
    else:
        print("\n[MAIN] Turn may still be processing — check server logs")

    # Summary
    print(f"\n[Summary] Total WS messages: {len(all_messages)}, UI messages: {len(ui_messages)}")
    ui_types = {}
    for m in ui_messages:
        t = m.get('method', '?')
        ui_types[t] = ui_types.get(t, 0) + 1
    for t, c in sorted(ui_types.items()):
        print(f"  {t}: {c}")

if __name__ == '__main__':
    asyncio.run(main())
