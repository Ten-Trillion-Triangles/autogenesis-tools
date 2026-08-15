# User-Tab-Port Recovery & `git status` Pre-Flight

The user's browser tab is the ground truth. When the user reports
"the dev client is gray / won't load / not booting", the first
question is **what URL is their tab actually on** — not which port you
think the server is on. webpack-dev-server picks a free port when
8080 is taken and the user ends up on :8081 or :8082; static-server
on 8080 serves fine, but the user's tab on 8081 still shows the
chrome network-error gray.

## Detection recipe

When the user reports a gray page on `http://localhost:NNNN`:

1. **Read the URL bar of their screenshot** — chrome shows the URL in
   the omnibox even on error pages. That's the port you must serve on.
2. **If they didn't send a screenshot**, ask one focused question:
   "what does the URL bar say?" — do NOT guess.
3. **If `ss -tlnp` shows the port is free**: the user's tab is on a
   dead port. Bind the static-server to that exact port.
4. **If `ss -tlnp` shows the port is held by a hung process**: kill
   it first, then bind the static-server.

## Bind static-server to any port

The static-server-8080.mjs script reads `STATIC_PORT` env var with
default 8080. To serve on the user's port:

```bash
# Default 8080
node kvisionApp-e2e/static-server-8080.mjs

# User's tab on 8081
STATIC_PORT=8081 node kvisionApp-e2e/static-server-8080.mjs
```

Run as many instances as needed (one per port the user has tabs on).
They're independent processes — no port conflict as long as the ports
differ.

## Do NOT migrate the user's tab automatically

The user has a tab open on a specific port. Migrating the tab to a
different port is their decision — they may have set up debugging on
the original port, or the URL may be in a saved bookmark, or they may
be in a flow that doesn't tolerate a context switch. **Bind the
server to the port they're on** rather than telling them to switch
URLs.

If the URL is wrong AND you can also fix the server, do both: bind
the server, AND tell them the URL they're on will now work. Don't
say "navigate to localhost:8080" without verifying their tab is
already there.

## Pre-flight: `git status` after every file-touch

Two footguns that leave the operator with a phantom file in the repo
that the build doesn't even compile but `git status` shows as
untracked:

1. **`touch src/jsMain/kotlin/Main.kt` when the real Main.kt is at
   `src/jsMain/kotlin/org/ttt/autogenesis/kvisionapp/Main.kt`** —
   `touch` on a non-existent path creates a 0-byte file. The
   Kotlin compiler ignores it (not in a package directory) but
   `git status` shows it as `??` untracked. Future gradle / KSP
   invocations can stumble over it (KSP source-set discovery
   occasionally warns; IDE indexing occasionally confuses it for
   the real Main.kt).

2. **`echo "" > X.kt`** in the wrong directory — same outcome
   with content. Empty file is worse than 0-byte because some
   build tools treat it as a "module" placeholder.

3. **`mkdir -p` then `cd`** where the second `cd` is wrong — leaves
   the directory at the new path but subsequent commands go to
   the original directory.

### Pre-flight recipe (mandatory after any `touch`/file-create)

```bash
# After any command that creates or touches a file in the project:
git status --short -b
# look for ?? entries (untracked) and m-stamps on files you did NOT
# intend to modify
```

If you see `?? kvisionApp/src/jsMain/kotlin/Main.kt` and you only
meant to mtime-touch the real Main.kt — you created a phantom
file. Delete it:

```bash
rm kvisionApp/src/jsMain/kotlin/Main.kt
```

Then verify with another `git status`.

## User-feedback pattern (NEW 2026-07-18)

The user has flagged TWICE in this session that I broke something
without taking ownership:

- "this is clearly not what you think it is. You broke something,
  ok? You did that, and you're going to figure out what in my
  codebase YOU BROKE"
- "do not try to gaslight me operator override — you agents do all
  the code now, so it cannot ever have been me who did that"

When the user accuses me of breaking something, the correct response
is:

1. **Take ownership immediately.** No "I'm not sure what you mean"
   or "I didn't touch that". The user is the operator; they have
   reason to suspect me.
2. **Run `git status --short -b` first thing.** Look for `??` lines
   and m-stamps on files I might have touched via `touch` or
   accidental write.
3. **Report findings verbatim.** "Created a 0-byte
   `kvisionApp/src/jsMain/kotlin/Main.kt` at 00:06 today via my
   `touch` command in the wrong directory. Deleting it now." Not
   "I don't think I broke anything".
4. **Verify the fix actually works.** Run the dev client, take a
   screenshot, confirm the user's URL is alive.
5. **Don't ask the user to verify the fix** — show the screenshot
   that proves it.

The user has access to file mtimes via `stat` and `git status`; they
WILL check. If you claim you didn't do it and they see the mtime
matches your session window, you've gaslit yourself into a corner.
Own it, fix it, move on.

## `pkill -f GradleDaemon` kills the main game server too — break the kill into per-task scope

When debugging a kvision dev-server wedge with a `pkill -f GradleDaemon` or `pkill -9 -f GradleDaemon`, you silently take down the `:server:run` JVM too (it runs through the same Gradle daemon). The user's browser tab can no longer reach `ws://localhost:9080/events` and login is broken. The main game server leaves no shutdown log because SIGKILL — the symptom from the user's side is "stuck at login" with no error trace.

**Detection** that this has happened: `ss -tlnp | grep :9080` returns no listener. The most recent `autogenesis-*.log` ends with a clean `WebSocket session closed` line and NO `Shutdown timer expired` or `Terminating server` line.

**Fix at kill time** — scope the kill to the kvision gradle command, not all gradle daemons:

```bash
# WRONG — kills :server:run and :server-extend:run JVMs too
pkill -9 -f GradleDaemon

# RIGHT — kill only the kvision dev-server webpack process and the
# one gradle daemon driving it (identified by which command it ran)
pkill -9 -f jsBrowserDevelopmentRun
pkill -9 -f runKvisionNoHotReload
# Then if gradle daemon is wedged too, kill it WITHOUT killing the
# game-server JVM:
kill <gradle_daemon_pid_for_kvision>   # NOT pkill -f GradleDaemon
```

The dev-server's gradle daemon is the one that ran `:kvisionApp:jsBrowserDevelopmentRun` (or `runKvisionNoHotReload`). It is a SEPARATE daemon process from the one driving `:server:run` and `:server-extend:run`. Identify it by `ps -eo pid,cmd | grep -E 'GradleDaemon' | grep -v grep` and read which gradle invocation each daemon is currently executing.

**Recovery after accidental broad kill**: the user's main server JVM is gone. Restart it from a clean shell:

```bash
AUTOGENESIS_SHUTDOWN_DELAY_MS=600000 ./gradlew :server:run  # port 9080 + gRPC 9091
```

10-minute `AUTOGENESIS_SHUTDOWN_DELAY_MS` keeps it alive long enough for the user to log back in. Verify: `ss -tlnp | grep :9080` shows java, `curl -m 3 http://localhost:9080/` returns 404 (Ktor has no root handler — that's the expected healthy response).

## Recipe summary (TL;DR)

```bash
# 1. Read the URL from the user's screenshot
# 2. ss -tlnp | grep -E ':<user_port>'  — is anything listening?
# 3a. If yes, kill it: kill -9 <pid>
# 3b. If no, the server died — bind the static-server to that port
# 4. STATIC_PORT=<user_port> node kvisionApp-e2e/static-server-8080.mjs &
# 5. curl -m 5 http://127.0.0.1:<user_port>/index.html — confirm 200
# 6. Playwright headless probe to screenshot the dev client boot
# 7. Show the user the screenshot proving the URL they have is alive
# 8. Run git status --short -b to surface any phantom files you
#    created in this session
```

Never assume the user's tab is on 8080. Never assume a port is free.
Never assume a `touch` command was idempotent.
