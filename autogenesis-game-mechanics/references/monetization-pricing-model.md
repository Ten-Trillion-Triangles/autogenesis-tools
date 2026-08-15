# Monetization & Pricing Model — Autogenesis

Complete reference for the cost basis, subscription tier design, free tier + credit economy, and
matchmaker subsidy ladder. Load when building any pricing/monetization dashboard, projection, or
rate-limiter config for the game.

Source artifacts referenced throughout:
- `server/.../accounting/ModelPricing.kt` — billing map (partial, may need updates)
- `server/.../globals/BedrockConfig.kt` — model registry, budget settings, factory builders (lines 431-1459)
- `sharedModel/.../structs/account/CostClass.kt` — matchmaker cost class enum (BYO_KEY=4, PRO=2, CASUAL=1, CREDIT=0, FREE=0)
- `sharedModel/.../structs/account/AccountSettingsMatchmaking.kt` — cost class resolution + subsidy capacity
- `server/.../org/ttt/autogenesis/server/TurnHarness.kt:2786` — strict sequential turn advancement
- `server/.../gameplayOrchestrator.kt:529-533, 1084-1104` — action point economy
- `server/.../judge.kt:1303-1307` — karma accumulation

## Cost basis (from real traces, R3 + R4, 4 completed turns)

Trace-derived token counts (cleaned, retries excluded):
| Archetype | Trace | Input (K) | Output (K) | Total (K) | LLM calls |
|---|---|---:|---:|---:|---:|
| NPC turn | `Round_3_Turn_1_Syrup_Whisperer/` | 149 | 20 | 169 | 58 |
| Human player | `Round_3_Turn_0_Lord_Maple_Tree/` | 972 | 50 | 1,022 | 29 |
| Human player | `Round_4_Turn_0_Lord_Maple_Tree/` | 1,289 | 48 | 1,336 | 30 |
| AI player | `Round_3_Turn_2_Robert/` | 1,138 | 47 | 1,185 | 31 |

**Token composition per R25 game** (4 human + 2 AI + 3 NPC per round):
- Input per round: 972 + 1,138 + (149 × 3) = 2,557K
- Output per round: 50 + 47 + (20 × 3) = 157K
- Total per round: 2,714K tokens
- R25 total game: ~67.85M tokens (4p ÷ 4 = 16.96M per user; 1v3 = 67.85M single payer; 1v1 = 33.92M)

## Active production model portfolio (4 models)

Confirmed from `BedrockConfig.kt` and trace data. **Qwen3 235B A22B is dormant code, not used in any trace.**
| Model | Concrete ID | Transport | Context | Role |
|---|---|---|---|---|
| Qwen3 Coder 30B A3B | `qwen.qwen3-coder-30b-a3b-v1:0` | Bedrock Converse | 235K | Gameplay workhorse |
| Gemma 4 E2B | `bedrock-mantle.gemma4ModelId` | Bedrock Mantle | 128K | Classifiers, refinement, OpenWidget |
| Gemma 4 31B | `bedrock-mantle.gemma31ModelId` | Bedrock Mantle | 235K | AI planning, high-context writing, maintenance |
| Llama 4 Scout 17B | `us.meta.llama4-scout-17b-instruct-v1:0` | Bedrock Converse | 3.5M | Answer Agent, UserActionClassificationAgent |

## Pricing (AWS Bedrock, 2026-07-31 snapshot)

The operator caught a "25% markup" fabrication early in the pricing session. The CORRECT rates are:

| Model | Tier | Input / 1M | Output / 1M |
|---|---|---:|---:|
| Qwen3 Coder 30B | Standard | **$0.15** | **$0.60** |
| Qwen3 Coder 30B | Flex | **$0.07725** | **$0.309** |
| Gemma 4 E2B | Standard | $0.04 | $0.16 |
| Gemma 4 31B | Standard | $0.14 | $0.56 |

**Flex discount is not exactly 25%** — it's roughly 48.5% off Standard. Don't derive one from the other; cross-check.

## Per-game cost (mid estimate, 4-player at R25)

- Human player turn (mid): $0.127
- AI player turn (mid): $0.150
- NPC turn (mid): $0.025
- 4P total game (mid): $16.01; per-user: $4.00
- 1v1: $8.00; 1v3: $16.01

## Per-turn wall-clock (empirical, with 90s human input planning estimate)

| Archetype | Wall (s) | LLM calls |
|---|---:|---:|
| Human player (avg R3+R4) | 262.6 + 90 input = **352.6** | ~30 |
| NPC turn | **365.6** (upper bound) | 58 |
| AI player | **814.4** (includes one cancelled retry) | 31 |

Per-game wall-clock at R25: 4 humans = 14.2 hr, 1H+3AI = 23.9 hr, 1H+3NPC = 14.5 hr.

## Subscription tier design (operator's intent — feature-gate, not affordability-gate)

| Tier | Price | 4p | 1v1 | 1v3 |
|---|---:|:---:|:---:|:---:|
| $25 Casual | $25 | ✓ | ✗ | ✗ |
| $50 Regular | $50 | ✓ | ✓ | ✗ |
| $75 Hardcore | $75 | ✓ | ✓ | ✓ |
| $100 Grinder/Creator | $100 | ✓ | ✓ | ✓ |

The unlock gate is **tier-based**, NOT affordability-based. Margin/overage sliders change the affordability annotation, not which modes a tier can access. A $25 user at 50% margin can't afford 1v1 either, but the design intent is that $25 = multiplayer-only regardless.

## Cohort behavior (games/month by tier)

| Tier | Typical | P95 | P99 | Mix |
|---|---:|---:|---:|---|
| $25 | 6 | 12 | 18 | 1-2 games/week + long inactive tail |
| $50 | 16 | 28 | 40 | 3-4 games/week regular cadence |
| $75 | 30 | 55 | 80 | Daily play + weekend doubles |
| $100 | 60 | 110 | 170 | 2 games/day + creator/streaming testing |

## Free tier funding

- `freeRatio` slider (0-50%): fraction of a paying user's after-margin budget that funds one free user.
- Free users get a free $ budget = `$tier × (1 - margin) × freeRatio` worth of credit-budget equivalents.
- At freeRatio=10%, $25 tier, margin=80%: free user gets `$25 × 0.20 × 0.10 = $0.50/mo` → 0.14 R25 4p games.

## Credit economy (operator's standing decision)

- **1 credit = 1,000 tokens.** Token-anchored, not per-call pricing.
- Pack tiers: $5 / $10 / $25 / $50 / $100. $100 pack eligible for operator-set bulk discount (default 10%).
- Cost-per-credit at blended rate: `$0.24/M × 1000 / 1e6 = $0.00024/credit` → 4,167 credits per dollar.
- Credit packs at default state: $5 = 21,182 cr, $10 = 42,364, $25 = 105,910, $50 = 211,820, $100 = 381,276 (with 10% bulk off).
- Game cost in credits (R25): 4p = 16,956 cr/user, 1v1 = 33,911, 1v3 = 67,823.

**Conclusion:** $25 credit pack = ~1.2 R25 4p games per user. **Credit packs are NOT a subscription replacement — they're an overage escape valve + free-to-play enablement.**

## Matchmaker subsidy ladder (hardcoded source: `AccountSettingsMatchmaking.kt`)

The matchmaking algorithm uses a "subsidy capacity" — how many OTHER player slots a user can effectively cover. This is the hidden funnel where credit purchases buy matchmaking placement.

| Class | How earned | Subsidy slots | Matchmaking effect |
|---|---|---:|---|
| BYO_KEY | Player brings own API key | 4 (cap) | Other 3 players effectively free |
| PRO | $75/$100 plan + auto-renew | 2 | Subsidizes 2 other slots. Common match target. |
| CASUAL | $25/$50 plan + auto-renew | 1 | Subsidizes 1 slot. Standard priority. |
| CREDIT | Non-zero credit balance (≥1,000 cr) | 0 + bonus | Floor 0; +1 slot per 1,000 cr held (capped at +2). 2,000+ cr ≡ CASUAL-level placement. |
| FREE | No plan, no credits | 0 | Matched only into groups with surplus capacity. |

**CREDIT bonus formula** (from `AccountSettingsMatchmaking.kt:46-57`):
```kotlin
fun AccountSettings.subsidyCapacity(): Int {
    val klass = costClass()
    val base = klass.subsidyCapacity
    if (klass == CostClass.CREDIT) {
        val thousands = (billingStatus.credits / 1000.0).toInt().coerceAtLeast(0)
        val bonus = thousands * klass.creditSubsidyPerThousand
        return (base + bonus).coerceIn(0, 2)
    }
    return base
}
```

`creditSubsidyPerThousand = 1` for `CostClass.CREDIT` → **every 1,000 credits held = +1 subsidy slot, capped at 2 bonus slots above the 0 baseline**.

## Margin semantics (frequently misunderstood)

The "margin" slider in pricing dashboards is the after-inference headroom fraction. **It does NOT directly equal real profit margin.** Real-world SaaS has to subtract from that headroom:
- Payment fees: ~3% (Stripe-like)
- Infra/support: ~5% (hosting, observability, support staff amortized)
- Taxes: variable
- Then real profit

**Default fixed costs in the model:** `paymentFee=0.03, infraSupport=0.05, tax=0.00`. Operator should adjust per jurisdiction.

**Break-even formula** (margin floor at which profit = 0):
```
breakEvenMargin = (fixedRate + profitPct) / (1 - freeRatio)
```

For fixedRate=0.08, profitPct=0, freeRatio=0.10: break-even at 8.9% margin floor. Below that, the tier loses money after fixed costs.

**Below 50% margin** = loss-leader / break-even zone, NOT "still profitable with reduced margin." The 25% margin floor extends into the range where the operator is funding inference + fixed costs out of headroom with no profit remaining.

## Per-call token composition (observed)

From R3T0 + R4T0 traces: ~95.8% input, ~4.2% output. Used to derive blended $/M token cost:
```
blendedDollarsPerMToken(rounds, mode) = gameCost(rounds, "mid") / totalGameTokens(rounds) * 1e6
```

This is the canonical conversion from $ budget to token cap. Token caps are enforced by token count, not dollar — so they survive price-tier changes and currency drift.

## Live model artifact

The pricing/monetization model lives at `tools/autogenesis_subscription_model.html` (single-file HTML+JS dashboard, 18 renderers, 10+ interactive controls). Always rebuild from this reference; the model is governed by a `verify-*-section.sh` ad-hoc pattern (structural + math sentinels) before any visual review. Suite-green canonical test does not exist for this artifact.
