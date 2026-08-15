# Anti-Premise Failure Modes

The two failure modes the landing page must NOT collapse into. Each has a signature in the copy and a defense.

## Mode 1: "AI writes funny stories"

The reader walks away thinking Autogenesis is an AI-story-generation toy with a game skin. They do not register the four-player competition, the 25-round cap, the win thresholds, or the karma/nemesis system.

### Signature phrases that produce this collapse

- "AI-generated narrative"
- "AI tells the story"
- "Powered by a creative AI"
- "Infinite replayability"
- "Endless stories"
- "Watch the AI write your adventure"
- "An AI dungeon master"
- Any framing where the AI is the protagonist of the marketing message

### Why it collapses

The reader's mental model for "AI writes stories" is: the LLM has full creative control, the user prompts, the LLM outputs prose. That's the ChatGPT-with-a-prompt frame. If the landing page lands there first, the reader never discovers that the LLM is gated by the validator/rectifier/judge pipeline, that stat changes are mechanically derived from narrative outcomes, or that another player's turn can ruin yours.

### Defense

1. Show the loop first, name the AI last. The hero reel shows player input → world response → board change before any copy mentions the AI.
2. When the AI is named, name its role: "the storyteller inside a rules-bound world" or "the dungeon master that has to answer to the same rules you do." Both phrases make clear the AI is a piece of the game, not the game's soul.
3. Place the 4-player, 25-round, win-threshold facts in the second or third scroll section. They reframe the AI as a referee, not an author.

## Mode 2: "Strategy game with a chat box"

The reader walks away thinking Autogenesis is a Civilization-style grand-strategy game with a freeform-text command interface. They do not register that the player invents the action, that the world responds with narrative prose, or that the consequence can be a microscopic civil war inside the player's own body.

### Signature phrases that produce this collapse

- "Strategic world domination"
- "Conquer the world with your empire"
- "Lead your civilization to victory"
- "Build your nation, manage your resources"
- "Military, diplomatic, and economic strategy"
- Any framing where the game looks like a 4X or grand-strategy title

### Why it collapses

The reader's mental model for "strategy game" is: there's a menu of legal actions, each has known outcomes, the optimal move is a calculation. That's the chess frame. If the landing page lands there first, the reader never discovers that the player can attempt `I train the syrup-trap sentient demolition robots to demolish the sky`, or that the world responds with a written story that the rules then turn into a board consequence.

### Defense

1. Lead with a player action that no strategy-game menu would offer. "Lord Maple Tree deploys two major invasions of Great White North and Greenland with maple-syrup armies" is the right kind of action: clearly strategic, but framed in a register no strategy-game copy uses.
2. Show the narrative reveal as a visual beat. The character-by-character prose typing effect is the strongest proof that this isn't a 4X. If the reader skips the proof clip, they will revert to the strategy-game mental model.
3. Do NOT lead with a screenshot of the top bar (Main Score / Military / Diplomatic / Research / Summit). Numbers + bars + scoreboard = strategy-game frame. The narrative panel is the disambiguator.

## The Combined Defense (When Both Modes Threaten Simultaneously)

The premise sentence is the single load-bearing piece of copy. It has to do all of the following at once:

- Survive a three-second skim.
- Avoid copula avoidance ("X is not Y, X is Z").
- Name the loop in three beats: invent → world responds → board changes.
- Land the emotional hit (excitement → anticipation → being blown away) without reducing to either failure mode.
- Not lead with the word "AI" or the phrase "dungeon master."

If a draft premise sentence makes the reader picture a chatbot OR a strategy game, the sentence is wrong even if the rest of the page would rescue it. The premise is the first frame; it sets the mental model; the rest of the page can refine but not overturn.

## Detection Heuristic Before Ship

```bash
# Read the premise sentence (first 1-2 sentences of body content on the page)
# Check for failure-mode signatures:
grep -i "AI" src/pages/index.astro | head -3
grep -i "dungeon master" src/pages/index.astro
grep -i "strategy" src/pages/index.astro
grep -i "conquer" src/pages/index.astro
grep -i "narrative adventure" src/pages/index.astro
```

If any of these appear in the FIRST 200 words of the page body, the premise sentence is wrong or the page ordering is wrong. The loop (invent → world responds → board changes) must come before any of these words.

If the loop is shown visually (in the hero reel) but not stated textually in the first paragraph, the reader who can't see the reel (text-only reader, screen reader, broken embed) will fall into one of the two failure modes. The textual premise and the visual reel must agree.
