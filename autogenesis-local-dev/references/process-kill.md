# Process Kill Sequence — Autogenesis Dev Servers

The user explicitly expects all dev servers shut down at the end of
every interactive session. They'll ask "did you shut the servers down?"
otherwise. Run this sequence before signing off.

## What's running when dev is up

| Process owner | PID group | Port(s) | Notes |
|---|---|---|---|
| `:server:run` gradle wrapper | gradle wrapper shell PID | 9080, 9091 | Netty/HTTP+WS, long-lived JVM |
| `:server-extend:run` gradle wrapper | gradle wrapper shell PID | 7070, 9092 | Python FastAPI bridge, long-lived JVM |
| `:kvisionApp:jsBrowserDevelopmentRun` gradle wrapper | gradle wrapper shell PID | 8080 | webpack-dev-server |
| `webpack` (child of gradle wrapper) | spawned by gradle | 8080 | same port as parent |
| Kotlin compile daemon (shared) | gradle daemon | none | survives server kills, that's OK |
| Gradle daemon | gradle daemon | none | survives server kills, that's OK |

## Kill sequence

```bash
# Kill in order: webpack → kvision gradle → server-extend → server
pkill -f "jsBrowserDevelopmentRun"    # kills webpack + kvision gradle wrapper
pkill -f "server:run"                  # kills game server gradle wrapper
pkill -f "server-extend:run"           # kills server-extend gradle wrapper
sleep 3

# Verify all ports free
ss -tlnp 2>/dev/null | grep -E ":(7070|8080|9080)" || echo "all clear"

# Also verify no orphaned JVMs holding autogenesis-classes.jar
ps aux | grep -E "java.*ServerKt|java.*ServerExtend|webpack" \
    | grep -v grep | grep -v "language-server" || echo "no leftover JVMs"
```

## What NOT to do

- Don't `pkill -9 gradle` — that kills the Gradle daemon too which is
  shared with the IDE and slows the next session's first compile by
  30+ seconds. Killing the per-task gradle wrapper is enough.
- Don't try to free ports by killing the LISTENING socket with
  `ss -K` — the JVM that holds the port will keep it reserved, you
  must kill the JVM.
- Don't trust `pkill -f gradle` — gradle daemons match too broadly and
  you'll kill the IDE's daemon.

## Why "pkill -f" works but `kill <pid>` is brittle

The process names change between sessions (different PIDs each boot)
but the command lines are stable. `pkill -f` matches command line. Use:

- `pkill -f "jsBrowserDevelopmentRun"` — matches the gradle wrapper
  whose full command line includes `:kvisionApp:jsBrowserDevelopmentRun`.
  This kills BOTH the wrapper AND the webpack child (since webpack is
  its child process group).
- `pkill -f "server:run"` — matches the gradle wrapper whose command
  line includes `:server:run`. (Beware: matches `:server-extend:run`
  too if run later, so do `:server-extend:run` LAST or do them with
  exact prefixes.)

## If pkill fails to free a port

Sometimes the JVM doesn't die on TERM signal. SIGKILL is then needed:

```bash
pkill -9 -f "jsBrowserDevelopmentRun"
pkill -9 -f "server:run"
pkill -9 -f "server-extend:run"
```

The gradle wrapper shells usually exit on their own once the child
JVM dies. If a port is STILL held after SIGKILL, find the inode via
`ss -tlnp` and report — something else (Docker, kvm, unrelated) has
the port.

## Verifying you actually killed everything

Three independent checks. All three must agree.

1. **Ports free:** `ss -tlnp | grep -E ":(7070|7075|7071|8080|9080|9091|9092)"` returns nothing.
2. **No autogenesis JVMs:** `ps aux | grep -E "java.*ServerKt|java.*ServerExtend" | grep -v grep` returns nothing.
3. **No autogenesis node:** `ps aux | grep -E "webpack" | grep -v grep` returns nothing.

If any one shows something, keep killing until all three are clear.
Don't trust a single check.

## What to leave alive

- Gradle daemon (GradleDaemon / KotlinCompileDaemon) — kills between
  sessions are fine but not required; the warm cache speeds up next
  compile.
- IDE process tree (IntelliJ) — must NOT be touched.
- All non-autogenesis node/java/gradle processes — must NOT be touched.

The kill pattern `pkill -f <substring>` is safe because the substring
is specific to the autogenesis gradle wrapper.