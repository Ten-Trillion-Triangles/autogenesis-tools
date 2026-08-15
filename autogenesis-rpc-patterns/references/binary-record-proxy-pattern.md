# Binary Record Proxy Pattern (Autogenesis)

The Autogenesis `proxy.CloudSaveProxy` exists to bypass CORS for AccelByte CloudSave JSON game records. The web client cannot talk to AGS directly because AGS's CORS configuration does not cover browser-issued requests with arbitrary origins. The proxy holds an OAuth client and forwards metadata calls on behalf of the client.

**Binary records do NOT follow this pattern.** This file documents the architectural mismatch and the three viable designs for the binary-record equivalent (decided 2026-08-09 in the `feature/binary-record-cors-proxy` branch).

## Why the JSON pattern doesn't transfer

| Concern | JSON record (existing) | Binary record |
|---|---|---|
| Storage substrate | `VirtualFileSystemManager` (local cache + AGS) | Direct AGS SDK calls (no JSON caching) |
| Data shape | JSON envelope `{value: {...}}` | Raw bytes via presigned URL |
| Upload flow | Synchronous JSON POST | Two-step: AGS returns presigned URL → client uploads bytes directly to AGS/S3 |
| Download flow | VFS returns parsed JSON | Client reads presigned `url` from record metadata → downloads bytes |
| CORS resolution | Proxy holds OAuth client, waits for AGS to add the origin | Presigned URL is CORS-configured by AGS — direct browser→S3 upload works |

The existing `VirtualFileSystemManager.fetchUserRecord` / `saveUserRecordFromJsonString` calls return `Result<PlayerRecordResponse>` with a `JsonElement?` value. Binary records return `UploadBinaryRecordResponse` with a presigned URL — the JVM proxy never sees the bytes. **There is no value in caching binary payloads in the proxy's VFS** because the bytes never go through the proxy.

## The three viable architectures (decided 2026-08-09)

### Option A — Same-server-extend proxy, metadata-only passthrough

```
WebClient → server.extend.uploadBinaryRecord(key, fileType) → AGS presigned URL
WebClient → AGS S3 (PUT bytes directly, presigned URL is CORS-configured)
WebClient → server.extend.getBinaryRecord(key) → AGS metadata + presigned download URL
WebClient → AGS S3 (GET bytes directly)
```

- Proxy only handles metadata + auth. Byte transfer is client→S3.
- Solves CORS because client only talks to server-extend for metadata; the S3 upload/download endpoint is CORS-configured by AGS itself.
- Recommended for almost all binary record use cases.

### Option B — Same-server-extend proxy, full byte pass-through

```
WebClient → server.extend.uploadBinaryRecord(bytes) → JVM buffers bytes → AGS upload
WebClient → server.extend.getBinaryRecord(key) → JVM downloads → returns bytes
```

- Double bandwidth (client→proxy→AGS). JVM heap pressure for large blobs.
- Only viable if the bytes must transit server-extend (e.g. for server-side processing, virus scanning, transcoding).
- Recommended for binary transformations that the server must perform.

### Option C — Hybrid (selected default for new Autogenesis features)

Same as A, but the proxy holds `@RpcMethod` functions that return AGS metadata + presigned URLs. The web client (`accelbyteSdk`) gets a `BinaryRecordFacade` that calls the proxy for metadata and AGS S3 directly for bytes.

## The Autogenesis implementation shape (recommended)

### Server-extend proxy surface (`server-extend/src/main/kotlin/proxy/BinaryRecordProxy.kt`)

Mirror the existing `CloudSaveProxy` JSON pattern but route to AGS SDK directly (not VFS). Match the **primary server's `BinaryRecord` helper** API surface in `server/src/main/kotlin/accelbyte/cloudsave/BinaryRecord.kt` — that helper already has all 14 calls (public + admin, Game + Player tracks).

Per AGS binary record naming, the proxy methods follow the existing JSON pattern:
- `server.extend.getBinaryRecord` → get metadata for a game binary
- `server.extend.uploadBinaryRecord` → get presigned upload URL
- `server.extend.deleteBinaryRecord` → delete
- `server.extend.listBinaryRecords` → list with pagination + tag filters
- `server.extend.bulkFetchBinaryRecords` → bulk fetch
- `server.extend.getBinaryRecordMetadata` → update metadata (admin only)
- Parallel player-binary methods prefixed with `Player`

### KMP facade (`accelbyteSdk/src/commonMain/kotlin/org/ttt/autogenesis/accelbyte/facades/BinaryRecordFacade.kt`)

Mirror the existing `CloudSaveFacade` JSON pattern but call `Cloudsave.PublicGameBinaryRecordApi` (not `PublicGameRecordApi`). The TS SDK's `sdk-cloudsave` package exposes these APIs at `generated-public/PublicGameBinaryRecordApi.ts` and `PublicPlayerBinaryRecordApi.ts` — verified via grep 2026-08-09.

### Shared models (`sharedModel/src/commonMain/kotlin/structs/accelbyte/cloudsave/BinaryRecordModels.kt`)

These already exist (112 lines, 11 typed classes) — the primary server's `BinaryRecord.kt` already imports them. No new model work needed.

### Tests (`server-extend/src/test/kotlin/proxy/BinaryRecordProxyTest.kt`)

Mirror `CloudSaveProxyMasterRecordTest.kt` pattern. The existing test uses a local VFS because the JSON proxy routes through VFS. Binary tests will use a **mock AGS SDK** (or a real local AGS in dev mode) — the proxy does NOT route through VFS.

## IAM permission gap (flagged in AGENTS.md, not blocking)

The server-extend OAuth client needs `cloudsave:game:binary:read/write/admin` AND `cloudsave:player:binary:read/write/admin` permissions on the AGS namespace. The existing JSON proxy uses `cloudsave:record:read/write` (lower privilege). Binary records are a separate OAuth scope in AGS — the operator must add the new permissions to the OAuth client before the binary proxy methods will work against a live namespace. This is a **deployment concern**, not a code concern — the code surfaces it as a 403 at runtime, and the AGENTS.md note should link to the IAM runbook.

## Key files to reference

- Primary server binary helper (the API surface to mirror): `Autogenesis/server/src/main/kotlin/accelbyte/cloudsave/BinaryRecord.kt` (321 lines, 14 methods)
- Shared models (already exist): `Autogenesis/sharedModel/src/commonMain/kotlin/structs/accelbyte/cloudsave/BinaryRecordModels.kt` (112 lines)
- JSON proxy pattern (the one to NOT blindly copy): `Autogenesis/server-extend/src/main/kotlin/proxy/CloudSaveProxy.kt` (275 lines)
- JSON KMP facade (the shape to mirror): `Autogenesis/accelbyteSdk/src/commonMain/kotlin/org/ttt/autogenesis/accelbyte/facades/CloudSaveFacade.kt` (87 lines)
- Player JSON facade (parallel pattern): `Autogenesis/accelbyteSdk/src/commonMain/kotlin/org/ttt/autogenesis/accelbyte/facades/PlayerRecordFacade.kt` (52 lines)
- Admin JSON facade (parallel pattern): `Autogenesis/accelbyteSdk/src/commonMain/kotlin/org/ttt/autogenesis/accelbyte/facades/AdminUserRecordFacade.kt` (54 lines)
- TypeScript SDK binary surface (the AGS API to bind): `Autogenesis/accelbyte/accelbyte-typescript-sdk/packages/sdk-cloudsave/src/generated-public/PublicGameBinaryRecordApi.ts` and `PublicPlayerBinaryRecordApi.ts`

## Why this is a class-level pattern, not a one-off

The mismatch between JSON and binary record proxy patterns will recur in any future AccelByte integration that needs to handle binary blobs (avatars, replay files, screenshots, voice clips). The two-step presigned-URL design is AGS's intended pattern for binary — never try to proxy bytes through a JVM server when AGS gives you a presigned URL. This is the session's main lesson: **proxy metadata, not bytes**.
