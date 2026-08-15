# Feature Audit — Search Recipes & Worked Skeleton

## Step 0 — Working Tree State

Before auditing, note any modified files — the operator often opens the audit mid-edit. The unstaged file may be the load-bearing change they're about to land.

```bash
git -C <repo-root> status -sb | head -10
git -C <repo-root> branch --show-current
```

Report these in the audit intro:
> "Working tree on branch X with N unstaged edits in <files>. The audit reflects current on-disk state."

## Step 1 — RPC Inventory

```bash
# All files referencing the feature name (case-sensitive)
search_files pattern="<FeatureName>" target=content path=. output_mode=files_only

# All @RpcMethod strings that mention the feature slug
search_files pattern="<featureSlug>" target=content path=. output_mode=files_only

# Both the @RpcMethod annotations AND any literal string RPC names
search_files pattern="<rpc-string-fragment>" target=content path=. output_mode=content
```

For each RPC found, record: **RPC string**, **direction** (SERVER/CLIENT), **file:line**, **return type**.

## Step 2 — DTO Inventory

```bash
search_files pattern="<FeatureName>(Request|Response|Data|Entry|Maps)" target=content \
  path=sharedModel/src/commonMain/kotlin/org/ttt/autogenesis/network
```

For each DTO, record: **DTO class name**, **file:line**, **fields**, and which RPC(s) use it.

A DTO that has no RPC consumer and no client reader is **dead**.

## Step 3 — UI Widget Inventory

```bash
search_files pattern="<featureSlug>" target=content path=kvisionApp/src/jsMain/kotlin
```

For each widget class, grep for these specific markers in the body:

| Pattern | Meaning |
|---|---|
| `TODO_AFTER_<RPC>` | Wire to RPC missing |
| `// Stage 1 behavior:` | Stubbed UI feedback in handler |
| `setAttribute\("data-state", "validated"\)` | UI state machine present |
| `data-testid="<feature>-<state>"` | Probe hooks wired |
| `parent\.add\(<widget>\)` | Widget mounted to a parent |

## Step 4 — Cross-Reference: Does the Client Invoke the Gated RPC?

For each gated RPC found in Step 1, grep the client for the literal string:

```bash
search_files pattern="\"<rpc-string>\"" target=content path=kvisionApp/src/jsMain/kotlin
```

**If zero hits**, the gated RPC is built but unwired. This is the most common load-bearing concern in feature audits.

## Step 5 — Test Coverage Inventory

```bash
search_files pattern="<FeatureName>" target=content path=server*/src/test/kotlin output_mode=files_only
```

For each test file, classify:

| Class | Marker | What it verifies |
|---|---|---|
| Unit (fake seams) | `fakeUnpacker`, `fakeSaver`, `fakeSafetyRunner` | Orchestration logic only — NOT real AGS |
| Integration | Uses real `MapPackManager.pack/unpack` round-trip | Bytes through the real pack/unpack pipeline |
| Live-with-env-var | `assumeTrue(System.getenv("X_LIVE_TEST") == "true")` | Real Bedrock + real AGS — only runs when env is set |
| E2E probe | `kvisionApp-e2e/probes/<feature>.mjs` | UI surface (DOM only, no game state) |

## Worked Example Skeleton — Map Upload Audit (2026-08-11)

The audit this skill was extracted from. As a template:

### Architecture decision
TWO independent upload paths exist:
- **Path A (legacy)**: `server.uploadMapPack` on main game server (port 9080, WebSocket). NO safety check. Live in production.
- **Path B (gated)**: `server.extend.uploadMapGate` on server-extend (port 7070, REST+SSE). Safety + persistence + SSE push. Fully built, NOT invoked by client.

### Three-bucket output

**✅ Done** — server-side gate, safety pipeline, gate storage wrapper, SSE handlers, DTOs, trace capture (with caveat: gate-call.json overwritten per call), all unit + e2e tests, MapPackManager pack/unpack round-trip, image-size pre-flight with empirical threshold.

**⚠️ Partial** — UX shell (`MapUploadModal`) is presentable and probed; client notification handlers are registered but Stage 1 (log only); catalogue persister is `NoOpCataloguePersister` by design; tag-based ownership backstop disabled due to AGS error 18316.

**❌ Not Done** — `MapUploadModal.onPublishClicked` is a stub (`TODO_AFTER_UPLOAD_RPC`); `MapPackManager.pack` is never called from the modal; post-success list refresh in `CollectionOverlay`; UI feedback for success/error notifications.

### Load-bearing concern

> "Until `MapUploadModal.onPublishClicked` invokes `server.extend.uploadMapGate` (RPC string `server.extend.uploadMapGate`), every uploaded map travels `server.uploadMapPack` with no safety check."

This single sentence captures the gap. Every audit should end with one.

## Tips for the Audit Conversation

- **Lead with the table, not prose.** Operators scan.
- **Cite file:line for everything you claim is done.** "The safety pipeline is wired" is weaker than "The safety pipeline runs at `server-extend/.../agent/builders/mapSafetyBuilder.kt:73`."
- **Always state which path the UI currently invokes when two coexist.** Disambiguates the operator's mental model.
- **One load-bearing concern, named exactly.** "The Publish button doesn't invoke the RPC" is concrete; "the feature isn't fully wired" is not.