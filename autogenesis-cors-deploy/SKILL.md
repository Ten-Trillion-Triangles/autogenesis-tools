---
name: autogenesis-cors-deploy
description: AccelByte Service Extension CORS + per-namespace platform CORS — making the deployed game client work against extend server + AGS gateway in both dev and live. Load when working on CORS allow-lists in server-extend, when the user reports "CORS error" / "blocked by CORS" / "Origin not allowed" against a deployed Amplify frontend, when provisioning a new namespace's CORS config, or when designing the browser→extend or browser→AGS auth path.
version: 1.0.0
author: TTT
created: 2026-07-19
tags: [autogenesis, accelbyte, service-extension, cors, deploy]
changelog:
  - "1.0.0 (2026-07-19): Initial extraction from Jun's chess repo reference + Autogenesis server-extend CORS redo. Two-layer architecture (extend-server Ktor CORS + per-namespace AGS platform CORS), env-driven allow-list merge pattern, cookie-as-fallback for ingress-strips-Authorization."
  - "1.1.0 (2026-08-02): Added `references/extend-deploy-credential-and-port-patterns.md` covering (a) the `extend-helper-cli` headless credential path — `AB_*` from `config/accelbyte-extend.properties`, NOT the AGS pair from `docker/.env.server`, NOT local AWS creds — and (b) the Service-Extension port-routing failure mode where the platform routes to e.g. 8000 but the container listens on 7070, surfacing as `l5d-proxy-error ... service in fail-fast` even though the JVM started fine."
---
# CORS for Deployed AccelByte Service Extension Apps

When the deployed Autogenesis frontend (Amplify-hosted) calls both our `:server-extend` (port 7070) and the AccelByte platform (`*.accelbyte.io`) directly from the browser, two independent CORS surfaces must allow the calls. This reference pins the pattern Jun's chess repo proved works and maps it onto Autogenesis's existing surface.

## Architecture: two layers, both required

```
Browser (live Amplify origin, e.g. https://autogenesis.tentrilliontriangles.com)
   │
   ├─→ Browser → server-extend   (port 7070, Ktor CORS allow-list)
   │
   ├─→ Browser → AGS gateway      (*.accelbyte.io, per-namespace platform CORS)
   │       │
   │       └─→ ingress strips Authorization header (AMS / Extend Forward proxy)
   │           └─→ origin uses HttpOnly cookie for browser-auth fallback
   │
   └─→ server-extend reads cookie OR Authorization header
```

A mistake at either layer produces a different symptom:
- **Wrong layer 1 (extend allow-list):** `403 origin not allowed` from server-extend. Fix: add the live origin to the allow-list.
- **Wrong layer 2 (platform CORS):** browser cannot complete the IAM `/oauth/token` round-trip — login fails before any extend call. Fix: per-namespace config (see "Platform-side" below).
- **Missing cookie path:** login succeeds, but every extend call fails with 401 because ingress ate the `Authorization` header. Fix: `cookies_allowed: true` so IAM sets `Set-Cookie: access_token=...; HttpOnly` AND server-extend reads the cookie on incoming requests.

## Layer 1: server-extend (Ktor) CORS

The allow-list must include every origin the browser could run from. In practice: localhost variants (dev) + the deployed Amplify origin(s) (live). Jun's pattern from `Junaili/chess` `custom-extend-app/ethan-chess-service/cmd/main.go:341-354`:

```go
func parseAllowedOrigins(raw string) map[string]struct{} {
    defaults := []string{
        "https://junaili.github.io",   // GitHub Pages (deployed web)
        "https://localhost:8808",      // local dev
        "capacitor://localhost",       // iOS Capacitor shell
    }
    set := make(map[string]struct{})
    for _, o := range defaults { set[o] = struct{}{} }
    for _, o := range strings.Split(raw, ",") {
        o = strings.TrimSpace(o)
        if o != "" { set[o] = struct{}{} }
    }
    return set
}
```

Three load-bearing properties of this shape:

1. **Defaults are additive, not exclusive.** `ALLOWED_ORIGIN` env var MERGES with the defaults instead of replacing them — prevents an empty/missing env var from disabling the iOS app or any other pre-deployed origin.
2. **Env var is a comma-separated list.** Easy to wire via Helm/AMS env-var injection for live, and via `ConfigSource.property("*.local.properties", "...")` for local dev. Single key, multiple values.
3. **No hostname stripping or scheme-rewriting.** Origins are full URLs (`https://`, port included). Caller is responsible for canonicalizing their input.

> **Canonical reference:** the exact Go source for `parseAllowedOrigins`, `corsMiddleware`, and `playerAuthorizationHeader` is in `references/jun-cors-middleware.go` — copy from there when porting to Kotlin, not from the paraphrase above.

For Autogenesis's Ktor (Kotlin) side, the equivalent lives at `server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt` around `install(CORS) { allowHost(...) }`.

**Ktor `allowHost` vs Jun's whitelist middleware — the difference matters:**
- `allowHost` is **permissive**: it accepts subdomains, port variants, and schemes loosely. Requests from unknown but similar origins (e.g. `https://autogenesis.tentrilliontriangles.com` vs `autogenesis.tentrilliontriangles.com:8080`) may pass when they shouldn't.
- Jun's `corsMiddleware` is **strict**: it does `allowed[origin]` map lookup, returns `403 {"error":"origin not allowed"}` for anything not in the set. There is no fuzzy match.

**If strict is required (e.g. same domain, different subdomain must not pass), write a custom Ktor middleware instead of relying on `allowHost`.** Autogenesis currently uses `allowHost`; this is a known gap — patch if strict origin validation is needed.

The defaults list must include:
- `localhost` / `127.0.0.1` (and `:8080` webpack dev port, `:4173` vite preview port)
- `0.0.0.0` (some KVision dev-mode URLs surface this)
- The `AB_BASE_URL` host (derived at runtime — the API gateway the extend server proxies AGS calls through)
- The live Amplify origin(s) — **read from `ConfigSource.property(...)` so the public repo carries no tenant string**

Required response headers on every preflight + actual response — three are load-bearing, one is critical for CDN cache correctness:

| Header | Value | Why |
|---|---|---|
| `Access-Control-Allow-Origin` | the request's `Origin` (echoed) | per-origin credentialed CORS — wildcard breaks `Access-Control-Allow-Credentials` |
| `Vary` | `Origin` | **required.** CDN and browser caches collapse responses with different origins into one cached entry without this. Without it, a cached response from `https://autogenesis.tentrilliontriangles.com` may be served to `https://staging.autogenesis.tentrilliontriangles.com` (or vice versa), breaking CORS or leaking cached data. Jun's middleware explicitly sets `Vary: Origin` on every response — this is not optional. |
| `Access-Control-Allow-Methods` | `POST, GET, OPTIONS` (plus `PUT`/`PATCH`/`DELETE` if the surface needs them) | list what extend actually uses |
| `Access-Control-Allow-Headers` | `Authorization, Content-Type` | the only two headers the browser sends in this auth model |
| `Access-Control-Allow-Credentials` | `true` | **required** so the browser attaches the `Cookie: access_token=...` header on the cross-origin request |

`allowCredentials = true` is the load-bearing line. Without it, browser drops the HttpOnly `access_token` cookie from cross-origin requests, every extend call is anonymous, and the session silently breaks.

## Layer 2: per-namespace platform CORS

This is set via the AccelByte admin namespace config endpoint — NOT inside any code we ship. One-shot operator setup, per environment:

```bash
curl 'https://<ENV>.gamingservices.accelbyte.io/config/v1/admin/namespaces/<NAMESPACE>/configs' \
  -H 'content-type: application/json' \
  --data-raw '{"key":"CORS","isPublic":false,"value":"{\"allowed_domains\":[\"https://<LIVE_ORIGIN>\"],\"allowed_headers\":[],\"expose_headers\":[],\"allowed_methods\":[],\"cookies_allowed\":true,\"max_age\":0}"}'
```

What each field does:

| Field | Value | Why |
|---|---|---|
| `allowed_domains` | `["https://<LIVE_ORIGIN>"]` | the origin(s) the browser will run from. Per-namespace, so prod and staging can have different lists. |
| `allowed_headers` | `[]` | empty → AGS allows `Authorization`, `Content-Type`, and other simple headers by default |
| `expose_headers` | `[]` | response headers the browser can read. Empty unless the frontend needs to read a non-simple response header |
| `allowed_methods` | `[]` | empty → all methods allowed by default |
| `cookies_allowed` | `true` | **required.** When the user logs in via AGS, IAM sets `Set-Cookie: access_token=<JWT>; HttpOnly; SameSite=Lax`. The browser attaches this cookie on subsequent cross-origin requests to AGS subdomains. |
| `max_age` | `0` | preflight cache TTL. 0 = no caching (browser re-preflights every request). Use a non-zero value (e.g. 600) if you want to reduce preflight traffic at the cost of origin-list-change latency. |

**Empty `allowed_headers` and `allowed_methods` look like an error — they are not.** AGS treats `[]` as "allow the standard set" rather than "allow nothing." If you supply a non-empty list, it becomes the ONLY set allowed; that's a much sharper surface than the empty default.

**Document the curl in `server/RUNBOOK_PUSH.md` (or equivalent ops runbook).** This is a one-shot setup per environment; it must be in the deploy runbook so a new namespace or a new environment doesn't get stuck wondering why login is broken.

## Layer 1 ↔ Layer 2 contract: the cookie is the bridge

The reason both layers matter: AMS / Extend Forward ingress **strips the `Authorization` header** from incoming requests before forwarding to the deployed service. From Jun's commit message (`Authenticate Extend browser calls with AGS cookie`, commit `2bc2b3fb`):

> AGS ingress consumes Authorization before forwarding to a deployed Service Extension. IAM sets an HttpOnly access_token cookie during login, which is the supported browser-auth fallback at the service boundary.

Concretely:
- `POST /iam/oauth/token` (browser → AGS) sets `access_token` cookie on success.
- `POST /safety/reasons` (browser → service extension): browser sends `Cookie: access_token=<JWT>` instead of `Authorization: Bearer <JWT>`.
- service extension reads cookie → re-broadcasts to upstream AGS calls as `Authorization: Bearer <JWT>` (server-to-server is not stripped).

The implementer pattern on the extend server side (from Jun's `cmd/main.go:447-457`):

```go
func playerAuthorizationHeader(r *http.Request) string {
    if header := r.Header.Get("Authorization"); header != "" {
        return header
    }
    if cookie, err := r.Cookie("access_token"); err == nil && cookie.Value != "" {
        return "Bearer " + cookie.Value
    }
    return ""
}
```

Authorization header takes precedence (for server-to-server and tooling), but cookie is the fallback for browser-originated requests. **If `cookies_allowed: false` in the platform config, the cookie is never set, this fallback returns "", and every browser request is anonymous.**

For Autogenesis specifically: `CloudSaveProxy` and similar `@RpcMethod` RPC endpoints are CALLED FROM the browser via `RestRpcBridge`. They inherit the cookie path automatically if the browser sends the cookie. If they DON'T inherit (Ktor doesn't auto-attach cookies on cross-origin requests without `allowCredentials = true`), the fix is on the CORS install side, not on the RPC side.

## Verification recipe

Three checks, in order, before declaring CORS "fixed":

1. **Layer 1 allow-list shape (TDD):** run the new CORS allow-list unit test class with a preflight (`OPTIONS`) and an actual (`POST`) request from each origin in the allow-list, assert `Access-Control-Allow-Origin` echo and `Access-Control-Allow-Credentials: true` on both. The pre-attempt Autogenesis state failed this check on `autogenesis.tentrilliontriangles.com` (the live Amplify origin).

2. **Layer 2 platform config (operator side):** `curl -s -X GET 'https://<ENV>.gamingservices.accelbyte.io/config/v1/public/namespaces/<NAMESPACE>/configs/CORS' -H 'accept: application/json'` — confirm the response includes the live origin in `allowed_domains` and `cookies_allowed: true`. This is a GET not a POST; it's safe to run as a smoke.

3. **End-to-end browser path:** load the live Amplify URL in a real browser (not just curl — curl won't exercise cookie attachment on cross-origin requests), open DevTools → Network, click "Login As Guest", confirm:
   - `/iam/oauth/token` returns 200
   - Response includes `Set-Cookie: access_token=...; HttpOnly` in the response headers
   - Subsequent `/iam/oauth/verify` or first `server.extend.*` call includes `Cookie: access_token=...`
   - No `CORS error` / `Origin not allowed` console messages

If step 3 fails but steps 1 and 2 pass, the bug is in the cookie attachment path — recheck `allowCredentials = true` and `Access-Control-Allow-Credentials: true` on every preflight AND actual response.

## Common failure modes

| Symptom | Likely cause |
|---|---|
| 403 `{"error":"origin not allowed"}` from extend | live origin missing from allow-list, OR allow-list exact-match (not suffix/prefix) and the request includes a trailing `/` |
| CORS error on login, no preflight success | platform `CORS` config not provisioned for this namespace, OR `cookies_allowed: false` |
| Login succeeds, every extend call 401 | ingress stripped Authorization AND `cookies_allowed: false` (cookie never set) |
| Localhost works, live fails | allow-list hardcoded for localhost; live origin never added (most common post-scrub regression) |
| Live works for one user, fails for another | `Access-Control-Allow-Origin` is wildcard (`*`) but `Access-Control-Allow-Credentials: true` → browser rejects per spec. Echo the Origin header literally. |

## Where this lives in Autogenesis

- **`server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt:229-250`** — Ktor `install(CORS)` block. Source of truth for the allow-list at runtime.
- **`server-extend/src/test/kotlin/.../`** — preflight + actual-request tests per origin. TDD red-then-green is the right discipline here; don't ship a CORS change without a test that pins every origin in the allow-list.
- **`server/RUNBOOK_PUSH.md` or `server-extend/RUNBOOK_CORS.md`** — operator runbook for the platform-side `CORS` config curl. Both production AND staging need this documented, not just one.
- **`kvisionApp/src/jsMain/kotlin/globals/ServerExtendConfig.kt`** — frontend side of the live-origin → server-extend URL resolution. The frontend's `liveServerUrl` getter already exists; confirm it produces the same origin string the server-extend allow-list expects.
