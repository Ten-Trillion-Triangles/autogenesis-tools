#!/usr/bin/env python3
"""
aws_mcp_query.py — Direct JSON-RPC client for mcp-proxy-for-aws.

Bypasses the Hermes MCP loader entirely. Useful when:
  - Your session's toolset doesn't include `mcp_aws_*` tools
    (e.g. session started before MCP late-binding could fire, or
    hermes_workflow plugin is broken and the tool-snapshot is stale)
  - You want a single non-interactive AWS CLI call from a script
  - You're reproducing an AWS-MCP behavior and need a known-good client

Usage:
  /tmp/aws_mcp_query.py <tool_name> '<json_args>'
  /tmp/aws_mcp_query.py aws___call_aws '{"cli_command":"aws sts get-caller-identity"}'
  /tmp/aws_mcp_query.py aws___list_regions
  /tmp/aws_mcp_query.py aws___search_documentation '{"limit":3,"search_phrase":"cloudfront list-distributions","topics":["general"]}'

Output: pretty-prints the `result.content[*].text` blocks (or the error).

Captured 2026-07-03 from the "aws mcp not visible" investigation:
the AWS MCP server works fine when invoked directly. The 42 MB
mcp-stderr.log was a red herring — the server produces NO stdout banner
until it receives a JSON-RPC `initialize` request, so the Hermes loader
miscounted it as "failed to start" even though the connection was fine.
"""

import json, subprocess, sys, time

PROXY_CMD = [
    "uvx", "--quiet", "mcp-proxy-for-aws@latest",
    "https://aws-mcp.us-east-1.api.aws/mcp",
    "--metadata", "AWS_REGION=us-east-1",
]

INITIALIZE = json.dumps({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "shitty-bob-direct", "version": "1.0"},
    },
})

INITIALIZED = '{"jsonrpc":"2.0","method":"notifications/initialized"}'


def query(tool_name, arguments=None, timeout=60):
    args = arguments or {}
    call = json.dumps({
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": args},
    })

    proc = subprocess.Popen(
        PROXY_CMD,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    proc.stdin.write(INITIALIZE + "\n")
    proc.stdin.flush()
    time.sleep(2)
    proc.stdin.write(INITIALIZED + "\n")
    proc.stdin.flush()
    time.sleep(1)
    proc.stdin.write(call + "\n")
    proc.stdin.flush()

    started = time.time()
    while time.time() - started < timeout:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.2)
            continue
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == 2:
            proc.terminate()
            return msg

    proc.terminate()
    return {"error": "timeout", "elapsed": time.time() - started}


def main():
    tool = sys.argv[1] if len(sys.argv) > 1 else "aws___list_regions"
    arg_json = sys.argv[2] if len(sys.argv) > 2 else "{}"
    args = json.loads(arg_json) if arg_json else {}

    msg = query(tool, args)
    if "error" in msg and "result" not in msg:
        print(json.dumps(msg, indent=2))
        return

    content = msg.get("result", {}).get("content", [])
    for c in content:
        if c.get("type") == "text":
            print(c["text"])
        else:
            print(json.dumps(c, indent=2))


if __name__ == "__main__":
    main()
