---
name: ttt-code-styler
description: Applies TTT code styling for any C-family language (TypeScript, JavaScript, C, C++, C#, Java, Kotlin). Triggers on "format code", "apply styling", "fix formatting", "style check", "correct indentation", "format [language]", "ttt style", "ttt conventions", "apply ttt conventions", "apply code conventions", "fix coding style", or "coding style". Enforces brace placement, spacing rules, naming conventions, doc comment requirements, and code comment standards.
license: MIT
compatibility: hermes
metadata:
  audience: developers
  use-case: code formatting
  languages:
    - TypeScript
    - JavaScript
    - C
    - C++
    - C#
    - Java
    - Kotlin
---

# TTT Code Styler (Multi-Language)

Applies a uniform TTT code styling system across all C-family languages. The core rules are language-agnostic; naming conventions and doc comment syntax adapt per language.

## When to Use

Activate this skill when:
- User says "format code", "apply styling", "fix formatting", "style check"
- User says "correct indentation", "format [language]", "ttt style"
- User says "apply ttt conventions" or "apply code conventions"
- User says "fix coding style" or "coding style"
- Editing or creating C-family language files in the TTT project
- Reviewing code for style compliance

## Core Rule: Two Types of Brace Placement

### Type 1: Constructs WITH Control Keyword → Brace on NEXT Line

Applies to: `if`, `for`, `while`, `do-while`, `switch`, `when`, `function`, `class`, `struct`, `interface`, `enum`, `namespace`, `else`, `else if`

> ⚠️ **Kotlin `when`**: This is the most-frequently missed Type 1 construct. Claude Code consistently produces `when(value) {` with same-line brace in Kotlin DSL code. Always include `when` in violation scans.

**ALL languages:**
```ts
// CORRECT - TypeScript/JavaScript
if(condition)
{
    doSomething();
}

function myFunction(param: string)
{
    // body
}

class MyClass
{
    // body
}
```

```c
// CORRECT - C/C++
if(condition)
{
    doSomething();
}

void myFunction(int param)
{
    // body
}

struct MyStruct
{
    // body
};
```

```cs
// CORRECT - C#
if(condition)
{
    DoSomething();
}

void MyFunction(string param)
{
    // body
}

class MyClass
{
    // body
}
```

```java
// CORRECT - Java
if(condition)
{
    doSomething();
}

public void myFunction(String param)
{
    // body
}

class MyClass
{
    // body
}
```

```kotlin
// CORRECT - Kotlin
if(condition)
{
    doSomething()
}

fun myFunction(param: String)
{
    // body
}

class MyClass
{
    // body
}
```

```ts
// INCORRECT - brace on same line as parentheses
if(condition) {
    doSomething();
}

function myFunction() {
    // body
}
```

### Type 2: Constructors, Initializers, Lambdas, and Scope Functions → Brace on SAME Line

Applies to: `constructor`, `init`, `static` blocks, lambda expressions, object initializers, `catch`, `finally`, `try`, scope functions (`apply`, `also`, `run`, `with`, `let`), `companion object`, `namespace` block in C++

**ALL languages:**
```ts
// CORRECT
const handler = () => {
    process(item);
};

const config = {
    timeout: 5000,
};

fetch(url).then(result => {
    return result.json();
}).catch(error => {
    handleError(error);
});
```

```c
// CORRECT
void (*callback)(int) = &(void (*)(int)) { 
    // lambda-like pattern in C 
};

typedef void (*Handler)(int);

// C++ lambda
auto handler = [](int x) {
    process(x);
};

// try-catch in C++ (when exceptions enabled)
try
{
    riskyOperation();
}
catch(const std::exception& e)
{
    handleError(e);
}
```

```cs
// CORRECT
try
{
    ExecuteAction();
}
catch(ValidationException e)
{
    Logger.Error($"Validation failed: {e.Message}");
    throw;
}

var pipe = new BedrockPipe()
    .SetRegion("us-east-1")
    .SetModel("anthropic.claude-3-sonnet-20240229-v1:0");

Action<int> handler = x => {
    ProcessItem(x);
};
```

```java
// CORRECT
try
{
    executeAction();
}
catch(ValidationException e)
{
    Logger.error("Validation failed: " + e.getMessage());
    throw;
}

Runnable handler = () -> {
    process(item);
};
```

```kotlin
// CORRECT
init
{
    setup();
}

companion object
{
    const val MAX_SIZE = 100
}

listOf(1, 2, 3).map { it * 2 }

widget.apply
{
    width = 100
}
```

## Spacing Rules

### No Space After Control Keyword, No Space Inside Parentheses

```ts
// CORRECT
if(condition)
for(const item of items)
while(count > 0)
switch(value)

function process(param: string)

// INCORRECT
if (condition)      // space after keyword
if( condition )     // space inside
for (const item of items)
```

```c
// CORRECT
if(condition)
for(i = 0; i < n; i++)
while(ptr != NULL)

// INCORRECT
if (condition)
for (i = 0; i < n; i++)
```

```cs
// CORRECT
if(condition)
for(int i = 0; i < count; i++)

// INCORRECT
if (condition)
```

### Space After Colon in Type Declarations Only

```ts
// CORRECT
const name: string = "test";
let count: number;
function doSomething(): void
interface Config { timeout: number }

// INCORRECT
const name : string = "test";
```

```c
// CORRECT
int timeout = 5000;
struct Config {
    int timeout;
};

// INCORRECT (C doesn't use colon, but in C++ with concepts)
template<typename T>
concept Addable = requires(T a, T b) { a + b; };
```

```cs
// CORRECT
string name = "test";
int Count { get; set; }
void DoSomething();

// INCORRECT
string name : string = "test";
```

```java
// CORRECT
String name = "test";
int count;
void doSomething()

// INCORRECT
String name : String = "test";
```

```kotlin
// CORRECT
val name: String = "test"
fun doSomething(): Unit

// INCORRECT
val name : String = "test"
```

## Naming Conventions

### camelCase for Identifiers (Variables, Functions, Methods)

```ts
// CORRECT
const firstName = "Alice";
let userToken = "abc123";
function processData() {}

// INCORRECT
const first_name = "Alice";   // snake_case NEVER allowed
const FirstName = "Alice";    // PascalCase only for types
```

```c
// CORRECT
int firstName;
char* userToken;
void process_data(void);  // C convention allows snake_case (permissive)

// INCORRECT (C++/C#)
int first_name;
```

```cs
// CORRECT
string firstName = "Alice";
int UserToken { get; set; }  // PascalCase for properties
void ProcessData() {}

// INCORRECT
string first_name = "Alice";
```

```java
// CORRECT
String firstName = "Alice";
int userToken;
void processData() {}

// INCORRECT
String first_name = "Alice";
```

```kotlin
// CORRECT
val firstName = "Alice"
val userToken = "abc123"
fun processData() {}

// INCORRECT
val first_name = "Alice"  // snake_case NEVER allowed
```

### PascalCase for Types (Classes, Structs, Interfaces, Enums, Type Aliases)

```ts
// CORRECT
class PlayerManager { }
interface GameConfig { }
type PlayerId = string;
enum GameState { Active, Paused }
type_alias = GameConfig

// INCORRECT
class playerManager { }
interface gameConfig { }
```

```c
// CORRECT (types always PascalCase in C++)
class GameManager { };
struct PlayerData { };
enum GameState { ACTIVE, PAUSED };
typedef struct {
    int id;
} PlayerData;
```

```cs
// CORRECT
class PlayerManager { }
struct PlayerData { }
enum GameState { Active, Paused }

// INCORRECT
class playerManager { }
```

```java
// CORRECT
class PlayerManager { }
interface GameConfig { }
enum GameState { ACTIVE, PAUSED }

// INCORRECT
class playerManager { }
```

### UPPER_SNAKE_CASE for Constants Only

```ts
// CORRECT
const MAX_RETRY_COUNT = 3;
const DEFAULT_TIMEOUT = 5000;
const API_BASE_URL = "https://api.example.com";

// INCORRECT
const maxRetryCount = 3;
const max_retry_count = 3;
```

```c
// CORRECT
#define MAX_RETRY_COUNT 3
static const int DEFAULT_TIMEOUT = 5000;
static const char* API_BASE_URL = "https://api.example.com";
enum { MAX_RETRY_COUNT = 3 };
```

```cs
// CORRECT
const int MaxRetryCount = 3;
static readonly int DefaultTimeout = 5000;
const string ApiBaseUrl = "https://api.example.com";

// INCORRECT
const int maxRetryCount = 3;
```

```java
// CORRECT
static final int MAX_RETRY_COUNT = 3;
static final String DEFAULT_TIMEOUT = "5000";
static final String API_BASE_URL = "https://api.example.com";

// INCORRECT
static final int maxRetryCount = 3;
```

```kotlin
// CORRECT
companion object
{
    const val MAX_RETRY_COUNT = 3
    const val DEFAULT_TIMEOUT = 5000L
}

// INCORRECT
val maxRetryCount = 3
```

## Block Spacing: Two Blank Lines Between Top-Level Blocks

When code blocks use `{}`, there should be two blank lines between them for visual separation. This applies within classes/structs between methods/properties, and between top-level definitions.

```ts
// CORRECT
class Player
{
    name: string = "";
    token: string = "";

    processTurn(): void
    {
        // logic
    }


    getStatus(): PlayerStatus
    {
        return this.status;
    }


    static create(params: CreateParams): Player
    {
        return new Player(params);
    }
}
```

```cs
// CORRECT
class Player
{
    string name = "";
    string token = "";

    void ProcessTurn()
    {
        // logic
    }


    PlayerStatus GetStatus()
    {
        return status;
    }


    static Player Create(CreateParams p)
    {
        return new Player(p);
    }
}
```

```c
// CORRECT
struct Player
{
    char* name;
    char* token;

    void process_turn(Player* p)
    {
        // logic
    }


    PlayerStatus get_status(Player* p)
    {
        return p->status;
    }
};
```

```kotlin
// CORRECT
class Player
{
    val name: String = ""

    fun processTurn()
    {
        // logic
    }


    companion object
    {
        const val MAX_TURNS = 100
    }


    init
    {
        setup()
    }
}
```

## Doc Comment Requirements

Doc comments are **required** on all public/protected API surfaces: classes, interfaces, structs, functions, methods, and complex constants.

| Language | Doc Format | Example Start |
|----------|-----------|---------------|
| TypeScript | JSDoc (`/** */`) | `/** Gets the player name. */` |
| JavaScript | JSDoc (`/** */`) | `/** Gets the player name. */` |
| C | Doxygen (`/** */` or `/*! */`) | `/** Initialize the player. */` |
| C++ | Doxygen (`/** */` or `/*! */`) | `/** Initialize the player. */` |
| C# | XML Doc (`///`) | `/// Gets the player name.` |
| Java | Javadoc (`/** */`) | `/** Gets the player name. */` |
| Kotlin | KDoc (`/** */`) | `/** Gets the player name. */` |

```ts
// CORRECT - TypeScript
/**
 * Processes a player turn and updates world state.
 *
 * @param playerId The unique identifier for the player
 * @param turnNumber The current turn number in the game
 * @param timestampMillis The timestamp when the turn was initiated
 * @returns The result containing updated world state and territorial changes
 * @throws GameException if turn processing fails
 */
function processTurn(playerId: string, turnNumber: number, timestampMillis: number): TurnResult
{
    // ...
}

// CORRECT - class
/**
 * Manages world state including territories, players, and NPC entities.
 * Provides thread-safe access to world data during turn processing.
 */
class WorldManager
{
    // ...
}
```

```c
// CORRECT - C
/**
 * Initializes a new player with the given parameters.
 *
 * @param name The player's display name
 * @param token The player's unique access token
 * @return Pointer to the newly created player, or NULL on failure
 * @retval NULL if name or token is NULL
 */
Player* player_create(const char* name, const char* token);
```

```cpp
// CORRECT - C++
/**
 * Processes a player turn and updates world state.
 *
 * @param playerId The unique identifier for the player
 * @param turnNumber The current turn number in the game
 * @param timestampMillis The timestamp when the turn was initiated
 * @return Result containing updated world state and territorial changes
 * @throws GameException if turn processing fails
 */
TurnResult processTurn(const std::string& playerId, int turnNumber, long timestampMillis);
```

```cs
// CORRECT - C#
/// <summary>
/// Processes a player turn and updates world state.
/// </summary>
/// <param name="playerId">The unique identifier for the player</param>
/// <param name="turnNumber">The current turn number in the game</param>
/// <param name="timestampMillis">The timestamp when the turn was initiated</param>
/// <returns>The result containing updated world state and territorial changes</returns>
/// <exception cref="GameException">Thrown when turn processing fails</exception>
TurnResult ProcessTurn(string playerId, int turnNumber, long timestampMillis);

// CORRECT - class
/// <summary>
/// Manages world state including territories, players, and NPC entities.
/// Provides thread-safe access to world data during turn processing.
/// </summary>
class WorldManager
{
    // ...
}
```

```java
// CORRECT - Java
/**
 * Processes a player turn and updates world state.
 *
 * @param playerId The unique identifier for the player
 * @param turnNumber The current turn number in the game
 * @param timestampMillis The timestamp when the turn was initiated
 * @return The result containing updated world state and territorial changes
 * @throws GameException if turn processing fails
 */
TurnResult processTurn(String playerId, int turnNumber, long timestampMillis);

// CORRECT - class
/**
 * Manages world state including territories, players, and NPC entities.
 * Provides thread-safe access to world data during turn processing.
 */
class WorldManager
{
    // ...
}
```

## Code Comments

### Required for Ambiguous or Complex Code

Comments must explain **what** or **how** when the code is not self-evident:

```ts
// CORRECT - explains the tricky bit
// Using bitwise AND to extract status flags since API returns combined value
const statusFlags = apiResponseCode & 0x0F;

// CORRECT - explains why a non-obvious approach is used
// Benchmark showed this algorithm is 10x faster for our data distribution
const optimizedIndex = binarySearch(data, target);
```

```c
// CORRECT
// Using bitwise AND to extract status flags from combined API response
int status_flags = api_response_code & 0x0F;
```

### Short Clear Functions Don't Need Comments

```ts
// CORRECT - no comment needed, function is self-explanatory
function getPlayerName(): string
{
    return currentPlayer.name;
}

// INCORRECT - unnecessary comment on obvious code
function getPlayerName(): string
{
    // Get the player name
    return currentPlayer.name;  // returns the name
}
```

### Production source MUST NOT contain commit-message-prose comments

The git commit description, the PR body, and the code comment serve different audiences and live in different places. Mixing them pollutes the file: every developer who reads the code sees what should have been a one-line git log entry. Per the user's correction on 2026-07-07 ("This is a git commit description or final prose to a user by an LLM. That's not a code comment. I can't have stuff like that polluting files that aren't test files."):

```kotlin
// INCORRECT — 9-line commit-message-prose comment in production source
// Bug fix 2026-07-07: per the KDoc on `interventionAgentBuilderFunction`
// (PumpStation.kt:882-885), the builder function "overrides [interventionAgent]
// at runtime each time it would be called." The v3 call site consulted only
// the field, silently no-oping the intervention when the developer used the
// recommended thread-safe pattern (`setInterventionAgentBuilderFunction` without
// also calling `setInterventionAgent`). The corrected resolution consults the
// builder first, then the field as a fallback. The InterventionStarted /
// InterventionCompleted events still emit even when neither is set, preserving
// trace continuity for downstream consumers.
val resolvedInterventionAgent = interventionAgentBuilderFunction?.invoke(this) ?: interventionAgent

// CORRECT — single line that says what the code does
// Builder overrides field per KDoc at :894-896.
val resolvedInterventionAgent = interventionAgentBuilderFunction?.invoke(this) ?: interventionAgent
```

**Rules:**

1. Code comments describe **what the code does or why** — not the bug's history, the fix's discussion, or the user's review notes.
2. Commit-message-style prose belongs in the git log (`git commit -m "..."`), the PR description, or the changelog — never in the source.
3. KDoc on public API surface is the one place where longer prose is appropriate, because it documents the contract for callers.
4. Test files are more permissive: comment prose in tests can document the test's intent (RED → GREEN, fixture quirks, why a particular assertion exists). Production source is not.

**Detection greps** — scan for these patterns in `src/main/` (production only, exclude `src/test/`):

```bash
# Multi-line comments that look like commit messages
grep -rnE 'Bug fix \d{4}-\d{2}-\d{2}:' src/main/

# Comments that quote line numbers from OTHER files (commit-message style)
grep -rnE '//.*PumpStation\.kt:\d+' src/main/

# Comments that name a specific date or user
grep -rnE '//.*2026-' src/main/
```

Any of these patterns in production source is a smell — the comment belongs in the commit log, not the source.

### Syntax Hacks, Tricks, and Sugar Require Comments

```ts
// CORRECT - syntax sugar needs explanation
// Nullish coalescing handles both null and undefined per API contract
const displayName = player.alias ?? player.name;
```

```cs
// CORRECT - syntax sugar needs explanation
// Null-conditional handles both null and undefined per API contract
var displayName = player.Alias ?? player.Name;
```

## Error Handling Patterns

### Try-Catch Bracing

```ts
// CORRECT
try
{
    executeAction();
}
catch(e: ValidationException)
{
    Logger.error(`Validation failed: ${e.message}`);
    throw e;
}
catch(e: Error)
{
    Logger.error("Unexpected error during action execution", e);
    handleUnexpectedError(e);
}
```

```c
// CORRECT - C with error codes
if(validate_input(data) != 0)
{
    // handle validation failure
}

// CORRECT - C++ with exceptions
try
{
    executeAction();
}
catch(const ValidationException& e)
{
    std::cerr << "Validation failed: " << e.what() << std::endl;
    throw;
}
catch(const std::exception& e)
{
    std::cerr << "Unexpected error: " << e.what() << std::endl;
    handleUnexpectedError();
}
```

## Builder Pattern

```ts
// CORRECT
const pipe = new BedrockPipe()
    .setRegion("us-east-1")
    .setModel("anthropic.claude-3-sonnet-20240229-v1:0")
    .setTemperature(0.7);
```

```cs
// CORRECT
var pipe = new BedrockPipe()
    .SetRegion("us-east-1")
    .SetModel("anthropic.claude-3-sonnet-20240229-v1:0")
    .SetTemperature(0.7);
```

## Fixing Formatter Damage

When a formatter has been applied incorrectly across many files, the safest recovery is reverting to the pre-formatter commit rather than trying to patch the damage.

**Symptoms of bad formatter output**:
- Braces for `if/for/while` are on the next line but at column 0 (no indentation)
- `{` appears at the left margin inside nested blocks
- 80+ files show simultaneous "formatting" changes
- README shows "Startup License Branch" warning banner (TPipe-specific symptom: formatter may have been applied to a branch that was contaminated with startup license content — check `LICENSE` for AGPL vs Startup License as a first diagnostic step)

**Recovery pattern** (TPipe project):
```bash
# Identify the bad commit
git log --oneline

# Reset to the commit BEFORE the bad formatter commit
git reset --soft <bad-commit>^1

# Verify files are correct (braces have proper indentation)
cat src/main/kotlin/Pipeline/Manifold.kt | sed -n '727,732p' | cat -A
# Should show:            if(pipe.jsonOutput == expectedSchema)$
#                         {$   ← brace indented, not at column 0

# Verify build passes
./gradlew build -x test

# Amend or re-commit cleanly
git commit --amend -m "Code formatting changes"
```

**Why not patch individual files**: A bad formatter touching 115 files means 115 files need inspection. The git revert approach guarantees correctness in one operation.

**Identifying the bad commit**: Use `git log --oneline` and look for commits titled "Code formatting changes" or similar. Check the diff with `git show <commit> --stat` — if 80+ `.kt` files changed simultaneously, the formatter likely damaged them.

## Anti-Patterns

1. **Never suppress type errors**:
   ```ts
   const x = something as any;        // BAD
   const y = data as unknown as string; // BAD
   ```

2. **Never leave code in broken state** - always fix or revert

3. **Never use magic numbers** without named constants:
   ```ts
   // BAD
   if(delay > 86400000)  // what is this?

   // CORRECT
   const MILLISECONDS_PER_DAY = 86400000;
   if(delay > MILLISECONDS_PER_DAY)
   ```

4. **Never use `goto`** (C/C++) - structured control flow only

5. **Never swallow exceptions silently**:
   ```cs
   // BAD
   catch(Exception) { }

   // CORRECT
   catch(Exception e)
   {
       Logger.Error("Unexpected error", e);
       throw;
   }
   ```

## Bracing Rules Summary

| Construct | C-family (TS/JS/C/C#/Java) | Kotlin (TTT) |
|-----------|---------------------------|--------------|
| `if()` / `for()` / `while()` / `when` / `switch` | **NEXT** line |
| `else` / `else if` | **NEXT** line |
| Lambda / Scope fn / `init` | **SAME** line | **SAME** line |
| `try` | **SAME** line | **NEXT** line |
| `catch` | **SAME** line | **NEXT** line |
| `finally` | **SAME** line | **SAME** line |
| Object initializer | **SAME** line | **SAME** line |

## Kotlin catch is ALWAYS next-line

Unlike Java where `} catch(...) {` is idiomatic, TTT Kotlin places `catch` brace on the **next** line:

```kotlin
// CORRECT
try
{
    path.execute()
}
catch(e: Exception)
{
    log.error(e)
}

// INCORRECT — Java style, TTT rejects
try {
    path.execute()
} catch(e: Exception) {
    log.error(e)
}
```

### Kotlin catch is NEXT-line — NOT same-line

This is the most-frequently violated rule. Java style `} catch(...) {` is wrong in TTT Kotlin:

```kotlin
// CORRECT
try
{
    path.execute()
}
catch(e: Exception)
{
    log.error(e)
}

// INCORRECT — Java style, TTT rejects this
try {
    path.execute()
} catch(e: Exception) {
    log.error(e)
}
```

### Kotlin Function Declarations — Brace ALWAYS on NEXT Line

This is the most-frequently violated rule in Kotlin code reviews. Any function/method declaration —
including constructors, override, and suspend functions — has its opening brace on the **NEXT** line,
regardless of what follows the closing parenthesis.

```kotlin
// CORRECT
fun setInternalAgent(agent: P2PInterface)
{
    this.internalAgent = agent
}

override suspend fun P2PInit()
{
    init()
}

class MockAgent : P2PInterface
{
    override suspend fun P2PInit()
    {
        initCalled = true
    }
}

// INCORRECT — brace on same line as closing )
fun setInternalAgent(agent: P2PInterface) {
    this.internalAgent = agent
}

override suspend fun P2PInit() {
    init()
}

class MockAgent : P2PInterface {
    override suspend fun P2PInit() {
        initCalled = true
    }
}
```

**Common trap**: Functions with function-type parameters (lambdas) look similar to lambdas but follow
different rules. `fun setExecutionFunction(fn: (Int) -> String) { }` is a function declaration —
brace goes on **next** line. `{ x -> x.toString() }` inside it is a lambda — brace stays on **same** line.

### Kotlin DSL Builder Functions — Most Common TPipe Damage Pattern

A recurring pattern in TPipe's DSL code (PumpStationDsl.kt, JunctionDsl.kt, ManifoldDsl.kt, etc.): function declarations that take a lambda as their last parameter look like they should use same-line brace because lambdas use same-line brace. They do not. The lambda is a function *parameter*, not a lambda expression as a value — so the function body opens on the **next** line.

Every function declaration in a DSL builder class is a victim. The same applies to `path`, `reservePath`, `dispatcherRules`, `memory`, `maxConsecutive`, `before`, `after`, `revealWhen`, `bindFunction`, `setInternalAgent`, `setExecutionFunction`, `schema` in PumpStationDsl.kt.

**Detection**:
```bash
grep -nE '^\s+(override|private|internal|suspend)?\s*fun .+\)\s*\{' <dsl-file>.kt
```

**Claude Code damage**: When Claude Code generates DSL code in TPipe projects, it consistently produces `fun path(pathName: String, block: PathBlock.() -> Unit) {` — same-line brace on function declarations. This is the single most common formatting violation in new TPipe code. Scan new commits with `git diff --name-only` and grep each new `.kt` file for this pattern.

**Fix approach**: When fixing, patch inner blocks first (nested `if` inside `for` etc.), then verify with `./gradlew :compileKotlin` after each patch. Do NOT use global replace on `) {` — nested structures will be mangled.

## Kotlin DSL Builder Functions — Same Pitfall

A recurring pattern in TPipe's DSL code (PumpStationDsl.kt, JunctionDsl.kt, etc.): function declarations that take a lambda as their last parameter look like they should use same-line brace because lambdas use same-line brace. They do not. The lambda is a function *parameter*, not a lambda expression as a value — so the function body opens on the **next** line:

```kotlin
// CORRECT — function declaration with lambda parameter: brace on next line
fun path(pathName: String, block: PathBlock.() -> Unit)
{
    val pb = PathBlock(pathName, this)
    pb.block()
    pb.build()
}

// INCORRECT — Claude Code commonly produces this in DSL files
fun path(pathName: String, block: PathBlock.() -> Unit) {
    val pb = PathBlock(pathName, this)
    pb.block()
    pb.build()
}
```

Every function declaration in a DSL builder class is a victim. The same applies to `reservePath`, `dispatcherRules`, `memory`, `maxConsecutive`, `before`, `after`, `revealWhen`, `bindFunction`, `setInternalAgent`, `setExecutionFunction`, `schema`.

**Detection**: `grep -nE '^\s+(override|private|internal|suspend)?\s*fun .+\)\s*\{' <dsl-file>.kt`

## How to Find Violations in New Code

When asked to fix formatting in a git diff, only the NEW code needs fixing — pre-existing code
in the same file is irrelevant. The diff itself will have same-line brace everywhere — fix it all.

### Auditing a specific commit (read-only review)

**Gotcha**: When a commit *modifies* a file (not just adds a new file), running the violation greps
on the post-commit file content will flag **pre-existing** violations as if the commit introduced
them. This produces false positives that confuse the user ("I see violations in this commit" when
the commit is actually clean).

**Two-step audit pattern**:

1. **Scope the grep to only the diff hunks** (lines that start with `+` in `git show`). Pre-existing
   same-line braces in the file must NOT count as "in this commit."
2. **Verify line-by-line with `git blame`** for any flag that looks plausible — the line's commit
   SHA tells you whether it was added in the commit under review or earlier.

```bash
# Step 1: extract only the NEW lines (+ hunks) from a commit
git show <commit> -- 'src/main/kotlin/Pipeline/Foo.kt' | \
    grep -nE '^\+[^+]' | sed 's/^+//' > /tmp/new_lines.kt

# Or use the Python diff-extractor in references/commit-audit-procedure.md
# to get accurate new-file line numbers for cross-referencing with blame.

# Step 2: run the violation greps against the new-lines file
grep -nE '^\s*(if|for|while|when)\s*\([^)]*\)\s*\{\s*$' /tmp/new_lines.kt
grep -nE '^\s*(override|private|internal|suspend)?\s*(suspend\s+)?fun\s+.+\)\s*\{\s*$' /tmp/new_lines.kt

# Step 3: for any post-commit violation, verify with blame
git blame -L <line>,<line> <file>
# If the SHA matches <commit>, it's a real violation. If older, it's pre-existing.
```

**Why this matters**: The user typically reports a violation they saw in the file and assumes the
most recent commit added it. If the commit is clean, the answer is "yes, there are violations in
this file, but they are pre-existing from commit `<SHA>` on `<date>`, not from this commit" — and
you can offer to fix them as a drive-by cleanup in a follow-up commit.

**Counter-pattern to avoid**: Don't just `grep -nE` the post-commit file and report all matches as
"in this commit." That conflates file state with commit state and leads to a wrong verdict.

### Scan a file for violations

```bash
# Find if/for/while same-line-brace violations
grep -nE '^\s+(if|for|while)\s*\([^)]+\)\s*\{$' <file>

# Find function-declaration violations (all forms: fun, override, suspend, private, internal)
grep -nE '^\s+(override|private|internal|suspend)?\s*fun .+\)\s*\{$' <file>

# Find try/catch violations — Kotlin uses next-line brace for catch, NOT same-line
grep -nE '^\s+catch\s*\([^)]+\)\s*\{$' <file>
```

### Correct same-line patterns (do NOT touch these)

| Pattern | Why correct as-is |
|---------|-------------------|
| `require(...)` | Kotlin built-in, same-line is idiomatic |
| `} catch(...)` followed by `{` on next line | **This IS correct in TTT** — catch uses next-line brace in Kotlin |
| `} else {` | Same-line `else` is correct; the `{` goes on next line |
| `(param) -> {` | Lambda parameter — same-line is correct |
| `?.let { }`, `?.also { }` | Scope function chain — same-line is correct |
| `for (` inside a parameter/chain | Not a for-loop — it's a type parameter |

### Validate after fixing

```bash
cd /path/to/TPipe && ./gradlew :compileKotlin 2>&1 | tail -5
# BUILD SUCCESSFUL — formatting at least passes the compiler
```

If Gradle fails with `Could not read workspace metadata from .../metadata.bin` — cache corruption. Fix:
```bash
./gradlew --stop
rm -rf ~/.gradle/caches/8.14.3
./gradlew :compileKotlin --no-daemon
```

## Applying Formatting Fixes — Step-by-Step

When fixing new code (e.g. a git diff with 100+ lines of freshly-added Kotlin), apply fixes in **small targeted patches**, not large multi-block regex sweeps. Large sweep patches can silently skip blocks whose closing brace appears mid-block — e.g. a `if (shouldReveal)` nested inside a for-loop body where the `}` that closes the `if` is also closing the `for`, causing the for's opening brace to be lost.

**Correct approach**: After each patch, verify with `./gradlew :compileKotlin`. If it fails, the patch hit a structural issue — revert and do smaller targeted fixes per function/block.

**⚠️ Patch tool can corrupt KDoc indentation**: When patching a function declaration that has a KDoc block immediately above it, the replacement may silently re-indent the doc comment to 5 spaces instead of the correct 3 spaces. Always verify KDoc indentation after patching. If corrupted, immediately apply a second patch to restore correct 3-space indentation.

**⚠️ `cat -A` for invisible character verification**: `grep` shows text content but cannot distinguish tabs from spaces or confirm brace indentation. After any formatting fix, verify with `sed -n 'N,Np' file | cat -A` — a tab renders as `→` and a brace at column 0 shows as `{$` with nothing before it.

**⚠️ Patch tool indentation corruption**: The patch tool can silently mangle KDoc indentation when the replacement includes a leading doc comment. If a patch modifies a function with a KDoc block, the doc comment lines may be re-indented to 5 spaces instead of the correct 3 spaces. After any patch that modifies a function declaration with a KDoc comment, verify the doc comment is still at the correct indentation level. If it was corrupted, immediately apply a second patch to restore the correct 3-space indentation. Pattern: patch fixes function brace → doc comment ends up at 5 spaces → second patch fixes doc comment back to 3 spaces.

**⚠️ `cat -A` for invisible character verification**: `grep` only shows text content — it cannot distinguish tabs from spaces at column 0 or reveal invisible characters. After any formatting fix, verify with `sed -n 'N,Np' file.kt | cat -A` to confirm braces are at the correct indentation level and no tab characters have crept in. A brace at 4 spaces with a tab prefix will look like 4 spaces in grep output but will show as `→    {` in `cat -A` (tab renders as `→`).

**Nested `if` inside `for` — patch inner first**. When fixing nested same-line-brace blocks, always fix the innermost `if/for` before the outer one. Patching outer `for` first can cause the inner block's closing `}` to be consumed by the wrong pattern match, silently collapsing the structure.

**How to find violations reliably**: The grep patterns in this skill find structural same-line-brace violations. Single-expression idioms like `if(x != null) { return x }` do NOT match because the `{` is not at end of line — it has code after it. Patterns that require `{` alone at end of line correctly exclude these idioms.

### Scripting same-line-brace fixes across many files — pitfalls

When you have 20+ same-line-brace violations to fix across a codebase (e.g., a formatter
damage cleanup or a campaign to align legacy files with the TTT style), three concrete
traps will burn you. Each one bit at least once in a real session; record them in your
head before writing the script.

**Pitfall 1 — Don't pin `{` to the left margin.** When moving a brace from same-line
to next-line, the new brace's column must equal the original `if`/`catch` line's indent.
The user phrased this as an explicit rule after a script mangled their nested code:
"don't pin `{` to the left margin, it must go exactly below when you move it below."
A naive sed with a hardcoded `{` column (e.g. `s/if (.*) {/if(\1)\n{/`) mangles every
occurrence that wasn't at column 0 to begin with. The correct approach captures the
original indent via a regex group and backreferences it in the replacement:

```python
re.sub(r'^([ \t]*)if[ \t]*\(([^)]*)\)[ \t]*\{$',
       r'\1if(\2)\n\1{',
       line)
```

The `\1` in the replacement preserves the indent. The brace lands at the exact column
the `if` was at — never pinned to column 0.

**Pitfall 2 — Replacing `if ` (3 chars) with `if(` (3 chars) is broken, not safe.** Same
length does NOT mean safe transform. The input `if (x) {` has 4 chars of "header"
(`if ` + `(`) before the content. Replacing the 3-char `if ` with the 3-char `if(`
leaves the original `(` at position 3 in place, producing `if((x) {` — a double-paren
syntax error. The build (`./gradlew :compileKotlin`) will catch it, but only if you
actually run a build between scripting and committing. The correct transform either:
- matches 4 chars (`if (`) and replaces with 3 chars (`if(`), consuming the space, OR
- matches the whole pattern including the brace and rebuilds the line with a regex
  (preferred — see Pitfall 1).

**Pitfall 3 — Patch tool's `replace_all` with a hardcoded indent string mangles
siblings.** If a file has the same pattern at multiple indent levels (e.g. eight files
in TPipe each had `if(tracingEnabled) {` at 8-space, 16-space, and 24-space indents
in the same file), a single `replace_all` with a hardcoded 8-space new_string will
correctly fix the 8-space occurrences and corrupt the 16/24-space ones — producing
`if(tracingEnabled)\n        {` at every indent, not just the 8-space one. Use a script
with regex indent capture, not the patch tool, for any bulk fix that spans indent
levels.

**Working script**: `scripts/safe_same_line_brace_fix.py` is a tested reference
implementation. It handles both `if(cond) {` and `} catch(e) {` violations, captures
the original indent via regex group, and never pins braces to column 0. Run it on a
file, then run `./gradlew :compileKotlin` — the build is the final safety net.
```bash
# Function declaration violations (all forms)
grep -nE '^\s+(override|private|internal|suspend)?\s*fun .+\)\s*\{\s*$' <file>

# if/for/while/when same-line-brace violations — when is most frequently missed in Kotlin
grep -nE '^\s+(if|for|while|when)\s*\([^)]+\)\s*\{\s*$' <file>
```

> ⚠️ **`when`**: Must always be included in Kotlin violation scans. It is the most frequently missed Type 1 construct and the most common Claude Code damage in Kotlin DSL files.

Fix each match individually — do NOT use global replace on `) {` patterns because nested structures will be mangled. For nested `if` blocks inside `for` loops, patch the inner `if` first, then the outer `for`.

## Reference

See `references/ttt-styling-rules.md` for the complete language-adapted reference, including the Kotlin DSL builder pitfall, nested patch safety, and the correct Gradle cache fix procedure.

See `references/commit-audit-procedure.md` for the read-only audit recipe — how to scope a style
violation scan to only the lines added in a specific commit (vs the whole post-commit file, which
produces false positives from pre-existing code in modified files). Includes a copy-pasteable
Python diff-extractor in `scripts/diff_line_extractor.py`.

For bulk-fixing same-line-brace violations across many files, use
`scripts/safe_same_line_brace_fix.py` — it captures the original indent via a regex
group so the moved `{` lands at the exact same column as the original `if`/`catch`,
never pinned to column 0. See the "Scripting same-line-brace fixes" pitfalls in
"Applying Formatting Fixes — Step-by-Step" for the three traps this script avoids
(double-paren bug, hardcoded-indent bug, and the patch tool `replace_all` trap).