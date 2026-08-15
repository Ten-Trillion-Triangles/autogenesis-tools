# Astro dev server management for ttt-site

## The stale server problem

The Astro dev server (`npm run dev`) started on 2026-06-01 ran for 5 days without restart. After that long, it can serve stale content — file changes are detected by the watcher but not reflected in the live page because the content cache in the dev server process is out of sync.

**Symptom**: You edited the `.md` file, `curl` returns the old text.

**Why it happens**: The Astro content layer caches the parsed frontmatter and content. After days of uptime, this cache can desync from the actual files.

**Fix**: Kill and restart the server.

```bash
# Find and kill the process on port 4321
kill $(lsof -t -i:4321 -s TCP:LISTEN 2>/dev/null)

# Wait, then restart in background
cd /home/cage/Desktop/Workspaces/ttt-site
npm run dev > /tmp/astro-dev.log 2>&1 &

# Wait for startup, then verify
sleep 8
ss -tlnp | grep 4321
curl -s -o /dev/null -w "live: %{http_code}\n" http://127.0.0.1:4321/blog/
```

## The upstream-reaper SIGKILL pattern (HMR + reaper conflict)

Distinct from the stale-cache problem above. Symptom set: `npm run dev` starts, serves a handful of requests successfully (each shows up in stdout as `127.0.0.1 - - [date] "GET /..." 200 -`), then exits with code `137` (SIGKILL). Process never gets a chance to print a stack trace or write a crash log. Memory looks fine (`free -h` shows 49Gi+ available), swap is idle, and re-running the same `npm run dev` reproduces within 30-90 seconds. With multiple `astro dev` cycles in one session, every one gets SIGKILLed the same way.

**Cause** (observed pattern, 2026-07-01 session, four consecutive kills): an upstream reaper (Hermes runtime idle-kill, container OOM watcher, or cgroup limit) terminates any long-lived foreground child process attached to this terminal context. The Astro dev server is the canary because its Vite HMR triggers a `[vite] program reload` cluster that keeps the process active and connected — exactly the behavior the reaper is watching for.

**The Vite error inside the kill window is the trigger, not the cause.** The log will show `Failed to load url astro:server-app.js (resolved id: astro:server-app.js)` followed by a HMR cycle, then the kill. That Vite error is a known Astro v6 HMR quirk that happens routinely and is recovered automatically on the next reload. Trying to "fix" the Vite error by editing Astro config wastes a session; the kill is happening regardless.

**Reliable fallbacks**, in order of preference:

1. **Use the existing `dist/client/` build with a static file server.** Astro is a static site by default — `npm run build` emits a complete site into `dist/client/` and that's the exact same HTML the dev server serves. A bare `python3 -m http.server 4321 --bind 127.0.0.1 --directory dist/client` serves the site identically. Pro: zero upstream reaper exposure (Python's `http.server` is intermittent and gets reaped cleanly when it dies, the user reads what was served, no surprise hot-reload mid-thought). Con: changes to `src/` are NOT picked up automatically — rebuild after each edit.

2. **Use `npx serve dist/client -l 4321`** if Python isn't preferred. Same trade-off as #1.

3. **Run the dev server inside `setsid` or `nohup` to detach from the terminal.** Sometimes the reaper is bound to the terminal session, not the process. Frequently doesn't help (the reaper sees process tree by PID, not by session), but worth one attempt before going to #1.

```bash
# Fallback #1 (recommended when dev server dies more than twice):
cd /home/cage/Desktop/Workspaces/ttt-site
npm run build                                          # ~10s; populates dist/client/
cd dist/client && python3 -m http.server 4321 --bind 127.0.0.1
# Note: cd + server in same process group. If port 4321 collides with a zombie
# astro dev (common after a SIGKILL), pick the next port (4322, 4323, ...).
# Verify the new URL with curl before sharing with the user.
```

**Side effect to watch for**: when using the static server, `public/llms.txt` and other text files are served from `dist/client/llms.txt`, which is a COPY of `public/llms.txt` taken at build time. Any edit to `public/llms.txt` after a build is invisible on the static server until the next `npm run build`. Same drift applies to anything else in `public/` — images, icons, redirects. Re-run `npm run build` after any `public/*.txt` or `public/assets/*` edit.

## YAML frontmatter indentation errors

Astro's content collection loader uses a YAML parser. **4-space indentation for all list items within frontmatter arrays.** Indentation errors cause the content loader to fail silently (server starts, page returns 404 or empty content).

### The error

```
bad indentation of a mapping entry
  Location: /home/cage/Desktop/Workspaces/ttt-site/src/content/blog/2026-06-06-how-to-build-a-tpipe-pipeline.md:34:6
```

This error appears in the Astro dev server log. The server still starts and serves other pages, but the malformed page returns 404.

### The pattern

The ttt-site blog frontmatter has `faqItems` and `howToSteps` arrays with `name:` / `text:` pairs. The `text:` field must be at **exactly 4 spaces of indentation** under its list item:

```yaml
faqItems:
  - question: "What is this?"
    answer: "Something."
  - question: "How do I use it?"
    answer: "Like this."
```

Common mistake (6 spaces on `text:`):
```yaml
faqItems:
  - question: "What is this?"
      text: "This is wrong — 6 spaces."   # WRONG
  - question: "How do I use it?"
    answer: "This is also wrong."          # WRONG
```

The Astro YAML parser is strict. All list children under `- name:` / `- question:` / etc. must be at 4 spaces relative to the list item, not 6.

### Verification after any frontmatter edit

After editing any `.md` file in `src/content/blog/`, check:
1. Server log: `tail /tmp/astro-dev.log` — look for "bad indentation" or "Synced content"
2. The page: `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:4321/blog/YYYY-MM-DD-slug/`
3. The actual text: `curl -s http://127.0.0.1:4321/blog/YYYY-MM-DD-slug/ | grep "unique phrase from the file"`

## Astro content config

The schema is at `ttt-site/src/content.config.ts`. Every blog post needs:
- `title`, `description`, `author` ("Richard Wang"), `publishDate`, `updatedDate`
- `hasFAQ: true`, `hasHowTo: true`, `schemaTypes: ["FAQ", "HowTo"]` for tutorial posts
- `faqItems[]` — `{question, answer}` pairs
- `howToSteps[]` — `{name, text}` pairs with imperative voice

The FAQ and HowTo arrays are parsed as YAML arrays of objects. **All fields within list items must be at the same indentation level** (4 spaces for `text`/`answer` fields).

## Quick verification checklist

After any change to a blog post:
```bash
# Check server is up
ss -tlnp | grep 4321

# Check page loads
curl -s -o /dev/null -w "post: %{http_code}\n" http://127.0.0.1:4321/blog/YYYY-MM-DD-slug/

# Check content is fresh (look for a phrase you just wrote)
curl -s http://127.0.0.1:4321/blog/YYYY-MM-DD-slug/ | grep "unique phrase"

# Check for YAML errors in server log
tail -5 /tmp/astro-dev.log
```