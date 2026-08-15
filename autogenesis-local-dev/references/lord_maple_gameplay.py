#!/usr/bin/env python3
"""
Autogenesis direct gameplay script — Lord Maple Tree Edition.

Connects to the game server WebSocket and plays turns for Lord Maple Tree.
Requires:
  - Servers running (:server:run, :server-extend:run, runKvisionNoHotReload)
  - Browser open at http://127.0.0.1:8080/?skipLogin=true (provides connection IDs)
  - Matchmaking already triggered via curl RPC

Usage:
  1. Start servers
  2. Open browser, get kvision-ws ID from logs:
     tail -f ~/.autogenesis/logs/autogenesis-$(date +%Y-%m-%d)*.log | grep "kvision-ws.*registered"
  3. Get rest-client ID from server-extend logs:
     tail -f ~/.autogenesis/logs/server-extend-$(date +%Y-%m-%d)*.log | grep "rest-client.*SSE"
  4. Send matchmaking curl RPC (see SKILL.md)
  5. Run: python3 lord_maple_gameplay.py

Edit WS_ID and ACTION below before running.
"""
import asyncio, json, time
from websockets.asyncio.client import connect

# ===== CONFIGURATION =====
WS_ID = "kvision-ws-client-CHANGE-ME"  # e.g. "kvision-ws-client-1283398400"
GAME_SERVER = "127.0.0.1"
GAME_PORT = 9080
# ===== LORD MAPLE TREE'S NEXT ORDERS =====
ACTION = "I mobilize my Ent army and march toward enemy territory, spreading maple syrup as we march."
# ================================

async def main():
    uri = f"ws://{GAME_SERVER}:{GAME_PORT}/events?playerId={WS_ID}&guestMode=true"
    print(f"[{time.strftime('%H:%M:%S')}] Connecting to {uri}")
    async with connect(uri) as ws:
        print(f"[{time.strftime('%H:%M:%S')}] Connected. Sending orders...")

        # Send Lord Maple Tree's march order
        await ws.send(json.dumps({
            "type": "request",
            "id": f"submit-{int(time.time())}",
            "method": "game.submitAction",
            "params": {
                "action": ACTION,
                "playerName": "LordMapleTree"
            }
        }))
        print(f"[{time.strftime('%H:%M:%S')}] ORDERS SENT. Awaiting battle results...")
        print("(TPipe takes ~4 min/turn. Sit tight.)\n")

        turn_done = False
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=300)
                data = json.loads(raw)
                method = data.get("method", "")
                params = data.get("params", {})

                if method == "ui.setLocalPlayer":
                    p = params.get("player", {})
                    print(f"\n=== LORD MAPLE TREE STATE ===")
                    print(f"  Name: {p.get('name')}")
                    print(f"  Territories: {[t.get('name') for t in p.get('capturedTerritory', [])]}")
                    print(f"  VP: {p.get('victoryPoints')} | Mil: {p.get('militaryPoints')} | Dip: {p.get('diplomacyPoints')} | Res: {p.get('researchPoints')}")
                    print(f"============================\n")

                elif method == "ui.setResolutionStep":
                    step = params.get("step", "")
                    msg = params.get("message", "") or ""
                    print(f"[{time.strftime('%H:%M:%S')}] RESOLUTION: {step} -- {msg[:100]}")

                elif method == "ui.narrativeChunk":
                    chunk = params.get("chunk", "")
                    print(f"[{time.strftime('%H:%M:%S')}] NARRATIVE: {chunk[:200]}")

                elif method == "ui.updateProgressBar":
                    cur = params.get("current", 0)
                    tot = params.get("total", 100)
                    if cur % 20 == 0 or cur == tot:
                        print(f"[{time.strftime('%H:%M:%S')}] PROGRESS: {cur}/{tot}")

                elif method == "ui.updateTurnTimer":
                    r = params.get("remainingSeconds", 0)
                    if int(r) % 60 == 0 or int(r) < 30:
                        print(f"[{time.strftime('%H:%M:%S')}] TIMER: {r}s")

                elif method == "ui.agentWorkStream":
                    # Lots of these — summarize to avoid spam
                    pass  # quiet: hundreds of chunks per turn

                elif method == "ui.thinkingUpdate":
                    thinking = params.get("thinking", "")[:100]
                    print(f"[{time.strftime('%H:%M:%S')}] THINKING: {thinking}")

                elif method == "ui.forceShowTurnResolution":
                    print(f"[{time.strftime('%H:%M:%S')}] Turn resolution triggered!")

                elif method == "ConnectionState":
                    print(f"[{time.strftime('%H:%M:%S')}] Connection: {params.get('event', {}).get('status')}")

                elif method == "ui.updateWorld":
                    world = params.get("world", {})
                    print(f"[{time.strftime('%H:%M:%S')}] World: {world.get('name', 'unknown')}")

                elif method == "notification":
                    pass  # ignore raw notifications

                elif method == "client.pong":
                    pass  # ignore pong

                else:
                    if method:
                        print(f"[{time.strftime('%H:%M:%S')}] {method}: {str(params)[:80]}")

            except asyncio.TimeoutError:
                elapsed = time.strftime("%-M:%S")
                print(f"[{elapsed}] (TPipe still thinking... {time.strftime('%H:%M:%S')})")

if __name__ == "__main__":
    asyncio.run(main())
