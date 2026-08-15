# JitPack Publishing Reference

## How JitPack Works

JitPack builds GitHub repositories on-demand when a version/tag is requested. It watches GitHub tags/releases and builds whatever `publishToMavenLocal` produces.

**Dependency format:**
```kotlin
repositories {
    maven { url = uri("https://jitpack.io") }
}
dependencies {
    implementation("com.github.{owner}:{repo}:{version}")
}
```

## Version Resolution

| Tag Format | Consumer Use | Notes |
|------------|-------------|-------|
| `v1.0.0` | `com.github.user:repo:v1.0.0` | Standard semver, recommended |
| `Community` (branch) | `com.github.user:repo:Community` | Rolling, not a stable release |
| `v1.0.0-community` | `com.github.user:repo:v1.0.0-community` | Dual-license branch tagging |

**Branches as versions** — JitPack treats non-tag refs as aliases to the latest commit on that branch. Not recommended for releases.

## What JitPack Publishes

The published artifact depends on the build configuration:

**Default (no maven-publish plugin):**
- JAR with compiled classes
- Auto-generated POM — no sources, no javadoc, no license

**With `withSourcesJar()` + `withJavadocJar()`:**
- `<artifact>-sources.jar`
- `<artifact>-javadoc.jar`
- Main JAR

**For TPipe specifically:**
- `TPipe-1.0.0.jar` (compiled JVM classes)
- `TPipe-1.0.0-sources.jar` (from `withSourcesJar()`)
- `TPipe-1.0.0-javadoc.jar` (from `withJavadocJar()` — empty unless project has KDoc coverage)
- `TPipe-1.0.0-license.jar` (custom, from `licenseJar` task)
- `TPipe-all.jar` (fat/shadow JAR with all dependencies)

## TPipe Build Configuration

```kotlin
// build.gradle.kts (root project)
java {
    withSourcesJar()
    withJavadocJar()
}

// Custom license JAR bundled into publications
val licenseJar by tasks.registering(Jar::class) {
    archiveClassifier.set("license")
    from(rootProject.file("LICENSE"))
}

artifacts {
    add("archives", licenseJar)
}

plugins {
    `maven-publish`  // Required — JitPack runs `gradlew publishToMavenLocal`
}
```

**Key:** JitPack runs `./gradlew build publishToMavenLocal` — no special publish task needed. The `maven-publish` plugin combined with the standard publication (group + artifact + version) is sufficient.

## Deployment Workflow

```bash
# Option A: Tag a release
git tag v1.0.0
git push origin v1.0.0

# Option B: Branch as rolling version
git push origin Community

# Verify at:
# https://jitpack.io/com/github/{owner}/{repo}/{version}/
```

## Public vs Private Repos

- **Public repos**: No deploy key needed. JitPack can read directly.
- **Private repos**: Add JitPack deploy key (read-only SSH key) to the repo settings.

## DynamoDB Backend Pattern (ttt-site)

For form data → Lambda → DynamoDB, the pattern is:

1. Astro page: modal-trigger button → opens form overlay
2. Form component: `<form id="...">`, POST via `fetch('/api/contact', {method:'POST', body: JSON.stringify(data)})`
3. Astro API route: `src/pages/api/contact.ts` — proxies to Lambda, falls back to local file storage
4. Lambda: plain JS in `src/lambda/contact-handler/index.js` — writes to DynamoDB + sends SES email
5. SAM template: `infrastructure/template.yaml` — defines Lambda + API Gateway + DynamoDB table

**For ArkVcs/Autogenesis title card forms**, a new Lambda function (or new route in existing contact-handler) would be needed, with a separate DynamoDB table or GSI for distinguishing the source product.