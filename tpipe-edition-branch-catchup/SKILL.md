---
name: tpipe-edition-branch-catchup
description: "Catchup procedure for the TPipe dual-edition model — merging `main` into `startup-license` (the canonical Startup-edition branch) while preserving the three license-boundary files (LICENSE, README.md, build.gradle.kts publishing block). Use when asked to 'catchup startup-license', 'merge main into startup-license', 'sync startup with main', or any TPipe-edition-branch sync operation. Also load when investigating why the `startup` branch has the wrong license (it is the stale duplicate; `startup-license` is canonical), when LICENSE / README banner / POM name drift between branches, or when setting up a new edition (Community / Startup / Commercial) that needs a frozen ancestor branch."
version: 1.0.1
author: Ten Trillion Triangles LLC
license: Apache-2.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [tpipe, git, license, dual-edition, merge, branch-management]
    related_skills:
      - open-source-licensing   # the licensing-design skill — covers the tri-license MODEL
      - git-branch-reconciliation   # general "merge X into Y preserving identity-specific code"
      - aws-codeartifact-publishing   # legacy CodeArtifact publish path (pre-PublishPoint)
      - static-hosted-maven-repository   # PublishPoint-side consumer/install block
---

# TPipe Edition-Branch Catchup Procedure

TPipe ships under two editions with **separate license branches**:

| Branch | Edition | License | POM `<name>` | CodeArtifact repo | PublishPoint URL prefix |
|---|---|---|---|---|---|
| `main` | Community | AGPL-3.0 | `TPipe (Community)` | `tpipe-community-maven` | `…/community/` |
| `startup-license` | Startup | TPipe Startup License 1.0 | `TPipe (Startup)` | `tpipe-startup-maven` | `…/startup/` |

The two branches have **intentionally-frozen source divergence on three files only**:

1. **`LICENSE`** — full license text per edition.
2. **`README.md`** — `startup-license` carries a "⚠️ Startup License Branch" banner redirecting AGPL-seekers to `main`.
3. **`build.gradle.kts`** — only the `publishing { publications { create<MavenPublication>("maven") { pom { name.set(...) ; description.set(...) } } } }` block differs (POM name + CodeArtifact repo URL).

All Kotlin source code is byte-identical across branches. The license divergence lives entirely in those three files.

## The stale `startup` branch trap

**There is also a `startup` branch that is NOT canonical.** It is a stale duplicate created from `main` early in the project's dual-edition setup (commit `82e37fb9`), now ~122 commits behind main with no purpose. Every catchup merge into `startup` silently overwrites the license with AGPL because there's no boundary protection. It is NOT what the user means by "catchup startup." **Always operate on `startup-license`, not `startup`.** Memory carries this fact; future agents have repeatedly asked about the duplication, so the rule is: if the user says "startup" without "-license," confirm via `git branch -a | grep startup` before doing anything.

## When to use this skill

- Operator asks to catchup `startup-license` from `main`.
- Operator asks to merge `main` into `startup-license`.
- A `verifyLicenseBoundary`-style test fails on `startup-license`.
- LICENSE / README / build.gradle.kts drift is detected between branches.
- Setting up a NEW edition branch (e.g. a third "Commercial" tier) following the same pattern.

## When NOT to use this skill

- **Code-level changes to TPipe source code.** Those go on `main` first, then catchup to `startup-license` via this procedure. Do not edit source on `startup-license` directly.
- **Initial bootstrap of the dual-edition model.** Use `open-source-licensing` skill for the tri-license design, then come back here for the operational pattern.
- **Publish-side work.** Once branches are in sync, the publish workflow lives in `aws-codeartifact-publishing` (CodeArtifact, legacy) or `static-hosted-maven-repository` / the `publishpoint` skill (current path).
- **General branch-reconciliation unrelated to license/edition branches.** Use `git-branch-reconciliation` for provider/identity preservation (OpenRouter vs Bedrock, Anthropic vs OpenAI).

## Procedure (canonical, verified 2026-07-17)

### Step 0 — Confirm pre-state on `startup-license`

Before any merge, verify `startup-license` itself is in canonical Startup-edition state. Run:

```bash
git checkout startup-license
head -3 LICENSE                                            # must be "TPipe Startup License 1.0"
grep -c "TPipe (Startup)" build.gradle.kts                 # non-zero → Startup POM present
grep -c "Startup License Branch" README.md                # non-zero → Startup banner present
```

If any of these fail on `startup-license`, STOP — fix `startup-license` first by checking out the canonical blobs from the prior published commit. Do NOT proceed with the catchup merge from a broken baseline.

### Step 1 — Fetch latest from origin

```bash
git fetch origin main startup-license
```

This guarantees you're not merging from a stale local view of main.

### Step 2 — Identify what main has that startup-license lacks

```bash
git merge-base HEAD origin/main
git log --oneline $(git merge-base HEAD origin/main)..origin/main | wc -l   # commit count
git diff --name-only $(git merge-base HEAD origin/main)..origin/main | grep -E '^(LICENSE|README\.md|build\.gradle\.kts)$'
```

The second command tells you whether main has touched any of the three boundary files since the merge-base. **If main has changed LICENSE / README.md / build.gradle.kts, expect a textual conflict on those files at merge time** — see Step 4.

### Step 3 — Run the catchup merge with no-fast-forward

```bash
git merge --no-ff origin/main \
    -m "merge(main): catchup startup-license, preserve LICENSE + README + Startup POM"
```

The `--no-ff` flag is load-bearing. It forces a merge commit (not a fast-forward), preserving the topology that shows `startup-license` as a long-running parallel branch rather than a fork that silently got reabsorbed. Future bisects and audit logs depend on this.

### Step 4 — Resolve boundary-file conflicts (if any)

If main changed LICENSE / README.md / build.gradle.kts since the merge-base, `git merge` will pause on those files. The resolution is **always the startup-side version**, never the main-side version:

```bash
git checkout --ours LICENSE README.md build.gradle.kts
git add LICENSE README.md build.gradle.kts
git merge --continue
```

This is the entire license-boundary contract. The `startup-license` side wins on the three files; everything else takes the main-side value automatically.

### Step 5 — Verify post-merge state

```bash
head -3 LICENSE                                            # still "TPipe Startup License 1.0"
grep -c "TPipe (Startup)" build.gradle.kts                 # still non-zero
grep -c "Startup License Branch" README.md                # still non-zero
git diff $(git rev-parse HEAD~1) HEAD --stat                # shows what came in from main
```

All three boundary checks must still pass. If any drifted (e.g. `LICENSE` shows "GNU AFFERO GENERAL PUBLIC LICENSE"), the merge was not done correctly — abort and re-do.

### Step 6 — Verify compileKotlin on `startup-license`

```bash
JAVA_OPTS="-Xmx2g" ./gradlew :compileKotlin --no-daemon --offline
```

This is the load-bearing build verification. `--offline` skips the chronotrace init-script token gate. The recipe takes ~1 minute on TPipe HEAD. Any warnings shown are pre-existing carry-overs (Pipe.kt `@Transient` redundancy, HttpExecutor.kt `URL` deprecation, Manifold.kt `Condition is always 'true'`, Util.kt `Json format` redundancies, McpSessionManager.kt `when` exhaustiveness) — these are NOT regressions from the merge. New warnings would be a signal to investigate; the same list of files warning today is the baseline.

### Step 7 — Push to origin

```bash
git push origin startup-license
```

This step requires GitHub auth configured in the shell. From the operator's terminal: `gh auth login` if not already configured. From a sandboxed CI without auth, this step blocks — flag the blocker explicitly to the operator; do NOT mark the catchup as done until push succeeds.

## Boundary-file preservation — what to do, what NOT to do

**Do:**
- Use `--no-ff` (Step 3) — preserves parallel-branch topology.
- Take `--ours` on the three boundary files at conflict time (Step 4).
- Verify each boundary file post-merge (Step 5).

**Do NOT:**
- Do not edit LICENSE / README.md / build.gradle.kts on `startup-license` to "fix drift" — the drift IS the license story. If main legitimately needs to update one of these (e.g. publishing block metadata), update `startup-license` separately with a focused commit. Don't try to merge a one-sided change through the catchup procedure.
- Do not run `git pull` on `startup-license` without inspecting. A bare pull is fast-forward-friendly and silently drops the merge-commit history that future audits depend on.
- Do not introduce a `.gitattributes` `merge=ours` directive as a "lock". This was tried on 2026-08-04 and is doubly broken — see the pitfall below.

### Pitfall — `.gitattributes` `merge=ours` does not actually defend the boundary

The instinct is to add to `.gitattributes`:

```
LICENSE merge=ours
README.md merge=ours
build.gradle.kts merge=ours
```

and have future merges auto-resolve the boundary. Verified 2026-08-04 against a throwaway clone with synthetic AGPL/Community rewrites — **this does not work, in two distinct ways.**

**Why the attribute itself is silently ignored.** Per `man gitattributes`, the `merge` attribute accepts only built-in driver names (`text`, `binary`, `union`) or a custom driver name registered via `[merge "<name>"] driver = ...` in `.git/config`. The strings `ours` and `theirs` are NOT valid values — they are merge STRATEGY OPTIONS (`-X ours` / `-X theirs`), passed at the command level, not file-level attributes. When git sees `merge=ours`, it parses `ours` as "use a custom merge driver named `ours`." No driver is registered under that name, so git silently falls back to the default 3-way merge. `git check-attr merge -- LICENSE` correctly reports `ours` (the lookup succeeds), but the resolution is unchanged.

**Why a registered custom driver still wouldn't fire for THIS boundary.** Even with a real driver wired, it would not help. The startup-license boundary files vs main are wholesale content replacements: main's LICENSE is AGPL-3.0 (~660 lines, completely different text), startup's is TPipe Startup License 1.0 (~224 lines). git's 3-way merge sees both sides changed the file but the changes are not textually conflicting at the merge-hunk level — git auto-merges by taking the THEIRS content because both sides are complete rewrites. There is no conflict for the per-file merge driver to resolve. The path does not enter the driver at all.

**Symptom signature for this pitfall (check after ANY catchup, not just ones where you used `.gitattributes`):**

- `git check-attr merge -- LICENSE` returns `ours` (attribute set, no syntax error)
- `git merge` exits 0 with "Automatic merge went well" — no conflict flagged
- Working tree shows main's content on the boundary file anyway
- `git rev-parse HEAD:LICENSE` blob SHA matches main, not startup-license

**Reproduction recipe (run BEFORE believing any `.gitattributes` defense works):**

```bash
TMP=$(mktemp -d)
git clone -q --no-local --branch startup-license "$PWD" "$TMP/repo"
cd "$TMP/repo"
git checkout -q -b fake-mainline HEAD
printf 'GNU AFFERO GENERAL PUBLIC LICENSE\nVersion 3\n%s\n' "$(date)" > LICENSE
sed -i 's|TPipe (Startup)|TPipe (Community)|;s|tpipe-startup-maven|tpipe-community-maven|' build.gradle.kts
printf '# plain readme no preamble\n' > README.md
git add -A && git commit -q -m "synthetic mainline rewrite"
git checkout -q fake-mainline~  # back to startup-license HEAD
git merge --no-commit --no-ff fake-mainline 2>&1 | tail -5
head -3 LICENSE  # if this shows "GNU AFFERO", the defense is inert
cd - && rm -rf "$TMP"
```

If the merge "succeeds" with AGPL in LICENSE, the defense is broken. The recipe costs ~10 seconds.

**Correct mechanisms, in order of preference:**

1. **`git checkout --ours LICENSE README.md build.gradle.kts` after merge** — always do this on startup-license catchups even if `git merge` succeeded silently with no conflict. The wholesale-replacement case never flags a conflict, so the only way to know whether you need the restore is to verify post-merge (see Step 5). Combine with the post-merge `grep` checks below to catch the case where you forgot.
2. **Blob-restore recipe** (capture pre-merge SHAs, restore via `git cat-file -p` after merge, commit as separate restore commit) — for FF merges or where the post-merge shape is complex enough that `git checkout --ours` could mask a real conflict.
3. **Custom merge driver + `.gitattributes`** — only useful for genuine textual conflicts (additive changes on both sides). Does NOT trigger on wholesale replacements. Same blind spot as `-X ours`. Skip for this boundary.

The `--ours` resolution at conflict time is sufficient and human-reviewed each merge. An automated merge directive would bypass that human review and, as proven above, would not work anyway.

## Cross-edition sync for the `startup` stale duplicate (special case)

If the operator specifically asks about `startup` (the stale branch, not `startup-license`):

1. Run the same catchup procedure against `startup` if a catchup is genuinely wanted.
2. Then re-run Steps 4-5 with the AGPL/Side fix: `git checkout startup-license -- LICENSE README.md build.gradle.kts` to restore the Startup-edition blobs.
3. Recommend the operator delete `startup` (`git push origin --delete startup && git branch -D startup`) — its purpose ended with `startup-license` becoming canonical. If the operator declines deletion, document the trap clearly in CLAUDE.md so future agents don't conflate the two branches.

## Source-convergence caveat

TPipe's primary JARs are byte-identical across `main` and `startup-license` at HEAD (source-converged; tier divergence is in LICENSE/README/POM only). This was an intentional simplification after the dual-tier rollout. If source-level divergence is ever reintroduced (e.g. a `TIER` constant embedded in the binary per edition), the catchup procedure does not change — but the boundary file set expands to include any per-edition source files. Update CLAUDE.md's "License Boundary" section if this happens.

## Origin

Captured from a TPipe dual-edition catchup session. Verified end-to-end: LICENSE / README.md / build.gradle.kts preserved byte-identical to canonical Startup-edition blobs, `:compileKotlin` succeeded in 1m 2s, merge commit `e08266f3 merge(main): catchup startup-license, preserve LICENSE + README + Startup POM` shipped with all three boundary checks passing.
