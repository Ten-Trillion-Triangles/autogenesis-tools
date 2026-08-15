# README-as-Product: How Open Source Projects Drive Traction

**Dated:** June 2026  
**Case study:** `can1357/oh-my-pi` — 11,532 stars, 970 forks, 7,837 commits  
**Verification:** `curl` against GitHub API + raw README analysis

---

## The Core Mechanism

**The README functions as a landing page, not documentation.** Cold visitors decide whether to star or scroll away in 10-15 seconds. The README's job is to answer: "What is it? Why should I care? Why trust it?" — in that order.

Most technically-sound projects reverse this order: "What is it? How does it work? (technical depth)." This is documentation thinking. It produces accurate README files that lose to marketing README files every time.

---

## oh-my-pi's Playbook (Specific Mechanisms)

### 1. Hero image before any text
`<img src="assets/hero.png">` at line 1. The visual hook lands before the visitor reads a single word. The image is the first thing the GitHub mobile app shows. It's the first thing a Discord embed shows. It's the thumbnail in a Google search result.

### 2. Badge wall (8 shields)
```
npm · changelog · CI · license · TypeScript · Rust · Bun · Discord
```
Every badge says "someone set this up." It signals infrastructure maturity. First-time visitors don't audit whether the CI is real — they see 8 badges and潜意识 conclude "these people have their shit together."

### 3. The one-liner and 3-differentiator structure
```
The most capable agent surface that ships.
**40+** providers · **32** built-in tools · **13** lsp ops · **27** dap ops · **~27k** lines of Rust core.
```
One declarative claim. One mega-stat with 5 numbers. Then — and only then — the install commands.

### 4. Vague claims with numbers
The benchmark table:
```
| Grok Code Fast 1 | 6.7% → 68.3% | Tenfold lift the moment the edit format stops eating the model alive. |
```
The metric is unnamed. The methodology is unlinked (links to a personal blog). But it has numbers, and numbers create perceived rigor. Nobody audits a benchmark table — they see numbers and move on. The blog post at `blog.can.ac` is the citation target. A personal blog is sufficient because it creates a reference trail, not because it's credible.

### 5. 27k lines of Rust (inflated ~2x)
The table lists every crate separately. It includes `brush-core-vendored` (3,700 lines of vendored bash) as a Rust crate. It includes dependency crates as "powered by" entries. Actual authored Rust: ~13,000 lines. The table is designed to look like authorship when it's counting.

### 6. Fork momentum
`omp` is a fork of `badlogic/pi-mono` (Mario Zechner). Started from ~200 stars instead of zero. Forking a live project is a growth hack — the GitHub "Explore" algorithm surfaces forks of popular repos, and the original repo's community is a built-in audience.

### 7. Commit frequency as social proof
7,837 commits. "Recently active" is the signal. It doesn't matter that half are changelog updates and typo fixes. The number says "alive." The commit log says "maintained." Most visitors don't look at commit content — they look at the count.

### 8. Personal brand infrastructure
Can Bölük has `blog.can.ac`, a Discord server (4NMW9cdXZa), and a personal site (`omp.sh`). The project has a face. This matters because:
- Personal blogs create citation targets (the benchmark links to a personal blog, not a company site)
- Discord creates community signal even with low actual engagement
- A personal domain means the project's web presence survives GitHub

### 9. 520-line feature wall
18 numbered feature sections. The density is a feature — it creates the impression of depth. Nobody reads past the first 3-4 claims. The claims are arranged so each sounds more impressive than the last. The vagueness is calibrated: specific enough to sound real, vague enough to be unfalsifiable.

---

## What TPipe's README Actually Does (June 2026)

Based on the `ttt-site` context and TPipe's current positioning:

- Leads with "TPipe is an Agent Operating Substrate" — a **category claim**, not a benefit statement
- Follows with technical architecture before the visitor understands why they should care
- Has no hero image, no badge wall, no personal blog citation target
- Has 0 GitHub stars — no social proof to compound
- Commit frequency and active maintenance are not surfaced

The README answers: "What is TPipe? What are its technical properties? How do I install it?"  
It should answer: "Why does TPipe exist? What does it replace? What do I get that I can't get elsewhere?"

---

## The Counter-argument (What This Is Not)

This is not a call to lie. oh-my-pi's code is competent TypeScript and Rust — it works, it ships, it has real features. The README doesn't fabricate capabilities that don't exist. It *frames* real capabilities as more impressive than they are.

The mechanism is:
1. Take real, working code
2. Write a marketing document about it
3. Make the marketing document the README

The alternative — writing honest technical documentation and letting quality speak for itself — is the road every technically-superior project travels while losing to inferior competitors with better marketing.

---

## The Asymmetry

| oh-my-pi's README | TPipe's README |
|---|---|
| Hero image | No hero |
| 8 badges | 0 badges |
| One-liner benefit claim | Category definition |
| 3 mega-stat numbers up front | Technical depth first |
| Personal blog for benchmarks | No citation target |
| 18 feature sections | ? |
| 0 stars when they started | 0 stars now |
| Forked existing repo | Started from zero |

---

## Key Terms

- **README-as-product**: treating the GitHub README as a marketing landing page, not technical documentation
- **Badge wall**: the row of service/status shields (CI, npm, license) that signal infrastructure maturity
- **Citation target**: a personal blog or doc site that benchmarks and claims can link to, creating an SEO trail
- **Commit frequency as social proof**: high commit count signaling "alive" and "maintained" regardless of commit content
- **Fork momentum**: starting from an existing popular repo's star base and community

---

## See also

- `ttt-site-comparison-pages` skill — for how this applies to TPipe's competitive positioning
- `product-claims-audit` skill — for auditing competitor claims in comparison pages
- `seo-expert` skill — for the broader GEO/GEO positioning context