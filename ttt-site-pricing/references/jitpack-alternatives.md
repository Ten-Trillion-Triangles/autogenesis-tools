# JitPack Incompatibility (Durable Fact)

This is the only durable fact from the pre-CodeArtifact era that
warrants keeping in this skill's references. Everything else in the
older "jitpack-alternatives" document described the now-deprecated
raw-GitHub-Maven hosting path, which has been fully removed.

## Why JitPack can't work for TPipe (ever)

TPipe uses Kotlin DSL Gradle files (`.gradle.kts`). JitPack's build
environment is **locked to Gradle 4.8.1** (released 2018). Gradle 4.8
cannot parse `.gradle.kts` files — they did not exist yet. The build
fails with:

```
Could not create service of type ScriptPluginFactory
```

No `jitpack.yml` configuration can override this. JitPack's build
runner calls its own `/opt/gradle-4.8.1/gradle` binary directly.
The following all fail because they run AFTER JitPack has already
selected its Gradle version:

- `GRADENT_VERSION` env var in `jitpack.yml`
- `gradle.version:` in `jitpack.yml`
- `before_install: sdk install java 24-open && sdk use java 24-open` (SDKMAN)
- PATH modifications in `before_install`
- Any `before_install` hook that tries to point to a different Gradle

**TL;DR:** If a project has `.gradle.kts` files, JitPack cannot build it.
There is no workaround. This is a structural limitation, not a config bug.

## Current working solution: AWS CodeArtifact

See the main `ttt-site-pricing` SKILL.md for the CodeArtifact pattern,
and `aws-codeartifact-publishing` for the publish-side details:

- `tpipe-community-maven` (AGPL-3.0) and `tpipe-startup-maven`
  (TPipe Startup License 1.0) in the `tpipe` domain
- Both currently at version `1.0.8` (verify with
  `scripts/discover-codeartifact-live-state.py` from
  `aws-codeartifact-publishing` before relying on any version number)
- Maven coordinate is `com.github.ten-trillion-triangles:TPipe:1.0.8` for
  both editions; the repo URL is what carries the license attribution
- Consumer install uses `settings.gradle.kts` with an auto-fetch of
  the CodeArtifact auth token via `aws codeartifact get-authorization-token`

## Historical context (for archaeology only)

Before the 2026-06-11 CodeArtifact migration, TPipe used raw-GitHub-Maven
hosting: JARs committed to a `maven/` tree on the TPipe repo, served via
`raw.githubusercontent.com`. The `maven/` tree was deleted as part of the
CodeArtifact migration. Symlinks in the old `maven/` tree did not work
because GitHub raw does not resolve symlinks — that detail is preserved
in the `aws-codeartifact-publishing` skill's
`references/raw-github-maven-anti-pattern.md` for reference, but no
relevant code is still deployed using that pattern.

## What to do if a user mentions JitPack in a TPipe context

1. Confirm the structural incompatibility (Gradle 4.8.1 + .gradle.kts).
2. Point at the CodeArtifact pattern (see above).
3. If they want the install-side details, the install modal in
   `src/components/pricing/InstallModal.astro:344-385` is the canonical
   consumer-facing reference.
4. If they want the publish-side details, load `aws-codeartifact-publishing`.
5. Do NOT suggest workarounds for JitPack. There are none. Suggesting
   `jitpack.yml` configurations or `before_install` hooks wastes the
   user's time and signals that you don't understand the limitation.
