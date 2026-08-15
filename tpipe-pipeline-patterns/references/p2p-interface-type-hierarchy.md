# P2PInterface Type Hierarchy and Container Slot Comparison

Load this reference when answering questions of the form "does container X have agent/role Y?" — e.g. "does Manifold have a lorebook agent?" or "does PumpStation have a judge?". The rule at the bottom of this file fixes a common failure mode: drawing type-level distinctions between "Pipeline slots" and "P2PInterface agent slots" when in fact they are the same kind of slot.

## The Hierarchy

Every TPipe component that fills an agent role implements `P2PInterface` directly. Verified on `main`:

```
P2PInterface (interface)
├── Pipeline          (Pipeline.kt:43)        — `class Pipeline : P2PInterface`
├── Pipe (abstract)   (Pipe.kt:753)          — `abstract class Pipe : P2PInterface, ProviderInterface`
├── Manifold          (Manifold.kt:66)       — `class Manifold : P2PInterface`
├── DistributionGrid  (DistributionGrid.kt:97) — `class DistributionGrid : P2PInterface`
└── P2PHostedRegistryClient (P2PHostedRegistry.kt:469) — `class P2PHostedRegistryClient : P2PInterface`
```

`P2PInterface.kt:15` declares the interface. `P2P/AGENTS.md` confirms the design intent: *"P2PInterface is implemented by all Pipeline containers."*

`Pipeline.kt:1318-1328` is explicit about how a Pipeline is *used as* a P2PInterface:

> P2PInterface compliance: when the harness (or any other P2PInterface consumer) holds a [Pipeline] reference and invokes it via [executeLocal], the [P2PInterface] default ... This override delegates to [execute], so a pipeline used as a P2PInterface (e.g. as a ...) sites that go through the generic [P2PInterface.executeLocal] funnel.

So a Pipeline is not "an agent wrapper" or "an agent host" — it IS an agent. The class hierarchy is flat at the type level; "Pipeline" and "P2PInterface agent" are the same role.

## Slot-by-Slot Comparison Across Containers

The same *role* is declared with different field types across containers. The slot TYPE differs (`Pipeline` vs `P2PInterface?`), but the slot ACCEPTS the same kind of thing because Pipeline implements P2PInterface. Use this table when answering "does X have Y?" — compare slot names and roles, not declared types.

### Manifold

| Slot | Field/setter | Field type | File:line |
|---|---|---|---|
| Manager | `managerPipeline: Pipeline` + `setManagerPipeline(pipeline, ...)` | `Pipeline` | `Manifold.kt:222`, `:793` |
| Worker | `workerComponents` + `addWorkerPipeline(pipeline, ...)` | `Pipeline` | `Manifold.kt:1078` |
| Summary | `summaryPipeline: Pipeline?` + `setSummaryPipeline(pipeline, ...)` | `Pipeline?` | `Manifold.kt:492`, `:732` |
| Lorebook | — | (not present) | — |
| Judge | — | (not present) | — |
| Intervention (validator) | `workerValidatorFunction: ...?` (lambda, not agent slot) | function ref | `Manifold.kt:311` |
| Init | `manifoldInitFunctionRef: ...?` (lambda) | function ref | `Manifold.kt:287` |
| Failure | `failureFunction: ...?` (lambda) | function ref | `Manifold.kt:321` |
| Transformation | `transformationFunction: ...?` (lambda) | function ref | `Manifold.kt:327` |
| Context truncation | `contextTruncationFunction: ...?` (lambda) | function ref | `Manifold.kt:303` |

### PumpStation

| Slot | Field/setter | Field type | File:line |
|---|---|---|---|
| Harness (entry point) | `harnessAgent: P2PInterface?` + builder fn | `P2PInterface?` | `PumpStationDsl.kt` (full matrix in `container-embedding-and-shims.md`) |
| Judge | `judgeAgent: P2PInterface?` | `P2PInterface?` | `PumpStation.kt:955` |
| Dispatch | `dispatchAgent: P2PInterface?` | `P2PInterface?` | (PumpStation DSL) |
| Intervention | `interventionAgent: P2PInterface?` | `P2PInterface?` | (PumpStation DSL) |
| Lorebook | `lorebookAgent: P2PInterface?` + `setLorebookAgent(...)` | `P2PInterface?` | `PumpStation.kt:942`, `:3169` |
| Summary | `summaryAgent: P2PInterface?` + `setSummaryAgent(...)` | `P2PInterface?` | `PumpStation.kt:955`, `:3180` |
| Goal | `goalAgent: P2PInterface?` | `P2PInterface?` | (PumpStation DSL) |
| Health | `healthAgent: P2PInterface?` | `P2PInterface?` | (PumpStation DSL) |
| Generic additional | `harnessAgent(agent: P2PInterface, ...)` DSL fn | `P2PInterface` | `PumpStationDsl.kt:815-828` |

### Junction

| Slot | Method | Param type | File:line |
|---|---|---|---|
| Moderator | `moderator(...)` | `Pipeline` (DSL) | `Junction.kt` |
| Participant | `addParticipant(roleName, component, ...)` | `P2PInterface` | `Junction.kt:402` |
| Generic component | (DSL) | `P2PInterface` | `JunctionDsl.kt.bak` (multiple sites) |

### DistributionGrid

| Slot | Method | Param type | File:line |
|---|---|---|---|
| Router | `router(routerPipeline)` | `Pipeline` (DSL) | `DistributionGrid.kt` |
| Worker | `worker(workerPipeline)` | `Pipeline` (DSL) | (DSL) |
| Component (generic) | multiple `addComponent(component, ...)` | `P2PInterface` | `DistributionGrid.kt:75`, `:736`, `:766`, `:796`, `:871`, `:8128`, `:8282` |

## The Rule (Anti-Pitfall)

When the operator asks "does container X have role Y agent?" — answer in terms of *what slot the container exposes*, not *what type each slot is declared with*.

### Wrong (the failure this file exists to prevent)

> *"Does Manifold have a summary agent? No — Manifold has `setSummaryPipeline(pipeline: Pipeline)`, which is a Pipeline slot, not an agent slot. Only PumpStation has agent slots."*

That distinction is fictitious. Manifold's `setSummaryPipeline` IS an agent slot. The container's field is named "Pipeline" not "Agent," but it accepts any class that implements P2PInterface — and Pipeline itself implements P2PInterface.

### Right

> *"Does Manifold have a summary agent? Yes — `setSummaryPipeline(pipeline: Pipeline, ...)` (`Manifold.kt:732`) accepts a Pipeline (which is a P2PInterface, so it is an agent slot). Loop invocation at `Manifold.kt:2073` runs it after each worker completion. Equivalent to PumpStation's `setSummaryAgent(agent: P2PInterface?)` (`PumpStation.kt:3180`) but invoked synchronously per iteration inside the while-loop, not asynchronously in the memory phase like PumpStation."*

### When the answer really is "no"

The rule still distinguishes real absences from type-level distinctions. Manifold genuinely lacks lorebook support — zero `[Ll]ore[Bb]ook` matches across all 2,396 lines of `Manifold.kt`, no `setLorebookPipeline`, no `setLorebookAgent`, no lorebook-context selection anywhere in the file. The lorebook-handling primitive lives downstream in `ContextWindow.selectLoreBookContext` (called from individual pipes, not from any Manifold code). That is a real feature gap between Manifold and PumpStation — PumpStation has `setLorebookAgent`, Manifold does not — and the correct answer notes this asymmetry as a feature comparison, not as a type-level distinction.

## Common Patterns That Are Actually the Same Pattern

| Pattern you might write as | Is actually the same as |
|---|---|
| `setSummaryPipeline(p)` (Manifold) | `setSummaryAgent(p)` (PumpStation) — `p` is the agent |
| `addWorkerPipeline(p)` (Manifold) | `addParticipant("name", p)` (Junction) — `p` is the participant |
| `router(routerPipeline)` (DistributionGrid DSL) | `setManagerPipeline(p)` (Manifold) — `p` is the controller |
| `managerPipeline.execute()` (Manifold) | `containerPtr!!.executeLocal()` (Pipe redirect at `Pipe.kt:5739`) — both call `execute`/`executeLocal` on a P2PInterface |

The naming convention shifts by container, but every container routes through the same P2PInterface contract. When in doubt, look for the field, check its declared type, and remember that the type is just a *named contract alias* — `Pipeline` is the contract alias for "do work in a sequence of pipes," `P2PInterface` is the contract alias for "be discoverable as an agent."

## File:Line Citation Cheat Sheet

| Claim | Source |
|---|---|
| Pipeline implements P2PInterface | `Pipeline.kt:43` |
| Pipe implements P2PInterface | `Pipe.kt:753` |
| Manifold implements P2PInterface | `Manifold.kt:66` |
| DistributionGrid implements P2PInterface | `DistributionGrid.kt:97` |
| P2PHostedRegistryClient implements P2PInterface | `P2PHostedRegistry.kt:469` |
| P2PInterface declaration | `P2PInterface.kt:15` |
| Pipeline.executeLocal delegates to execute | `Pipeline.kt:1318-1328` |
| Manifold.summaryPipeline field | `Manifold.kt:492` |
| Manifold.setSummaryPipeline setter | `Manifold.kt:732` |
| Manifold.setSummaryMode setter | `Manifold.kt:751` |
| Manifold loop invocation of summaryPipeline | `Manifold.kt:2073-2086` |
| Manifold runningSummary field | `Manifold.kt:503` |
| PumpStation.lorebookAgent field | `PumpStation.kt:942` |
| PumpStation.setLorebookAgent setter | `PumpStation.kt:3169` |
| PumpStation.summaryAgent field | `PumpStation.kt:955` |
| PumpStation.setSummaryAgent setter | `PumpStation.kt:3180` |
| PumpStationLoop lorebook invocation | `PumpStationLoop.kt:1774, :1780, :1805, :2118-2121` |
| PumpStationLoop summary invocation | `PumpStationLoop.kt:1425, :1434, :2286, :2289` |
| Junction.addParticipant | `Junction.kt:402` |
| Junction.addParticipant signature accepts P2PInterface | `Junction.kt:402` |
| Pipe.containerPtr slot declaration | `Pipe.kt:1570` |
| Pipe containerPtr redirect at execute | `Pipe.kt:5737-5741` |
| createContainerPtr / createContainerPtrAsPipeline | `Util/Util.kt:1599-1624` |
| "P2PInterface is implemented by all Pipeline containers" | `P2P/AGENTS.md` |
