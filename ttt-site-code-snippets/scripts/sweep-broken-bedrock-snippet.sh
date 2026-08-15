#!/bin/bash
# sweep-broken-bedrock-snippet.sh
#
# Find any ttt-site Astro page that still uses invented TPipe APIs in its
# BedrockPipe snippet. Run before declaring a code-snippet fix complete.
# Exit non-zero if any invented APIs are found.

set -u

SITE_ROOT="${SITE_ROOT:-/home/cage/Desktop/Workspaces/ttt-site}"

# Patterns that indicate the snippet hasn't been verified against TPipe source.
# Add new patterns as new invented APIs are discovered.
# All confirmed via /home/cage/Desktop/Workspaces/TPipe/TPipe/ source as of June 25, 2026.
PATTERNS=(
    # BedrockPipe / Pipe-level
    "attachContextBank"             # invented; real API is setPageKey(key: String)
    "setReasoningPipe(ChainOfDraft" # passes an enum to a function that takes a Pipe
    "ReasoningPipe\\.ChainOfDraft"   # wrong package; ChainOfDraft lives in Defaults.reasoning.ReasoningMethod
    "import com\\.TTT\\.Pipe\\.ReasoningPipe"  # wrong package
    "JsonOutput("                   # invented wrapper around setJsonOutput(String); no JsonOutput class
    # ContextBank
    "ContextBank\\.connect("        # invented; ContextBank is an object singleton with no connect(pageKey, lorebook)
    # Manifold / multi-agent
    "Manifold(manager = "           # invented constructor; real builder is Manifold().setManagerPipeline(...) + addWorkerPipeline(...)
    "Manifold(manager="             # same, without spaces
    "\\.cycle(query"                # invented; real API is .pause() / .resume() / .execute(MultimodalContent)
    "manifold\\.cycle("             # same on the instance
    "state\\.checkpoint"            # invented state shape; pause/resume don't expose a checkpoint field
    # DistributionGrid / P2P
    "registerP2P("                  # invented; real API is grid.addPeer(...) + grid.registerWithRegistry()
    "global = true"                 # invented parameter on attachContextBank; real global toggle is pullGlobalContext()
    "contentOf("                    # invented helper for MultimodalContent; constructor takes String directly
)

EXIT_CODE=0

echo "Scanning $SITE_ROOT/src/pages for invented TPipe APIs..."
echo ""

for pattern in "${PATTERNS[@]}"; do
    echo "=== Pattern: $pattern ==="
    matches=$(grep -rln "$pattern" "$SITE_ROOT/src/pages" 2>/dev/null || true)
    if [ -z "$matches" ]; then
        echo "  (clean)"
    else
        for file in $matches; do
            echo "  HIT: $file"
            grep -n "$pattern" "$file" | sed 's/^/    /'
            EXIT_CODE=1
        done
    fi
    echo ""
done

if [ $EXIT_CODE -eq 0 ]; then
    echo "All snippets clean."
else
    echo "Invented APIs detected. Run the accuracy workflow from ttt-site-code-snippets skill."
fi

exit $EXIT_CODE