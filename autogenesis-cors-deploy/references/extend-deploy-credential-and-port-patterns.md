# extend-helper-cli headless credential path (verified 2026-08-02)

The agent repeatedly picked the wrong credential file during a Service-Extension
deployment. The lesson is class-level, not session-specific.

## Which file for which tool

| Tool                     | Credential file (canonical)                                                                                    | Notes                                                                                  |
|--------------------------|---------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| `ags` CLI                | `autogenesis-secrets/docker/.env.server` — `AGS_CLIENT_ID_AUTOMATION` / `AGS_CLIENT_SECRET_AUTOMATION`       | The `_AUTOMATION` pair is preferred for headless work; the primary pair was flagged exposed in 2026-06-30. |
| `extend-helper-cli`      | `autogenesis-secrets/config/accelbyte-extend.properties` — `AB_CLIENT_ID` / `AB_CLIENT_SECRET`                | NOT the AGS pair. NOT AWS credentials. NOT the OS keychain.                             |
| Local server JVM         | `autogenesis-secrets/config/accelbyte.properties`                                                             | Read via `AccelByteConfig` properties-file fallback.                                    |
| `server-extend` JVM      | `autogenesis-secrets/config/accelbyte-extend.properties`                                                      | Same value as the main server; kept separate so the extend module can diverge.          |
| Browser (KVision)        | `autogenesis-secrets/config/kvision.properties`                                                               | Browser-side `Iam.kt` + `ServerExtendConfig.kt`.                                        |
| Gradle deploy (`ags` auth path) | `autogenesis-secrets/config/ams.properties`                                                              | `AGS_BASE_URL` / `AGS_CLIENT_ID` / `AGS_CLIENT_SECRET` for the Gradle deploy tasks.     |

`autogenesis-secrets/.runtime/.env.server-extend` exists for docker-compose and is NOT
what `extend-helper-cli` reads in a headless setup.

## Why `extend-helper-cli` rejects the AGS pair

`extend-helper-cli` uses the `AB_*` env vars (or browser OAuth) for IAM authentication,
NOT the `AGS_*` env vars. The IAM client behind the AGS pair may not be authorized for
the Extend endpoints the helper needs; supplying it produces
`{"result":"invalid credentials"}` from `extend-helper-cli status --output json` while
`ags auth status` still shows `✔ Authenticated`.

The right pair is `AB_CLIENT_ID` / `AB_CLIENT_SECRET` from
`config/accelbyte-extend.properties`. The credential value is currently the same as the
main server, but the file is the canonical source of truth — the README documents that
the two files are kept separate specifically so the extend module can diverge
independently.

## Why the agent hit AWS ECR errors

When the wrong credential file was supplied, the helper's `--login` path would fail
with `no credentials found` or `invalid credentials`. When the AGS pair was supplied
(authenticates IAM correctly but rejected by Extend API), the helper fell through to
its local docker push path. Local docker authenticated with the machine's AWS identity
(the `hermes` IAM user), which lacks `ecr:InitiateLayerUpload` on Extend's ECR
repository. The error
`arn:aws:iam::521369004927:user/hermes ... no resource-based policy allows the ecr:InitiateLayerUpload action`
is a SYMPTOM of bad upstream credential selection, not an AWS permission problem.
The fix is the credential file, not an ECR policy change.

## Verified sequence (2026-08-02)

```bash
set -e
SECRETS="$HOME/Desktop/Workspaces/autogenesis-secrets/config/accelbyte-extend.properties"
export AB_NAMESPACE="$(grep '^AB_NAMESPACE=' "$SECRETS" | cut -d= -f2-)"
export AB_CLIENT_ID="$(grep '^AB_CLIENT_ID=' "$SECRETS" | cut -d= -f2-)"
export AB_CLIENT_SECRET="$(grep '^AB_CLIENT_SECRET=' "$SECRETS" | cut -d= -f2-)"
export AB_BASE_URL="$(grep '^AB_BASE_URL=' "$SECRETS" | cut -d= -f2-)"

$HOME/Desktop/Workspaces/AMS/extend-helper-cli image-upload \
  --namespace "$AB_NAMESPACE" --app autogenesis-server-extend \
  --image-tag "$TAG" --work-dir "$PWD/server-extend" --platform linux/amd64 --login
$HOME/Desktop/Workspaces/AMS/extend-helper-cli deploy-app \
  --namespace "$AB_NAMESPACE" --app autogenesis-server-extend \
  --image-tag "$TAG" --wait
$HOME/Desktop/Workspaces/AMS/extend-helper-cli get-app-info \
  --namespace "$AB_NAMESPACE" --app autogenesis-server-extend
```

## Pitfalls

1. **Don't supply `AGS_CLIENT_ID` to `extend-helper-cli`.** The CLI accepts them but
   the IAM client may not have the Extend permissions. Use `AB_CLIENT_ID` from the
   extend-specific properties file.
2. **Don't `docker login` to Extend's ECR directly with local AWS credentials.**
   `extend-helper-cli --login` mints time-limited scoped credentials via the IAM path;
   manual `docker login` against the ECR with the `hermes` identity fails with
   `ecr:InitiateLayerUpload denied`.
3. **Don't run `extend-helper-cli login` for headless CI/agent work.** The browser
   OAuth flow cannot complete unattended. Use the `AB_*` env vars from the extend
   properties file.
4. **Don't reuse `docker/.env.server` `AGS_*` values for Extend work.** That file is
   the `ags` CLI source of truth; mixing it with `extend-helper-cli` triggers the
   "invalid credentials" path even when both IAM clients are otherwise valid.

## How to detect you picked the wrong file

- `extend-helper-cli status --output json` returns `"result": "invalid credentials"`
  despite `ags auth status` showing `✔ Authenticated`.
- Image upload fails with `no credentials found` despite env vars being set
  (cause: env vars are `AGS_*` not `AB_*`).
- Image upload reaches ECR but fails with
  `arn:aws:iam::<acct>:user/<local-identity> ... ecr:InitiateLayerUpload ... no
  resource-based policy allows` — the agent-supplied credentials fell through to
  local docker auth; not an AWS permission issue to fix.

# Service-Extension port-routing failure mode (verified 2026-08-02)

A Service-Extension deployment can stay `deployment-in-progress` for >10 minutes and
expose a 504 from `l5d-proxy` while the JVM is actually running. The platform routes
to a specific logical port (commonly `8000` for Service-Extensions); if the container
listens on a different port, the readiness probe never succeeds and the pod never
becomes healthy.

## Symptom shape

```text
HTTP/2 504
l5d-proxy-error: logical service <ip>:8000: route default.http: backend default.service: service in fail-fast
x-envoy-upstream-service-time: 3001
server: envoy
```

The literal `8000` in the proxy error is the platform's intended port. If the
container binds a different port, this is the surface signal that the JVM started
but readiness is failing because nothing is listening on the platform's port.

## Source-side fix shape

`server-extend/src/main/kotlin/org/ttt/autogenesis/serverextend/ServerExtend.kt:191`
hardcoded `port = 7070`. The right pattern matches `ExtendConfig.grpcPort` —
env-overridable, default preserving local dev:

- Add `REST_PORT_PROPERTY` / `REST_PORT_ENV` (`SERVER_EXTEND_REST_PORT`) and
  `DEFAULT_REST_PORT = 7070` to `globals/ExtendConfig.kt`.
- Add `var restPort: Int = resolveRestPort()` and a `resolveRestPort(...)` helper
  mirroring `resolveGrpcPort` precedence (JVM property > env > default).
- Change the Netty `embeddedServer(Netty, host = "0.0.0.0", port = ExtendConfig.restPort)`.
- The Dockerfile's `ENV SERVER_EXTEND_REST_PORT=7070` is fine for local dev.
- At deploy time, `extend-helper-cli update-var --key SERVER_EXTEND_REST_PORT --value 8000 --force`
  sets the runtime port to the platform's expectation.

## Anti-patterns

- **Do not hardcode the platform port (e.g. `port = 8000`) in source.** That breaks
  local dev where nothing runs on `8000`. Always go through the env-var override.
- **Do not use an unconditional `socat` redirect in the entrypoint.** Same local-dev
  breakage plus a hidden failure mode when the redirect succeeds but the readiness
  probe still races.
- **Do not assume the runtime-build (JVMCI, etc.) fix is the active blocker** when
  the deployment is stuck. Build issues usually surface as a non-starting JVM with no
  pod ready; port-routing issues surface as a started JVM with no `/player` 200.
  Both can keep the deployment `deployment-in-progress` indefinitely; they need
  different diagnostics.

## Diagnostic sequence when a Service-Extension is stuck

1. `extend-helper-cli get-app-info --namespace <ns> --app <app>` — confirm
   `appStatus: deployment-in-progress`.
2. `curl -k -i --max-time 15 https://<base>/<basePath>/player` — read the
   `l5d-proxy-error` field for the platform-intended port.
3. Confirm the container's listener port by reading the source `embeddedServer(...)`
   call and the Dockerfile `EXPOSE` directives.
4. If the platform port ≠ source port, apply the env-overridable fix above and
   redeploy with `--image-tag` set to the new short SHA.
5. If ports match, the failure is elsewhere — JVM startup (JVMCI, OOM, missing
   credential) needs runtime logs from Grafana Cloud or the in-container
   `HEALTHCHECK` failure reason; the CLI does not expose pod logs.

## Why this matters

The `JVMCI` build-file change for `server-extend/build.gradle.kts` was a real fix
that landed earlier in the session, but it was not the active blocker for the
deployment that stayed stuck at "75% / in-progress". The actual cause was port
mismatch — the agent's first response blamed the JVMCI fix, then the ECR error from
the wrong credential file, neither of which was the real failure mode. The platform's
own 504 response is the source of truth for routing, not the in-progress status field.