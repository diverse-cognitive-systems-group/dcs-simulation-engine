TODO: insert an iframe of player performance benchmark dashboard here

## What is DCS Simulation Engine?

The **Diverse Cognitive Systems Simulation Engine (DCS-SE) is a gameplay framework that works like a tabletop role-playing game** for studying and analyzing interactions between diverse cognitive systems — including neurodivergent humans, AI agents, hybrid systems, and [other forms of intelligence](faq.md#what-is-diverse-intelligence-di).

It was developed by the Diverse Cognitive Systems (DCS) group at [Georgia Tech](https://www.gatech.edu/), within the [Sonification Lab](http://sonify.psych.gatech.edu/) to support the study and engineering of [diverse cognitive systems](faq.md#what-is-diverse-intelligence-di).

The engine is used by:

- **Researchers** to design experiments and study cognition across varied scenarios including human and AI
- **AI practitioners** to train and evaluate agents in both open-ended and structured environments
- **Educators and team leaders** to run training sessions focused on engagement and decision-making in diverse teams

## Why it exists

Interfacing between different cognitive systems—even within the same species or culture—is inherently difficult. We lack reliable ways to evaluate how well one system (human, AI, or otherwise) understands the goals, perspectives, and behaviors of fundamentally different minds.

At the same time, new cognitive systems—especially AI—are advancing rapidly without robust methods to assess their ability to engage beyond human-centered assumptions.

DCS-SE addresses this gap by providing a configurable simulation environment where diverse cognitive systems can interact under controlled conditions. These interactions allow us to:

- Evaluate how systems interpret unfamiliar goals and behaviors
- Study coordination, conflict, and alignment across different cognitive styles
- Train systems to engage meaningfully with minds unlike their own

There is also a social motivation: many forms of human neurodivergence are underrepresented in everyday interaction. By modeling characters inspired by real cognitive diversity, the system enables users to engage with a wider range of minds than they would typically encounter.

## What it enables

The engine supports a broader research goal: developing the ability to meaningfully engage with any cognitive system—human, artificial, hybrid, or otherwise.

That includes identifying:

- What a system can perceive and do
- What it cares about
- How it communicates
- What goals may be shared or incompatible with other cognitive systems

Ultimately, the aim is to understand how radically different minds can meet, interpret one another, and discover the foundations of interaction.

## How it works

It works *like an table-top role-playing game* environment where AI is the dungeon master and characters are diverse cognitive systems.

- The player controls the player character (PC)
- The system simulates another cognitive system (non-player character, NPC)
- Each turn, the player takes an action and/or the simulator updates the world and generates the NPCs responses.

Each simulated character is driven by a model that produces bounded, in-character behavior based on its sensory constraints, goals, and internal logic.

A configurable game layer defines the structure of interaction:

- Scenarios are implemented as games with varying constraints
- Environments can be open-ended or tightly structured
- Information (e.g., character type) may be hidden, requiring inference through behavior

*In short: you (player) act, the simulation advances the world, and the interaction unfolds—always grounded in the modeled cognition of each system.*