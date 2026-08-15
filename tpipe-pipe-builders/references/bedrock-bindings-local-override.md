# Bedrock Model Bindings — Local-Override Ritual

When adding a new Bedrock model binding to the Autogenesis server, the
binding must be present in **two distinct properties files** before the
runtime can resolve it. Missing one produces a test-time
`IllegalStateException: bedrock.local.properties missing key '<key>'` —
catching this in production requires running the model with a real
runtime, not a unit test.

## The two locations

### 1. `~/.autogenesis/config/bedrock.properties` (per-environment override)

The runtime override that the autogenesis server reads at startup. This
file is OUTSIDE the repository — it's in the user's home directory and
varies per environment. The file is the canonical place for the
**actual Bedrock inference profile ARN** (the long
`arn:aws:bedrock:region:account:inference-profile/<id>` string).

Example existing entries:

```
bedrock.llamaMaverick=arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0
bedrock.llama70B=arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.meta.llama3-3-70b-instruct-v1:0
bedrock.llama405B=arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.meta.llama3-1-405b-instruct-v1:0
bedrock.PalmyraX5=arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.writer.palmyra-x5-v1:0
```

### 2. `server/bedrock.local.properties` (test fallback)

The repo-local fallback that the test runner uses when no `~/.autogenesis/config/`
override is present. Same keys, same ARN values. Without this file,
`./gradlew :server:test` fails with `IllegalStateException` for any
`ConfigSource.property("bedrock.local.properties", "<key>")` lookup.

## The binding code

`BedrockConfig.kt` reads each model via `ConfigSource.property(...)` and
binds it via `bedrockEnv.bindInferenceProfile(...)` in the init block:

```kotlin
val llamaScout17BModelName: String get() = ConfigSource.property(
    "bedrock.local.properties",      // <-- reads from BOTH files
    "bedrock.llamaScout17B"          // <-- the key name
)

init {
    try {
        bedrockEnv.bindInferenceProfile(
            llamaScout17B,             // <-- the model ID (constant or fallback)
            llamaScout17BModelName     // <-- the ARN (resolved from properties)
        )
    } catch (e: Exception) {
        Logger.error(LogCategory.SYSTEM, "Failed to initialize Bedrock inference config: ${e.message}")
    }
}
```

The two-argument pattern is important:
- 1st arg: identifier the pipe uses to look up the model (constant string)
- 2nd arg: the actual ARN (resolved from properties at runtime)

## Step-by-step recipe

When adding a new Bedrock model binding (e.g. Llama 4 Scout 17B):

1. **Get the ARN** from the AWS console or via `aws bedrock list-inference-profiles --region us-west-2`.
2. **Add the constant** to `BedrockConfig.kt` (model ID string, not the ARN):
   ```kotlin
   val llamaScout17B = "us.meta.llama4-scout-17b-instruct-v1:0"
   ```
3. **Add the accessor** for the ARN:
   ```kotlin
   val llamaScout17BModelName: String get() = ConfigSource.property(
       "bedrock.local.properties",
       "bedrock.llamaScout17B"
   )
   ```
4. **Add the binding** in the init block:
   ```kotlin
   bedrockEnv.bindInferenceProfile(llamaScout17B, llamaScout17BModelName)
   ```
5. **Add the property** to **both** files:
   - `~/.autogenesis/config/bedrock.properties`:
     ```
     bedrock.llamaScout17B=arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0
     ```
   - `server/bedrock.local.properties` (same line):
     ```
     bedrock.llamaScout17B=arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0
     ```
6. **Verify with a unit test** that asserts `modelNameAccessor.isNotBlank()` — this catches the missing-property-file case:
   ```kotlin
   @Test
   fun `llamaScout17BModelName accessor is non-blank`() {
       val resolved = BedrockConfig.llamaScout17BModelName
       assertNotNull(resolved)
       assertTrue(resolved.isNotBlank(), "must be non-blank ARN from ConfigSource")
   }
   ```
   The test fails with `IllegalStateException: bedrock.local.properties missing key 'bedrock.llamaScout17B'` if step 5 is missing.

## Account-bound vs foundation-model IDs

The two argument slots have different concerns:

- **Identifier** (1st arg): typically a cross-region inference ID like `us.meta.llama4-scout-17b-instruct-v1:0` — what the codebase uses to reference the model.
- **ARN** (2nd arg): the **account-bound** inference profile ARN — `arn:aws:bedrock:region:accountId:inference-profile/<id>`. Account-bound ARNs MUST live in the config files, NOT in source code. The AWS account ID `521369004927` is for the autogenesis account.

Foundation-model IDs (no AWS account in the ARN, e.g. `qwen.qwen3-235b-a22b-2507-v1:0`) can be hardcoded in source — but the autogenesis pattern keeps all of them in `ConfigSource` for symmetry.

## Pitfall — only updating one file

The most common error: patching `~/.autogenesis/config/bedrock.properties`
(the runtime override) but forgetting `server/bedrock.local.properties`
(the test fallback). The production server starts and works. The test
suite fails with `IllegalStateException`. Both must be updated in the
same change.

## Pitfall — committing the ARN to source

The BedrockConfig code should NEVER contain the literal ARN. The pattern
is:

```kotlin
// BAD — commits the ARN to git history
val llamaScout17B = "arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0"

// GOOD — ARN lives in the config files
val llamaScout17B = "us.meta.llama4-scout-17b-instruct-v1:0"
val llamaScout17BModelName: String get() = ConfigSource.property(
    "bedrock.local.properties",
    "bedrock.llamaScout17B"
)
```

## Verified working entries (2026-07-30)

| Model | Cross-region ID | Bedrock ARN |
|---|---|---|
| Llama 4 Scout 17B | `us.meta.llama4-scout-17b-instruct-v1:0` | `arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.meta.llama4-scout-17b-instruct-v1:0` |
| Llama 4 Maverick 17B | `us.meta.llama4-maverick-17b-instruct-v1:0` | `arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.meta.llama4-maverick-17b-instruct-v1:0` |
| Llama 3.3 70B | `us.meta.llama3-3-70b-instruct-v1:0` | `arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.meta.llama3-3-70b-instruct-v1:0` |
| Llama 3.1 405B | `us.meta.llama3-1-405b-instruct-v1:0` | `arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.meta.llama3-1-405b-instruct-v1:0` |
| Palmyra X5 | `us.writer.palmyra-x5-v1:0` | `arn:aws:bedrock:us-west-2:521369004927:inference-profile/us.writer.palmyra-x5-v1:0` |
| Claude Sonnet 4 | `us.anthropic.claude-sonnet-4-20250514-v1:0` | `arn:aws:bedrock:us-east-2:521369004927:inference-profile/us.anthropic.claude-sonnet-4-20250514-v1:0` |

## See Also

- `server/src/main/kotlin/globals/BedrockConfig.kt:489-509` — init block with the `bindInferenceProfile` chain
- `server/src/main/kotlin/globals/BedrockConfig.kt:436-456` — Llama constants and accessors
- `~/.autogenesis/config/bedrock.properties` — runtime override
- `server/bedrock.local.properties` — test fallback
- `references/mantle-streaming.md` — companion: streaming parity concerns
- `references/agent-migration-bedrock-to-mantle.md` — full migration recipe
