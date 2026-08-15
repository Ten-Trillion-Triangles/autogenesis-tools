---
name: ttt-site-pricing
description: "TPipe/TenTrillionTriangles marketing site pricing page — PublishPoint artifacts (CloudFront-fronted S3, no auth), install modal contents, license tier commands, and pricing component patterns. Triggers on: pricing page, install command, TierCards, InstallModal, license tier, Community vs Startup artifact, version bump procedure."
---

# ttt-site Pricing Components

Site: `https://www.tentrilliontriangles.com/pricing/`

## License Tiers and Artifact Versions

**As of 2026-08-13 (verified live on tentrilliontriangles.com/pricing):** TPipe migrated to PublishPoint (CloudFront-fronted S3, no auth). **CodeArtifact is deprecated.** See `publishpoint` skill for the producer-side flow and `static-hosted-maven-repository` for the host-decision context.

| Tier | Plan Name | License | PublishPoint URL Prefix | Maven Coordinate |
|------|-----------|---------|-------------------------|-------------------|
| Pipe | Community | AGPL-3.0 | `https://d8777bk79dr28.cloudfront.net/community/` | `com.github.ten-trillion-triangles:TPipe:1.0.15` |
| Pipeline | Startup/Indie | TPipe Startup License 1.0 (Noncompete, $1M ARR cap per TPipe-using product) | `https://d8777bk79dr28.cloudfront.net/startup/` | `com.github.ten-trillion-triangles:TPipe:1.0.15` |
| Manifold | Commercial | Closed-source (>$1M/yr) | Contact Sales | — |
| Substrate | Enterprise | Custom | Contact Sales | — |

**As of 2026-08-13:** the latest published version is **1.0.15** on both PublishPoint tiers. JARs are byte-similar across editions on 1.0.15 (source-convergence on `main` and `startup-license` by design — see the "License boundary invariant" section in the publishpoint skill). License isolation lives in `-license.jar` and POM `<name>`. The version string is encoded in:
- `src/components/pricing/TierCards.astro:6-7` — `PIPE_COMMAND` and `PIPELINE_COMMAND` constants (the `implementation(...)` strings rendered in the modal)
- `src/components/pricing/InstallModal.astro:10-11` — `pipeCommand` and `pipelineCommand` default props

Both pairs must be bumped together on a version release. After bumping, `npm run build` should produce `dist/client/pricing/index.html` containing 3× the new version string and 0× the old one — verify with `grep -c "TPipe:1.0.X" dist/client/pricing/index.html`.

**Note:** The Maven coordinate (`com.github.ten-trillion-triangles:TPipe:1.0.10`) is identical for both editions. The repo URL is what determines which license binary ships. Different editions = different CodeArtifact repos = different binaries at the same coordinate.

**GitHub tag convention** (for the publish workflow): `TPipe-Community-1.0.10` on `main`, `TPipe-Startup-1.0.10` on `startup-license`.

## CRITICAL: License File Disambiguation

**The actual deployed license is at `https://www.tentrilliontriangles.com/licenses/LICENSE.TPipe-Startup.txt` — ALWAYS use this as the source of truth.** It is a BSL-style license with a Noncompete clause (Section 6), NOT an "AGPL with commercial carve-out below $1M" license. The restriction is on building **competing products** (LLM orquestación, multi-agent pipeline orquestación, or anything overlapping with TPipe's core purpose), NOT on "no public forks" or "no standalone distribution" as a casual reader might assume.

**Drafts/alternatives live in the TPipe repo at `License-templates/`.** These are NOT necessarily what is deployed:
- `License-templates/LICENSE.TPipe-Commercial.md` — a different/older commercial-addendum style license. **Do not use this for the pricing page** — it describes a different model (Permitted Uses + FOSS exception with 4 conditions) that does not match the live Startup license.
- `License-templates/LICENSE.TPipe-Commercial-Upgrade.md` — the upgrade agreement template for above-$1M buyers.
- `License-templates/LICENSE` — likely a draft AGPL, not the Startup license.

**Rule of thumb:** when the user gives you a license URL, that's the source of truth. License-templates/ is a working directory and may contain drafts. Before writing any tier descriptions, FAQ content, or license mechanics, read the deployed file from the live site.

## Key Files

- `src/components/pricing/TierCards.astro` — plan cards, "Get Started" triggers, passes props to InstallModal
- `src/components/pricing/InstallModal.astro` — install steps modal with per-plan content (3-step flow: add PublishPoint repo → add TPipe dependency → set JVM toolchain)
- `src/components/pricing/PricingFAQ.astro` — pricing-page FAQ (see "FAQ Content" section below)
- `src/components/pricing/FeatureTable.astro` — full feature matrix across all 4 tiers
- `src/components/pricing/ContactForm.astro` — Manifold/Substrate "Contact Sales" form (POSTs to API Gateway directly, not `/api/contact`)

## Reference Files

- `references/install-modal-live-snapshot-2026-08-13.md` — exact rendered HTML/text of the live install modal for both Pipeline (Startup) and Pipe (Community) tiers, captured 2026-08-13. Use this when auditing the modal against the .astro source, or when triaging "what does the user actually see today?" reports.

## FAQ Content (`PricingFAQ.astro`)

The pricing page has a 16-question FAQ. When editing it, follow these rules:

**1. Read the deployed license, not drafts in License-templates/.** The licensing model in the actual `LICENSE.TPipe-Startup.txt` (BSL-style, Noncompete) is different from the older `License-templates/LICENSE.TPipe-Commercial.md` (AGPL-with-addendum, Permitted Uses). Writing FAQ content from the wrong file will produce factually wrong answers.

**2. ARR is per TPipe-using product, not per legal entity.** Section 13 of the actual license defines ARR as "Total annual revenue in USD, calculated according to generally accepted accounting principles, from all sources attributable to your TPipe-using product or service." A company with $50M total revenue but $500K from their TPipe product still qualifies for Startup.

**3. Above $1M, there are TWO paths, not one.** Section 7 of the actual license: above $1M, the user has 30 days to either (a) enter a Commercial Agreement with TTT, or (b) switch to AGPL-3.0 by releasing their TPipe modifications. Failure to do either converts retroactively backdated to the day they exceeded $1M. Do not present "you must upgrade to Commercial" as the only option.

**4. Don't write encyclopedia-style answers.** Real competitor pricing FAQs (MongoDB SSPL FAQ, HashiCorp BSL FAQ, GitLab licensing FAQ, Confluent Community License FAQ) are operational and brief, not comprehensive. Pricing pages are sales tools, not license texts. License boilerplate (patent termination, audit rights, anti-extraction clauses, liability caps, indemnification, survival) belongs in the license file, not the FAQ.

**5. Don't restructure or remove questions without cause.** The 16-question structure and bluf (bold first sentence) pattern are fine. Common LLM mistakes: removing "minimum Substrate contract" because the price is in the TierCard, removing "what's in the free Community tier" because the FeatureTable shows it. Trust the existing structure; fix only the actual errors.

**6. Don't add editorializing language.** Phrases like "plan accordingly", "today", "you'll need to" or framing things as warnings/legal threats come off as marketing copy that real users see through. State facts directly.

## Maven Repository URL Format (PublishPoint)

**TPipe artifacts are hosted on PublishPoint** (CloudFront-fronted S3, no auth). The CodeArtifact approach used previously is **deprecated as of 2026-08-08** — see `publishpoint` skill for the current pattern. The raw-GitHub-Maven and GitHub-Releases patterns are deprecated as of 2026-06-11 and 2026-07-12 respectively.

**Maven repository URL per edition (verified live 2026-08-13):**
```
# Community edition (AGPL-3.0)
https://d8777bk79dr28.cloudfront.net/community/

# Startup edition (TPipe Startup License 1.0)
https://d8777bk79dr28.cloudfront.net/startup/
```

**Users add this to their `settings.gradle.kts`:**
```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven {
            name = "TPipeStartup"  // "TPipeCommunity" for the Pipe tier
            url = uri("https://d8777bk79dr28.cloudfront.net/startup/")
        }
        mavenCentral()  // required: PublishPoint bucket only carries com.github.ten-trillion-triangles:TPipe
    }
}

dependencies {
    dependencies {
        implementation("com.github.ten-trillion-triangles:TPipe:1.0.15")
    }
}
```

**No auth required.** PublishPoint CloudFront serves artifacts anonymously. Consumers do NOT need to:
- Set any env var or AWS credential
- Install AWS CLI
- Fetch or rotate a token

**Consumer-side `mavenCentral()` is required** for transitive resolution — see `publishpoint` skill PITFALL on transitive resolution. Without `mavenCentral()` in the same `repositories { ... }` block, transitive deps like `org.jetbrains.kotlin:kotlin-stdlib` 403 against the PublishPoint bucket.

**For consumers on Gradle versions where `ignoreGradleMetadataRedirection` is needed:** add `metadataSources { mavenPom(); artifact(); ignoreGradleMetadataRedirection() }` on the PublishPoint maven block to skip the shadow variant. See `publishpoint` PITFALL on `*.module` shadow references.

**Important:** Both editions use the same Maven coordinate (`com.github.ten-trillion-triangles:TPipe:1.0.15`). The repo URL prefix is what determines which license binary ships. Different editions = different URL prefixes = different `-license.jar` content (and POM `<name>`) at the same coordinate. See `publishpoint` skill "Dual-tier convention" for the full mechanism.

## Install Modal Dynamic Linking Pattern

The install modal is a **single shared instance** used by all plan tiers. Both the Gradle `implementation()` command AND the CodeArtifact repo URL must update when a trigger fires, based on which plan opened the modal. The current modal has a 3-step flow (add to `settings.gradle.kts` → add TPipe dependency → set JVM toolchain) — the auth token is auto-fetched at Gradle init, not shown as a separate step.

**TierCards.astro — define both command and CodeArtifact URL per tier (CURRENT as of 1.0.10):**
```astro
const PIPE_COMMAND = 'implementation("com.github.ten-trillion-triangles:TPipe:1.0.10")';
const PIPELINE_COMMAND = 'implementation("com.github.ten-trillion-triangles:TPipe:1.0.10")';
const PIPE_JITPACK_URL = 'https://tpipe-521369004927.d.codeartifact.us-east-1.amazonaws.com/maven/tpipe-community-maven/';
const PIPELINE_JITPACK_URL = 'https://tpipe-521369004927.d.codeartifact.us-east-1.amazonaws.com/maven/tpipe-startup-maven/';
```

**Current install modal flow (3 steps, less manual than the original 4-step):**

(Note: the variable names `PIPE_JITPACK_URL` / `PIPELINE_JITPACK_URL` are legacy from the JitPack era and still in use — they hold CodeArtifact URLs now. The class name `jitpack-link` is also legacy. Don't rename in a half-step; rename as a paired refactor when convenient.)

**Pass as props to InstallModal:**
```astro
<InstallModal
  pipeCommand={PIPE_COMMAND}
  pipelineCommand={PIPELINE_COMMAND}
  pipeJitpackUrl={PIPE_JITPACK_URL}
  pipelineJitpackUrl={PIPELINE_JITPACK_URL}
/>
```

**Trigger buttons include `data-jitpack-url` (legacy name, holds CodeArtifact URL):**
```astro
<Button variant="primary" href="#" size="md" class="install-trigger"
  data-install-command={PIPE_COMMAND}
  data-jitpack-url={PIPE_JITPACK_URL}>
  Get Started
</Button>
```

**InstallModal.astro — props interface (ACTUAL prop names — legacy `pipeJitpackUrl`):**
```astro
export interface Props {
  pipeCommand?: string;
  pipelineCommand?: string;
  pipeJitpackUrl?: string;      // CodeArtifact Community URL
  pipelineJitpackUrl?: string; // CodeArtifact Startup URL
}

const {
  pipeCommand = 'implementation("com.github.ten-trillion-triangles:TPipe:1.0.10")',
  pipelineCommand = 'implementation("com.github.ten-trillion-triangles:TPipe:1.0.10")',
  pipeJitpackUrl = 'https://tpipe-521369004927.d.codeartifact.us-east-1.amazonaws.com/maven/tpipe-community-maven/',
  pipelineJitpackUrl = 'https://tpipe-521369004927.d.codeartifact.us-east-1.amazonaws.com/maven/tpipe-startup-maven/',
} = Astro.props;
```

**Step 1 — settings.gradle.kts (PUBLISHED LIVE 2026-08-13):**
```kotlin
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        maven {
            name = "TPipeStartup"  // "TPipeCommunity" for the Pipe tier
            url = uri("https://d8777bk79dr28.cloudfront.net/startup/")  // "/community/" for Pipe tier
        }
        mavenCentral()  // required — PublishPoint bucket only carries com.github.ten-trillion-triangles:TPipe
    }
}
```

**No auth required.** The PublishPoint bucket is served via public CloudFront with no auth layer. Consumers do NOT need to:
- Set any env var or AWS credential
- Install AWS CLI
- Fetch or rotate a token

**Why this is "less manual than the CodeArtifact era":** The earlier 4-step flow had an `aws codeartifact get-authorization-token` provider baked into `settings.gradle.kts`. That provider is GONE from the published modal — the live step-1 block is just the two `maven { }` calls above.

**The single PITFALL the modal doesn't show:** `mavenCentral()` must be present alongside the PublishPoint `maven { }` block. PublishPoint bucket only carries `com.github.ten-trillion-triangles:TPipe` — it does NOT carry `org.jetbrains.kotlin:kotlin-stdlib`, ktor, logback, or any other transitive. Without `mavenCentral()` in the same `repositories { }` block, transitive deps 403 against the PublishPoint bucket.

**Consumer-side `build.gradle.kts`:**
```kotlin
dependencies {
    implementation("com.github.ten-trillion-triangles:TPipe:1.0.15")
}
```

No `exclude(group = "com.TTT")` is required — TPipe 1.0.15's published JAR is self-contained. The exclude-rule pattern from the CodeArtifact era is obsolete.

**NOTE: The displayed settings.gradle.kts code in the modal uses `REPO_URL_PLACEHOLDER` and `TIER_NAME` as placeholders.** The script in `InstallModal.astro` substitutes them at modal-open time (Pipe → Community URL + `TPipeCommunity` name; Pipeline → Startup URL + `TPipeStartup` name). The settings text is also defined in the script (not in the HTML body) to avoid the Astro template-literal pitfall — see "CRITICAL: Astro Template-Literal Pitfall in the Install Modal" section below.

**Step 2 — add TPipe dependency. Step 3 — set JVM toolchain.** (These are the same as the older 4-step flow but renumbered, see the existing step blocks below.)

**Script — openInstallModal takes (command, jitpackUrl), updates the span with id="install-repo-url":**
```javascript
function openInstallModal(command, jitpackUrl) {
  if (commandText) commandText.textContent = command;
  if (jitpackLink) jitpackLink.href = jitpackUrl;
  const repoUrlSpan = document.getElementById('install-repo-url');
  if (repoUrlSpan) repoUrlSpan.textContent = jitpackUrl;
  overlay?.classList.add('open');
  // ...
}
```

**Trigger listener reads both data attributes:**
```javascript
document.querySelectorAll('.install-trigger').forEach(trigger => {
  trigger.addEventListener('click', (e) => {
    e.preventDefault();
    const command = trigger.getAttribute('data-install-command') || pipeCommand;
    const jitpackUrl = trigger.getAttribute('data-jitpack-url') || pipeJitpackUrl;
    openInstallModal(command, jitpackUrl);
  });
});
```

**The "View on GitHub" link at the bottom of the modal was joined by a "Browse on PublishPoint" link (PUBLISHED LIVE 2026-08-13):**
```astro
<a href={pipeJitpackUrl} target="_blank" rel="noopener noreferrer" class="jitpack-link" id="jitpack-link">
  <svg width="16" height="16" ...>
    <!-- generic stack-of-layers icon, fine to keep -->
  </svg>
  View on CodeArtifact
</a>
<a href="https://d8777bk79dr28.cloudfront.net/{community,startup}/" target="_blank" rel="noopener noreferrer">
  <svg width="16" height="16" ...>
    <!-- generic globe icon -->
  </svg>
  Browse on PublishPoint
</a>
```

**The legacy "View on CodeArtifact" label is now misleading** — the link points at the CloudFront PublishPoint URL, not at CodeArtifact. A future sweep should rename both the link label AND the `jitpack-link` class. The renaming was deferred because the legacy variable names (`PIPE_JITPACK_URL` / `PIPELINE_JITPACK_URL`) are still in use across TierCards.astro → InstallModal.astro → script — renaming as a paired refactor is the right move when convenient.

## README SEO Link Policy (GitHub Org Repos)

When adding "Made with TPipe" / company header links to READMEs across the `Ten-Trillion-Triangles` GitHub org, use **different destination URLs depending on whether the repo is TPipe-based**:

| Repo Type | Example | "TPipe" Link | Company Name Link |
|-----------|---------|--------------|-------------------|
| **TPipe-based** (uses TPipe as a dependency) | ChronoTrace, TPipeWriter | `https://tentrilliontriangles.com/blog` (TPipe product page) | `https://tentrilliontriangles.com` (root = company) |
| **Unreal Engine tools** (standalone products) | BlueprintToJson, TSync, ConsoleX3, UBuild, WorldContextScanner | `https://www.tentrilliontriangles.com` (company hub) | `https://www.tentrilliontriangles.com` (company hub) |

**Footer pattern (both types):**
```markdown
---

**Made with [TPipe](https://tentrilliontriangles.com/blog) by [Ten Trillion Triangles](https://tentrilliontriangles.com)**
```

For Unreal tools, replace `tentrilliontriangles.com/blog` with `www.tentrilliontriangles.com` in both links.

## Contact Form Backend (Important — Avoid CORS Trap)

The pricing page has a "Contact Sales" button on the Manifold/Substrate tiers. The form does NOT go through the Astro API route (`src/pages/api/contact.ts`) — that route is dead in production because the Astro build is `output: 'static'`. The form POSTs directly to API Gateway.

**Why this matters**: The form post target is hardcoded in `src/components/pricing/ContactForm.astro` (line ~341):
```javascript
const response = await fetch('https://mgf9b7ggkd.execute-api.us-east-1.amazonaws.com/Prod/contact', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data)
});
```

**If you change the API Gateway URL or stack**, update this URL AND the matching `WAITLIST_LAMBDA_URL` in `src/components/pricing/WaitlistModal.astro` (used on the `/company/` page for ArkVCS/Autogenesis waitlists). Centralize new URLs in `src/config/api.ts`.

**Required Lambda env var**: The Lambda's `ALLOWED_ORIGIN` env var MUST match the production site origin exactly (including `www.`). Mismatch = browser preflight fails even though curl works. See `aws-serverless` skill → "Curl-vs-Browser CORS Divergence".

**CORS is enforced at API Gateway, not just Lambda.** SAM `Globals.Api.Cors` configures OPTIONS method responses, but if the actual deployed method-response parameters are `false` (not `true`), Allow-Methods/Allow-Headers are stripped and the browser blocks the preflight. See `aws-serverless` skill → "OPTIONS MOCK Integration Setup" for the recipe to fix this without redeploying the stack.

## GitHub Releases / Maven Verification Workflow

When asked to verify artifact links on the pricing page, use this sequence:

1. **Check Maven artifacts** — verify POM and JAR are accessible:
   ```bash
   curl -sI "https://raw.githubusercontent.com/Ten-Trillion-Triangles/TPipe/main/maven/com/github/ten-trillion-triangles/TPipe/TPipe-Community-{VERSION}/TPipe-TPipe-Community-{VERSION}.jar"
   # Expect: HTTP/2 200, Content-Length > 1MB
   curl -sI "https://raw.githubusercontent.com/Ten-Trillion-Triangles/TPipe/main/maven/com/github/ten-trillion-triangles/TPipe/TPipe-Community-{VERSION}/TPipe-TPipe-Community-{VERSION}.pom"
   # Expect: HTTP/2 200
   ```
2. **Check GitHub Releases page** — verify the release tag exists:
   ```
   https://github.com/Ten-Trillion-Triangles/TPipe/releases/tag/{TAG}
   ```
3. **Test resolution in a fake Gradle project** — create `/tmp/maven-test/` with `settings.gradle.kts` + `build.gradle.kts`, run `gradle dependencies --configuration compileClasspath`

**Test project recipe:**
```bash
mkdir -p /tmp/maven-test/src/main/kotlin
```

**settings.gradle.kts:**
```kotlin
pluginManagement {
    repositories {
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        mavenCentral()
        maven { url = uri("https://raw.githubusercontent.com/Ten-Trillion-Triangles/TPipe/main/maven/com/github/ten-trillion-triangles") }
    }
}
rootProject.name = "maven-test"
```

**build.gradle.kts:**
```kotlin
plugins {
    kotlin("jvm") version "1.9.22"
}

repositories {
    mavenCentral()
    maven { url = uri("https://raw.githubusercontent.com/Ten-Trillion-Triangles/TPipe/main/maven/com/github/ten-trillion-triangles") }
}

dependencies {
    implementation("com.github.ten-trillion-triangles:TPipe:TPipe-Community-{VERSION}")
}
```

**Verify:**
```bash
cd /tmp/maven-test && gradle dependencies --configuration compileClasspath
# FAILED = artifact not resolving
# Resolved = artifact builds and is available
```

## Publish Workflow (PublishPoint — `s3 sync` to `publishpoint-public-maven`)

**As of 2026-08-08: TPipe artifacts publish to PublishPoint (S3 + CloudFront), not CodeArtifact.** The CodeArtifact flow that ran from 2026-06-11 to 2026-07-31 is deprecated. The earlier raw-GitHub-Maven flow (pre-2026-06-11) is also deprecated. The current flow is the `dual-tier-publish.sh` script in `~/Desktop/Workspaces/publishpoint/` followed by an `aws s3 sync` to the `publishpoint-public-maven` bucket and a CloudFront invalidation.

The brief verification sequence (post-publish):

```bash
# 1. POM and JAR are reachable on both tiers
curl -sI "https://d8777bk79dr28.cloudfront.net/startup/com/github/ten-trillion-triangles/TPipe/1.0.15/TPipe-1.0.15.pom"
# Expect: HTTP/2 200, Content-Length: 4541 (POM), ~6.4MB (JAR)
curl -sI "https://d8777bk79dr28.cloudfront.net/community/com/github/ten-trillion-triangles/TPipe/1.0.15/TPipe-1.0.15.pom"

# 2. SHA256 differs across editions (license isolation check)
aws s3 cp s3://publishpoint-public-maven/startup/com/github/ten-trillion-triangles/TPipe/1.0.15/TPipe-1.0.15.jar /tmp/startup.jar
aws s3 cp s3://publishpoint-public-maven/community/com/github/ten-trillion-triangles/TPipe/1.0.15/TPipe-1.0.15.jar /tmp/community.jar
sha256sum /tmp/startup.jar /tmp/community.jar
# Expect: distinct hashes (license.jar differs; main JAR converges on source-identical builds)
```

**Version tag convention** (still the same as before — tags drive `dual-tier-publish.sh`'s `-PpublishVersion=`):
- Tag `TPipe-Community-X.Y.Z` on `main` triggers publish of the Community tier
- Tag `TPipe-Startup-X.Y.Z` on `startup-license` triggers publish of the Startup tier

**Auth:** No GitHub Action secret required for the publish itself — PublishPoint's S3 bucket is write-gated to a deployer IAM role, not a CodeArtifact-style 12-hour token. The `verify-ide-grade.sh` recipe in `~/Desktop/Workspaces/publishpoint/` exercises the full flow end-to-end.

**JitPack remains permanently incompatible** (unchanged from before): TPipe uses Kotlin DSL Gradle files. JitPack's locked Gradle 4.8.1 can't parse `.gradle.kts`. No workaround. PublishPoint replaces the CodeArtifact-era JitPack-link URL pattern.

## CRITICAL: Astro Template-Literal Pitfall in Code Blocks

The install modal's code blocks (step 1 settings.gradle.kts, step 3 JVM toolchain) must NEVER contain a literal `${...}` template expression in the `.astro` HTML body — Astro's parser evaluates it as JavaScript at compile time, not as display text. The `\$` escape does **not** work in `.astro` file body content (it only works inside JavaScript template literals).

**The pattern that breaks:**
- Any literal `{` followed by content in a `.astro` file body
- The `\$` escape does NOT prevent the parser from seeing `${...}` as a JS template expression
- This includes Kotlin's `{}` blocks, JSON's `{}` objects, Gradle's `{}` blocks, ANY language with curly braces

**What happened (deployment #27, 2026-06-11):** The first install modal had:
```astro
credentials &#123;
    username = "aws"
    password = "\${System.getenv("CODEARTIFACT_AUTH_TOKEN")}"
&#125;
```
Intended as: show the consumer the literal Java/Kotlin syntax for the credentials block. Actual result: Astro evaluated `${System.getenv("CODEARTIFACT_AUTH_TOKEN")}` as JS at compile time, generated a `pricing@_@astro-BfarzM74.js` containing `System.getenv(...)` literal, and the pricing page prerender threw `[WARNING]: System is not defined` at `dist/server/.prerender/_astro/pricing@_@astro-BfarzM74.js:23:20131`. Build failed, deploy #27 marked FAILED. 1m 53s of CI wasted on a documentation edit.

**What happened (deployment #29, 2026-06-11, SAME bug class):** The 3-step install flow added a `settings.gradle.kts` template to step 1. The displayed code used Kotlin's `val` keyword and a `<String>` type parameter, all wrapped in `{ }`. The Astro template parser saw the `{` after `dependencyResolutionManagement` and the `{` after `<` as JS expression openers, and started evaluating the content as JS. The first non-`}` (Kotlin's `${'$'}{e.message}`) closed the expression too early, leaving trailing Kotlin code that the parser tried to compile as JS. The next `val` keyword threw `Expected "}" but found "val"` at SVG path coordinates. Build failed, deploy #29 marked FAILED. The error position (SVG path data) was the closest valid line number, but the root cause was the `settings.gradle.kts` template earlier in the file.

**Three valid fixes (pick one):**

1. **Plain placeholder** (used in the current install modal — preferred when the literal text isn't required to be exact):
   ```astro
   credentials &#123;
       username = "aws"
       password = "<your CODEARTIFACT_AUTH_TOKEN from step 1>"
   &#125;
   ```
   The fetch-the-token step is step 1 of the install flow, so a placeholder pointing back at step 1 reads naturally.

2. **HTML entity for the dollar sign AND any `{` `}` in the displayed text:**
   ```astro
   password = "&#36;&#123;System.getenv("CODEARTIFACT_AUTH_TOKEN")&#125;"
   ```
   Produces the literal `${System.getenv(...)}` in the rendered page without triggering Astro's parser. **But this still doesn't help with `{ }` that are NOT inside `${...}`** — those are still parsed as Astro expressions. So this fix only works for `${...}`-like patterns, not for the deployment #29 case where the issue was just `{` and `}` in Kotlin code.

3. **Move the entire code template into the `<script>` block** (the fix that actually works for the deployment #29 case, and is what's used in the current install modal):
   ```html
   <pre><code id="install-settings-text"></code></pre>  <!-- empty in HTML -->
   <script define:vars={{ pipeJitpackUrl, pipelineJitpackUrl }}>
     const SETTINGS_TEMPLATE = `dependencyResolutionManagement {
       val codeArtifactAuthToken: org.gradle.api.provider.Provider<String> =
         providers.environmentVariable("CODEARTIFACT_AUTH_TOKEN").orElse(...)  // etc
     }`;
     function renderSettingsText(jitpackUrl) {
       const tierName = jitpackUrl.includes('startup') ? 'TPipeStartup' : 'TPipeCommunity';
       return SETTINGS_TEMPLATE
         .replace('REPO_URL_PLACEHOLDER', jitpackUrl)
         .replace('TIER_NAME', tierName);
     }
     document.getElementById('install-settings-text').textContent =
       renderSettingsText(pipeJitpackUrl);
   </script>
   ```
   The script body is JavaScript, not Astro template content — so `{` and `}` are not parsed as expressions. The substitution happens client-side. The textContent is set on page load and again on modal open.

**Symptom in the build log:**
```
[WARNING]: System is not defined
Location: dist/server/.prerender/_astro/pricing@_@astro-BfarzM74.js:23:20131
[ERROR]: !!! Build failed
[ERROR]: !!! Error: Command failed with exit code 1
```
Or any `X is not defined` warning, or `Expected "}" but found "<keyword>"` (where keyword is a non-JS keyword like `val` or `class`). The error position is often misleading (the parser points at the first line where the syntax is broken, but the actual `{` that started the bad expression might be much earlier in the file). **When the error position is in a path that doesn't seem related to the bug, search backward for unmatched `{`.**

**Debugging recipe for Amplify build failures:**
1. Open Amplify console → app → job N → click BUILD step → download `log.txt` via the presigned URL
2. Get the URL programmatically: `aws amplify get-job --app-id <id> --branch-name <branch> --job-id <n> --query 'job.steps[0].logUrl' --output text`
3. Search the log for `WARNING`, `is not defined`, or `Expected "}"` — the identifier tells you which `.astro` file the bug is in (Astro's build output embeds the source path)
4. Grep that file for `${...}` patterns AND any unmatched `{` in raw text (NOT inside `{...}` Astro expressions, NOT inside backtick JS template strings)
5. Apply one of the three fixes above

**Generalizes to any `.astro` file.** The pitfall isn't specific to the install modal — any `.astro` file that includes code blocks (Kotlin, Java, Gradle, Rust, Go, JSON, ANY language with curly braces) risks this. Whenever you write a `<pre><code>` block in a `.astro` file, scan for `{` characters and either escape with `&#123;` AND avoid Astro expression syntax entirely, or put the template in the `<script>` block and set textContent.

**Safer alternative for any code-display need:** the most robust pattern is to put the entire code string in a JS template literal in the `<script>` block, then assign to `textContent` from the script. The script body is plain JavaScript, not Astro template content, so the parser never sees the curly braces as expressions. This works for any language, any complexity, any `{ }` density.

## Common Errors (PublishPoint)

- **Identical commands for different tiers** — Pipeline (Startup License) and Pipe (AGPL) must NOT share the same JAR bytes. The Maven coordinate is the same but the binaries MUST differ. **Verify SHA256 differs between editions after every publish.** (Source-convergence on 1.0.15 means the class files are similar — license isolation lives in `-license.jar` content and POM `<name>`.)
- **Wrong repo URL in `repositories { }` block** — pointing the consumer at the wrong edition's PublishPoint URL prefix (`/community/` vs `/startup/`) gives them the wrong license binary. The URL prefix is what carries the license attribution, not the coordinate.
- **`mavenCentral()` missing alongside PublishPoint** — PublishPoint bucket only carries `com.github.ten-trillion-triangles:TPipe`. Without `mavenCentral()` in the same `repositories { }` block, transitive deps like `org.jetbrains.kotlin:kotlin-stdlib` and `io.ktor:ktor-server-core` 403 against the PublishPoint bucket. Symptom: a clean Gradle resolve of TPipe itself, then `Could not resolve org.jetbrains.kotlin:kotlin-stdlib:2.3.21` on the next dep. Fix: add `mavenCentral()`.
- **Hardcoded PublishPoint link** — if the modal's "Browse on PublishPoint" link doesn't update per plan, users on Pipeline see the Community URL prefix instead of Startup. The `data-jitpack-url` attribute on `.install-trigger` is the carrier — same handler updates both repo block and link.
- **`*.module` shadow variant resolution** — Gradle Module Metadata may try to fetch a `TPipe-1.0.15.module` file that doesn't exist in PublishPoint. If `gradle dependencies` works but `gradle build` 404s on a `.module` file, add `metadataSources { mavenPom(); artifact(); ignoreGradleMetadataRedirection() }` on the PublishPoint `maven { }` block.
- **Wrong LICENSE file in repo** — the published `-license.jar` contains whatever `LICENSE` is at the repo root. If the README says AGPL-3.0 but `LICENSE` is GPL-3.0, the published binary ships with wrong text. Verify the LICENSE file content matches the claim in the README.
- **`from(components["java"])` doesn't include the license jar** — must explicitly add `artifact(tasks.named("licenseJar"))` to the `MavenPublication`. Otherwise the `-license.jar` is missing or empty.
- **Tag/branch mismatch** — tagging `TPipe-Startup-1.0.15` while on `main` (before `git checkout startup-license`) makes the Startup tag point at the main commit. Always `git checkout <branch>` BEFORE `git tag`. Verify with `git rev-parse <tag>^{}`.
- **Bumping internal version vs published version** — root `build.gradle.kts` has `version = "1.0.0"` for inter-module resolution. The published version (e.g., `1.0.15`) is set on the `MavenPublication` directly. Don't change the root version. Use `-PpublishVersion=X.Y.Z` for overrides.
- **CloudFront cache shows stale artifact after a republish** — PublishPoint CloudFront fronts an S3 bucket with `cache-control: public, max-age=300` (5 minutes). A consumer's Gradle that caches the dependency report inside that window may fetch a 1.0.15 artifact that has been overwritten by a hotfix republish. Fix: bump the patch version on hotfixes, or run `aws cloudfront create-invalidation --distribution-id <id> --paths "/startup/com/github/ten-trillion-triangles/TPipe/1.0.15/*"` after a republish.

## Deprecated Patterns (do not use)

The following patterns were used before the CodeArtifact migration and are now obsolete. If you find them in old code or documentation, replace them.

- **Raw GitHub Maven hosting** — committing JARs to a `maven/` directory and serving via `raw.githubusercontent.com`. No metadata, no integrity, license boundary collapse. Removed in the CodeArtifact migration.
- **`TPipe-Community-X.Y.Z` as the Maven version** — the version string was the tag name, with the edition baked in. New scheme is `1.0.8` (no edition prefix) with the repo URL carrying the edition. Both editions use `com.github.ten-trillion-triangles:TPipe:1.0.8` — only the repo URL differs.
- **Symlinks in `maven/` directory** — the old pattern committed both `TPipe-Community-X.Y.Z.jar` AND `TPipe-TPipe-Community-X.Y.Z.jar` as actual file copies because raw GitHub doesn't resolve symlinks. With CodeArtifact, Maven generates the correct filename via the artifactId + version, no copy needed.
- **Two filename variants of every JAR** — `TPipe-Community-1.0.6.jar` AND `TPipe-TPipe-Community-1.0.6.jar` existed because the build produced one and Maven expected the other. CodeArtifact handles this correctly via the artifactId in the POM. Single file per edition.
- **`mvn deploy` in the publish workflow** — the old workflow used `mvn deploy:deploy-file` with hardcoded paths. Replaced by `./gradlew publishMavenPublicationToCodeArtifactRepository`.
- **GitHub Releases as the canonical artifact source** — old `maven/` directory + GitHub Releases was a double-source-of-truth. CodeArtifact is the single source.

See `aws-codeartifact-publishing` skill for the current pattern in full.