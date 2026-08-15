---
name: autogenesis-feature-audit
description: Autogenesis feature state audit. Done/partial/not-done.
category: software-development
tags: [autogenesis, audit, inventory, triage, e2e]
version: 1.0.0
---

# Autogenesis Feature Audit

End-to-end inventory methodology for any Autogenesis feature/system. The operator's recurring framing is *"identify what is done and what is not done so far"* — produce a structured report, not an essay.

## When to Load

- "audit the <X> system", "how does <X> work", "what's wired up for <X>"
- "what is done and what is not done", "triage <X>", "inventory the <X> flow"
- Any feature/system review spanning server, server-extend, sharedModel, and kvisionApp
- Operator asks for a state-of-play report before authorizing implementation work

## Core Methodology — 5 cross-references

For any feature name (e.g. "map upload", "commander creation", "session resume"):

### 1. Find every RPC that touches the feature
```bash
search_files pattern="<FeatureName>" target=content path=. output_mode=files_only
search_files pattern="<featureName>|\"<featureSlug>\"" target=content path=. output_mode=files_only
```
Distinguish:
- `server.<feature>...` — main server (WS, port 9080) — **legacy** path
- `server.extend.<feature>...` — server-extend (REST+SSE, port 7070) — **gated** path

**Trap (two-path coexistence):** when both `server.X` AND `server.extend.X` exist for the same feature, the *server-extend* path is usually the one with safety/persistence guarantees, and the *server* path is the legacy one. Verify which one the **client actually invokes**.

### 2. Find every DTO the RPCs use
```bash
search_files pattern="<FeatureName>Data|<FeatureName>Request|<FeatureName>Response" target=content path=sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network
```
DTOs in `sharedModel/.../network/` are the contract between client and server. If a DTO exists but no RPC references it, it's dead-on-arrival (or awaiting wiring).

### 3. Find every UI widget that touches the feature
```bash
search_files pattern="<featureSlug>|<FeatureName>" target=content path=kvisionApp/src/jsMain/kotlin
```
Check whether the widget's action handlers actually invoke any RPC. Stubbed widgets leave **literal TODO markers** — see § Tell-Tale Markers below.

### 4. Cross-reference what the client actually calls
For every RPC the feature exposes, grep the client side for the RPC string (e.g. `"server.extend.uploadMapGate"`). If a server-side RPC has **zero client invocations**, it's built but unwired.
```bash
search_files pattern="<rpc-string>" target=content path=kvisionApp/src/jsMain/kotlin
```

### 5. Inventory test coverage
```bash
search_files pattern="<FeatureName>" target=content path=server*/src/test/kotlin output_mode=files_only
```
List which paths are covered by tests (unit / integration / live-with-env-var). Anything without a test is "untested" not "done" — distinguish.

## Output Format — Three Buckets

Operator's preferred shape for these reports:

### ✅ What's Done
- The thing exists, is wired end-to-end, has tests, and is reachable from the UI.
- Cite file:line for the load-bearing call site, plus a brief description of what it does.

### ⚠️ What's Partially Wired
- The component exists and may even have tests, but a **load-bearing wire is missing** — usually "the client never invokes the RPC" or "the success notification is logged but no UI feedback fires".
- Be specific about which wire is missing and what file:line shows the stub.

### ❌ What's Not Done
- The component is missing entirely, or only the contract (DTO) exists.
- Reference any TODO/Stage-N comments in source that confirm the gap.

End with **a single load-bearing concern** — the one gap that, if not closed, makes the whole feature non-functional for a real user. Example: *"Until the Publish button calls `server.extend.uploadMapGate`, every uploaded map travels the legacy `server.uploadMapPack` path with no safety check."*

## Tell-Tale Markers (greppable)

When auditing a feature, grep for these patterns to surface stubs quickly:

| Marker pattern | Meaning | Example location |
|---|---|---|
| `TODO_AFTER_<RPC_NAME>` | Stubbed client wire to a server RPC | `kvisionApp/src/jsMain/kotlin/ui/MapUploadModal.kt:339` |
| `// Stage 1 behavior: log only. Stage 2 will replace the body with...` | Stubbed UI feedback in a client notification handler | `kvisionApp/.../mapUpload/MapUploadSuccessClientHandlers.kt:22` |
| `NoOp<Persister>` / `// Persister is wired once the JSON-record path lands` | Persistence is intentionally in-memory-only | `server-extend/src/main/kotlin/maps/PlayerMapRepository.kt:37` |
| `// intentionally NOT modified — it runs the upload with no safety pass` | Legacy path left intact alongside the gated one | `server-extend/src/main/kotlin/network/MapUploadGate.kt:46` |
| `assertTrue(true, "...")` after a no-call | Test theatre — the agent's standing `grep -rn "assertTrue(true"` audit rule | (any `*Test.kt`) |
| `@Ignore` on a live test (instead of env-var gate) | Anti-pattern — should be `assumeTrue(System.getenv("X") == "true")` | (any `*Test.kt`) |
| `if (ExtendConfig.debugMode) return SafetyBillingOutcome.Skipped(...)` | Production code that short-circuits BEFORE the test seam can fire; tests must flip `ExtendConfig.debugMode = false` AND drop a synthetic `MapUploadGate/trace.json` at `${TPipeConfig.configDir}/debug/trace/MapUploadGate/trace.json` (note: TWO levels below `configDir`, not one) for the seam to be consulted. See `MapUploadSafetyBillingLedgerWriteTest` for the canonical pattern. | `server-extend/src/main/kotlin/network/MapUploadSafetyBilling.kt:95` |
| `connectionManager.register(playerId, origin)` without `accelbyteId` | SSE handler forgets to thread the URL parameter into the session; downstream RPCs (notably the map-upload catalogue save) can't resolve the canonical storage userId. The fix is `connectionManager.register(playerId, origin, accelbyteId)` so the session's `accelbyteId` field carries the parameter. See `ServerExtendSseAccelbyteIdTest` for the canonical pattern. | `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt:406` |

## Pitfalls

- **Don't conflate "the backend is built" with "the feature works."** Most audits find the backend gates and storage layers are fully implemented — the gap is almost always client-side wiring. State this explicitly.
- **Don't trust the KSP-generated wiring claim without checking the registry.** If `register<Name>ClientRpcHandlers(this, ...)` exists in `Main.kt`, the *handler* is wired, but that doesn't mean the *trigger* (e.g. Publish button click) invokes anything.
- **Don't read test files as "feature is done" — read them as "this path is verified."** A test using fake seams (`fakeSaver`, `fakeUnpacker`) verifies the orchestration logic, not the real AGS path. Distinguish fake-seam tests from end-to-end-pack tests.
- **Don't ignore `M ` (modified) files in `git status -sb`.** The operator often opens a feature audit mid-edit; the unstaged edit may itself be the load-bearing change they're about to land. Note it in the audit intro.
- **When two paths coexist (legacy + gated), state explicitly which one the UI currently routes through.** Operators forget which path is reachable and need the disambiguation.
- **Do not produce a wall-of-text audit.** The operator wants a table they can scan. Three buckets, file:line citations, one load-bearing concern at the end. Stop there.

## Per-Architecture-Component Search Recipes

| Component | Default port | Transport | Search pattern |
|---|---|---|---|
| Main server | 9080 (WS) | WebSocket | `path=server/src/main/kotlin` |
| Server-extend | 7070 (REST), 9092 (gRPC) | REST + SSE | `path=server-extend/src/main/kotlin` |
| Shared DTOs | n/a | n/a | `path=sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network` |
| KVision UI | 8080 (dev) | WebSocket (to 9080) + REST (to 7070) | `path=kvisionApp/src/jsMain/kotlin` |
| E2E probes | varies | Playwright | `path=kvisionApp-e2e/probes` |

When the UI talks to **server-extend**, it uses `RestRpcBridge`; when it talks to the main server, it uses `WebSocketRpcBridge`. The transport choice changes which `@RpcMethod` strings land where.

## Reference

- `references/audit-checklist.md` — concrete search commands + worked example skeleton