# Test Fixture Cryptographic Correctness

## The Pattern

When a test uses a synthetic fixture (a base64 string, a JSON literal, a synthetic key, a hand-crafted JWT) that has **hidden structural or cryptographic invariants**, the test can pass via the **wrong code path entirely**. The library or framework under test throws a fixture-validation error, the production code's catch block swallows it, and the test's `assertX` captures the green check without the test's claimed behavior ever actually running.

This is the most insidious class of "test passed for the wrong reason" because the test often looks plausible — the assertion makes sense, the test name describes a real behavior, and the code path being exercised is silently something else entirely (most commonly: a generic catch-all in the production code).

## When it bites

Anywhere a test fixture embeds data the framework/library validates before doing the work the test claims to test:

| Domain | Hidden invariant |
|---|---|
| Web Push / VAPID | `p256dh` must decode to a valid uncompressed P-256 curve point (65 bytes starting with `0x04`) |
| JWT / OAuth | signature must validate against the issuer; `aud` must match; `exp` must be in range |
| Cryptographic hashes (HMAC, signed cookies, CSRF tokens) | must match expected bit length and pass library validation |
| PEM-encoded keys (RSA, EC) | must parse via `KeyFactory`, must be the expected algorithm |
| WebCrypto / SubtleCrypto | key derivation parameters must be accepted by the algorithm |
| ASN.1 / DER-encoded structures | must parse via the library's decoder; TLVs must be in expected order |
| UUID | not all libraries accept all versions (`v1` vs `v4`); some have variant constraints |
| Email / URL parsing | strict RFC compliance differs from `String.contains("@")` |
| Date / Time | DST / timezone / leap-second edge cases |

In each case, **a synthetic fixture that's "looks right but isn't structurally valid" silently fails at the library boundary**, and the test's `assertX` captures the resulting error swallowing instead of the test's claimed code path.

## Diagnostic tells

1. **The library/framework throws a different exception than the test name implies.** "Incorrect length for uncompressed encoding" instead of "got HTTP 410."
2. **The production code's `catch (Throwable)` (or any "swallow on exception" pattern) makes the test green for unrelated reasons.** Generic catch blocks are silent tests' hideout.
3. **Replacing the fixture with obviously-broken garbage makes the test fail with a different error message than `assertX` captures.** That difference is the code path the test actually exercises.
4. **The test logs a warning, info, or warn-level "library failed" message that the test author didn't write an assertion against.** A passing test with a warning log is suspicious. Check what triggered the warning.
5. **The fixture is too symmetric or too regular.** A 32-byte secret like `"01234567890123456789012345678901"` or a 65-char base64 like `"BIPUL12_..."` is suspicious precisely because it's too easy to type — the author probably didn't verify it against the format spec.
6. **Removing or rearranging the fixture's structure doesn't change which code path the test exercises.** If the test is genuinely testing the HTTP 410 path, changing the p256dh should change the request the library sends. If it doesn't, the test isn't exercising what it claims.

## Fix recipe

**Derive the fixture from the same generator the library uses internally.** For a keypair:

```kotlin
// BAD — synthetic 64-char string, not a valid uncompressed P-256 point
val p256dhB64 = "BIPUL12_K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5K4Z1K9y5"

// GOOD — derive from a real keypair so the curve point is guaranteed valid
val keyPair = KeyPairGenerator.getInstance("EC").apply { initialize(256) }.generateKeyPair()
val ecPublicKey = keyPair.public as java.security.interfaces.ECPublicKey
val w = ecPublicKey.w
val rawPoint = ByteArray(65).also {
    it[0] = 0x04
    System.arraycopy(affineX32, 0, it, 1, 32)
    System.arraycopy(affineY32, 0, it, 33, 32)
}
val p256dhB64 = java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(rawPoint)
```

Other generator mappings:

| Need | Generator the library uses | Synthetic fixture (BAD) |
|---|---|---|
| Keypair (RSA, EC) | `KeyPairGenerator.getInstance("EC")` / `("RSA")` | Hand-crafted Base64 strings |
| JWT | `Jwts.builder().setClaims(...).signWith(...)` | String-concat with `"."` separators |
| HMAC | `Mac.getInstance("HmacSHA256")` with the right key bytes | Hardcoded hex strings |
| UUID | `UUID.randomUUID()` / `UUID.nameUUIDFromBytes(...)` | `"test-uuid-string"` |
| Timestamp (signed cookies) | `Instant.now()` | Hand-written epoch numbers |
| VAPID token | Library's `PushService.sign(...)` method | Hand-edited JWTs |
| CSR/PEM | `KeyPairGenerator` + Bouncy Castle PEM writer | Hardcoded `-----BEGIN ... PRIVATE KEY-----` strings |

The rule: **if the library parses the fixture, generate the fixture with the same primitives the library parses with.** If you can't use the library itself (because it's the thing under test), use the underlying cryptographic primitive the library wraps.

## Companion debugging recipe

When a test passes but the behavior being tested is suspicious:

1. **Read the production code's exception path.** Does it have a `catch (Throwable)` or broad exception handler? If yes, expect the test can pass for the wrong reason.
2. **Run the test with logging on.** A passing test that produces any warning log is suspect — find what triggered the warning before trusting the green check.
3. **Mutate the fixture in ways that should fail the test's primary assertion, not the test's known assertion.** If mutating p256dh makes the test still pass on the "deletes subscription" assertion but fail with a different error, the test was always exercising the error path.
4. **Trace what code path the test actually exercises.** Add a breakpoint or `println` at the production-code point the test is named after. Verify the test reaches it.

## Adjacent trap: catch blocks hiding fixture failures

Many production code paths have layered exception handling:

```kotlin
// Example: a layered catch structure common in HTTP-client code
return withContext(Dispatchers.IO) {
    try {
        val response = client.send(request)
        when (response.statusLine.statusCode) {
            in 200..299 -> true       // success
            404, 410 -> {             // the path this test cares about
                store.removeByEndpoint(userId, subscription.endpoint)
                false
            }
            else -> false             // other transient failure
        }
    } catch (e: Throwable) {
        logger.warn("push failed: ${e.message}")
        false                        // <-- fixture-validation errors land here
    }
}
```

If the test asserts `assertFalse(sent)` it cannot distinguish between:

- (a) The library threw because of fixture-invalid p256dh (catch block swallows it, returns false) — **WRONG CODE PATH**
- (b) The server returned 410 (handler branch executes `removeByEndpoint`, returns false) — **RIGHT CODE PATH**

The assertion alone is insufficient. Add `coVerify { vfs.removeByEndpoint(userId, any()) }` (or equivalent) to pin the second code path. Tests that rely on catch-block fall-through for their green check are the single most common fake-green source across this codebase.

## When a non-cryptographic test hits the same shape

The pattern generalizes to any test where the fixture has hidden invariants the library validates:

- **JSON parsing tests** with synthetic JSON strings that miss a required field — the parser throws, the test's `assertX` capture matches the catch-block return.
- **HTTP request tests** with URL fixtures that miss required headers or path components — the framework rejects the request, the test passes for the wrong reason.
- **OAuth flow tests** with synthetic token strings that fail signature validation — the framework swallows, the test passes.
- **Rate-limit tests** with hand-crafted timestamps that fall outside the rate window — the limiter silently allows nothing, the test's "rejected" assertion matches the empty result.

In every case the fix is the same: **derive the fixture from the library's own generator when the library validates the fixture's format.**

## Reference case

The Autogenesis `removeDeletesSubscriptionOn410Gone` test (pre-v1.1.0, fixed in the 2026-06-29 multi-device patch). Symptom recap:

- Test stored a synthetic `BIPUL12_K4Z1K9y5...` p256dh string in the VFS.
- Web-push library validated the curve point pre-flight, threw `Incorrect length for uncompressed encoding`.
- Production code's `catch (Throwable)` swallowed the exception, returned `false`.
- Test asserted `assertFalse(sent)` and `coVerify { vfs.deleteUserRecord }` — both passed.
- Result: the 410-prune code path was never exercised. The test was green for months.

Fix: replaced synthetic base64 with keypair-derived `rawPoint`. With the new fixture, the encryption check passes, the request hits the local HttpServer, the server returns 410, the 404/410-handler branch executes `removeByEndpoint`. Test now genuinely exercises the surgical prune path.

## Quick audit checklist

For any test with a synthetic crypto / parse / validate fixture:

- [ ] Is the fixture generated by the same primitive the library validates against?
- [ ] If not, can the test be rewired to use the primitive (a real KeyPairGenerator, a real JWT builder, a real checksum, etc.)?
- [ ] Does the production code have a `catch (Throwable)` or broad exception handler? If yes, the test needs an explicit `coVerify` / equivalent on side effects, not just an assertion on the return value.
- [ ] Does the test produce any log warning or info-level message? If yes, the warning is suspicious. Find what triggered it.
- [ ] Does mutating the fixture in a way that should fail the test's primary assertion still make the test pass on the secondary assertion? If yes, the test is exercising the secondary assertion's code path, not the primary.
- [ ] If the fixture is symmetric / very regular / well-known-looking, it's probably synthetic and probably hasn't been validated against the format spec.

Pinning every synthetic-fixture test against these six checks catches the wrong-code-path failure mode before it ships.
