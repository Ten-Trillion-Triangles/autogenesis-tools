# Autogenesis Tools — RUNBOOK

**Repo:** `autogenesis-tools`
**Purpose:** Devtools, skills, scripts, references, and templates that let a coding agent (LLM) boot, test, debug, deploy, and audit the [Autogenesis](https://github.com) KMP game server + KVision browser UI + AccelByte Service Extension.
**Audience:** (1) any human developer who wants to set up this repo against their own coding agent (Claude Code, Hermes, Cursor, Aider, OpenCode, Codex, etc.), (2) the LLM agent itself, which needs to know which skills to load, which scripts to run, and which dependencies to install before kicking off the automated test suites.

---

## Table of contents

1. [What this repo is](#1-what-this-repo-is)
2. [TL;DR — 5-minute setup](#2-tldr--5-minute-setup)
3. [System architecture at a glance](#3-system-architecture-at-a-glance)
4. [Prerequisites and dependencies](#4-prerequisites-and-dependencies)
5. [Installing the skills into various coding agents](#5-installing-the-skills-into-various-coding-agents)
6. [Booting the Autogenesis stack](#6-booting-the-autogenesis-stack)
7. [Running automated tests](#7-running-automated-tests)
8. [Skill directory map (48 skills)](#8-skill-directory-map-48-skills)
9. [Script catalog (60+ scripts)](#9-script-catalog-60-scripts)
10. [Verifying a fix before reporting it](#10-verifying-a-fix-before-reporting-it)
11. [Deploying to production](#11-deploying-to-production)
12. [Common failure modes and fixes](#12-common-failure-modes-and-fixes)
13. [Telemetry, logs, and traces](#13-telemetry-logs-and-traces)
14. [Conventions every skill enforces](#14-conventions-every-skill-enforces)
15. [Appendix — file layout reference](#15-appendix--file-layout-reference)

---

## 1. What this repo is

`autogenesis-tools` is a **portable toolkit** for working on the Autogenesis codebase. It is NOT the game itself — the game source lives in sibling directories (`~/Desktop/Workspaces/Autogenesis/Autogenesis/` and `~/Desktop/Workspaces/Open-Autogenesis/`). This repo contains the agents that fix it, test it, and deploy it.

Three deliverable shapes live in this repo:

| Shape        | Count   | What it is                                                                                                              |
|--------------|---------|-------------------------------------------------------------------------------------------------------------------------|
| **SKILL.md** | 48      | A reusable procedure packaged for an LLM coding agent. Loading it teaches the agent how to do one specific thing.        |
| **script**   | 60+     | A standalone shell, Node, or Python script that an agent (or human) runs to verify, build, screenshot, or transform.    |
| **reference** | 70+    | Long-form markdown or code that backs the skills — diagnostic recipes, worked examples, file:line evidence.             |
| **template** | 7       | Reusable skeletons for probes, blog posts, hero-image prompts, snippets, and Pipe/Manifold starters. |

The skills fall into four domains:

- **autogenesis-*** (13) — *booting, testing, debugging, and deploying Autogenesis.*
- **tpipe-*** (25, counting `tpipewriter-*`) — *TPipe library internals — agent orchestration, containers, traces, lorebooks, scripting, testing, docs maintenance.*
- **ttt-*** (7) — *Ten Trillion Triangles site (marketing, blogs, pricing, hero images, code snippets, code styler).*
- **operational utilities** (3) — `log-parser`, `log-writer`, `pump-station`.

**Two seed sister skills** sit under `references/` of `autogenesis-local-dev/` but logically belong with the toolset:
- `probes/guest-login.mjs` — proves real AccelByte OAuth login works end-to-end
- `templates/echo-verify-resume-probe.mjs` — copy-paste starter for login/resume probes

---

## 2. TL;DR — 5-minute setup

> **You need:** a workspace that already contains the Autogenesis source tree at `~/Desktop/Workspaces/Autogenesis/Autogenesis/`, the secrets repo at `~/Desktop/Workspaces/autogenesis-secrets/`, and an AGS-style service-extension setup. If those don't exist, see §4 and §11 first.

```bash
# 1. Clone or copy this repo
git clone git@github.com:TenTrillionTriangles/autogenesis-tools.git
cd autogenesis-tools

# 2. Make every script executable
find . -type f \( -name "*.sh" -o -name "*.py" -o -name "*.mjs" \) -exec chmod +x {} +

# 3. Verify your env matches the workspace paths the scripts assume
echo "AUTOGENESIS_HOME=$HOME/Desktop/Workspaces/Autogenesis/Autogenesis"
test -d "$HOME/Desktop/Workspaces/Autogenesis/Autogenesis" \
  && echo "workspace OK" \
  || echo "MISSING — clone https://github.com/.../Autogenesis first"

# 4. Install Python deps used by tooling scripts
pip3 install playwright python-dotenv

# 5. Install Node deps used by e2e probes
#    (the *target* repo's kvisionApp-e2e/ directory owns package.json —
#     cd there and `npm install`)

# 6. Smoke-test: does the script inventory render?
./autogenesis-local-dev/scripts/verify-map-pack.py --help

# 7. Smoke-test: do the boot scripts exist?
test -f ~/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/scripts/start_servers.sh \
  && echo "start_servers.sh present" \
  || echo "MISSING — see Section 6 to recreate the boot script"

# 8. (Optional) Wire this repo into your coding agent — see Section 5.
```

If both echoes return OK, you're ready. Section 6 covers the actual boot.

---

## 3. System architecture at a glance

Autogenesis is a **three-process game server** plus an AccelByte Service Extension, plus a webpack-dev-server-hosted KVision browser UI. Each tier has its own log sink, its own RPC surface, and its own `RUNBOOK` / operator notes:

```
                          Browser (KVision UI, webpack 8080)
                                        │
                          ┌─────────────┴─────────────┐
                          ▼                           ▼
                  WebSocket (port 9080)       REST + SSE (port 7070)
                          │                           │
                          ▼                           ▼
                  :server (Ktor+Netty)       :server-extend (Ktor, Python)
                  port 9080 + gRPC 9091      port 7070 + gRPC 9092
                          │                           │
                          └──────────► Bedrock ◄───────┘
                                       (LLM calls)
```

| Tier            | Gradle task                    | Port(s)             | Logs                                                          | Skills that own it                                    |
|-----------------|--------------------------------|---------------------|---------------------------------------------------------------|-------------------------------------------------------|
| Browser (KVision UI) | `:kvisionApp:jsBrowserDevelopmentRun` | 8080                | `~/.autogenesis/logs/browser-*.log`, `webpack-*.log`           | `autogenesis-local-dev`, `autogenesis-mobile-ui-support`, `autogenesis-resume-flow-e2e` |
| Main server     | `:server:run`                  | 9080 + 9091 (gRPC)  | `~/.autogenesis/logs/autogenesis-*.log`                       | `autogenesis-local-dev`, `autogenesis-rpc-patterns`, `autogenesis-trace-analysis`, `autogenesis-prompt-debugging` |
| Service extension | `:server-extend:run`         | 7070 + 9092 (gRPC)  | `~/.autogenesis/logs/server-extend-*.log`                     | `autogenesis-resume-flow-e2e`, `autogenesis-cors-deploy`, `autogenesis-web-push-notifications` |
| Bedrock LLM calls | (no port; called by `:server`) | n/a                  | `~/.tpipe/debug/trace/Round_<N>_Turn_<M>_<Name>/`              | `autogenesis-trace-analysis`, `tpipe-trace-parser`, `tpipe-trace-output-conventions` |

**Load-bearing invariants:**
- Browser's `WebSocketRpcBridge` is on port 9080; browser's `CommanderDataSync` REST goes to `https://prod.gamingservices.accelbyte.io/rpc` (NOT `server-extend`'s port 7070) — this trips up every session.
- `:server-extend` must come up FIRST on 7070 because the `:server` process proxies some flows through it.
- All three services must be alive before any UI probe runs (`ss -tlnp | grep -E ':(7070|8080|9080)'` must return three rows).

---

## 4. Prerequisites and dependencies

### Host tooling

| Tool             | Minimum version | Why                                                               | Install                                                                       |
|------------------|-----------------|-------------------------------------------------------------------|-------------------------------------------------------------------------------|
| **JDK**          | 17 (LTS)        | Gradle / Kotlin / Netty requirement                                | `sudo apt install openjdk-17-jdk`                                              |
| **Gradle**       | Wrapper-bundled | `gradlew` ships in the Autogenesis repo; never install globally   | n/a (use `./gradlew`)                                                          |
| **Node.js**      | 20 LTS          | Playwright probes + webpack-dev-server                             | `nvm install 20`                                                              |
| **npm**          | 10              | Resolves `playwright` in the kvisionApp-e2e workspace              | bundled with Node 20                                                          |
| **Python 3.11+** | recommended     | `verify-map-*.py`, `analyze_validator_trace.py`, lorebank tooling | `sudo apt install python3.11`                                                  |
| **Playwright**   | 1.40+           | e2e probing (browser, screenshots, computed styles)                | `pip3 install playwright && playwright install chromium`                      |
| **JDK signing tools** | n/a         | BouncyCastle depends on openssl on `$PATH` for SEC1→PKCS8 (push)  | `sudo apt install openssl`                                                    |
| **AGSL CLI / `extend-helper-cli` / `ams` uploader** | latest | AccelByte Extend deployment + per-namespace CORS config             | See §11 and §11.2 |
| **Browsers (Chromium + Firefox)** | latest stable | Playwright defaults                                            | bundled with `playwright install`                                             |

### System libraries

```bash
sudo apt update
sudo apt install -y \
  build-essential curl wget git \
  openjdk-17-jdk \
  python3.11 python3.11-venv python3-pip \
  nodejs npm \
  openssl ca-certificates \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libxkbcommon0 \
  libxcomposite1 libxdamage1 libxfixes1 libxrandr2 libgbm1 libasound2 \
  libpangocairo-1.0-0 libpango-1.0-0 libcairo2 \
  xvfb
```

The `libnss3`-etc. block is what Playwright needs to actually launch Chromium on Linux. `xvfb` is for headless server runs (`xvfb-run -a node probes/foo.mjs`).

### Workspace files

The scripts in `autogenesis-tools/` and the runbooks in the game repo (`server/RUNBOOK*.md`) hard-code paths under `~/Desktop/Workspaces/`. If your layout differs, either:

1. **Symlink the workspace to the expected path:**

   ```bash
   mkdir -p ~/Desktop/Workspaces
   ln -sfn /your/real/workspace/Autogenesis ~/Desktop/Workspaces/Autogenesis
   ln -sfn /your/real/workspace/autogenesis-secrets ~/Desktop/Workspaces/autogenesis-secrets
   ln -sfn /your/real/workspace/autogenesis-tools ~/Desktop/Workspaces/autogenesis-tools
   ```

2. **Patch the scripts.** Every Python/JS verifier takes a `--workspace` flag or reads `$AUTOGENESIS_HOME`. Set the env var and the scripts adapt.

### Per-environment configuration

Two property files drive the JVM at runtime. Place them under `~/.autogenesis/` (each script reads from there via the `ConfigSource.jvm.kt` resolver):

**`~/.autogenesis/accelbyte.local.properties`** — AccelByte IAM, OAuth, namespaces.
**`~/.autogenesis/bedrock.local.properties`** — AWS Bedrock model IDs, inference profiles.
**`~/.autogenesis/vapid_private.pem`** — VAPID keypair for Web Push (auto-provisioned by `:kvisionApp:generateVapidKeys`).

> The **public / open-source Autogenesis build** (in `Open-Autogenesis/`) deletes the literals from these and replaces them with `ConfigSource.property(...)`. If you fork, scrub before publishing — see `autogenesis-local-dev`'s `references/release-scrub-pattern.md` (in the parallel upstream repo) for the 9-item checklist.

### AGS plugin & Contact 7

**AGS plugin** = any AccelByte Gaming Services plugin that the game integrates against (CloudSave, IAM, Lobby, Matchmaking, etc.). Required plugins for Autogenesis:

| Plugin              | Used by                                              | Where to enable it                                              |
|---------------------|------------------------------------------------------|-----------------------------------------------------------------|
| CloudSave           | Resume snapshots (server-side persistence)            | AGS admin → your namespace → Plugins → CloudSave → enable       |
| IAM                 | Login (`Login as Guest`), OAuth, session tokens        | Always-on in every AGS namespace                                |
| Statistics          | Operator-cost dashboard (token tracking)               | AGS admin → Plugins → Statistics → enable                       |
| Achievements        | (Optional; reserved for future operator-facing badges) | AGS admin → Plugins → Achievements → enable (optional)         |

**Contact 7** is the AccelByte Service-Extension framework (`extend-helper-cli` and the AMS uploader). The server-extend module deploys to a namespace via:

```bash
# Configure credentials (one-time)
export AB_BASE_URL=https://<ENV>.gamingservices.accelbyte.io
export AB_CLIENT_ID=<client>
export AB_CLIENT_SECRET=<secret>

# Build + push the extension image
docker build -t autogenesis-server-extend:latest server-extend/
ams upload --image autogenesis-server-extend:latest --namespace <NAMESPACE>
```

See `autogenesis-cors-deploy/SKILL.md` for the full extension-deploy runbook including credential resolution and port-routing.

---

## 5. Installing the skills into various coding agents

This repo is **framework-agnostic**. Every skill is a single `SKILL.md` with optional `references/` + `scripts/` + `templates/` siblings. Drop the directory into the agent's skill root and it works.

### 5.1 — One-time layout (for any agent)

```text
<agent-skill-root>/
└── autogenesis-tools/                  # THIS repo, drop-in
    ├── RUNBOOK.md                      # ←  you are here
    ├── autogenesis-local-dev/
    │   ├── SKILL.md
    │   ├── references/
    │   ├── scripts/
    │   └── templates/
    ├── tpipe-*/                        # 24 sibling directories
    ├── ... etc ...
    └── ttt-*/                          # 8 sibling directories
```

> Most agents expect a **flat** directory of named skill folders, not a nested `autogenesis-tools/`. The supported shapes are listed below per agent.

### 5.2 — Hermes Agent

Hermes (this host) auto-loads skills from `~/.hermes/skills/`. Two install paths:

```bash
# A) Per-skill install (curated; what the operator uses):
cp -r autogenesis-tools/autogenesis-local-dev ~/.hermes/skills/
cp -r autogenesis-tools/autogenesis-resume-flow-e2e ~/.hermes/skills/
# ... repeat for every skill you want...

# B) Whole-bundle install (every skill, all 45):
cp -rT autogenesis-tools ~/.hermes/skills/autogenesis-tools/
# Then tell Hermes to use them via the umbrella name:
echo "autogenesis-tools" >> ~/.hermes/skills/.enabled.list  # if you curate that
```

Hermes's `skill_view(name='autogenesis-local-dev')` loads the bundle. `references/` files are addressed as `skill_view(name='autogenesis-local-dev', file_path='references/kvision-mobile-portrait-css.md')`.

> **Tip:** This repo's master branch is the canonical mirror. The operator's dev process was: import from `~/.hermes/skills/...` → `git add && git commit` here → the repo became the source of truth. If you fork, mirror that flow.

### 5.3 — Claude Code (`.claude/skills/`)

```bash
mkdir -p .claude/skills
cp -rT autogenesis-tools .claude/skills/autogenesis-tools
# Restart Claude Code. Skill names are derived from directory names.
```

To grant access to the entire umbrella, create `.claude/skills/autogenesis-tools/index.md` listing each `SKILL.md` with a one-line description, and put `@autogenesis-tools` in your prompt when you want the LLM to discover the catalog.

### 5.4 — Cursor (`.cursor/rules/` or `.cursor/skills/`)

```bash
mkdir -p .cursor/skills
cp -rT autogenesis-tools .cursor/skills/autogenesis-tools
# Cursor auto-loads *.md files in .cursor/rules/ — symlink or copy SKILL.md
# files into .cursor/rules/<name>.md for "always-on" injection.
```

### 5.5 — Aider (`--read` or `--config`)

```bash
# Per-session:
aider --read autogenesis-tools/RUNBOOK.md --read autogenesis-tools/autogenesis-local-dev/SKILL.md
# Persistent via config:
echo 'read: autogenesis-tools/RUNBOOK.md' >> .aider.conf.yml
```

Aider doesn't have a "skill" concept, but `READ` directives simulate one well — list each skill's `SKILL.md` here.

### 5.6 — Codex CLI / OpenCode CLI

```bash
# Codex CLI: pass as additional system-prompt context
codex --system-prompt-file autogenesis-tools/RUNBOOK.md

# OpenCode: drop into ~/.opencode/skills/
mkdir -p ~/.opencode/skills
cp -rT autogenesis-tools ~/.opencode/skills/autogenesis-tools
```

### 5.7 — Generic "load my tools"

For any agent that consumes a directory tree of `SKILL.md` blobs, the recipe is identical: `cp -rT autogenesis-tools <skill-root>/autogenesis-tools`, then start the agent.

### 5.8 — Verifying the install

After installing, smoke-test:

```bash
# Pick any skill and look for the trigger phrase
grep -E '^description:' <skill>/SKILL.md
# Expected: a one-line "Use when X" sentence.
```

If your agent has an `execute_skill` / `load_skill` tool, run it on `autogenesis-local-dev`. It should return without errors and disclose the trigger phrase.

---

## 6. Booting the Autogenesis stack

### 6.1 — The canonical startup sequence

The three-tier boot is orchestrated by `debugger/scripts/start_servers.sh` **inside the Autogenesis game repo** (not this tools repo). If you don't have that script yet, you can recreate it from §6.4.

```bash
cd ~/Desktop/Workspaces/Autogenesis/Autogenesis
./debugger/scripts/start_servers.sh   # starts ALL THREE services in order

# Health check
for i in $(seq 1 30); do
  ss -tlnp 2>/dev/null | grep -E ":?(7070|9080|8080)\b" | wc -l | grep -q 3 \
    && echo "stack up" && break
  sleep 2
done
```

**Expected ports:**

| Port | Service                | Health probe                                                  |
|------|------------------------|---------------------------------------------------------------|
| 7070 | server-extend (REST/SSE) | `curl -sN http://127.0.0.1:7070/health`  (custom; some impls: `/api/health`) |
| 9080 | server (WS)            | `curl -sN http://127.0.0.1:9080/health`                        |
| 9091 | server (gRPC)          | `nc -zv 127.0.0.1 9091`                                        |
| 9092 | server-extend (gRPC)   | `nc -zv 127.0.0.1 9092`                                        |
| 8080 | webpack-dev-server     | `curl -sI http://127.0.0.1:8080/`                              |

### 6.2 — Background-launch gotcha (Hermes / Claude Code / OpenCode)

When launching with `terminal(background=true, ...)`, the wrapper shell is **fresh** — it does not inherit filesystem state. If your foreground calls created `/tmp/foo`, the background call won't see it and any redirect `> /tmp/foo/log` will fail with "No such file or directory".

Always bake the `mkdir -p` into the background command itself:

```bash
mkdir -p /tmp/log && ./gradlew :server:run 2>&1 | tee /tmp/log/server.log
```

### 6.3 — Short turn timer for e2e

Default per-turn timer is ~5 minutes, which makes e2e probes take 5+ minutes per Phase 1. Override:

```bash
AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000 ./gradlew :server:run
```

(See `autogenesis-resume-flow-e2e/SKILL.md` for full env-var catalog.)

### 6.4 — Recreating the boot script

If your Autogenesis fork does not have `debugger/scripts/start_servers.sh`, recreate it:

```bash
mkdir -p ~/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/scripts
cat > ~/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/scripts/start_servers.sh << 'EOF'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
mkdir -p /tmp/log

# server-extend MUST start first (port 7070)
( cd "$ROOT" && \
  ./gradlew :server-extend:run --no-daemon 2>&1 ) > /tmp/log/server-extend.log &
EXTEND_PID=$!

# main server (port 9080)
( cd "$ROOT" && \
  ./gradlew :server:run --no-daemon 2>&1 ) > /tmp/log/server.log &
SERVER_PID=$!

# webpack dev server (port 8080)
( cd "$ROOT" && \
  AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000 ./gradlew :kvisionApp:jsBrowserDevelopmentRun --no-daemon 2>&1 ) > /tmp/log/webpack.log &
WEBPACK_PID=$!

trap "kill $EXTEND_PID $SERVER_PID $WEBPACK_PID 2>/dev/null" EXIT
echo "started; PIDs=$EXTEND_PID $SERVER_PID $WEBPACK_PID"
echo "  /tmp/log/server-extend.log  (port 7070)"
echo "  /tmp/log/server.log         (port 9080)"
echo "  /tmp/log/webpack.log        (port 8080)"
tail -F /tmp/log/server-extend.log &
wait
EOF
chmod +x ~/Desktop/Workspaces/Autogenesis/Autogenesis/debugger/scripts/start_servers.sh
```

### 6.5 — Pulling up just one service

```bash
# :server-extend only
./gradlew :server-extend:run

# :server only (needs :server-extend already running for some flows)
./gradlew :server:run

# :kvisionApp only (browser dev server; needs both servers running)
AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS=5000 \
  ./gradlew :kvisionApp:jsBrowserDevelopmentRun
```

### 6.6 — Login-bypass on the UI

Once the stack is up, navigate to `http://localhost:8080/`. Two bypass paths:

| Path                             | URL                                          | Use when                                              |
|----------------------------------|----------------------------------------------|-------------------------------------------------------|
| Synthetic guest, no AccelByte    | `http://localhost:8080/?skipLogin=true`      | Layout/visual tests, hover tests; no OAuth round trip |
| Real AccelByte OAuth login       | Click `data-testid="login-as-guest"`         | E2E tests that must prove the real AGS path           |

Use the **second path** for any "did the live backend do X correctly" test. `?skipLogin=true` has a 4-5 redundant `ServerExtendBridge.connect()` boot storm that triggers a "rpcInvoker is null" wedge (documented in `autogenesis-resume-flow-e2e` — wait ≥12s post-mount or use the real OAuth path).

### 6.7 — Kill sequence

```bash
# Kill the three gradle processes by port (most reliable)
for port in 7070 9080 8080; do fuser -k $port/tcp 2>/dev/null; done

# Optionally kill the gradle daemons
cd ~/Desktop/Workspaces/Autogenesis/Autogenesis && ./gradlew --stop
```

---

## 7. Running automated tests

There are **four** layers of tests, ordered from cheapest to most expensive:

### 7.1 — Source-tree verifiers (Python; ~50 ms; no JVM)

The fastest signal. Source-level checks of files on disk. Run first.

```bash
# Map pack integrity (zip + JSON + pin/connection consistency)
python3 autogenesis-tools/autogenesis-local-dev/scripts/verify-map-pack.py path/to/foo.map

# Map pack removal verification (for regression)
python3 autogenesis-tools/autogenesis-local-dev/scripts/verify-map-removal.py <MapName>

# Map exclusion (for tutorial/reserved maps)
python3 autogenesis-tools/autogenesis-local-dev/scripts/verify-map-exclusion.py tutorial
```

### 7.2 — Targeted JUnit suite (Gradle; ~70 s per suite)

For semantic verification — actual JVM behavior with the real classpath. Use the helper:

```bash
# Copy the helper to a session-specific name (operator convention)
cp autogenesis-tools/autogenesis-resume-flow-e2e/scripts/hermes-verify-targeted-suite.sh \
   /tmp/hermes-verify-mapupload-2026-08-16.sh

# Run a small set of suites
bash /tmp/hermes-verify-mapupload-2026-08-16.sh \
  MapUploadGateTest \
  MapUploadGateDownsamplePreFlightTest \
  MapUploadGatePackContentValidationTest
```

Output is parsed JUnit XML at `<suite>/build/test-results/test/TEST-<fqcn>.xml`. Exit non-zero on any failure.

### 7.3 — Per-class sweep (Gradle; one class at a time)

For class-level triage. From `autogenesis-tools/tpipe-test-patterns/scripts/per-class-sweep/`:

```bash
MINIMAX_API_KEY=sk-stub \
TPIPE_LIVE_LLM_TEST=false \
AllowTest=true \
TPIPE_ALLOW_INSECURE_BASEURL=true \
bash build-fqcns.sh   # writes the class list

bash run-class.sh :TPipe-Bedrock:test bedrockPipe.ConstructPipeTest
bash run-class.sh :test com.TTT.Pipeline.JunctionTest
```

Each invocation logs to `.hermes/test-results/per-class-sweep/per-class.log` with: `tests=N skipped=N failures=N errors=N`.

### 7.4 — End-to-end Playwright (Node.js; ~30 s per probe)

The proof. Real browser, real WS, real AGS, real screenshots.

```bash
# Login + resume flow
cd ~/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e
node probes/login-flow-e2e.mjs            # 11 assertions, must be 11/0
node probes/echo-verify-resume.mjs --phase=1
node probes/echo-verify-resume.mjs --phase=2
node probes/guest-login.mjs               # proves real AccelByte OAuth
node probes/capture-resume-flow.mjs       # saves 2 PNGs to artifacts-echo-verify/

# Map upload safety gate (full vertical)
node probes/map-upload-e2e.mjs

# Push notification round trip (needs AUTOGENESIS_DEV_PUSH_MOCK_PORT=9099)
node probes/push-turn-start.mjs
```

### 7.5 — Visual / computed-style probes (iPhone 12 mobile-portrait)

```bash
cd ~/Desktop/Workspaces/Autogenesis/Autogenesis/kvisionApp-e2e

# Mobile-portrait polish verification
node probes/mobile-portrait-polish.mjs

# Computed styles — proves CSS specificity / !important / cascade
node autogenesis-tools/autogenesis-local-dev/scripts/probe-computed-styles.mjs

# 6-modal visual inventory (MainMenu, Shop, Usage, Settings, Collection, Commander Creation)
node autogenesis-tools/autogenesis-local-dev/scripts/probe-mobile-polish.mjs
```

### 7.6 — TPipe trace parsing

For LLM-pipeline analysis post-hoc:

```bash
# Single trace → report
python3 autogenesis-tools/tpipe-trace-parser/scripts/parse_html_trace.py \
  ~/.tpipe/debug/trace/Round_1_Turn_0_Lord_Maple_Tree/Judge/trace.json

# Bulk pipeline summary + token totals
python3 autogenesis-tools/tpipe-trace-parser/scripts/extract_pipeline.py \
  --root ~/.tpipe/debug/trace/ --tokens-only

# Post-mortem (failed trace → top suspects)
python3 autogenesis-tools/tpipe-trace-parser/scripts/autogenesis_post_mortem.py \
  ~/.tpipe/debug/trace/Round_2_Turn_3_Failed_Trace/

# Strict verification of the parser contract
python3 autogenesis-tools/tpipe-trace-parser/scripts/verify_extraction.py --strict
```

### 7.7 — The "I'm not sure which layer" cheat sheet

| Symptom                                           | Run                                            |
|---------------------------------------------------|------------------------------------------------|
| "Map JSON looks malformed"                        | §7.1 source-tree                               |
| "Map renders but the catalogue thumbnail is blank"| §7.4–7.5 catalog visual + §7.6 HTML trace      |
| "Probe fails with `fail to fetch`"                | §6.1 stack-health + §6.6 OAuth bypass path     |
| "Login succeeds but resume dialog missing"        | §7.4 `login-flow-e2e.mjs` + `guest-login.mjs`   |
| "TPipe pipe kept the wrong content"               | §7.6 HTML trace + §7.2 targeted suite          |
| "Server console throws on boot"                   | §6.4 boot script + §12 common failures          |
| "The LLM fired but produced nonsense"             | §7.6 trace-parser + `autogenesis-post-mortem.py`|

---

## 8. Skill directory map (48 skills)

> Each row is one `SKILL.md` directory. **`trigger`** is the one-line "Use when X" description that coding agents match against your prompt. **`shape`** = `(s)` if it ships scripts, `(r)` if it ships references, `(t)` if it ships templates.

### Autogenesis domain — 13 skills

| Skill                                              | Trigger (paraphrased)                                                                                              | Shape        | Owner of                                                                                  |
|----------------------------------------------------|--------------------------------------------------------------------------------------------------------------------|--------------|-------------------------------------------------------------------------------------------|
| `autogenesis-local-dev`                            | Boot the game and run it locally                                                                                    | (s)(r)(t)    | Server startup, login, RPC contracts, map-pack install/removal, Mobile UI cookbook, post-scrub boot crash fixes |
| `autogenesis-mobile-ui-support`                     | Add mobile-portrait rendering to a widget                                                                           | (s)         | 10 widgets at iPhone 12 (390×844); `@media (max-width:600px)` overrides in `night-mode.css` |
| `autogenesis-resume-flow-e2e`                       | Claim a fix to login + resume + dialog                                                                              | (s)         | 11-assertion suite; screenshot proofs; `AUTOGENESIS_DEBUG_SHORT_TURN_TIMEOUT_MS` env var    |
| `autogenesis-rpc-patterns`                          | Add or debug an `@RpcMethod`                                                                                        | (r)         | KSP constraints, transport invokers, server-extend bridge, Kotlin 2.2 launch-parser quirks  |
| `autogenesis-trace-analysis`                        | Debug "why my play got rewritten" / "validator flyby" / "gemma swap" / "strategic-pipe stall"                          | (s)(r)      | Pipeline traces (`~/.tpipe/debug/trace/`) + lorebank narrative (`chat-*.bank`/`*.bank`); 11 pitfalls |
| `autogenesis-prompt-debugging`                     | Debug prose drift, hallucinated entities, wrong tone register, register-priming root cause                            | (r)         | ~30 LLM agents; 5-rule LLM contract; `judge-agency-rule-2026-08-09`                          |
| `autogenesis-game-mechanics`                       | Audit or change swing factors / pacing / karma / nemesis / win thresholds                                            | (r)         | Action costs, stat decay, karma, victory gates, validator 5-rule                              |
| `autogenesis-feature-audit`                         | "What is done / partial / not-done for X"                                                                            | (r)         | Three-bucket (✅⚠️❌) inventory via 5-reference sweep; tell-tale markers                  |
| `autogenesis-cors-deploy`                           | CORS error / new Amplify origin / new namespace CORS provisioning                                                     | (r)         | Two-layer (extend Ktor + per-namespace AGS platform); cookie-as-fallback                    |
| `autogenesis-verification-workflow`                 | TDD probe + dev-mode seam; bypass-flag anti-patterns                                                                  | (r)         | 256K-token image cap + iterated downsample + Pillow fallback                                |
| `autogenesis-web-push-notifications`                | Add or debug Web Push (VAPID/SW/multi-device/click-to-restore)                                                        | (r)         | VAPID PEM, service worker, `pushsubscriptionchange` rotation, multi-device fan-out            |
| `autogenesis-agent-pipe-model-audit`                | Migrate models / Bedrock Flex-tier routing / agent-pipe fleet scope                                                    | (r)         | Pipe-slot taxonomy (Main/Reasoning/Branch/Validator/Swap/Dead); file:line matrix            |
| `autogenesis-marketing`                             | Landing page / hero copy / premise sentence / demo asset                                                              | (r)         | 4-promise premise + canonical-doc discipline + 6 pitfalls                                  |

### TPipe library — 25 skills (24 `tpipe-*` + 1 `tpipewriter-*`)

> The middle column flags which skills ship **`(s)`** scripts, **`(r)`** references, **`(t)`** templates alongside their SKILL.md.

| Skill                                | Trigger (paraphrased)                                                                       | Shape | Owner of                                                            |
|--------------------------------------|---------------------------------------------------------------------------------------------|-------|----------------------------------------------------------------------|
| `tpipe-pipe-builders`                | Wire a TPipe `Pipe` (Bedrock/Mantle/MiniMax/OpenRouter/Ollama) + reasoning factory            | (r)(s) | Builder pattern, parent/child pipe alignment, Mantle auth path       |
| `tpipe-pipe-feature-audit`           | "Does feature X reach pipe Y?" / cross-provider parity / tier/cache silent no-op              | (r)   | 5-path wire recipe + streaming-observer 6th path; SDK-upgrade audits |
| `tpipe-pipe-internals`               | Inside `Pipe.kt` / DITL hook wiring / `execute` flow / context-not-flowing                     | (r)   | Pipe lifecycle, DITL hook points, `DummyPipe` consumer-side entry    |
| `tpipe-pipeline-patterns`            | Builder vs DSL / embedding containers / custom Pipe subclass                                  | (r)(t) | 4 required overrides for custom Pipe; `setIP`/`setPort` gotcha       |
| `tpipe-reasoning-pipes`              | `setReasoningPipe` / ReasoningSettings / cross-provider reasoning                             | (r)   | All `ReasoningMethod` variants + `ReasoningInjector` enum             |
| `tpipe-token-budgeting`              | Wire budget constraints / port Autogenesis per-pipe pattern                                  | (r)   | `TokenBudgetSettings` field docs; 5 `MultiPageBudgetStrategy` modes   |
| `tpipe-context-budget-truncation`    | Context-budgeting math / model-swap sizing / binary-token counting                            | (r)   | `calculateAvailableContext()` formula; binary-token design space     |
| `tpipe-context-pull-builder-repair`   | Dead "pull from X" builders; merge-order broken                                              | (r)(s) | 6-step TDD recipe; deep-copy-before-merge; 7-test matrix              |
| `tpipe-ditl-hook-design`             | Add a DITL hook to a Pipe / PathObject lifecycle                                              | (r)   | Field/setter/invocation contract; nullable `suspend` callback        |
| `tpipe-scripting`                    | Author a `.kts` script or REPL that consumes a published TPipe                                | (r)   | `kotlin-scripting-jsr223`; 7 JPMS workarounds; fatjar recipes         |
| `tpipe-test-patterns`                | Container/Junction/Manifold/DistributionGrid tests with P2PInterface agents                  | (r)(s) | Per-class sweep runner; `runBlocking` anti-pattern                    |
| `tpipe-trace-parser`                 | Parse TPipe trace HTML/JSON/markdown                                                          | (r)(s) | Verified parsers; `inputTokens = provider-billed`; 7-case baseline    |
| `tpipe-trace-output-conventions`     | TraceConfig / debug artifact / billing record on-disk                                         | (r)(s) | `TPipeConfig.getTraceDir()`; 4 files violating the rule              |
| `tpipe-traceserver-live-testing`     | TraceServer feature needing real-Netty/real-port JUnit                                        | (r)(s) | 8-step recipe; `@TestInstance(PER_CLASS)`; port-0 + tenant gotcha     |
| `tpipe-tuner`                        | "Tune TPipe for model" / find optimal truncation settings                                     | (r)   | `./TPipe-Tuner/tuner.sh`; output format; common failures              |
| `tpipe-agent-architecture`           | TPipe 3-layer builder/pipeline/runner convention in production                                | (r)   | Autogenesis 30+ agents canonical; 12+ standard kit calls              |
| `tpipe-json-serialization`           | "Why is prompt big?" / default-encoding fix / wire-payload audit                             | (r)   | 3-layer JSON model; `@EncodeDefault`; 2-pin pattern                    |
| `tpipe-lorebook-system`              | Lorebook design / selection / merge / contextLock / persistence                              | (r)   | NovelAI-compatible keyword-triggered weighted context                |
| `tpipe-lorebook-agent-authoring`     | Write lorebook-extraction pipe; debug empty/stomped lorebank                                  | (r)   | 7-component canonical pattern + 7 failure modes                        |
| `tpipe-pcp-code-execution`           | PCP transports / debugging PCP / extending transport or security                              | (r)   | 6 transports (Stdio/Http/Tpipe/Python/Kotlin/JS); 4 security mgrs   |
| `tpipe-pipe-internals`               | (cross-listed)                                                                               | —     | —                                                                    |
| `tpipe-editions`                     | TPipe license / which edition / AGPL vs Startup vs Commercial                                 | (r)   | Tri-license model; `startup-license` canonical; 4 distinguishing clauses |
| `tpipe-edition-branch-catchup`       | "Catchup startup-license" / merge main into startup-license                                  | (r)   | LICENSE/README/POM-boundary preservation; `backup/<branch>-pre-<TS>` convention |
| `tpipe-docs-maintenance`             | "Update docs" / "audit docs" / "sync TPipe docs to ttt-site"                                  | (r)(s)(t) | Branch-anchored diff; 3-place update pattern                          |
| `tpipe-generic-openai`               | `GenericOpenAIPipe` streaming / API mode selection / Ktor executeStreamingDirect audit       | (r)(s) | OpenAI/Anthropic/OpenAIResponses wire-shape; Mantle/Gemma stall      |
| `tpipewriter-feature-delivery`       | TPipeWriter slash command / runtime-overridable variable / TPipeSettings / /help audit       | (r)   | 4-surface TUI/CLI rule; 5th inspector surface; system-prompt audit     |

### TTT marketing site — 7 skills

| Skill                            | Trigger (paraphrased)                                          | Shape       | Owner of                                                |
|----------------------------------|----------------------------------------------------------------|-------------|---------------------------------------------------------|
| `ttt-code-styler`                | Apply TTT code styling to any C-family language (TS/JS/C/C++/C#/Java/Kotlin) | (r)(s)      | Uniform brace/spacing/naming + Kotlin `when` rule; `safe_same_line_brace_fix.py` recipe |
| `ttt-site-backend-debugging`     | TTT site live-backend issues (contact form / SES / Lambda / DDB / index)  | (r)(s)      | Per-layer trace-every-layer playbook (account 521369004927 / us-east-1 / zone Z0266992GQSG7W4H336) |
| `ttt-site-blog`                  | Write a technical tutorial blog post for the TTT site          | (r)(s)(t)   | Apex voice rules + code-first + copula-blacklist         |
| `ttt-site-code-snippets`         | Verify TPipe API accuracy; add syntax-highlighted snippets       | (r)(s)(t)   | `canonical-bedrock-snippet.kt`; Shiki 4.x per-token colors; broken-snippet sweep |
| `ttt-site-comparison-pages`      | Rewrite/add competitor/comparison marketing copy              | (r)(s)      | Strength-first positioning; verified claims; hedge-phrase audit (`hedge-phrase-audit.sh`) |
| `ttt-site-hero-images`           | Generate, audit, optimize, wire a hero image                    | (r)(s)(t)   | mmx-cli generate → audit → PNG→WebP → frontmatter patch |
| `ttt-site-pricing`               | TPipe/TTT site pricing page updates                            | (r)         | License tiers (Community/Startup/Commercial/Enterprise); PublishPoint CloudFront URLs; version-1.0.15 bumping |

### Operational utilities — 3 skills

| Skill           | Trigger (paraphrased)                                       | Shape       | Owner of                                                  |
|-----------------|-------------------------------------------------------------|-------------|-----------------------------------------------------------|
| `log-parser`    | Read/analyze project logs (32K-line patterns etc.)           | (r)(s)      | Log-format discovery, JSON-payload extraction, 26-bug catalog |
| `log-writer`    | Add structured logging to a function                         | (r)         | Logger category/level rules, multi-tier flow tracing      |
| `pump-station`  | Work on TPipe PumpStation (judge/dispatch/path harness)      | (r)(s)(t)   | 8 magic contracts, `ConverseRole.harness` tier, defect catalog |

### Two cross-cutting resources

These aren't `SKILL.md`-shaped but are references the skills reuse:

- `autogenesis-local-dev/references/lord_maple_gameplay.py` — example Python controller that drives the game over websocket. Look here for the canonical "play the game from CLI" pattern.
- `autogenesis-local-dev/templates/echo-verify-resume-probe.mjs` — copy-paste starter for any login/resume probe.

---

## 9. Script catalog (60+ scripts)

### Source-tree verifiers (Python)

| Script                                                       | Purpose                                                            | Runtime  |
|--------------------------------------------------------------|--------------------------------------------------------------------|----------|
| `autogenesis-local-dev/scripts/verify-map-pack.py`           | ZIP + JSON + pin/connection consistency for a `.map` file          | <0.1 s   |
| `autogenesis-local-dev/scripts/verify-map-removal.py`        | Regression check after a map has been removed from gameplay        | <0.1 s   |
| `autogenesis-local-dev/scripts/verify-map-exclusion.py`       | Reserved/tutorial-map exclusion (4-path discovery)                 | <0.1 s   |
| `tpipe-pipe-builders/scripts/hermetic-pipe-cutover-verifier.sh` | Hermetic post-edit pipe-family cutover verification             | <1 s     |
| `tpipe-context-pull-builder-repair/scripts/verify-context-pull-builder.sh` | Per-cutover line-by-line read-from-X builder verification | <1 s   |
| `tpipe-trace-output-conventions/scripts/verify-loop-guard-tripped-meta.sh` | Trip-counters on harness loop-guard  | <1 s |
| `tpipe-generic-openai/scripts/run_tpw_full_test.sh`           | TPipeWriter full integration sweep                                 | ~5 min   |
| `tpipe-test-patterns/scripts/per-class-sweep/{build-fqcns,run-class,run-list}.sh` | Per-class JUnit triage | ~10 s/class |
| `tpipe-docs-maintenance/templates/sync-tpipe-docs-deterministic.py`                | Audit TPipe docs against current API surface (deterministic) | ~30 s      |
| `pump-station/scripts/verify-pumpstation-defect-fix.sh`       | Verify a single PumpStation defect fix holds end-to-end            | ~1 min   |

### Browser automation (Playwright via Node.js .mjs)

| Script                                                                                  | Purpose                                                              |
|------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| `autogenesis-local-dev/scripts/probe-computed-styles.mjs`                                | Computed-style probe — proves CSS specificity / cascade reached DOM  |
| `autogenesis-local-dev/scripts/probe-mobile-polish.mjs`                                  | 6-modal mobile-portrait visual inventory at iPhone 12 viewport        |
| `autogenesis-mobile-ui-support/scripts/hermes-verify-mobile-ui.sh`                       | Per-commit ad-hoc mobile UI verification (CSS+selectors+probe syntax) |
| `autogenesis-mobile-ui-support/scripts/hermes-verify-adhoc-injected-html.mjs`            | Ad-hoc HTML injection verification                                    |
| `autogenesis-mobile-ui-support/scripts/hermes-verify-adhoc-positional.mjs`               | Ad-hoc positional CSS verification                                    |
| `autogenesis-mobile-ui-support/scripts/hermes-verify-multi-viewport-template.mjs`        | Multi-viewport render verification                                    |
| `autogenesis-resume-flow-e2e/scripts/hermes-verify-targeted-suite.sh`                    | Targeted JUnit suite receiver (server-extend tests)                  |
| `autogenesis-local-dev/scripts/capture-resume-proof.mjs`                                 | Screenshot capture (dialog + resumed game) for user-proof             |
| `tpipe-trace-parser/scripts/find-live-tests.sh`                                          | Locate the live-test classes inside the TPipe tree                   |
| `tpipe-trace-parser/scripts/stress-test-parsers.sh`                                      | Stress-test the trace parsers against fixtures                        |
| `tpipe-trace-parser/scripts/run_r1t0_attribution.sh`                                     | Round-1-Turn-0 attribution recipe                                     |
| `ttt-site-blog/scripts/local-paths-to-github-blobs.py`                                   | Local path → github blob conversion for PR links                      |
| `ttt-site-code-snippets/scripts/sweep-broken-bedrock-snippet.sh`                         | Sweep ttt-site for snippets that no longer match current Bedrock API   |
| `ttt-site-comparison-pages/scripts/hedge-phrase-audit.sh`                               | Hedge-phrase grep on competitor pages                                  |
| `ttt-site-backend-debugging/scripts/check-backend-state.sh`                             | Smoke the live ttt-site backend                                        |
| `ttt-site-backend-debugging/scripts/aws_mcp_query.py`                                    | One-shot AWS MCP query helper                                          |
| `ttt-site-code-styler/scripts/diff_line_extractor.py`                                    | Extract diff lines for review                                          |
| `ttt-site-code-styler/scripts/safe_same_line_brace_fix.py`                               | Single-line brace fix                                                  |
| `ttt-site-hero-images/scripts/optimize-hero.sh`                                          | Optimize a hero image                                                  |

### TPipe trace parsers (Python — verified against ground truth)

```text
scripts/
├── parse_html_trace.py        # HTML trace → structured events
├── parse_json_trace.py        # JSON trace → structured events
├── parse_markdown_trace.py    # markdown trace → structured events
├── parse_pumpstation_html.py  # PumpStation-specific HTML → events
├── parse_agent_trace.py       # Plain agent trace JSON → events
├── extract_pipeline.py        # Single pipeline → event-type aggregates (--tokens-only)
├── extract_judges.py          # Pull Judge pipe verdicts
├── autogenesis_attribution.py # Trace → text attribution
├── autogenesis_post_mortem.py # Failed trace → top-5 suspects
├── bulk-pumpstation-defect-audit.py  # Bulk audit across many traces
├── generate_report.py         # Multi-trace → HTML report
└── verify_extraction.py       # 7-case strict baseline (--strict)
```

```bash
# Canonical parser-flow for one trace
python3 scripts/parse_html_trace.py <trace.html> > parsed.json
python3 scripts/extract_pipeline.py --pipeline-id <id> <parsed.json>
python3 scripts/verify_extraction.py --strict   # 7/0 = clean baseline
```

### Logging utilities

- `log-parser/scripts/detect_framework.py` — sniff which logging framework a project uses
- `log-parser/scripts/find_log_locations.py` — locate log sinks
- `log-parser/scripts/quick_validate.py` — quick log-line validator

### Operator / campaign

- `autogenesis-local-dev/scripts/lmt_autogenesis.py` — Lord Maple Tree bot (campaign controller). Example of driving the full UI from Python over the WS bridge.
- `autogenesis-local-dev/scripts/memory_sampler.py` — JVM memory sampler (`jcmd`/`jstat` polling)
- `autogenesis-local-dev/scripts/ws_rpc_test.py` — Raw WS RPC smoke test
- `autogenesis-trace-analysis/scripts/analyze_validator_trace.py` — Validator pipeline 3-stage walk-through with auto-tagging
- `autogenesis-trace-analysis/scripts/find_lorebanks.py [persona-substring]` — list matching lorebank files
- `pump-station/scripts/verify-pumpstation-defect-fix.sh` — defect-fix end-to-end verifier
- `pump-station/references/pumpstation-defect-audit-script.py` — bulk defect sweep (lives under `references/` but is a runnable Python audit tool)

### Template-skeleton index (7 template dirs)

| Template dir                                  | Starter files shipped                                                                |
|----------------------------------------------|--------------------------------------------------------------------------------------|
| `autogenesis-local-dev/templates/`           | `echo-verify-resume-probe.mjs` — copy-paste starter for login/resume probes            |
| `pump-station/templates/`                    | `pumpstation-defect-dispatch-context.md` — defect-dispatch context starter                |
| `tpipe-docs-maintenance/templates/`          | `sync-tpipe-docs-deterministic.py` — docs vs API audit determinizer                   |
| `tpipe-pipeline-patterns/templates/`         | `hello-pipe.kt`, `hello-ollama-pipe.kt`, `scope-dsl-manifold.kt` — minimal Pipe/Manifold starters |
| `ttt-site-blog/templates/`                   | `blog-post-template.md`, `hero-image-prompt.md`                                        |
| `ttt-site-code-snippets/templates/`          | `canonical-bedrock-snippet.kt`                                                          |
| `ttt-site-hero-images/templates/`            | `hero-image-prompt.md`                                                                  |

---

## 10. Verifying a fix before reporting it

Per the operator's stated contract (verbatim, 2026-06-27): *"I don't trust you. So you are going to e2e test this and verify its working the way I stated it needs to."*

**Before any "fixed" message:**

1. **Source-tree verifier** (§7.1) if applicable.
2. **Targeted JUnit suite** (§7.2) covering the touched code.
3. **End-to-end Playwright** (§7.4) covering the user-visible surface.
4. **Screenshots** (if UI-touched) saved under `~/Desktop/Workspaces/Autogenesis/screenshots/<YYYY-MM-DD>-<topic>/`.
5. **Receipts in the report:** file:line + JUnit XML test counts + screenshot path + before/after contrasted.
6. **Tests must fail RED on wrong code.** A sentinel that doesn't fail RED is theater. See `autogenesis-resume-flow-e2e`'s TDD section for the rule.
7. **PATCH tool failure mode:** `patch` retries can drop the `path` parameter; if you hit the same error 3×, switch to terminal-based Python text replacement (recipe in §13.4 of `autogenesis-resume-flow-e2e/SKILL.md`).

**Report shape:** at most one short paragraph + screenshots + receipt. No defensive prose. No "let me show you the evidence" essay — that's the Class 8 trap (operator's `did it work` report → defensive verification dissertation).

---

## 11. Deploying to production

### 11.1 — Pre-deploy checklist

- [ ] All three test layers pass on the last commit (§7)
- [ ] AWS Bedrock model IDs in `bedrock.local.properties` resolve and have valid ARN/quota in the target region
- [ ] VAPID keypair at `~/.autogenesis/vapid_private.pem` (auto-generated by `:kvisionApp:generateVapidKeys`)
- [ ] AccelByte AB_BASE_URL / AB_CLIENT_ID / AB_CLIENT_SECRET in `accelbyte.local.properties`
- [ ] CloudSave plugin enabled in the target namespace
- [ ] Per-namespace CORS config committed to `server/RUNBOOK_PUSH.md` (cookies_allowed=true, allowed_domains includes the live origin)
- [ ] At least one fresh login + resume cycle observed on a deployed build before "ship it"

### 11.2 — Deploy sequence

```bash
# 1. Build release artifacts
./gradlew clean build -PpublishVersion=<X.Y.Z> --no-daemon

# 2. Build + tag the server-extend Docker image
docker build -t autogenesis/server-extend:<X.Y.Z> server-extend/

# 3. Push to your image registry (ECR, Docker Hub, etc.)
docker push autogenesis/server-extend:<X.Y.Z>

# 4. Upload the extension to the target AGS namespace via AMS CLI
ams upload \
  --image autogenesis/server-extend:<X.Y.Z> \
  --namespace <NAMESPACE> \
  --service autogenesis-server-extend

# 5. Bind the extension's port mapping
#    (verify the AMS dashboard shows the container healthy on the expected port)

# 6. Build the KVision bundle and ship to your static host (Amplify / S3+CF / Vercel)
./gradlew :kvisionApp:jsBrowserProductionWebpack --no-daemon
aws s3 sync kvisionApp/build/dist/js/main/ \
  s3://<BUCKET> --delete --cache-control "public, max-age=300"

# 7. CloudFront / CDN cache invalidation
aws cloudfront create-invalidation \
  --distribution-id <DISTRIBUTION_ID> \
  --paths "/*"

# 8. Smoke the live URL — login as guest, click Commander, verify the resume
#    dialog appears for a user with a saved game.

# 9. Confirm CORS (§4 + §11.3 below)
```

> **Port-routing failure mode (autogenesis-cors-deploy pitfall):** the AMS dashboard may show the route on port 8000 while your container listens on 7070 — the proxy routes to the wrong port and you see `l5d-proxy-error ... service in fail-fast` even though the JVM started fine. Pin the container's `PORT` env var explicitly to 7070.

### 11.3 — CORS one-shot (operator curl)

Run **per namespace**:

```bash
ENV=production   # or 'staging'
NAMESPACE=<your-namespace>
LIVE_ORIGIN=https://your-live-origin.com

curl 'https://'${ENV}'.gamingservices.accelbyte.io/config/v1/admin/namespaces/'${NAMESPACE}'/configs' \
  -H 'content-type: application/json' \
  --data-raw '{"key":"CORS","isPublic":false,"value":"{\"allowed_domains\":[\"'${LIVE_ORIGIN}'\"],\"allowed_headers\":[],\"expose_headers\":[],\"allowed_methods\":[],\"cookies_allowed\":true,\"max_age\":600}"}'

# Verify
curl 'https://'${ENV}'.gamingservices.accelbyte.io/config/v1/public/namespaces/'${NAMESPACE}'/configs/CORS' | jq
```

Three required fields: `allowed_domains` (your live origin), `cookies_allowed: true` (IAM cookie is the auth fallback), and `max_age: 600` (10-min preflight cache).

### 11.4 — Rollback

```bash
# Revert server-extend to the previous image
ams upload \
  --image autogenesis/server-extend:<previous-tag> \
  --namespace <NAMESPACE> \
  --force

# Revert the frontend bundle (S3 rollback)
aws s3 cp s3://<BUCKET>/<OLD_BUNDLE_PATH> s3://<BUCKET>/<path> --recursive

# Re-invalidate CDN
aws cloudfront create-invalidation --distribution-id <DIST> --paths "/*"
```

---

## 12. Common failure modes and fixes

### 12.1 — Boot failures

| Symptom                                                                                  | Likely cause                                  | Fix                                                                   |
|------------------------------------------------------------------------------------------|----------------------------------------------|-----------------------------------------------------------------------|
| `compileKotlinJs FAILED` on `val x: String get() = ...`                                  | Kotlin forbids property-getter on a local     | Replace with plain `val x: String = ...`                                |
| `compileKotlinJs FAILED` on `var x: String get() = ...` with no setter                   | `var` needs both getter and setter            | Convert to `val`, or add a setter                                      |
| `compileKotlinJs FAILED` on `data?.x` where `data: dynamic`                              | Kotlin forbids `?.` on `dynamic`              | `val c = js("({})"); c.field = data.x`                                |
| `jsBrowserDevelopmentRun FAILED` `Identifier 'path' has already been declared`           | Two webpack.config.d files name the same binding | Rename one file's top-level to e.g. `pathModule`                   |
| `IllegalStateException: <file>.local.local.properties not found`                         | Property loader strips `.properties` but not `.local` | Patch `ConfigSource.jvm.kt` to also strip `.local` suffix        |
| `IllegalStateException: accelbyte.local.properties missing key 'AB_CORS_ALLOWED_ORIGINS'` | New key added but no file has it               | Derive the value at runtime (e.g. `AB_BASE_URL` minus `https://`)     |
| `:TPipe:TPipe-Bedrock:compileKotlin FAILED` `zip END header not found` on `TPipe-1.0.0.jar` | Stale includeBuild jar from a killed build  | `rm ~/Desktop/Workspaces/TPipe/TPipe/build/libs/TPipe-1.0.0.jar` and rebuild |

### 12.2 — UI / browser failures

| Symptom                                                            | Likely cause                                          | Fix                                                              |
|---------------------------------------------------------------------|-------------------------------------------------------|------------------------------------------------------------------|
| `ResumeOrNewDialog` re-mounts every ~60s                            | SSE reconnect re-fires push without dedup             | `ResumeAvailabilityListener` idempotency + push-service dedup    |
| "rpcInvoker is null" `MapUploadModal: ServerExtendBridge.rpcInvoker is null (disconnected); aborting publish` | ?skipLogin boot-storm | Wait ≥12s post-mount + bind a benign RPC first; or use real OAuth login |
| Modal clipping on mobile                                            | `@media` block missing on the new widget              | Add the same breakpoint rules as the existing 9 widgets          |
| `FAIL: Loading screen CTA not found`                                | Skipping past the loading screen                        | Wait for `[data-testid="loading-screen-cta"]` → click → wait for `[data-testid="main-menu"]` |
| CORS `403 origin not allowed`                                       | Live origin not in server-extend allow-list            | Add origin to `ConfigSource` allow-list (defaults are additive)  |
| CORS `403 cookies_allowed: false` but login succeeds                 | IAM ingress strips `Authorization`; cookie fallback silent | Set `cookies_allowed: true` via §11.3                                |
| `Cannot send agent work stream, session not found` but WS still up    | Work-stream emitter is chasing a dead session          | Wait for harness timeout; turn-loop dispatch auto-recovers        |

### 12.3 — LLM / pipeline failures

| Symptom                                                                              | Likely cause                                                            | Fix                                                                 |
|--------------------------------------------------------------------------------------|-------------------------------------------------------------------------|---------------------------------------------------------------------|
| Web Push never lands                                                                 | VAPID PEM missing                                                      | `:kvisionApp:generateVapidKeys`; verify `~/.autogenesis/vapid_private.pem` exists |
| Push fires but click never re-opens                                                  | Service worker not registered for live origin                           | Add `manifest.webmanifest` with `display: standalone` (iOS requires PWA install) |
| TPipe trace HTML has duplicated tokens (`II must must`)                              | Agent-work-stream + ResponseRefinementAgent both attach to same pipe    | Drop recursion in `AgentWorkStreamStreaming.kt:107` + dedupe self-reg in `ResponseRefinementAgent.kt:99-110` |
| Streaming never completes                                                             | Broken Bedrock inference config (e.g. `bedrock.llamaScout17B` missing) | Fix the config key; harness will exit after the timeout and you can re-run |
| Probe shows `correct` content but game rejects it                                     | Jurisdiction-tier gate changed silently                                  | Re-run targeted suite + check `validator-and-judge-gates.md`         |
| Disk full after a long session                                                        | Trace directory + lorebank files rotate slowly                          | See §13.3                                                             |

---

## 13. Telemetry, logs, and traces

### 13.1 — Log locations

```text
~/.autogenesis/logs/
├── autogenesis-*.log          # main server (:server), port 9080
├── server-extend-*.log        # service extension (:server-extend), port 7070
├── webpack-*.log              # HMR / build errors, port 8080 (NOT useful for game state)
└── browser-*.log              # posts from the JS LogWriter via /api/browser-log

~/.tpipe/debug/trace/           # per-pipeline JSON + HTML traces (rotated)
~/.tpipe/TPipe-Default/memory/lorebook/  # chat-vs-world lorebanks
```

Server logs keep the 10 most recent files of each. Browser logs surface via DevTools (Chrome / Firefox) or Playwright's `page.on('console', msg => captured.push(...))`. **Do NOT rely on `localStorage['autogenesis_logs']`** — that sink was removed in 2026-08-12 (`LogWriter.js.kt:30`); it returns empty.

### 13.2 — Telemetry / cost dashboard

The operator-facing **`operatorCostUsd` field on `UsageEntry`** records per-turn Bedrock cost. To build the operator-cost dashboard:

1. Boot stack via §6.
2. Run `probes/operator-cost-dashboard.mjs` (or implement against the `UsageEntry` API).
3. Open `http://localhost:8080/operator` → Subscription economics view (Human tier / AI Player tier / NPC tier / cap risk).

### 13.3 — Trace lifecycle

- Traces are rotated. Old rounds may be gone by the time you investigate — *always check `~/.tpipe/debug/trace/` first*.
- `AUTOGENESIS_DEBUG_TRACE=false` (default) **clears the trace directory at boot** (the operational reason is privacy in shared workspaces; replay by re-running).
- For TPipe trace structure, see `autogenesis-trace-analysis/SKILL.md` (§"Two Complementary Surfaces").
- For the parser contract, see `tpipe-trace-parser/SKILL.md` — run `verify_extraction.py --strict` to confirm a clean baseline (`7/0 pass`) before trusting any extraction.

### 13.4 — Log parsing cookbook

```bash
# Most-recent server log line matching a phrase
ls -t ~/.autogenesis/logs/server-*.log | head -1 | xargs grep -n "Rehydrated running-game"

# All browser console logs from a Playwright run (via tmp capture)
cat /tmp/playwright-browser.log | grep -E '\[(ERROR|WARN)\]'

# Pipeline trace by round+player
ls ~/.tpipe/debug/trace/ | grep -i "Round_2_Turn_0"
```

For JSON payloads >50KB inside logs, `grep -o` to extract specific fields (full-grep truncates). See `log-parser/SKILL.md` for the streaming-parse recipes.

---

## 14. Conventions every skill enforces

### 14.1 — Logging style

```kotlin
// RIGHT — Logger system, category, key=value
Logger.info(LogCategory.NETWORK, "fetchSnapshot: ok userId=${userId} bytes=${snapshot.size}")
// WRONG — no category, raw println
println("got here")
```

| Level    | Use for                                                |
|----------|--------------------------------------------------------|
| `DEBUG`  | Verbose tracing; inputs, intermediate state, branches   |
| `INFO`   | One-time lifecycle events (started, completed, restored)|
| `WARN`   | Recoverable problems (retry, stale cache, fallback)     |
| `ERROR`  | Unrecoverable failures (caught exceptions, broken invariant) |

**Never:** `println`, `console.log`, `e.printStackTrace()` for non-debug. Never log secrets/tokens/session IDs in plaintext.

### 14.2 — RPC convention

```kotlin
@RpcMethod(name = "server.doThing", direction = RpcDirection.SERVER)
fun doThing(ctx: RpcCallContext, req: DoThingRequest): DoThingResponse { ... }
```

- **First parameter is `RpcCallContext`** (KSP-required) — not optional.
- Transport-specific invoker objects:
  - From `server`: `wsRpcInvoker`
  - From `server-extend`: `restRpcInvoker`
  - From `kvisionApp` → server: `WebSocketRpcBridge.rpcInvoker`
  - From `kvisionApp` → server-extend: `RestRpcBridge.rpcInvoker`
- Auto-registration is the contract (KSP generates providers). See `autogenesis-rpc-patterns` for the manual-register failure mode.

### 14.3 — Multi-tier flow logging

When a payload crosses UI → RPC → server → agent → LLM, add logs at each boundary with a stable correlation key:

```kotlin
// Tier 1: UI sender
Logger.info(LogCategory.UI, "DelegateWidget.save: submitting player='$playerName' length=${instructions.length}")
// Tier 2: RPC receiver ENTRY (BEFORE the first early-return)
Logger.debug(LogCategory.NETWORK, "setDelegateInstructions: ENTRY player='$playerName' incomingLength=${instructions.length}")
// Tier 3: Server STATE MUTATION (AFTER the mutex release)
Logger.info(LogCategory.NETWORK, "setDelegateInstructions: ok player='$playerName' length=${normalizedInstructions?.length ?: 0}")
// Tier 4: Pure-function transform
Logger.debug(LogCategory.LLM, "buildDelegateGuidanceBlock: ENTRY rawLength=$rawLength")
Logger.debug(LogCategory.LLM, "buildDelegateGuidanceBlock: EXIT blockLength=${block.length}")
// Tier 5: Pipeline injection
Logger.info(LogCategory.LLM, "StrategicPlanningPipe: injected delegate_guidance for $name")
// Tier 6: Orchestrator pre-build
Logger.info(LogCategory.LLM, "TurnHarness.handleAiTakeover: Pre-build for $name — delegateInstructionsLength=${player.delegateInstructions?.length ?: 0}")
```

A single `grep "$playerName" ~/.autogenesis/logs/server-*.log` should reconstruct the round trip.

### 14.4 — TDD discipline

Every TDD sentinel test must **fail RED against the existing wrong code** with a specific assertion failure that names the wrong shape. A test that passes for both the right and the wrong shape pins nothing.

```kotlin
// RIGHT
assertNotNull(pipe.reasoningPipe) { "expected a reasoning pipe for the safety-agent factory" }
// WRONG (passes vacuously for both shapes)
assertTrue(pipe.name.isNotBlank(), "pipe must have a name")
```

### 14.5 — Forbidden patterns

These bit the operator in production code and are off-limits unless reintroduced with explicit direction:

- Adding `bypassSafetyInDev` / `DEV_SAFETY_LIVE_TEST=1` env-gated bypass mechanisms to production code without operator direction.
- Refactoring `MapPackManager.unpack` / `MapUploadGate.uploadMapGate` to a "factory pattern" when the existing shape is the intended design.
- Calling `Logger.configure(...)` from inside a function (one-time at startup only).
- Re-registering a service worker on every page load with a different scope.
- Calling `subscribeIfPermitted()` outside a user gesture.

See `autogenesis-resume-flow-e2e/SKILL.md` "Forbidden Patterns" for the full list with rationale.

### 14.6 — Repository-specific rules

- **Always cd to the nested working tree** when invoking tooling against `Autogenesis`. The sibling `~/Desktop/Workspaces/Open-Autogenesis/` has a broken `PROJECT` calculation in `debugger/scripts/start_servers.sh` (one level too deep).
- **Do not modify LICENSE, README.md preamble, `build.gradle.kts` POM name, or `gradle/libs.versions.toml` across a catchup merge in the dual-tier publish flow** without operator direction — these are load-bearing.
- **Backup branches before any catchup merge** that touches dual-tier publish flow: `backup/<branch>-pre-publish-<version>-<TS>` for both `main` and `startup-license`.

---

## 15. Appendix — file layout reference

```text
autogenesis-tools/
├── RUNBOOK.md                   ← this file
├── .gitignore                   # OS / editor / Python noise
│
├── autogenesis-local-dev/       ← SKILL: Boot & run the game locally
│   ├── SKILL.md                 #   21,300+ lines of operator knowledge
│   ├── scripts/                 #   verify-map-pack.py, lmt_autogenesis.py, mobile probes, etc.
│   ├── references/              #   server-architecture, kvision pitfalls, map system, gameplay debugging
│   └── templates/               #   echo-verify-resume-probe.mjs
│
├── autogenesis-mobile-ui-support/
├── autogenesis-resume-flow-e2e/
├── autogenesis-rpc-patterns/
├── autogenesis-trace-analysis/
├── autogenesis-prompt-debugging/
├── autogenesis-game-mechanics/
├── autogenesis-feature-audit/
├── autogenesis-cors-deploy/
├── autogenesis-verification-workflow/
├── autogenesis-web-push-notifications/
├── autogenesis-agent-pipe-model-audit/
├── autogenesis-marketing/
│
├── tpipe-pipe-builders/         ← Plus 23 sibling `tpipe-*` skill directories
├── tpipe-pipe-feature-audit/
├── tpipe-pipe-internals/
├── tpipe-pipeline-patterns/
├── tpipe-reasoning-pipes/
├── tpipe-token-budgeting/
├── tpipe-context-budget-truncation/
├── tpipe-context-pull-builder-repair/
├── tpipe-ditl-hook-design/
├── tpipe-scripting/
├── tpipe-test-patterns/
├── tpipe-trace-parser/          # 13 trace-parsing scripts + 7-case strict baseline
├── tpipe-trace-output-conventions/
├── tpipe-traceserver-live-testing/
├── tpipe-tuner/
├── tpipe-agent-architecture/
├── tpipe-json-serialization/
├── tpipe-lorebook-system/
├── tpipe-lorebook-agent-authoring/
├── tpipe-pcp-code-execution/
├── tpipe-editions/
├── tpipe-edition-branch-catchup/
├── tpipe-docs-maintenance/
├── tpipe-generic-openai/
├── tpipewriter-feature-delivery/
│
├── ttt-code-styler/             ← Plus 7 sibling `ttt-*` skill directories
├── ttt-site-backend-debugging/
├── ttt-site-blog/
├── ttt-site-code-snippets/
├── ttt-site-comparison-pages/
├── ttt-site-hero-images/
├── ttt-site-pricing/
│
├── log-parser/                  # python log sniffers + 26-bug catalog
├── log-writer/
└── pump-station/                # TPipe PumpStation — 8 magic contracts
```

### 15.1 — Companion repos and paths

| Path                                                      | What lives there                                              |
|-----------------------------------------------------------|---------------------------------------------------------------|
| `~/Desktop/Workspaces/Autogenesis/Autogenesis/`           | The game source. `gradlew` is at the root.                    |
| `~/Desktop/Workspaces/Autogenesis/Open-Autogenesis/`      | Source-available scrubbed fork (open-source release build).   |
| `~/Desktop/Workspaces/Autogenesis/secrets-repo-...`       | Live AccelByte IAM + Bedrock ARN literals (private).          |
| `~/Desktop/Workspaces/TPipe/TPipe/`                       | TPipe library (consumed via `includeBuild` by Autogenesis).   |
| `~/.autogenesis/`                                         | Per-user runtime dir (logs, vapid, accelbyte.local.properties, …) |
| `~/.tpipe/`                                               | TPipe runtime dir (trace/, TPipe-Default/memory/lorebook/…)   |
| `~/.hermes/`                                              | Hermes agent runtime (skills/, profiles/, …).                  |

### 15.2 — Glossary

| Term               | Definition                                                                                              |
|--------------------|---------------------------------------------------------------------------------------------------------|
| `?skipLogin=true`  | Browser query string that bypasses AccelByte OAuth and loads a synthetic guest. **Has its own boot-storm.** |
| AccelByte (AGS)    | The gaming-services platform whose CloudSave, IAM, Statistics, Achievements, and Extend the game uses.   |
| AMS                | AccelByte Managed Service — the deployment plane for Service Extensions.                                |
| `bw`               | `bn,w,mn` — the operator's shorthand for `backed by`, used in design discussions.                         |
| `Codable`          | Swift's protocol for `Encodable & Decodable`.                                                           |
| `Container-kind`   | TraceServer badge discriminator: `kind="pumpstation"` (or future: `kind="manifold"`, `kind="junction"`). |
| `ConverseRole.harness` | The role used for harness-injected messages (path-safety hint, DITL, etc.) — NOT `user`, NOT `system`. |
| CORS Layer 1       | Ktor `install(CORS)` allow-list in `:server-extend`.                                                    |
| CORS Layer 2       | Per-namespace AGS platform `CORS` config — `cookies_allowed: true` is load-bearing.                      |
| `DITL`             | Developer-in-the-Loop — a TPipe pause/resume seam for harness steering during a live run.                |
| `GRDB`             | GenericOpenAI pipe — strict wire-shape requires full envelope (`id`, `object`, `created_at`, `status`, `model`, `output`). |
| `?loginAsGuest`  | Real AccelByte OAuth via the `data-testid="login-as-guest"` button. **Use this path for any real-backend test.** |
| `PumpStation`      | TPipe's judge/dispatch/path-loop agentic harness.                                                       |
| `vfs.deleteUserRecord` | AccelByte CLOUDSAVE action 8 (admin scope needed) — sometimes fails with 20013 access forbidden. |
| `Manifold`         | TPipe container that runs a manager pipeline + workers with `setAgentPipeNames`.                         |
| `Splitter`         | TPipe container that fan-outs an input across pipelines and aggregates results.                          |
| `wc`               | The trace that contains the most event detail for a validator-pipe investigation.                        |

---

## Getting help when this runbook doesn't cover it

1. **Skill discovery:** `find autogenesis-tools -name SKILL.md | xargs grep -l '<topic>'` to find the closest skill.
2. **Skill content:** open the matched SKILL.md and follow its "When to load" + "References" sections.
3. **Trace a bug:** start with `autogenesis-trace-analysis` if a play was rewritten; `log-parser` if a server-side failure; `tpipe-trace-parser` if the parser questions need grounding.
4. **Audit:** `autogenesis-feature-audit` for any "is this done" question.
5. **Ask:** the runbook is descriptive, not normative for novel situations. For new surface, prompt the agent with the relevant skill name and the trigger.

**The contract:** this runbook is the source of truth for *what* and *how*; the per-skill SKILL.md files are the source of truth for *why*. When they disagree, the skill wins for its domain; this runbook wins for cross-cutting concerns.

— end of RUNBOOK.md —
