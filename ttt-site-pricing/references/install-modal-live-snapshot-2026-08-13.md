# Live Install Modal Snapshot — 2026-08-13

Captured by browsing https://www.tentrilliontriangles.com/pricing/ on 2026-08-13, opening the "Get Started" trigger on each tier, and reading the rendered install-modal HTML/text. Use this as the source-of-truth reference for what users actually see — not for what the .astro source code says.

## Pipeline / Startup tier (Get Started → modal opens)

```
Heading:    Install TPipe
Body:       Add TPipe to your Kotlin Gradle DSL project.
Requirements: JDK 24+ · Kotlin Gradle DSL · Gradle 8.14.3+

Step 1 — Add to settings.gradle.kts (no auth required):
    dependencyResolutionManagement {
        repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
        repositories {
            maven {
                name = "TPipeStartup"
                url = uri("https://d8777bk79dr28.cloudfront.net/startup/")
            }
            mavenCentral()
        }
    }

Step 2 — Add TPipe dependency:
    implementation("com.github.ten-trillion-triangles:TPipe:1.0.15")

Step 3 — Set JVM toolchain:
    java {
        toolchain {
            languageVersion.set(JavaLanguageVersion.of(24))
        }
    }

    kotlin {
        jvmToolchain(24)
    }

Footer links:
    View on GitHub           → Ten-Trillion-Triangles/TPipe
    Browse on PublishPoint   → https://d8777bk79dr28.cloudfront.net/startup/
```

## Pipe / Community tier (Get Started → modal opens)

Same modal shape, two substitutions:

```
Step 1 — name and URL prefix:
    name = "TPipeCommunity"
    url = uri("https://d8777bk79dr28.cloudfront.net/community/")

Step 2 — same coordinate and version (1.0.15)
Step 3 — same toolchain

Footer:
    Browse on PublishPoint → https://d8777bk79dr28.cloudfront.net/community/
```

## Observable facts vs the SKILL.md body

- The modal shows **`repositoriesMode.set(FAIL_ON_PROJECT_REPOS)`** in step 1. Apex's `settings.gradle.kts` does NOT set this — Apex uses the default `PREFER_PROJECT` mode. That difference is fine for Apex because Apex adds the PublishPoint repo at the project level (`apex-runtime/build.gradle.kts` doesn't have a per-module `repositories { }` block today, so the dependency is resolved from `dependencyResolutionManagement`).
- The modal does NOT include any `aws codeartifact get-authorization-token` provider. The CodeArtifact-era 4-step flow is fully gone.
- The modal includes `mavenCentral()` alongside the PublishPoint `maven { }` — this is load-bearing. The PublishPoint bucket only carries `com.github.ten-trillion-triangles:TPipe`; transitive deps land on Maven Central.
- The "Browse on PublishPoint" link is the second footer link (paired with "View on GitHub"). It's NOT a replacement of the GitHub link — both are present.
- The label "View on CodeArtifact" still appears in the legacy `jitpack-link` anchor on the live page (as of 2026-08-13 capture). The SKILL.md has been updated to flag this as a future-cleanup item; the live site still has the stale label.

## Verification commands (re-runnable)

```bash
# POM resolves on both tiers
curl -sI "https://d8777bk79dr28.cloudfront.net/startup/com/github/ten-trillion-triangles/TPipe/1.0.15/TPipe-1.0.15.pom" | head -3
curl -sI "https://d8777bk79dr28.cloudfront.net/community/com/github/ten-trillion-triangles/TPipe/1.0.15/TPipe-1.0.15.pom" | head -3

# JAR resolves
curl -sI "https://d8777bk79dr28.cloudfront.net/startup/com/github/ten-trillion-triangles/TPipe/1.0.15/TPipe-1.0.15.jar" | head -3
# Expect: content-length ~6.4MB, content-type application/java-archive
```
