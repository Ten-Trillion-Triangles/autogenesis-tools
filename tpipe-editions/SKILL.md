---
name: tpipe-editions
description: TPipe multi-edition model — Community (AGPL-3.0, main branch) vs Startup (TPipe Startup License 1.0, startup-license branch) vs Commercial Agreement. Use when asking about TPipe licensing, which branch to publish from, what license text ships with an artifact, why a TPipe branch exists, or how CodeArtifact publishing is wired. Triggers on "TPipe license", "which edition", "AGPL", "Startup License", "Commercial Agreement", "MIGRATION.md", "startup branch", "CodeArtifact", "tentrilliontriangles.com".
---

# TPipe Editions

TPipe ships in three editions that share code but differ in license, source branch, and distribution channel. The Community edition is what you build from `main`; the Startup edition is what you get from the `startup-license` branch as prebuilt JARs; Commercial is negotiated with TTT LLC.

## Edition matrix

| Edition | Source branch | License | Distribution |
|---|---|---|---|
| **Community** | `main` | AGPL-3.0 | Source build via `./gradlew publishToMavenLocal`; published as `TPipe (Community)` to CodeArtifact (artifactId `TPipe`, groupId `com.github.ten-trillion-triangles`) |
| **Startup** | `startup-license` | TPipe Startup License 1.0 | Prebuilt JARs only — see `tentrilliontriangles.com/pricing/` for per-edition install commands |
| **Commercial** | negotiated | Ten Trillion Triangles LLC Commercial Agreement | Direct contact with TTT LLC |

Canonical reference: **`MIGRATION.md`** at the repo root (do not look at README for install/license — it is outdated). It explicitly redirects to `tentrilliontriangles.com/licenses/` for full terms.

## Branch confusion (read this before guessing)

- **`startup`** — historical feature branch that landed PumpStation work. Fully merged into `main`. Stale. Do not base new work on it. `git merge-base startup main` returns `82e37fb9 Update PumpStation.kt`; `startup` is 0 commits ahead and 122 behind `main`.
- **`startup-license`** — the actual licensing-edition branch. This is where the `LICENSE` file deviates from AGPL-3.0 to the TPipe Startup License 1.0. Do not delete it.
- **`main`** — Community / AGPL source of truth.

If someone says "publish from the startup branch," ask whether they mean `startup` (dead) or `startup-license` (the licensing edition). The distinction matters because the artifact shipped is different.

## TPipe Startup License 1.0 — the four distinguishing clauses

The Startup License is a poly-form license (copyright + distribution + patent + changes) built on top of standard permissive terms. Four clauses distinguish it from AGPL:

1. **Noncompete** — you cannot offer a product that competes with TPipe ("LLM orchestration, multi-agent pipeline orchestration, or overlapping core functionality"). Competing is defined broadly across interface, language, platform, pricing, deployment. Internal use is fine.
2. **Revenue cap** — anyone with ≤ $1M USD ARR may use the Startup License. Above that, you must (a) sign a Commercial Agreement, or (b) drop the Startup License and switch to AGPL-3.0. Failure to convert within 30 days auto-converts retroactively to the date you crossed $1M ARR. Misreporting revenue = 2× commercial rate + audit costs for 18 months.
3. **FOSS carve-out** — exempts OSI-licensed open-source projects from the revenue cap provided (a) source is genuinely accessible AND buildable by third parties, (b) TPipe is used as a dependency not redistributed standalone, (c) the project itself does not compete with TPipe.
4. **Automatic commercial conversion** — at fiscal year end, if TPipe-attributable ARR > $1M USD, 30-day clock to Commercial Agreement or AGPL switch.

Cure period: 32 days from written violation notice. Patent defense termination applies. Full text lives in `LICENSE` on the `startup-license` branch and at `tentrilliontriangles.com/licenses/`.

## Where the license text actually lives

- `main` → `LICENSE` at repo root is canonical AGPL-3.0 (full FSF text, ~660 lines). Bundled into published JARs via the `licenseJar` Gradle task (`build.gradle.kts:40-46`).
- `startup-license` → `LICENSE` at repo root is the TPipe Startup License 1.0 text (~225 lines).
- The published POM's `<description>` literally says `Community/AGPL tier` for the Community artifact — quick smell check that you are publishing the right artifact from the right branch (`build.gradle.kts:125`).

**Per-artifact license isolation (verified 2026-07-08, v1.0.11 publish):** the published TPipe JAR set is split across THREE artifacts, and the license boundary lives in two of them — NOT in the main JAR:

1. `TPipe-<ver>.jar` — the main compiled-Kotlin JAR. **Byte-identical across editions** for TPipe (Community and Startup share source via the `startup-license` catchup merge). Verified at v1.0.11: both editions, 6,215,302 bytes, SHA256 `a2195c97...`.
2. `TPipe-<ver>-license.jar` — the `-license` classifier artifact, bundles the per-branch `LICENSE` file. **Differs across editions:** Community = 12,111 bytes (SHA256 `d9e3e13b...`, contains AGPL-3.0); Startup = 3,667 bytes (SHA256 `6e27c3cc...`, contains TPipe Startup License 1.0). This is where license-checkers and SPDX scanners read the license from.
3. `TPipe-<ver>.pom` — POM metadata. `<name>` = `TPipe (Community)` vs `TPipe (Startup)`; `<description>` includes "Community/AGPL tier" vs "Startup tier". This is what dependency-resolution metadata carries into downstream POMs.

The main JAR containing no LICENSE means a grep on `TPipe-1.0.11.jar` for "AGPL" or "Startup License" returns nothing — the license text is purely in the classifier artifact. This is correct per Maven conventions (the `-license` classifier is the standard way to attach license text to a JAR without bloating the main artifact).

For the corrected license-separation verification recipe and the failure mode this design prevents vs enables, see the `aws-codeartifact-publishing` skill's "Per-artifact license isolation, not per-JAR" pitfall.

## LICENSE file history pitfalls (this has bitten before)

The `LICENSE` file on `main` drifted to plain GPL-3.0 at one point — a real regression, not hypothetical. Commit `da20589e` (Jun 11 2026, author: hermes) caught it: *"fix: replace LICENSE with AGPL-3.0 (was incorrectly GPL-3.0)"*. The Maven POM was advertising AGPL while the LICENSE said GPL, which silently breaks downstream license tooling (SPDX scanners, FOSS-compliance audits, Apache RAT). Whenever publishing to CodeArtifact:

1. Sanity-check `LICENSE` is the canonical AGPL-3.0 FSF text, not GPL-3.0 or anything else.
2. Compare against `gnu.org/licenses/agpl-3.0.txt` if there is any doubt.
3. If you fix it, expect to bump publish version — the fix that became `da20589e` triggered a 1.0.8 re-publish to CodeArtifact.

Other relevant commits in the LICENSE history (for archaeology):
- `82e41ada` Initial commit (custom TTT license)
- `bf645fce` Mar 31 2026 — "Changeover to AGPL" (Community edition goes AGPL)
- `42fcad0f` May 27 2026 — "implement new startup license" (drafted Startup License 1.0 on `startup-license`)
- `cafe79d3` restore AGPL-3.0 license and original README to main branch
- `d228b886` sister commit to `cafe79d3` doing the same restore

If you are auditing why a LICENSE mismatch happened, run `git log --all --oneline -- '*LICENSE*'` from the repo root.

## Publishing path

The Community edition publishes to CodeArtifact at `https://tpipe-521369004927.d.codeartifact.us-east-1.amazonaws.com/maven/tpipe-community-maven/`. The `licenseJar` artifact (classifier `license`) bundles LICENSE into every publish — see `build.gradle.kts:39-46` and the publish block at `build.gradle.kts:120-130`.

For the Startup edition, follow the per-edition install commands on `tentrilliontriangles.com/pricing/` (which references the `startup-license` branch's published artifacts and includes `aws codeartifact get-authorization-token` snippets).

## Related skills

- `tpipe-docs-maintenance` — audit code changes vs documentation. The licensing model rarely changes but it is the kind of thing the audit flags if MIGRATION.md or `build.gradle.kts` is forgotten during an edition-model update.