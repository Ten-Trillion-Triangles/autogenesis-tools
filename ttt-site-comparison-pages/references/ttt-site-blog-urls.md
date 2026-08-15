# ttt-site Blog URL Pattern

Blog posts in ttt-site live in `src/content/blog/YYYY-MM-DD-slug.md` and serve at `/blog/YYYY-MM-DD-slug/`. The date prefix is part of the slug, not a path component.

## How to find blog URLs

```bash
ls /home/cage/Desktop/Workspaces/ttt-site/src/content/blog/
```

Files are named with the publication date as a prefix:

| Filename | URL |
|----------|-----|
| `2026-04-26-introducing-tpipe-agent-operating-substrate.md` | `/blog/2026-04-26-introducing-tpipe-agent-operating-substrate/` |
| `2026-05-11-p2p-agent-communication-inevitable.md` | `/blog/2026-05-11-p2p-agent-communication-inevitable/` |
| `2026-05-12-you-cannot-build-agent-substrate-in-python.md` | `/blog/2026-05-12-you-cannot-build-agent-substrate-in-python/` |

## The common mistake

Comparison pages, FAQ links, and see-also cards often reference blog posts by slug only (without the date prefix). These URLs return 404:

- ❌ `/blog/p2p-agent-communication-inevitable` → 404
- ✅ `/blog/2026-05-11-p2p-agent-communication-inevitable` → 200

When auditing dead links, use the full `/blog/YYYY-MM-DD-slug/` form to verify against the actual filesystem. If the file exists, fix the URL. If not, remove the link (per the "don't fabricate destinations" pitfall in the parent skill).

## ttt-site content directories

```
src/content/
├── docs/           # Technical documentation (70+ markdown files, synced from external TPipe repo during CI build)
└── blog/           # Blog posts (8 published as of June 2026)
```

`docs/` is overwritten by `amplify.yml` during CI — don't edit locally unless you intend to push to the source TPipe repo. `blog/` is hand-authored.

## Dead-link audit snippet

```bash
# Find all blog links in comparison pages
grep -rEoh 'href="/blog/[^"]+"' /home/cage/Desktop/Workspaces/ttt-site/src/pages/comparison/ | sort -u

# Verify each one against the dev server
for slug in $(grep -rEoh 'href="/blog/[^"]+"' src/pages/comparison/ | sed 's/href="//;s/"$//' | sort -u); do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:4321$slug")
  echo "$code  $slug"
done
```

Output of 404s = dead links to remove. Output of 200s = working.
