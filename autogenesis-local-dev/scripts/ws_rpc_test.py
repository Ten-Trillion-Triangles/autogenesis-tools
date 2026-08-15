#!/usr/bin/env python3
"""
Generic WebSocket RPC test script for the Autogenesis game server.

Bypasses the KVision browser UI entirely. Connects directly to the game
server WebSocket at port 9080 with an `accelbyteId` in the query string,
handles pong responses, and calls any server-side RPC method.

Use this when:
- The browser login is broken (KVision virtual DOM not firing handlers)
- You need to verify server-side code paths without a full game session
- You want to test resume/save flows with a real AccelByte userId

Usage:
    python ws_rpc_test.py <method> [<json-params>]
                          [--accelbyte-id <id>]
                          [--host <host>] [--port <port>]
                          [--player-id-prefix <prefix>]
                          [--wait <seconds>]

Examples:
    # Check if a snapshot exists for the guest test user
    python ws_rpc_test.py server.hasRunningGame

    # Restore a saved game
    python ws_rpc_test.py server.restoreRunningGame

    # Submit a turn action
    python ws_rpc_test.py game.submitAction '{"action": "test order", "playerName": "Test"}'

    # Custom accelbyteId (e.g. a real AccelByte user)
    python ws_rpc_test.py server.hasRunningGame --accelbyte-id 004c3eb02c0b4436b41b24d5d670b0e4

The script auto-handles `client.pong` requests by responding with the
matching id (critical — sending a new id causes `WorldManager.isReachable`
to return UNREACHABLE).
"""

import argparse
import base64
import json
import os
import socket
import struct
import sys
import time


def send_text(sock, msg):
    """Send a text frame over WebSocket (client must mask)."""
    data = msg.encode("utf-8")
    header = bytearray([0x81])  # FIN + text opcode
    length = len(data)
    mask_key = os.urandom(4)
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack(">Q", length))
    header.extend(mask_key)
    masked = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))
    sock.sendall(bytes(header) + masked)


def recv_text(sock, timeout=5):
    """Receive a single text frame. Returns None on timeout."""
    sock.settimeout(timeout)
    try:
        hdr = sock.recv(2)
        if len(hdr) < 2:
            return None
        length = hdr[1] & 0x7F
        if length == 126:
            length = struct.unpack(">H", sock.recv(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", sock.recv(8))[0]
        masked = hdr[1] & 0x80
        if masked:
            mk = sock.recv(4)
        else:
            mk = None
        data = b""
        while len(data) < length:
            chunk = sock.recv(min(4096, length - len(data)))
            if not chunk:
                break
            data += chunk
        if masked and mk is not None:
            data = bytes(b ^ mk[i % 4] for i, b in enumerate(data))
        return data.decode("utf-8", errors="replace")
    except socket.timeout:
        return None
    except Exception as e:
        print(f"[recv error] {e}", file=sys.stderr)
        return None


def build_handshake(host, port, player_id, accelbyte_id, guest_mode=False, role="PRIMARY"):
    key = base64.b64encode(os.urandom(16)).decode()
    path = (
        f"/events?playerId={player_id}"
        f"&accelbyteId={accelbyte_id}"
        f"&guestMode={'true' if guest_mode else 'false'}"
        f"&role={role}"
    )
    return (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "\r\n"
    ).encode()


def drain_loop(sock, duration=1.0, auto_pong=True):
    """Drain incoming frames for `duration` seconds, auto-responding to pongs."""
    end = time.time() + duration
    frames = []
    while time.time() < end:
        msg = recv_text(sock, 0.3)
        if msg is None:
            continue
        frames.append(msg)
        try:
            data = json.loads(msg)
            if auto_pong and data.get("type") == "request" and "pong" in data.get("method", ""):
                pong_id = data.get("id")
                send_text(sock, json.dumps({
                    "type": "response",
                    "id": pong_id,
                    "result": {"echo": "ok"}
                }))
        except Exception:
            pass
    return frames


def main():
    parser = argparse.ArgumentParser(description="WebSocket RPC test for Autogenesis game server")
    parser.add_argument("method", help="RPC method name (e.g. server.hasRunningGame)")
    parser.add_argument("params", nargs="?", default="{}", help="JSON params object")
    parser.add_argument("--accelbyte-id", default="004c3eb02c0b4436b41b24d5d670b0e4",
                        help="AccelByte user id (default: test guest user)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9080)
    parser.add_argument("--player-id-prefix", default="ws-rpc-test")
    parser.add_argument("--wait", type=float, default=2.0,
                        help="Seconds to wait for response")
    parser.add_argument("--drain-time", type=float, default=1.0,
                        help="Seconds to drain initial frames before sending RPC")
    args = parser.parse_args()

    try:
        params = json.loads(args.params)
    except json.JSONDecodeError as e:
        print(f"[error] Invalid JSON params: {e}", file=sys.stderr)
        sys.exit(1)

    player_id = f"{args.player_id_prefix}-{int(time.time() * 1000)}"

    # Connect
    sock = socket.create_connection((args.host, args.port), timeout=10)
    sock.sendall(build_handshake(args.host, args.port, player_id, args.accelbyte_id))

    # Read handshake response
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            print("[error] Connection closed during handshake", file=sys.stderr)
            sys.exit(1)
        resp += chunk
    status_line = resp.decode().split("\r\n")[0]
    print(f"Handshake: {status_line}")
    if "101" not in status_line:
        print(f"[error] Handshake failed: {resp.decode()}", file=sys.stderr)
        sys.exit(1)

    # Drain initial frames (handles CONNECTED notification + first ping)
    print(f"\n=== Drain initial frames ({args.drain_time}s) ===")
    initial = drain_loop(sock, duration=args.drain_time, auto_pong=True)
    for msg in initial:
        try:
            data = json.loads(msg)
            method = data.get("method", "")
            mtype = data.get("type", "")
            if "setLocalPlayer" in method:
                print(f"[SET_LOCAL_PLAYER] {str(data)[:300]}")
            elif mtype == "notification":
                print(f"[notif] {method}: {str(data)[:200]}")
        except Exception:
            pass

    # Send the RPC
    req_id = f"rpc-{int(time.time() * 1000)}"
    payload = {
        "type": "request",
        "id": req_id,
        "method": args.method,
        "params": params,
    }
    print(f"\n=== Sending {args.method} ===")
    print(f"Request: {json.dumps(payload)}")
    send_text(sock, json.dumps(payload))

    # Wait for response, auto-ponging
    print(f"\n=== Waiting {args.wait}s for response ===")
    deadline = time.time() + args.wait
    got_response = False
    while time.time() < deadline:
        msg = recv_text(sock, 0.5)
        if msg is None:
            continue
        try:
            data = json.loads(msg)
            if data.get("type") == "request" and "pong" in data.get("method", ""):
                pong_id = data.get("id")
                send_text(sock, json.dumps({
                    "type": "response",
                    "id": pong_id,
                    "result": {"echo": "ok"}
                }))
                continue
            if data.get("id") == req_id:
                print(f"\n*** Response for {args.method} ***")
                print(json.dumps(data, indent=2))
                got_response = True
                break
            else:
                method = data.get("method", "")
                if method:
                    print(f"[other msg] {method}: {str(data)[:200]}")
        except Exception:
            print(f"[raw] {msg[:200]}")

    if not got_response:
        print(f"\n[warn] No response received in {args.wait}s")

    sock.close()


if __name__ == "__main__":
    main()