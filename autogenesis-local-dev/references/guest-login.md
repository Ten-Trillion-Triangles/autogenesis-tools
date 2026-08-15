# Guest login — the real vs. the synthetic path

Two distinct paths lead to a "logged in" browser. They are **not
equivalent** — pick the one that matches the test you need.

## Path A — `?skipLogin=true` (synthetic)

URL: `http://127.0.0.1:8080/index.html?skipLogin=true` (optionally
combined with `&testMode=true` to mount a MapViewer directly).

`Main.kt:110-127` does:

```kotlin
if (KEnv.skipLogin) {
    globals.AccelByteEnv.userId = "guest-user"          // literal string
    globals.AccelByteEnv.userName = "Guest"
    globals.AccelByteEnv.displayName = "Guest Commander"
    WebSocketRpcBridge.connect(accelbyteId = "guest-user")
    RestRpcBridge.connect(accelbyteId = "guest-user")
}
```

No real AccelByte auth runs. The bridges are bound to the literal
`"guest-user"`, which is not a valid AccelByte UUID, so the game
server's per-user RPC handlers cannot resolve it to a real account.

Use it for: layout, visual, hover, MapViewer, in-process render tests.
It is the path `kvisionApp-e2e/tests/hover-border-lines.spec.mjs` uses.

Do NOT use it for: any test that exercises the game server's per-user
state (VFS restore, CloudSave, master record, billing, matchmaking
routing, resume-game push, account-scoped rate limits).

## Path B — "Login As Guest" button (real AccelByte OAuth)

URL: `http://127.0.0.1:8080/index.html` (no query params).

The LoginPage mounts. Click `data-testid="login-as-guest"`. This calls
`LoginPage.guestLogin()` (`ui/LoginWidgets.kt:624-629`) which fills in:

```kotlin
private const val GUEST_EMAIL = "ljn0toys0inc+test100@gmail.com"   // :63
private const val GUEST_PASSWORD = "TheFithLaw!"                    // :64
```

and runs the full AccelByte OAuth flow via
`UsersFacade.loginWithUsernameSuspend` (`ui/LoginWidgets.kt:655`).
On success, `AccelByteEnv.userId` is set to the real AccelByte UUID
returned by the auth response, the WebSocket and REST bridges are
rebound to that real accelbyteId, and MainMenu mounts.

Use it for: anything that requires a real account.

## Why both exist

`?skipLogin=true` is faster (no auth round-trip) and has no dependencies
on AccelByte's auth service being reachable from the test runner, so it
is the right default for purely client-side tests. The button is the
right default for any test that needs a real user (which is most
end-to-end tests of game-server behavior).

## Probe — `kvisionApp-e2e/probes/guest-login.mjs`

The probe drives Path B end-to-end and asserts:

1. LoginPage mounts after the loading-screen CTA click
2. The "Login As Guest" button (`data-testid="login-as-guest"`) is clicked
3. The success messageBox appears and OK is dismissed
4. MainMenu mounts (PLAY button + top bar)
5. The MainMenu's `data-accelbyte-user-id` attribute is non-empty
6. The attribute is NOT the literal string `"guest-user"`
   (which would mean we accidentally hit the skipLogin path)
7. The `data-accelbyte-display-name` attribute is non-empty

Last verified 2026-06-25:

```
accelbyteUserId: "004c3eb02c0b4436b41b24d5d670b0e4"
accelbyteDisplayName: "KingCandy13"
Result: PASS
  console errors (non-pre-existing): 0
  page errors (non-pre-existing): 0
  assertions: {"mainMenuPresent":true,"mainMenuHasMainMenuClass":true,
               "accelbyteIdNonEmpty":true,
               "accelbyteIdIsNotSyntheticSkipLogin":true,
               "displayNameNonEmpty":true}
```

Run:

```bash
cd kvisionApp-e2e
node probes/guest-login.mjs
```

Run with `--headed` to watch the browser:
`node probes/guest-login.mjs --headed`.

## Test surface — `data-testid` / data-attributes

Added in 2026-06-25; do not remove without updating the probe.

- `data-testid="login-as-guest"` on the Login As Guest button
  (`ui/LoginWidgets.kt:269`).
- `data-testid="main-menu"`, `data-accelbyte-user-id`,
  `data-accelbyte-display-name` on the MainMenu root VPanel
  (`ui/MainMenu.kt:60-65`).

## Debug-server signal alternative

`DebugSignalBridge.Signals.LOGIN_AS_GUEST`
(`org.ttt.autogenesis.kvisionapp.DebugSignalBridge.kt:52`) dispatches
`DebugConsole.triggerLoginAsGuest()` (`ui/DebugConsole.kt:45-59`),
which calls `LoginPage.guestLogin()` IF a LoginPage is mounted. In
`?skipLogin=true` mode the LoginPage is never created, so the signal
is a no-op. The Python debug server sends the signal via
`POST /debug/signal "LOGIN_AS_GUEST"`.

## Guest account rotation

The test account `ljn0toys0inc+test100@gmail.com / TheFithLaw!` is
hard-coded in `ui/LoginWidgets.kt:63-64`. If the password rotates
(AccelByte IAM, manual reset, etc.) update `GUEST_PASSWORD` and
re-run `node kvisionApp-e2e/probes/guest-login.mjs` to confirm the
new value works end-to-end.

The account is the `ljn0toys0inc+test100@gmail.com` gmail-plus-tag
pattern, which is the standard convention for this project's
ephemeral test accounts. The display name resolved at login was
"KingCandy13" as of 2026-06-25.
