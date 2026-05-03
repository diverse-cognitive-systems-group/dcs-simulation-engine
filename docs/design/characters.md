# Characters

*Characters* are cognitive systems that can be used as player characters (PCs) or non-player characters (NPCs) in simulations.

Each character is a fixed snapshot of a cognitive system, including its persona, abilities, constraints, and goals.

## Core Characters
Core characters are a curated set of cognitive systems included with the simulation engine. Each is selected to represent a distinct type of cognition—differing in goals, structure, or behavior—and is tested to ensure the engine can model it reliably.

### Coverage
A character is included if it meaningfully expands the range of cognitive systems we can model, especially those that challenge or extend typical assumptions about cognition and interaction.

Examples include:

- Alien-like intelligences with unfamiliar goal spaces or conceptual structures

- Humans or human-like systems that vary in sensory, perceptual, regulatory, or motor/action modalities (e.g., neurodivergent individuals, synesthetes, people with sensory processing differences, low-vision or non-ambulatory individuals)

- Artificial intelligences across different architectures and embodiments

- Abstract goal-directed systems, such as algorithms

- Distributed or collective intelligences (e.g., hive minds, decentralized systems)

- Basal or minimal intelligences (e.g., plants, single-celled organisms)

- Hybrid systems (e.g., cyborgs, human–AI integrations)

- Non-human biological intelligences (e.g., animals with distinct cognitive structures)

- Embryonic or cellular collectives

- And additional forms as needed

👉 See our character coverage reports for characters in [development](../reports/character_coverage_report_dev.html) and [production](../reports/character_coverage_report_prod.html).

### Character Development

Characters are defined using structured character sheets, informed by primary research and, where possible, interviews or first-person experiential input.

These sheets specify narrative fields such as descriptions, abilities, persona features, and goals, along with structured dimensions such as origin, form, agency, substrate, and size. They are iteratively refined to capture essential features of the cognitive system while remaining playable within the engine.

👉 See the [Custom Characters](../user_guide/advanced.md#custom-characters) section in the User Guide for the character development workflow.

### Production Consistency & Stability

Character behavior depends on three components:

- The character sheet
- The system prompt
- The role-playing model(s)

All **evaluations are fingerprinted** against this full configuration. As a result, evaluations are valid only for the exact combination of character sheet, system prompt, and model(s) they were run against.

Any change to one of these components (e.g., model version or prompt update) automatically invalidates prior evaluations and requires re-evaluation.

Character quality is governed by a character **release policy** (see `character-release-policy.yml` in the repository), which defines the minimum evaluation thresholds required before a character is added to production, including measures such as in-character fidelity (ICF) and scenario coverage.

Evaluations are conducted by internal and, when possible, external experts to ensure characters meet required thresholds.

For systems without real-world counterparts (e.g., alien or abstract systems), validation is based on DCS research group consensus regarding the character's plausibility and usefulness for research, informed by available evidence and theoretical grounding.

Because evaluations are costly, role-playing models and prompts are kept as stable as possible. When changes occur, affected characters are re-evaluated (including internal and, when applicable, external review).

👉 See the [Simulation Quality](simulation_quality.md) report for details on how role-playing quality is measured and maintained.
