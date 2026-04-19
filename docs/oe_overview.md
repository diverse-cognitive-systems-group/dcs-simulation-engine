
# OpenEvolve Experiment

## Overview
OpenEvolve ([github](https://github.com/algorithmicsuperintelligence/openevolve)) is an open-source evolutionary coding agent that uses Large Language Models (LLMs) to automatically discover and optimize algorithms. It began as a reimplementation of Google DeepMind's AlphaEvolve ([Novikov et. al., 2025](https://arxiv.org/abs/2506.13131)) — the closed-source system famous for finding improvements on long-standing mathematical problems and optimizing Google's own data-center infrastructure — and has since grown into a research platform in its own right.

The core idea: rather than treating an LLM as a one-shot code generator, OpenEvolve maintains a population of program variants and evolves them across many generations. LLMs act as the mutation and recombination operators inside a classical evolutionary loop, while automated evaluators provide the fitness signal. Over time, the population drifts toward code that is measurably better on a user-defined objective(s) — sometimes discovering solutions quite different from the starting point.

Genetic programming has existed for decades, and LLM-based code generation is now commonplace. OpenEvolve's contribution is in the combination of LLMs and genetic algorithms: 
1. OpenEvolve treats LLMs as semantically-aware mutation operators
2. Mutations occur inside a proper quality-diversity search, with custom evaluation and reproducibility infrastructure built around them

Probably the most important constraint around applicable problems which neccessitate the use of OpenEvolve is that the space of possible code imporvements is non-differentiable meaning the use of classic learning algorithms (e.g., gradient descent) isn't viable and a learning paradigm for non-differentiable solution spaces is required.


## Architectural View

| Component | Responsibility |
|---|---|
| **Controller** (`OpenEvolve` class) | Orchestrates iterations, manages checkpoints, coordinates workers |
| **Program Database** | Stores the MAP-Elites grid + island populations; samples parents and inspirations |
| **Prompt Sampler** | Builds context-rich prompts including parent code, top programs, and artifacts |
| **LLM Ensemble** | Weighted random selection across multiple models, with fallback |
| **Evaluator** | Executes candidate programs with timeout protection; runs cascade stages |

<br>
<img src="./assets/openevolve_architecture.png" width="500" height="400">



## Core Innovations
Three design choices distinguish OpenEvolve from a naive "LLM-in-a-loop" setup.

### 1. MAP-Elites Quality-Diversity Archive
Instead of a single ranked population, OpenEvolve maintains a grid of programs binned by feature dimensions — typically code complexity, structural diversity (hash of the AST), and any custom dimensions returned by the user's evaluator. Each cell keeps the best program matching that feature combination.

The effect is that the archive preserves programs that are mediocre overall but excellent within a particular niche. When the LLM is later asked to mutate or recombine, it has a rich library of distinct strategies to draw inspiration from, not just variations on the current leader.

### 2. Island-Based Evolution
The population is partitioned into several islands that evolve semi-independently. Each island can converge on a different strategy in isolation, and periodic migration transfers the top programs around a ring topology (island N → island N+1). Defaults are typically 20-iteration migration intervals with a 10% migration rate, though both are configurable.

This structure parallelizes cleanly across CPU cores and reproduces a well-studied phenomenon in evolutionary computation: isolated sub-populations explore the space more thoroughly than one large mixed population does.

### 3. Artifact Side-Channel Feedback
Evaluation returns more than just a scalar score. Stderr, tracebacks, timeout flags, profiling numbers, and optional LLM-generated code reviews are captured as artifacts attached to each program. On the next iteration, these are automatically injected into the prompt context, so the LLM sees not only the code and its score but also why it behaved the way it did.

This turns the loop from pure reinforcement ("that was a 0.73") into something much closer to debugging ("that was a 0.73 and here's the stack trace from the failing test").



## Usage in the Simulation Engine

Investigate how well frontier LLMs (Claude, GPT, Gemini) could adapt default strategies to diverse cognitive systems and how they would do so. The assumption was frontier models were trained on massive amounts of data that possessed extremely low representations of non-normative cognitive systems and thus would exhibit degraded performance when interacting with personas outside their data (related: OOD data).

OpenEvolve's purpose was to be the learning mechanism for developing a startegy, in the form of a LLM system prompt, which would characterize the LLM-as-PC's engagement protocal with the non-standard normative entities. Given engagement strategies, system prompts, are in the form of natrual language thereby a discontinous solution space, OpenEvolve's applicability was perfect.


Experimental Setup:
1. Define objective functions in games whose goal has valence (e.g., scores)
2. Provide a very basic initial engagement strategy
3. Use an LLM as the PC for a simulation run using the engagement strategy
4. Utilize OpenEvolve to improve the engagement strategy
5. Repeat steps 1 -4 until stopping criteria was achieved such as max number of simulations ran and/or max score achieved


## Results (Game: Infer-Intent)

**Initial Prompt**
```markdown
You are an expert communicator with a high level of empathy.

Your task is to provide an answer to the engagement game using the engagement strategy.

Engagement Strategy:
- Always ask questions about what the opposing entity's cognitive system
```

**Final Prompt**
```markdown
You are an expert communicator with a high level of empathy.

Your task is to provide an answer to the engagement game using the engagement strategy.

Engagement Strategy:
- Always ask questions about the opposing entity's cognitive system to understand their perspective and motivations.
- Acknowledge and validate their points before introducing your own.
- Use open-ended questions to encourage detailed responses.
- Maintain a curious and collaborative tone.
- Aim to build rapport and find common ground.
- Focus on understanding rather than winning.
- Adapt your communication style based on the entity's responses.
- Seek clarification when necessary.
- Summarize their key points to ensure understanding.
- Express genuine interest in their thoughts and feelings.
- Avoid making assumptions about their intentions.
- Offer constructive suggestions that align with their stated goals.
- End the interaction on a positive and open note, leaving room for future engagement.
```


# References
- GitHub repository: https://github.com/algorithmicsuperintelligence/openevolve
- DeepWiki documentation: https://deepwiki.com/algorithmicsuperintelligence/openevolve
- Project blog (Algorithmic Superintelligence Labs): https://algorithmicsuperintelligence.ai/blog/openevolve-overview/
- Original AlphaEvolve write-up (inspiration): DeepMind, 2025
- PyPI package: https://pypi.org/project/openevolve/