# Competitor style reference

When in doubt about how to write a TPipe tutorial, look at how the competitors write theirs. The pattern is consistent across the serious frameworks: code first, terse description after, no manifesto, no "this is the difference between X and Y" framing.

## LangChain: "Create an agent" doc

URL: https://docs.langchain.com/oss/python/langchain/overview (Create an agent section)

Structure:
- Title: "Create an agent"
- Lead: "This example demonstrates how to create a simple LangChain agent with a custom tool:"
- Code block (~20 lines)
- One sentence after: "See the Installation instructions and Quickstart guide to get started building your own agents and applications with LangChain."
- Done.

Body text: 30 lines of body and a code block. No manifesto. No "this is the difference between X and Y." No "first benefit / second benefit / third benefit."

The voice is "here's the code. here's a pointer to more." That's the target.

## LangGraph: Quickstart

URL: https://docs.langchain.com/oss/python/langgraph/quickstart

Structure:
- Lead: "This quickstart demonstrates how to build a calculator agent using the LangGraph Graph API or the Functional API."
- Step 1: "Define tools and model" with code
- Step 2: "Define state" with code
- Step 3: "Define model node" with code
- Step 4: "Define tool node" with code
- Step 5: "Define end logic" with code
- Step 6: "Build and compile the agent" with code
- Each step has one sentence of description
- Then a "Full code example" dump at the end

Six numbered steps. Each has a 10-word description and a code block. No comparison to competitors. No manifesto.

The numbered-step pattern is the right model for multi-stage tutorials (e.g., "how to build a Manifold"). Each step is a thing the reader does.

## CrewAI: "Build your First Crew" blog

URL: https://blog.crewai.com/getting-started-with-crewai-build-your-first-crew/

Structure:
- Lead: "CrewAI is an open-source framework designed specifically to simplify the development of these collaborative agent networks, enabling complex task delegation and execution without the typical implementation headaches."
- "This guide walks you through creating your first agent crew from scratch."
- Bullet list of what you'll learn
- "Prerequisites" section
- Numbered installation steps
- "Project Creation: Scaffolding your first Crew"
- Numbered configuration steps (agents.yaml, tasks.yaml, tools, entry point)
- "Execution: Running your Crew"
- "Next Steps: Expanding your CrewAI skills"

CrewAI has a slightly more marketing-y intro ("without the typical implementation headaches") but the body is tutorial-y. The intro states what the product IS, not what it ISN'T. The "without the X" pattern is mild here because it's a single descriptive phrase, not a structural pattern.

The bullet-list-of-what-you'll-learn is a fine structure for the opening if the topic warrants it (e.g., a "getting started" post).

## AutoGen: "Multi-agent Conversation Framework"

URL: https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat/

Structure:
- Lead: "AutoGen offers a unified multi-agent conversation framework as a high-level abstraction of using foundation models."
- Descriptive sentences
- "Agents" section
- Code with comments
- "Multi-agent Conversations" section
- "Supporting Diverse Conversation Patterns" section

Has some "this framework simplifies X" / "it maximizes Y" patterns but they're descriptive, not comparison-y. The descriptive voice is fine when it's brief.

## What to take from these

- **Code first, description after.** Always. Even when the description is "what we're about to do."
- **Numbered steps for multi-part tutorials.** Each step has a 10-30 word description and a code block.
- **No "this is the difference between X and Y" framing.** State what the thing IS.
- **No "first benefit / second benefit / third benefit" lists.** Just say the benefit.
- **A friendly closer** ("Congratulations on building your first agent!") is fine but not required.
- **The FAQ/HowTo at the end is structural** (for SEO/AEO), not the article's voice. Keep them terse and don't let the FAQ pattern leak into the body.

## The shared anti-pattern

None of these competitors use:
- "It's not X, it's Y" framing in the body
- "Skip it for [cases]" instructions without a positive alternative
- "Without X, Y doesn't work" as a directive structure
- "This is the first/second/third benefit" lists
- "Let me walk you through" / "Let me explain" as topic setters

These are the AI tells. They're not how human-written tutorials sound.

## How to actually use this reference

Before writing a TPipe tutorial post, fetch one of these competitor pages (curl is fine — they're plain HTML). Read the body structure. Note:
1. How many words of body are between code blocks? (Answer: usually 10-30.)
2. How many code blocks per post? (Answer: usually 3-6, with the full source at the end.)
3. What's the length of the post? (Answer: 1000-2500 words usually. TPipe posts can be longer because the framework is bigger.)
4. Are there "decision framework" sections? (Answer: rarely. Usually the post just walks you through the right choice.)

Then write the TPipe version following the same shape.
