# NPC Simulation Engine — Build Specification

You are being asked to build the foundation of a medieval life simulator with LLM-driven NPCs. This document captures the full design as it currently stands. A specific game loop has **not** been chosen yet and is explicitly out of scope for this build — the goal here is a robust base system that multiple game loops could later sit on top of.

Before writing code, propose a project layout and tech stack consistent with the constraints below, and flag any decisions you want my input on.

---

## 1. Project Overview

A sandbox life simulator set in a medieval-tech-ceiling world. The defining feature is NPCs whose dialogue, memory, and behavior are driven by a local LLM, with a tiered simulation system that scales fidelity to the NPC's importance to the player. The world starts as a small region (one or two villages) and is intended to grow.

Three architectural commitments shape the rest of the design:

- A **tag/property-based world** with affordances computed lazily from zone contents, and a **GOAP-style action system** layered on top. Affordances are first-class; everything else (NPC behavior, dialogue grounding, player interaction) reads from them.
- A future **world-generation system** that produces realistic landscapes, topography, and a bullet-point history of sentient species. World gen at MVP can be near-random, but the data structures must accommodate this later.
- A future **story director** that listens for interesting emergent events and softly amplifies them toward the player. The director is *deferred* but its architectural hooks (event log shape, amplification primitives) are part of the MVP build.

Visual style is 2D top-down (Zelda LTTP / Stardew Valley reference), possibly migrating to isometric 3D later. Either way, world geography maps cleanly onto a graph data structure.

---

## 2. Hard Constraints

- **No API costs during development.** All LLM inference is local.
- **Local LLM runner:** support Ollama as the default. Abstract the runner interface so llama.cpp and LM Studio can be swapped in.
- **Candidate models:** Llama 3.2, Mistral 7B, Phi-3 Mini, Gemma 2 2B. The integration layer should be model-agnostic.
- **Tech ceiling:** medieval. Fantasy elements (magic, multi-race, monsters) are layered in later — start with a "medieval life simulator" framing.
- **Time mode:** "perpetual now" first. NPCs do not age. Aging is a v2 mode and the schema should leave room for it but not implement it now.
- **Game time:** paused when the game is not running. Target ~15 real minutes per in-game day (Stardew-like), tunable.

---

## 3. MVP Scope

Build:
- One village with surrounding wilderness.
- ~10 NPCs spanning the tier system (mostly T1–T2, one or two T3s).
- World graph data structure with zones, containment, ownership, tags/properties.
- Affordance/action system: globally-defined actions with preconditions and effects, evaluated against zone contents and actor state.
- Crafting system: product DAG, recipe knowledge layer, quality model, player skill hook interface, gathering with confusion tables (see §6).
- NPC schema covering traits, skills, values, goals, relationships.
- Per-NPC memory store + a shared community knowledge base.
- Local LLM integration layer (Ollama wrapper first).
- Dialogue system with hybrid menu + freeform input.
- Tier promotion and demotion logic.
- Stochastic off-screen interaction system.
- Time tick system (paused when game off).
- Per-NPC system prompt composition pipeline.
- Event log designed to feed the future story director (see §14).
- Developer inspection tooling (see §15) — built alongside the systems, not bolted on after.

Explicitly **out of scope** for MVP:
- Any specific game loop / quest system / progression.
- Aging, generational play, experience-passing.
- Multiple villages / travel between locations.
- Combat.
- Written records / oral tradition propagation.
- Magic, multi-race, monsters.
- Real economic flow tracking.
- Story director runtime behavior (the architecture is in scope; the director itself is stubbed).
- Casting agent / romance system.
- Worldgen beyond hand-authored or near-random placement.
- Crafting experimentation / reverse-engineering system (architectural hooks only — see §6).
- Crafting minigame implementations (the player-skill interface is in scope; specific minigames are game-loop decisions).

---

## 4. World Model

The world is a **graph of discrete, non-overlapping zones**. Zones can contain other zones (rooms ⊂ building ⊂ village; the wilderness is itself a zone that surrounds a village). Connections in the graph represent adjacency or passage (doorways, paths).

Each zone has:
- **State** (current contents, occupants, conditions).
- **Tags and properties.** Tags are unstructured labels. Properties are key-value pairs with typed values. Both are mutable — a zone's tags change as its contents change (a forge that loses its bellows loses the `air_supply` tag).
- **Affordances** (what actions are possible here — derived from terrain, materials, and contents via the affordance system in §5).
- **Terrain / material composition.**
- **Ownership** — zones may be owned by one or more entities. This matters for GOAP and social rules. Buildings, rooms, and larger land areas (forests, fields, rivers) can be owned by individuals or authorities.
- An optional **appearance** trait, modifiable by certain affordances (e.g., a tended garden looks different from a neglected one). Not all zones need this.

Zones do **not** carry persistent narrative memory. An inn does not remember its guests; that memory lives in the heads of patrons and in the community knowledge base.

Items, NPCs, and zone features all carry tags and properties in the same format. A forge has `heat_source`, `anvil`, `tool_storage`. A river has `water_source`, `fish_population`, `crossable_shallow`. Composition flows bottom-up: a zone's effective tag set includes the tags of everything inside it.

---

## 5. Affordances and Actions

### Action schema

Actions are defined globally, in one place. Each action has:
- **Name** and human-readable description.
- **Category** — at minimum `gathering`, `crafting`, `social`, `movement`. Extensible by the designer.
- **Preconditions**: a predicate over (actor state, zone state, present items, present NPCs). Example for `smith_sword`: `nearby(heat_source) AND nearby(anvil) AND has(iron_ingot) AND skill(smithing) >= 2 AND knows_recipe(smith_sword)`.
- **Effects**: structured outcomes. `produces(sword)`, `consumes(iron_ingot)`, `advances(smithing, 0.1)`, `time_cost(2_hours)`, `noise(loud)`.
- **Tags** on the action itself — `craft`, `social`, `violent`, `private`, `requires_consent`, etc. These tags drive social and narrative consequences (a `violent` action witnessed by an NPC produces different memory and gossip than a `social` one).
- **Optional parameters** for parametric actions (e.g., `craft(item_type)` rather than ten separate actions per craftable item).
- **Optional step list** — an ordered sequence of sub-steps (see §6 for crafting-specific usage).
- **Optional player_skill_gate** — type identifier and difficulty value for player skill checks (see §6).
- **Optional confusion_table** — for gathering actions, maps intended output to possible erroneous outputs with skill-dependent probabilities (see §6).

### Querying affordances

The system answers two queries efficiently:
- **What can actor A do here, now?** Returns the set of actions whose preconditions A satisfies given the current zone contents.
- **Where can action X be performed?** Returns zones in the graph (or a bounded subgraph) whose contents satisfy the precondition shape, ignoring actor-specific clauses.

These are the primitives everything else uses.

### How other systems consume the affordance system

- **NPC behavior (GOAP).** NPCs' goals decompose into action chains. The planner queries the second form ("where can I smith a sword?") to navigate, and the first form ("what can I do here?") to execute.
- **Dialogue grounding.** When an NPC speaks, the prompt composer includes a digest of actions currently or recently available to that NPC. The smith can talk concretely about smithing because the system knows she can smith here.
- **Player interaction.** The first form drives the player's contextual interaction surface. Specific UX (verb wheel, menu, diegetic prompts) is deferred — the system just exposes the candidate set.
- **Off-screen simulation.** Stochastic ticks pick from the affordance set rather than from a hard-coded behavior table.
- **Crafting.** The crafting system (§6) is built on top of these primitives — crafting actions are actions in the registry with additional structure.

### LLM-mediated extensibility

The LLM can propose **novel parameter values** for parametric actions during dialogue. A player asks "could you make me a helmet shaped like a fox?" — there is no `smith_fox_helmet`, but `smith_armor(item_type, embellishments)` exists, and the LLM negotiates the request against the smith's capabilities, available materials, and personality. The action schema stays formal; the surface is generative.

The LLM does **not** invent new actions wholesale at runtime. New action *schemas* are an authoring activity. Adding one later does not require revisiting existing zones or NPCs — they become eligible for the action automatically if their tags qualify.

### Authoring discipline

- Actions live in one registry, not scattered across zone or NPC code.
- Tags are documented in a single source-of-truth file. Adding a new tag is cheap; renaming one is not, so commit early.

---

## 6. Crafting System

The crafting system extends the action/affordance architecture in §5. Every crafting operation is an action in the registry. The new pieces are the product DAG, the recipe knowledge layer, the quality propagation model, and the player skill hook interface.

### Design goal

Every man-made object in the world — from tools and weapons, to food and beverages (including potions), to buildings and vehicles — should be craftable by any character who (a) has the appropriate character skills, (b) has learned the requisite recipe, and (c) has access to the appropriate tools, materials, and helpers. This is the gold standard; the system is designed to make it achievable. If an object exists in the world, someone made it using this system (or its predecessor made it, and the recipe may since have been lost).

### Action taxonomy

Actions carry a `category` field. Two categories are relevant to crafting:
- **`gathering`** — harvesting raw materials from the world. No recipe gate. Optional tool requirements. Skill affects yield accuracy (see confusion tables below). Any ingredient at the root node of a product tree is a raw material obtainable via a gathering action.
- **`crafting`** — transforming inputs into outputs. Requires the actor to hold the recipe in their `known_recipes` set. Requires specific tools and materials. Produces output with a quality value.

The designer can add categories freely — this is just the starting vocabulary.

### Product DAG

The dependency structure is implicit in the action registry, not a separate data structure. If `smelt_iron` produces `iron_ingot` and `smith_sword` consumes `iron_ingot`, the tree exists by following those links. A utility walks the registry and builds the full DAG for validation, visualization, and world-gen bootstrap checking, but it is derived, not authored separately. Adding a new craftable item is just adding an action — the tree updates automatically.

### Gathering

Raw materials do not require recipes to gather. Character skill (and potentially player skill, at the designer's discretion) affects gathering efficiency and accuracy but is not a gate — anyone can attempt to gather.

**Confusion tables.** Gathering actions can declare a confusion table mapping the intended output to alternative outputs, with probability weights that shift based on character skill. At low herbalism skill, a character attempting to gather a medicinal herb may accidentally collect similar-looking plants that contaminate a potion. At high skill, they get exactly what they intended. Table entries should reference items by tag similarity where possible ("plants in the same biome") so the system doesn't need a hand-authored row for every possible mistake, though hand-authored overrides take priority.

**Player knowledge vs. character skill.** Player knowledge (knowing what a plant looks like, knowing where ore veins appear, knowing what bait attracts certain animals, knowing what time of day animals leave their dwellings) is distinct from character skill numbers. The framework provides hooks for this — e.g., "this ore vein has visual distinctiveness level 3" — and the game implementation decides what that means in the rendering and interaction layers. Player knowledge persists across characters in aging mode; character skill does not.

### Recipe knowledge

Each character (NPC and player) carries a `known_recipes` set. This is a filter on the affordance query — when the system asks "what can this actor craft here?", it intersects available actions with `known_recipes` before checking material/tool preconditions. Recipes are acquired through defined channels:
- **Taught by NPC** — a dialogue system event. The NPC must know the recipe themselves.
- **Observed** — the player watches a crafting animation to completion and receives the recipe data.
- **Read** — the character interacts with a written object (book, scroll, inscription) containing the recipe.
- **Discovered** — experimentation system (deferred; see below).

Recipes are data — the ordered step list for the action — not a boolean flag, so they carry enough information to drive animation, dialogue, and minigames.

**Recipe opacity.** The recipe space is opaque to a character who hasn't learned a recipe. However, clues exist: (1) if the object exists in the world, it has a recipe; (2) if the character can find someone who makes the object, they can try to negotiate to learn the recipe or watch the crafting animation to see what tools and materials are involved. Crafting animations are faithful to the recipe being processed — animation is informational, not cosmetic.

**Recipe loss.** Recipes exist as knowledge in character memories. If every character who knows a recipe dies (or is demoted below the fidelity tier that tracks recipes) and no written record of the recipe exists in the world, the recipe is effectively lost. The action remains in the registry — the product is still *possible* — but no living actor can perform it until the recipe is rediscovered. This is the future hook for the experimentation system.

### Step lists

Every crafting action *can* have an ordered step list. Whether it does is an authoring decision. Actions without a step list are treated as atomic — one animation, one time cost, one skill check. Actions with a step list decompose into sub-steps, each of which can independently carry:
- A time cost.
- A tool reference.
- A material consumption.
- A player-skill-gate hook.

The minigame system attaches to individual steps. A one-shot action with a step list still runs all steps automatically, but the animation faithfully represents each one, consuming the aggregate time. This is the mechanism that makes watching an NPC craft informative — the player sees the sequence and learns the recipe.

Whether specific layers of the product tree get minigames (e.g., harvesting vs. assembly), and what those minigames look like, are game-loop decisions made by the designer, not framework decisions.

### Player skill interface

A step (or an atomic action) can declare a `player_skill_gate` with a type identifier and a difficulty value. The framework defines the interface: "this step requires a player skill check of type X at difficulty Y; return a performance score 0.0–1.0." The game implementation supplies the minigame that resolves it. If no minigame is registered for that type, the framework falls back to auto-resolve using character skill alone.

The framework never knows what a minigame looks like. It provides the hook; the game implementation provides the content.

### Quality model

Every craftable item carries a `quality` float (0.0–1.0) set at creation time. The framework defines the input vector:
- Material qualities (averaged, worst-of, or custom aggregation — configurable).
- Tool qualities.
- Character skill level.
- Player skill performance score (from minigame, if applicable).
- Optional environment modifier.

The framework ships a default weighting function but exposes it as an overridable policy — per action, per action category, or globally. The designer controls how much each factor matters. One designer might want quality to be mostly skill-driven (good smith, bad iron, still decent sword); another might want material quality to dominate.

Quality affects downstream behavior: durability, efficiency, and effectiveness. A dull axe (low quality) still chops wood but not as efficiently. A poorly-made shield (low quality) breaks faster in combat. Tools and materials themselves carry quality, so quality propagates through the dependency tree — a sword made with poor iron on a low-quality anvil by a middling smith produces a correspondingly lower-quality result.

Crafting is not normally pass/fail, but objects that are breakable — especially during their construction process — can operate that way at the designer's discretion.

### Skill degradation

The framework supports optional skill decay as a configurable policy. The designer specifies per skill or per skill category:
- Whether decay is enabled.
- The rate of decay.
- Whether decay is continuous or threshold-based.

The default is no decay. There is no guarantee that all skills are equally easy to level, so decay rates must be independently configurable to avoid strategic imbalances where players focus exclusively on easy-to-master skills.

### Bootstrap validation

World generation runs a post-gen validation pass that walks the product DAG from every raw material that requires a tool, traces backward to verify the tool is reachable (exists in the world, is obtainable through trade or as loot, or can be crafted from tool-free materials), and flags or repairs broken chains. This is a hard invariant.

The world generator must guarantee that all tools needed for harvesting raw materials exist somewhere in the world, usually within easy reach of settlements, and will be in constant-enough production to ensure a player can always obtain one with reasonably little effort. Players will need currency or goods of value to trade for said tools, so they either start with some basic goods or can harvest enough tool-free raw materials to trade.

### NPC crafting

NPCs craft using the same system. An NPC blacksmith's inventory is conceptually the output of their crafting actions during off-screen ticks. At T0/T1 fidelity, this can be shortcut with stochastic restocking, but the data structures should support the full version where the blacksmith actually runs crafting action chains. An NPC's `known_recipes` and skill levels determine what they can make and at what quality.

### Experimentation (deferred)

A future system will allow characters to rediscover lost recipes through experimentation. The action registry contains all possible crafting actions — the product is always *possible* — but without the recipe, the character cannot perform it. Experimentation would allow a character to attempt to derive the recipe through trial and error, with mechanics that vary by domain (metallurgy experimentation looks different from herbalism experimentation). This is explicitly out of scope for MVP but the recipe-as-knowledge architecture supports it without modification.

---

## 7. NPC Tier System

Four tiers of simulation fidelity, scaled to the NPC's current importance to the player:

- **T0 — Background.** A name, a role, a stat sheet. No memory, no personality, no LLM calls. Exists for population density. May not even tick unless queried.
- **T1 — Familiar face.** Personality traits, a basic schedule, simple reactive dialogue. LLM dialogue is available but constrained. Minimal memory.
- **T2 — Acquaintance.** Full trait model, relationship graph, short-term memory, rule-based GOAP-lite behavior over the affordance system. Occasional LLM lookups for novel situations.
- **T3 — Key figure.** Full LLM-driven dialogue with episodic memory. Scene-level off-screen simulation when narratively significant. Detailed event log.

### Promotion triggers
- Direct player interaction (conversation, transaction, conflict).
- Indirect involvement in player-relevant events (gossip about them, their actions affecting the player's world).
- Network reach within the population — figures with broad downstream influence (rulers, prominent criminals, authority figures) carry a baseline elevated tier even without player contact, *but* this should be filtered by likely player impact rather than raw centrality. Default to a cheap reach heuristic; full graph centrality is an optimization for later.

### Demotion triggers
- Death.
- Time decay, weighted by event significance.
- Geographic distance from the player when fast travel is unavailable.
- Player attention decay (no recent contact, no recent mentions in nearby gossip).

When an NPC is demoted, their richer history is compressed into:
- A **structured event log** (machine-readable, durable).
- A **narrative summary** (LLM-generated, human-readable).

Both are kept. The narrative summary is what's injected into prompts when the NPC re-promotes; the event log is the source of truth.

### Simulation cost by tier
- T0/T1: pure stochastic state updates when ticked. No LLM calls.
- T2: lightweight rule-based behavior with occasional LLM lookups for novel situations.
- T3: full LLM-driven scene-level simulation when off-screen events require it.
- Off-screen NPC↔NPC interactions never generate dialogue content — they apply stochastic adjustments to relationship values and execute information/goods transactions abstractly. The contents of a conversation are not determined unless the player will encounter them.

---

## 8. NPC Trait Model

Each NPC carries:
- **Big Five** personality dimensions on a continuous scale.
- **Trait tags** — discrete modifiers that produce interesting dynamics: greedy, gossipy, altruistic, flirtatious, courageous, vengeful, pious, curious, etc. Extensible; the schema should make adding new tags cheap.
- **Skills** — craft and competency proficiencies. Read by the affordance system's preconditions and the crafting system's quality model.
- **Known recipes** — the set of crafting actions this NPC can perform (see §6).
- **Values** — what they care about (family, honor, wealth, freedom, faith). Used for goal generation and conflict resolution.
- **Goals** — active short- and long-term ambitions. Drive behavior, especially at T2+. Decompose into action chains via the affordance system.
- **Relationship graph** — per-NPC view of who they know and how they feel about them. Asymmetric (A may love B who is indifferent to A).
- **Physical traits** — appearance, age (placeholder for now), notable features.

Trait values feed both the rule-based simulation layer and the prompt composition layer for LLM dialogue.

---

## 9. Memory Architecture

Two stores:

- **Individual memory** (per NPC). Event log + narrative summary. Tier determines depth and granularity. T0/T1 NPCs may have no real memory at all; T3 NPCs maintain detailed episodic memory. Recipe knowledge lives here.
- **Community knowledge base** (shared). A pooled store NPCs query for "what is broadly known here." This is the MVP approach. A future evolution is per-NPC distorted copies of community knowledge to support oral tradition and rumor distortion — leave room for this but don't implement it.

Memory drives prompt composition: when an NPC speaks, their relevant individual memories plus relevant community knowledge are injected into the system prompt. RAG-lite — a simple retrieval pass keyed off the current conversation topic, NPCs/places mentioned, and recent salient events.

Implicit memory (causal world effects, what living characters remember, written records) is a v2 concern. Start with a non-literate populace so written records can be ignored.

---

## 10. Dialogue System

- **Per-turn LLM generation** for all dialogue with T1+ NPCs.
- **Hybrid input.** Each player turn surfaces 2–4 LLM-generated menu options *and* a freeform text input. Menu options are generated each turn from current context and the NPC's state.
- **Incoherent / off-world freeform input** is handled in-fiction: the NPC plays it off as misunderstanding, suspicion, distraction — they do not break character or refuse the input mechanically.
- **Speech engine requirements** (must be enforced via prompt engineering + context injection, not model fine-tuning):
  1. Grounded in the game world. No real-world references.
  2. Distinct personality and speech pattern per NPC.
  3. Per-NPC memory enforces accurate knowledge bounds — an NPC only "knows" what their memory + community knowledge say they know.
  4. Short, idiosyncratic dialogue. Enforced via output token cap and prompt instruction. Avoid the verbose, hedged, LLM-typical register.
  5. Conversational initiative calibrated to feel natural without overwhelming a player accustomed to traditional NPC conventions.

### Per-NPC system prompt composition
Each dialogue turn assembles a system prompt from modular pieces:
- Global world primer (genre, tone, what does and doesn't exist).
- NPC identity block (name, role, traits, values, current mood).
- NPC speech-style block (derived from traits — terse vs. verbose, formal vs. coarse, etc.).
- Relevant memory excerpts (RAG-lite retrieval).
- Current scene context (location, present characters, recent events, **available affordances for this NPC here**, including craftable items if relevant).
- Hard constraints (length, no real-world references, no breaking character).

This composition pipeline is a core deliverable — not an afterthought.

---

## 11. Off-Screen Simulation

When the player is not present, NPCs continue to exist but at sharply reduced fidelity:
- T0/T1: state may not even tick unless something queries them.
- T2: rule-based GOAP-lite over the affordance system.
- T3: scenes may be simulated when narratively significant; otherwise stochastic.
- All inter-NPC conversations off-screen are abstracted to relationship deltas and information/goods transactions. **No dialogue content is generated for off-screen interactions** unless the player will later encounter that content.

Significant events (births, deaths, crimes, conflicts, romances forming) are recorded in the event log and may propagate into the community knowledge base.

NPC crafting during off-screen ticks uses the same action/crafting system but at reduced fidelity — T0/T1 NPCs use stochastic restocking; T2+ NPCs may actually run crafting action chains through the affordance system.

---

## 12. Player Character

The player character is an NPC controlled by a human. Other NPCs treat the PC the way they'd treat any NPC — they appear in NPC memories, get attention-promoted in NPC awareness, etc. If the vibe doesn't feel right, traits and stats that govern interaction may need tuning.

The PC carries the same schema as any NPC: traits, skills, known recipes, values, goals, relationships, physical traits. The crafting system (§6) applies identically to the PC — they need recipes, skills, tools, and materials just like any NPC.

---

## 13. Economy (Off-Screen)

Player-relative and lazy. No real currency-and-goods flow simulation at MVP.
- The smith has a sword for sale if the player (or a proxy with player-adjacent stakes) needs one. Default: yes.
- Disruptions to availability matter only if they intersect the player's attention. If the smith is sick, sword availability dips — but only meaningfully if the player has any chance of being affected by or able to act on that fact.
- Build the schema such that real flows could be added later, but don't simulate them now.

Trade remains important even in a world where the player can craft everything. A player is likely to specialize (especially if player skill is a factor) and trade for goods that take them longer to produce. Character skill degradation over time (if enabled by the designer) and limited play time further incentivize trade over self-sufficiency.

---

## 14. Story Director (Architected, Not Implemented)

The director is **out of scope at runtime for MVP** but its architectural hooks are not. Build the event log and the amplification primitives such that turning the director on later is purely additive.

### Conceptual model

The director is a **listener over the event log**, not a planner. It does not invent events. It periodically scans recent events, scores each on whether-it-is-interesting-now, and turns up the **volume** on selected events — meaning it adjusts how aggressively those events propagate into the player's awareness through existing channels (gossip in the community knowledge base, NPCs developing goals that intersect the player's path, etc.).

### What MVP must deliver for the director

- **Event log schema with director-ready metadata.** Every recorded event carries: involved NPCs (with roles in the event), location, event type, severity, descriptive tags, and a timestamp. Whatever fields a future scorer will need must be present from day one — adding them retroactively means revisiting every event-emitting site. Crafting events (especially notable creations, recipe discoveries, or recipe losses) should be logged with the same metadata.
- **Amplification primitives, exposed but unused.** A `gossip_weight` field on community-knowledge entries that biases retrieval toward higher-weighted gossip. A `salience` field on individual NPC memories. A mechanism for the director (or anything else) to adjust an NPC's short-term goals to bring them into proximity with a topic, location, or person. These primitives must exist and be functional; the director just isn't calling them yet.
- **A stub director module.** Wired into the tick system at the right cadence, receives the event log, calls no scorers and applies no amplification. Exists so turning the director on is a code change in one file, not a plumbing project.

### Parked director questions (do not implement; do not forget)
- Scorer design: heuristic-only vs. LLM-assisted for ambiguous cases.
- Pacing: how does the director modulate its own aggressiveness based on how much is already happening?
- Casting agent: a sub-system that identifies NPCs suited to play roles in emerging arcs. Separate design pass when ready.

---

## 15. Developer Tooling

Developer tooling is a **first-class deliverable**, not an afterthought. Build it alongside the systems it inspects.

### Required inspectors

- **NPC inspector.** Given an NPC, render their full state: tier, Big Five values, trait tags, skills, known recipes, values, current goals (with decomposition into planned actions if T2+), full relationship graph, recent memory entries, current narrative summary, current zone, currently-available affordances (including craftable items). Should be live — viewing the same NPC after a tick reflects updated state.
- **Event log viewer.** Filterable browsing of the event log: by NPC, by location, by event type, by tag, by time range. Each entry shows full structured payload. Sortable; searchable.
- **World/zone inspector.** Given a zone: tags, properties, contents (items, NPCs), ownership, current affordances available to a hypothetical actor, neighbors in the graph. For zones with crafting-relevant features (forge, tannery, etc.), show which crafting actions are currently possible here.
- **Product DAG viewer.** Visualize the full dependency tree for any craftable item — raw materials at the leaves, intermediate products at internal nodes, the final item at the root. Show which recipes are known vs. unknown for a given character.
- **Community knowledge base viewer.** What does the village "know"? Filterable by topic, by gossip weight (forward-compatible with the director).
- **Prompt inspector.** For any LLM call (dialogue turn, memory summarization, etc.), show the fully composed prompt that was sent and the raw response received. Critical for debugging the speech engine.
- **Tick stepper.** Manually advance simulation by one tick (or N ticks) without running real-time. Pause, step, resume.
- **Scenario seeding.** Load a hand-authored world state from a config file — specific NPCs with specific traits/skills/recipes, in specific zones, at specific tiers — so that bug reproduction and feature testing don't require playing through to a particular state.

### Form factor

A local web UI is the recommended default — it's easy to build incrementally, easy to filter and search in, and decouples the inspector from whatever the eventual game client is. CLI is acceptable for early scaffolding but will not scale to the relationship graph and event log views.

The tooling should read the same data structures the simulation uses — no parallel "debug copy" of state. If something appears in the inspector that doesn't match reality, that's a bug in the game, not the inspector.

### Logging

Structured logging from day one. Every tick, every LLM call, every promotion/demotion, every action executed (including crafting actions with their quality outcomes). Log volume will be large; rotating files plus a queryable view (even just `grep`-friendly JSON lines) is enough for MVP.

---

## 16. Time

- Paused when the game is not running.
- ~15 real minutes per in-game day at MVP, tunable.
- Tick granularity for off-screen sim should be coarser than the on-screen update loop. A reasonable starting design: on-screen runs at frame rate; off-screen NPCs tick at a much slower cadence (per in-game hour or per scene), with tier governing how much work is done per tick.

---

## 17. Open Design Questions

These are intentionally unresolved. Surface them when implementation forces a decision rather than guessing:

- Specific network-importance heuristic. A "reach score" (direct relationships weighted by tie strength + economic dependents + political dependents, recomputed periodically) is the cheap default; full graph centrality is the expensive correct version.
- Demotion thresholds. Will need experimental tuning.
- Tier promotion thresholds.
- Player freeform-input fallback behavior. Likely needs empirical testing once the system is up.
- Player UX for surfacing affordances (verb wheel, contextual menu, diegetic prompts). Punted to game-loop design.
- Concrete tick cadences for off-screen sim per tier.
- Default quality weighting formula for crafting. Ship a reasonable default; expect it to be overridden per game implementation.
- Whether NPC crafting during off-screen ticks should run full action chains at T2+ or use stochastic shortcuts at all tiers. Depends on performance once the system is running.

---

## 18. Suggested Module Layout

Propose your own and we'll iterate, but a rough sketch:

- `world/` — zones, graph, ownership, terrain, tags/properties.
- `affordances/` — action registry, precondition/effect schema, query primitives.
- `crafting/` — product DAG utilities, recipe knowledge management, quality model, confusion tables, player skill hook interface, bootstrap validation.
- `npc/` — schema, traits, memory, tier, prompt composition.
- `llm/` — runner abstraction (Ollama, llama.cpp, LM Studio adapters), prompt templates, output post-processing.
- `sim/` — off-screen tick, stochastic interactions, promotion/demotion, GOAP-lite.
- `dialogue/` — turn logic, menu generation, freeform input parsing, in-fiction misunderstanding handling.
- `knowledge/` — community KB, individual memory store, retrieval.
- `events/` — event log, schema, emitters, amplification primitives.
- `director/` — stub module with the integration point wired but no logic.
- `time/` — tick system, scheduling.
- `tools/` — developer inspectors, log viewers, scenario seeding, prompt inspector, product DAG viewer.

Pick a language consistent with reasonable performance and tooling for local LLM integration. Python is the obvious default for the simulation/LLM-orchestration layer; the eventual game client may live elsewhere. Feel free to recommend.

---

## 19. Suggested Build Order

1. World graph + zone schema with tags/properties for one village + interior + surrounding wilderness.
2. Affordance/action registry with a small starter action set (including a few gathering and crafting actions); query primitives.
3. Crafting system foundations: product DAG utilities, recipe knowledge store, quality model with default formula, confusion table support, player skill hook interface.
4. NPC schema. Spawn ~10 T0/T1 NPCs with roles, trait sheets, skills, and known recipes.
5. Developer tooling foundation: NPC inspector, world inspector, product DAG viewer, scenario seeding. (Build alongside steps 1–4, not after.)
6. Bootstrap validation pass for world-gen.
7. Local LLM integration: Ollama wrapper with the runner-agnostic interface. Prompt inspector tooling.
8. Dialogue system end-to-end against a single T2 NPC. Menu + freeform input. Per-NPC system prompt composition, including affordance digest and crafting context.
9. Individual memory store + community knowledge base + RAG-lite retrieval. KB viewer tooling.
10. Tier system: promotion and demotion logic, history compression on demotion.
11. Trait-driven prompt composition (full Big Five + tags integrated into speech style).
12. Event log with director-ready metadata (including crafting events). Event log viewer tooling. Stub director module.
13. Amplification primitives (gossip weight, memory salience, goal nudging) — exposed and functional, unused at runtime.
14. Off-screen stochastic interaction tick. GOAP-lite over affordances. NPC off-screen crafting. Tick stepper tooling.
15. Polish, tuning, documentation.

---

## 20. How to Proceed

Before writing code:
1. Confirm the language and framework choices.
2. Propose the concrete module layout.
3. Flag any of the open design questions in §17 you want answered before starting.
4. Identify any conflicts or gaps in this spec you want resolved.

Then build incrementally per §19, checking in at each step.
