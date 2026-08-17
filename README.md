# autogenesis-tools

Automation tooling, agent skills, scripts, and references that let coding agents (LLMs) drive the [Autogenesis](https://github.com/Ten-Trillion-Triangles/Open-Autogenesis) game end-to-end.

This repo is **not** the game. The game source lives in the private [Autogenesis](https://github.com/Ten-Trillion-Triangles/Autogenesis) repo and its public source-available mirror [Open-Autogenesis](https://github.com/Ten-Trillion-Triangles/Open-Autogenesis). What lives here is the kit an agent loads to boot, test, debug, audit, and deploy that game.

---

## What's in here

- **48 SKILL.md files** — loadable procedures for an LLM coding agent. Each skill teaches the agent one specific job (booting the stack, running a trace analysis, auditing feature state, deploying a service, etc.).
- **60+ scripts** — standalone shell, Node, and Python scripts for build, test, screenshot, deploy, and verification work.
- **70+ references** — long-form markdown and code recipes backing the skills (diagnostic patterns, worked examples, file:line evidence).
- **7 templates** — reusable skeletons for probes, blog posts, hero-image prompts, code snippets, and Pipe/Manifold starters.

Top-level layout groups the skills by what they target:

| Group              | What it covers                                                                  |
|--------------------|---------------------------------------------------------------------------------|
| `autogenesis-*`    | Skills that operate on the Autogenesis game directly (boot, deploy, audit, e2e).|
| `tpipe-*`          | Skills that operate on TPipe — the LLM pipeline runtime that powers Autogenesis.|
| `pump-station`     | Skills for the PumpStation service that hosts TPipe pipes.                     |
| `ttt-*`            | Skills for the ttt-site (Ten Trillion Triangles marketing site / docs).         |
| `log-parser`, `log-writer` | Logging conventions reused across skills.                              |
| `RUNBOOK.md`       | The setup-and-run guide for humans and agents using this toolkit.               |
| `LICENSE.md`       | MIT License — see [LICENSE.md](./LICENSE.md).                                  |

The full skill directory map (all 48 entries with one-line descriptions) is in [RUNBOOK.md §8](./RUNBOOK.md).

---

## Quick start

1. Read [RUNBOOK.md](./RUNBOOK.md) end-to-end. It is the canonical setup guide for both humans and LLM agents.
2. Pick a coding agent (Claude Code, Hermes, Cursor, Aider, OpenCode, Codex, etc.) and point it at this repo.
3. Load the skills the agent needs from the directory map.
4. Boot the Autogenesis stack (see [RUNBOOK.md §6](./RUNBOOK.md)).

The `RUNBOOK.md` is the source of truth for prerequisites, installation steps, common failure modes, and verification rituals.

---

## Audience

This repo serves two readers at once:

1. **Human developers** who want to set up the toolkit against their own coding agent and use it to work on Autogenesis.
2. **LLM agents** (Hermes, Claude Code, etc.) that load individual `SKILL.md` files to learn how to do one specific job. Each skill is self-contained — an agent can load just `autogenesis-local-dev` to boot the game without touching any of the TPipe skills.

---

## Relationship to other repos

| Repo                                       | Role                                                                                  |
|--------------------------------------------|---------------------------------------------------------------------------------------|
| `Open-Autogenesis` (public source-available)| Source-available scrubbed mirror of the game — the upstream for everything in here.   |
| `autogenesis-tools` (this repo)            | The agents, skills, scripts, and references that operate on the game.                 |

---

## License

[MIT](./LICENSE.md) — Copyright (c) 2026 Ten Trillion Triangles LLC.