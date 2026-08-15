## Pitfall 9: Removing the post-stream "print banked chapter" line under the assumption that streaming "duplicates" the content

**The inverse of Pitfall 6.** Same removal pattern, different
mistake: removing a needed print under the wrong justification.

**Symptom**: After a writer pipeline run, the user sees the streamed
LLM output arrive in real-time, then the application prints only a
placeholder message like `[writer] Chapter segment banked into context.`
The user has to manually run a separate command (`/chapters show <N>`)
to see the actual chapter that was written.

**Cause**: A refactor (commonly a streaming-fix or writer-pipeline
rewrite) removes the existing `println(bankedResult)` call on the
grounds that "the streaming callback already wrote the prose, so
printing it again duplicates the output." This is wrong because the
streamed output and the banked output are NOT the same content:

1. **For `/continue` commands** the LLM emits JSON surgical changes,
   so the streamed output is unreadable JSON. The banked result (the
   final patched chapter after `applySurgicalReplacementsAndBank`
   runs) is the actual prose the user wrote.

2. **For `/write` commands** the streamed deltas happen to be prose,
   but the banked version is the canonical post-pipeline text with
   surgical changes applied. The two can differ in length and content.

3. **The user expects to see what was persisted to context.** The
   banked result is the canonical "what was written and added to the
   running story." The streamed deltas are intermediate, not the
   persisted artifact.

**Where this regression appears**: The OpenRouter and main branches
of TPipeWriter both print the banked chapter with a
`==== New Segment ====` banner after the pipeline run, matching the
pattern that writers (creative-writing TUI users) expect from
multi-session authoring tools. The MiniMax-M3 branch removed this
in commit `13c10c2` with the comment "we don't need to print the
full text again (that would duplicate the streamed output" — the
correct fix was to print the banked text, not to remove the print.

**Fix**: Read the banked result from `ContextBank` after the pipeline
runs and print it with a banner:

```kotlin
// In executeWriterPipeline, after runBlocking returns
if (result.text.isNotEmpty()) {
    try {
        val textBarrier = "==================================New Segment========================================="
        val bankedContext = ContextBank.getContextFromBank("new page")
        val bankedResult = bankedContext.contextElements.lastOrNull()
        if (!bankedResult.isNullOrBlank()) {
            println("\n\n\n$textBarrier\n\n$bankedResult")
        } else {
            println("\n\n[writer] Chapter segment banked into context.")
        }
    } catch (e: Exception) {
        println("\n\n[writer] Chapter segment banked into context.")
    }
} else {
    println("The model failed to return a result")
}
```

**Why `lastOrNull` not `[0]`**: The bank accumulates across multiple
runs — older entries are still in the bank. Print only the most
recent generation, not the full bank history (which would dump prior
chapters for every `/continue` call).

**Why a fallback to the placeholder**: If the bank is empty
(first generation that hasn't yet hit `recordWritingPipePage`) or
the bank read throws, fall back to the existing placeholder so the
user at least knows the run completed.

**Regression test** — covers 4 cases without needing a live API:

```kotlin
@Test
fun printsBankedChapterWithBannerWhenBanked() {
    val chapterText = "It was a dark and stormy night..."
    runBlocking {
        val bankedContext = ContextWindow()
        bankedContext.contextElements.add(chapterText)
        ContextBank.emplaceWithMutex("new page", bankedContext)
    }
    val output = captureStdout { printBankedChapterOrFallback("ok") }
    assertTrue(output.contains("New Segment"))
    assertTrue(output.contains(chapterText))
    assertTrue(!output.contains("Chapter segment banked into context"))
}

@Test fun fallsBackToPlaceholderWhenBankIsEmpty()
@Test fun reportsFailureWhenResultIsEmpty()
@Test fun printsLastElementWhenBankHasMultipleEntries()
```

**Diagnostic**: After running a writer pipeline, check whether the
TUI shows a `==== New Segment ====` banner with the chapter text.
If only `[writer] Chapter segment banked into context.` appears,
the post-stream print was removed or fell through to the placeholder
branch. Check the writer subshell's `if (result.text.isNotEmpty())`
block — the bank-read-and-print logic should be there.

**The general rule**: removing a `println` from a post-pipeline
block is safe ONLY if the streaming callback already wrote
*equivalent* content to stdout. If the post-pipeline print was
showing a *different* view (banked final result, summary, formatted
report), removing it silently drops user-visible behavior. Don't
remove prints under the assumption that "streaming already covers
it" without checking whether they actually wrote the same content.

**Cross-reference**: The user originally flagged this as "the streaming
isn't real-time" — see Pitfall 8. After fixing the streaming buffering,
the user noticed a separate symptom: the chapter wasn't shown at the
end. That's THIS pitfall, not Pitfall 8. Two distinct bugs, same
release. The fix order matters: fix streaming first (Pitfall 8), then
restore the banked-chapter print (this pitfall), in that order.
