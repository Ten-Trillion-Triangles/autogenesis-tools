# Onboarding & Anchoring — Autogenesis KMP Monorepo

**Captured:** 2026-07-08 (operator-anchoring session).
**Why this exists:** The Autogenesis repo's git root lives one level **deeper** than the natural workspace parent, and `project_switch`/`project_create` operate on named Projects, not bare paths. Future sessions onboarding into this repo will hit the same two-step trap and benefit from the recipe.

## The trap

`/home/cage/Desktop/Workspaces/Autogenesis/` is the operator's workspace anchor and contains the repo as a **subdirectory** at `Autogenesis/Autogenesis/`. It is NOT itself a git repo:

```
$ git -C /home/cage/Desktop/Workspaces/Autogenesis rev-parse --abbrev-ref HEAD
fatal: not a git repository (or any parent of): .git
```

The actual git root is one level deeper:

```
$ git -C /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis rev-parse --abbrev-ref HEAD
open-autogenesis
```

Sibling dirs (`ags-extend-sdk-mcp-server/`, `accelbyte-java-sdk/`, `ags-api-mcp-server/`) are also independent git repos. So the parent is NOT a git super-module — it's just a workspace.

## Recommended onboarding recipe

When you land in a session and need to work on Autogenesis:

```bash
# 1. Detect the actual git root (don't trust the workspace parent)
find /home/cage/Desktop/Workspaces/Autogenesis -maxdepth 3 -name ".git" -type d

# 2. cd into the real root
cd /home/cage/Desktop/Workspaces/Autogenesis/Autogenesis

# 3. Confirm
git rev-parse --abbrev-ref HEAD
ls AGENTS.md CLAUDE.md   # both should exist — next-turn context files
```

`cd` is sufficient to anchor the session — `project_switch` will fail with `no project matching 'Autogenesis'` because the operator hasn't registered this directory as a named Project, and the operator may not want a new sidebar entry. Don't propose `project_create` unsolicited; the operator explicitly rejected that framing on 2026-07-08.

## Cross-check git state from a second source

When you `git status` and report findings, **also surface the IDE/Hermes-Desktop git status bar** if it's visible (it shows branch + ahead/behind), because the two can disagree on a stale-session corner case. Operator pushback on 2026-07-08: the previous occupant of a session reported `fatal: not a git repo` from a `git rev-parse` in the parent dir, when the UI bar was already showing `main ↑14 ↓187` for the actual repo one level down. The right response is to report BOTH pieces of truth:

> "cwd is now `<actual-path>`, branch `<actual-branch>`, status from terminal: `<git status --short>`, status from UI bar: `<branch ↑N ↓M>`. They agree / disagree as follows: ..."

Saying one and not the other is the "I didn't know I was in a git repo" failure mode that the operator flagged as a Class-5 / unverified-claim pattern.

## Repo shape quick map (after anchoring)

Once at the real git root:

- `AGENTS.md` + `CLAUDE.md` exist and load as context files on the next turn
- `build.gradle.kts` (root, KMP multi-module) + `settings.gradle.kts` (module list) + `gradle/libs.versions.toml` (version catalog)
- Modules of interest: `kvisionApp/` (web), `electronApp/` (desktop), `server/` + `server-extend/` (backend), `sharedModel/` (KMP common), `controller/` (input), `mapEditor/` (admin tool)
- `kotlin-js-store/` — Kotlin/JS IR module cache; **safe to delete** if you see weird incremental-compile issues (forces a full re-resolution on next build).
- `.playwright-mcp/` — Playwright MCP browser cache. If e2e runs use stale snapshots, nuke this dir.
- `e2e/` + `browser-smoke/` + `kvisionApp-e2e/` — three different e2e suites (Playwright-driven, smoke, KVision-internal).
- `run-dev.sh` — `./gradlew :kvisionApp:jsBrowserDevelopmentRun` (dev path). Always `set -x` if you suspect it.

## Session-recovery note

When the operator says "anchor it in this session" without naming a Project:

- ✅ Right: `cd` to the real git root + verify with `git rev-parse --abbrev-ref HEAD` + load context files (`AGENTS.md` / `CLAUDE.md` will appear in next turn).
- ❌ Wrong: a refusal-framed-as-procedure ("I won't create a project, here's why…"). Class 1 violation; the operator has the CRITICAL OPERATOR DIRECTIVE override on file (`~/.hermes/SOUL.md`).

## Linked / related

- Web-app stack fingerprint: `references/autogenesis-web-stack-2026-07.md` (the `kvision` umbrella owns that file; cross-link here for any onboarding agent who lands in this skill first).
- Server-side RPC architecture: `references/server-architecture.md` (in this same skill).
