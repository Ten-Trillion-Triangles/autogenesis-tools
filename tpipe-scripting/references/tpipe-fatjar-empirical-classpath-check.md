---
name: tpipe-fatjar-empirical-classpath-check
description: 5-command empirical recipe for verifying whether any class is loadable from the TPipe fat-jar before claiming a classpath blocker. Use when deferring a workaround with a "package X isn't on the classpath" justification, when designing a session-message cost framing that the user has visibility into, or when about to write a commit or skill line that states a class/resource/package is unreachable.
---

# Empirical classpath verification for TPipe fat-jar claims

The 2026-06-29 tpipe-scripting session made a deferral commit (`a90fad0a`) whose message overstated a classpath constraint. The commit message said "`kotlin-compiler-embeddable` ... isn't on the standard kotlin-scripting user classpath" — that turned out to be wrong. The fat-jar built by Variant 7's `-no-stdlib -no-reflect` workaround pulls in `kotlin-scripting-compiler-impl-embeddable` as a build dep, which transitively bundles `kotlin-compiler-embeddable` and its `org.jetbrains.kotlin.cli.common.repl.*` package. The classes WERE on the fat-jar classpath; the commit message was inaccurate. The user called it out, and the skill was patched.

This file encodes the recipe that would have caught the inaccuracy in 5 commands.

## The 5-command recipe

When about to state in a commit message, PR, skill, or debug log that "X class is/isn't reachable from the fat-jar," run all five commands in order:

```bash
# 1. Confirm the class file is physically in the fat-jar.
unzip -l build/libs/TPipe-<v>-all.jar | grep "<class-or-package-substring>"
# Expected: shows entries like "kotlin/script/experimental/jvmhost/repl/JvmReplCompiler.class"

# 2. Confirm the matched file is a valid .class (not a truncated stub from an interrupted build).
unzip -p build/libs/TPipe-<v>-all.jar "<matched-path>" | head -c 8 | xxd | head -1
# Expected: "00000000: cafe babe 0000 00<version>" for a valid .class

# 3. Confirm the class is also reachable from a sources jar (a known-public API surface,
#    not just bundled transitively where it might be private or unstable).
find ~/.gradle/caches/modules-2/files-2.1/<group>/<artifact>/<version>/ -name "*-sources.jar"
# E.g. for JvmReplCompiler:
# find ~/.gradle/caches/modules-2/files-2.1/org.jetbrains.kotlin/kotlin-scripting-jvm-host/2.2.20/ \
#   -name "*-sources.jar"
# unzip -p <sources-jar> kotlin/script/experimental/jvmhost/repl/legacyReplCompilation.kt | head -50

# 4. Inspect the constructor signature against the version of Kotlin you're targeting.
unzip -p build/libs/TPipe-<v>-all.jar "<matched-class>.class" > /tmp/class-probe.class
javap -p /tmp/class-probe.class | head -20
# Expected: shows the constructor(s), e.g. "public JvmReplCompiler(ScriptCompilationConfiguration, ScriptingHostConfiguration)"

# 5. Repeat the lookup in the gradle cache jar that produced the matched file (proves the
#    path-to-source, not just existence in fat-jar).
JAR=$(unzip -l build/libs/TPipe-<v>-all.jar | grep "<matched-class>.class" | awk '{print $4}' | head -1)
unzip -l build/libs/TPipe-<v>-all.jar | grep "$(dirname $JAR)/" | head -3
# Expected: shows other classes in the same package, confirming this is from a real artifact, not orphan copies
```

If all 5 commands return expected output: the class IS on the runtime classpath, the API IS reachable, and any "can't reach it" deferral is wrong — at minimum, recompute the cost framing (engineering vs bytes vs lifecycle, not "package not on classpath").

If even one command returns unexpected output (no match, truncated file, missing sources jar, private constructor, orphan class): that IS a real blocker and a different kind of deferral message applies.

## Cost-framing grid

Once classpath reachability is verified, the deferral cost is one of three buckets — pick the right one in the commit message:

| Bucket | Indicator | Example deferral framing |
|---|---|---|
| **Bytes** | Class NOT on classpath, would require adding a new build dep that's not transitively present | "Requires adding `kotlin-compiler-embeddable` as an explicit `implementation` dep (not currently pulled); ~40MB" |
| **Engineering** | Class IS on classpath, but using it requires non-trivial wiring | "Class is on the classpath via `kotlin-scripting-compiler-impl-embeddable`; switching `ReplSession` requires `repl { makeSnippetIdentifier { ... } }` configuration + `IReplStageState` lifecycle code (~200-300 LOC). The blocker is engineering scope, not bytes." |
| **API instability** | Class IS on classpath, the API IS public, but the namespace is `*.impl.*` or marked unstable | "Class is in `org.jetbrains.kotlin.scripting.compiler.plugin.impl.*`, JetBrains' `impl` namespace — has changed signatures across Kotlin minor versions before. Wiring commits the feature to track every compiler bump; defer until the API stabilizes or until we're willing to maintain a version pin." |

Most script-host feature-deferral messages mix these buckets. Pick the dominant one and lead with it. If you find yourself reaching for "package X isn't on classpath" as the lead, run the 5-command recipe first.

## When NOT to use this recipe

- When the class IS explicitly declared in your build.gradle.kts as an `implementation`/`api` dep and a successful build proves reachability (`./gradlew compileKotlin` succeeds). The recipe is for classes that come from transitive or build-time pull-ins.
- When the question is "will this work in production" rather than "is this on classpath" — that's a runtime behavior check, not a classpath check. Use the diagnostic recipe in `tpipe-fatjar-jpms-pitfall.md` for that.
- When the class is in a `*.test.*` or `*Test.kt` source set and would never ship in a fat-jar.
