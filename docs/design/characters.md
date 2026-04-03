# Characters

*Characters* are cognitive systems that can be used as player characters (PCs) or non-player characters (NPCs) in simulations.

## Core Characters
Core characters are a curated set of cognitive systems included with the simulation engine. Each is selected to represent a distinct type of cognition—differing in goals, structure, or behavior—and is tested to ensure the engine can model it reliably.

### Selection Criteria
A character is included if it meaningfully expands the range of cognitive systems we can model. This includes systems that challenge or extend typical assumptions about cognition and interaction.

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

> See the [character coverage report](../reports/character_coverage.md) for details on coverage and gaps in our current character database.

----

## Character Quality and Evaluation

Each character is a fixed snapshot of a cognitive system, including its:

- Persona
- Abilities
- Goals

Characters are designed to behave consistently so simulations remain reliable over time.

### Development Workflow

Character sheets define each character and are refined through iterative testing.

**1. Develop and Test**

- Create or modify a character sheet based on research (e.g., primary source materials, interviews with experts, etc.)
- Add it to database (`database_seeds/dev/characters.json`)
- Run simulations and observe behavior

**2. Evaluate Fidelity**
- Flag character behavior that doesn't align with expectations (e.g., "Out of Character" flags)
- Iterate until the character meets an in-character fidelity (ICF) threshold across scenarios

**3. Generate Report**

Generate a character quality report using:

```sh
dcs generate report character_quality <path/to/results>
```

Then complete the manual sections of the report including:
- authorship
- data/chart/score interpretations
- evaluation method details
- character strengths and weaknesses observed
- failure modes and drift behavior
- recommended use cases and guardrails
- pass/fail justification

**4. Publish for Review**

Publish the character quality report using:

```sh
dcs publish report character_quality <path/to/results>
```

Or manually update the following:
- Add results to `character_evaluations.json`
- Add report to `docs/design/simulation_quality`
- Add character to `database_seeds/prod/characters.json`    

Then open a PR for peer review of the character.

### Production Quality and Evaluation Consistency

Character behavior depends on both the **character sheet** and the **model + system prompt** used to role-play it.

To ensure consistency:

- All evaluations are fingerprinted with the exact model and system prompt used
- Evaluations are only valid of for the exact fingerprint + character hid they were run against

If the model or system prompt changes, the character must be re-evaluated before it can be used in production.

Because character evaluations are costly, we aim to keep role-playing models and prompts **as stable as possible**. When changes do occur, affected character undergo re-evaluation (including internal and, when applicable, external expert review).

## Validation

### Real-World Systems

When a real-world counterpart exists, we use external expert evaluations.

### Hypothetical or Non-Observable Systems

For systems without real-world counterparts (e.g., alien, abstract, or imagined systems), validation is based on:

- internal justification
- coherence of the design
- DCS research group consensus on usefulness and plausibility

## Custom Characters

Anyone can create custom characters using the workflow above.

To propose inclusion in the core set, submit a PR with supporting evaluation and rationale.

## Future Development

The core character database is designed to be extensible. New characters can be added as needed to explore new dimensions of cognitive diversity or to address specific research questions. Any characters that we add will have been vetted as described above for its ability to meaningfully represent a distinct cognitive system and should undergo the same quality assurance processes as existing characters.