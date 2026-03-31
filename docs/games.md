# Games

Game definitions are python files that implement the `Game` interface. They define the rules, objectives, and interactions.

## Core Games

We maintain a curated set of games that are used internally called "core games" that are included with the simulation engine.

The simulation engine contains a set of core games that demonstrate different experimental paradigms for studying interactions between diverse cognitive systems. Each game is designed to explore specific aspects of cognition, communication, collaboration, and understanding among various types of agents. 

New experimental designs can be created by modifying existing games or configuring new ones, but the core games provide a foundational set of scenarios that are useful to our research.

### Explore - open-ended play
Explore is an open-ended, non-objective sandbox game that allows players to interact freely with different types of characters in various scenarios. This game is useful for observing naturalistic interactions and behaviors without predefined goals. Also, for demonstrating the simulation engine's capacity to handle diverse character interactions. Some have found it useful to play around and come up with interesting scenarios/questions and later design games around those.

### Foresight - predict next action
Foresight is a game that tests a player's ability to predict the next behavior of another character based on their understanding of that character. It offers insights into how thoroughly/completely a player understands another cognitive system in a vrariety of scenarios and also allows us to measure how many interactions it takes to build that understanding.

### Infer Intent - infer next goal
Infer Intent is a game that tests a player's ability to infer the specific goals or intents of another character during a single interaction. This game is useful for evaluating how well a player can pick up on limited cues and information to understand what another cognitive system is trying to achieve in the moment.

### Goal Horizon - infer goalspace bounds
Goal Horizon is a game designed to test a player’s ability to model another character’s capabilities in imagination space. Specifically, it evaluates how accurately a player can infer the largest-scale goals—across space and time—that a character is capable of pursuing, based on prior interactions. This game helps assess how well a player understands what another character is capable of thinking about.

### Teamwork - collaborate towards shared goals
Teamwork is a game that focuses on the collaborative efforts of multiple characters working together to achieve a common objective. This game is useful for studying how different cognitive systems can align their goals and strategies in a shared context.

## Custom Games