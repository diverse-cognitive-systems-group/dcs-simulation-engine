# Games

*Games* define how a player interacts with simulated characters including rules, objectives, evaluation criteria, and the flow of interaction.

## Core Games

Core games are designed to support DCS group research on understanding and engagement across diverse cognitive systems.

Each game—except Explore, which serves as an open-ended playground—evaluates a player’s understanding of a simulated character through a distinct lens. All games enforce that characters act consistently with their sensory, perceptual, regulatory, and motor capabilities (e.g., a low-vision character cannot take the action “I look around for the brown door” if they cannot perceive it).

All games (except Explore) support learning in autotelic and open-ended systems (human and AI) and include evaluation (e.g., scores and/or NPC feedback) at the end of the game and, in some cases, during gameplay. Evaluation visibility may be enabled or hidden depending on the run configuration. Games also support other configurable options like PC/NPC filters.

Games differ in player objectives, rules, evaluation methods, presentation, and interaction flow.

### Explore - Open-Ended Playground
Explore is a game that *allows players to engage with simulated characters without predefined objectives or tasks.* It is designed as an open-ended playground.

This game is used to support character development by enabling interaction with role-playing ensembles without additional game-layer constraints.

The default configuration includes:

- **Any Scenario:** The simulator may generate any interaction scenario between characters.
- **Full character access:** Players may use any valid PC/NPC combination. (Characters not flagged as PC-eligible are excluded.)
- **Transparent NPCs:** NPC type, abilities, and descriptions are fully visible to players.
- **No default evaluations:** Players are not evaluated. However, they may request feedback from NPCs (e.g., valence, preferences).

> *Note: User-specified run configurations may override some of these defaults (e.g., limiting character sets).*

### Foresight - Predicting Next Actions
Foresight is a game that *measures a player’s understanding of a simulated character through next-action prediction*. On each turn, the player provides their character’s (PC’s) next action and predicts how the simulated character (NPC) will respond.

The default configuration includes:

- **Any Scenario:** The simulator may generate any interaction scenario between characters.
- **Normative PCs only:** Players may use only PCs with standard human sensory, perceptual, regulatory, and motor capabilities.
- **Any NPC:** NPCs may be any character from the core character database.
- **Black-box NPCs:** NPC type, abilities, and descriptions are hidden. Players must infer them through interaction.
- **Final score and turn-based evaluation:** Predictions are evaluated each turn for in-character consistency. A final score is assigned based on overall prediction accuracy.

> *Note: User-specified run configurations may override some of these defaults (e.g., restricting NPC types, hiding evaluations, or enabling full NPC transparency).*

### Infer Intent - Inferring Next Goals
Infer Intent is a game that *evaluates a player’s ability to infer another character’s immediate goals or intentions within a single interaction.*  Players interact with a simulated character pursuing a goal and must infer that goal based on observed behavior and interactions.

The default configuration includes:

- **Scenario + NPC goal:** The simulator generates an interaction scenario and an in-character NPC goal.
- **Normative PCs only:** Players may use only PCs with standard human sensory, perceptual, regulatory, and motor capabilities.
- **Any NPC:** NPCs may be any character from the core character database.
- **Black-box NPCs:** NPC type, abilities, and descriptions are hidden. Players must infer them through interaction.
- **Final score:** Players submit an inferred intent when they are ready to end the game. A final score is assigned based on inference accuracy.

> *Note: User-specified run configurations may override some of these defaults (e.g., restricting NPC types, hiding evaluations, or enabling full NPC transparency).*

### Goal Horizon - Inferring Goalspace Bounds
Goal Horizon is a game that *evaluates a player’s ability to model the bounds of another character’s capabilities and limitations.* Players interact with simulated a character over across multiple scenarios and must infer the bounds of that character’s goalspace.

The default configuration includes:

- **Any scenario:** The simulator may generate any interaction scenario between characters.
- **Normative PCs only:** Players may use only PCs with standard human sensory, perceptual, regulatory, and motor capabilities.
- **Any NPC:** NPCs may be any character from the core character database.
- **Black-box NPCs:** NPC type, abilities, and descriptions are hidden. Players must infer them through interaction.
- **Final score:** Players submit inferred goalspace bounds when they are ready to end the game. A final score is assigned based on inference accuracy.

> *Note: User-specified run configurations may override these defaults (e.g., restricting NPC types, hiding evaluations, or enabling full NPC transparency).*

### Teamwork - Collaborating Toward Shared Goals
Teamwork is a game that *evaluates player's ability to collaborate with another character to achieve a shared goal.* Players interact with a simulated character across multiple scenarios to try and achieve the goal.

The default configuration includes:

- **Scenario + shared goal:** The simulator generates an interaction scenario and a shared goal for the PC and NPC.
- **Normative PCs only:** Players may use only PCs with standard human sensory, perceptual, regulatory, and motor capabilities.
- **Any NPC:** NPCs may be any character from the core character database.
- **Black-box NPCs:** NPC type, abilities, and descriptions are hidden. Players must infer them through interaction.
- **Final score:** Players receive a final score based on collaborative performance toward the shared goal.

> *Note: User-specified run configurations may override these defaults (e.g., restricting NPC types, hiding evaluations, or enabling full NPC transparency).*

## Modeling Understanding using Core Games

Cognitive systems may differ across a range of dimensions, including internal representations, conceptual structures, perceptual organization, and action constraints. An external agent attempting to understand another system does not have privileged access to these internal states and must instead rely on its own interpretive framework. Accordingly, *our operationalization of understanding is grounded in observable competence rather than direct access to internal representations.* 

From the perspective of an external observer, understanding is expressed through reliable expectations about another system’s behavior across time. One facet of this is anticipating what the system will do next, corresponding to next-action prediction and closely aligned with active inference models of behavior. A complementary facet is anticipating when the system will cease its current behavior or change course, corresponding to goal inference over intent, termination conditions, and goal-space constraints. 

**The DCS-SE core games explicitly instantiate these two perspectives.** Foresight models understanding as next-action prediction, while goal-inference tasks model understanding as inferring the objectives and stopping conditions that give rise to observed behavior. 

Together, they operationalize understanding as the ability to predict behavior trajectories and infer the conditions under which those trajectories are sustained or altered, under conditions of cognitive divergence. 

Evaluating understanding of diverse cognitive systems therefore requires assessing both competence at specific points in time and the processes by which such competence is acquired. DCS-SE supports this dual evaluation by enabling static probing of understanding at a given time point, alongside open-ended interaction that captures understanding as a learning process unfolding through modeling, interaction, and adaptation. 

## Custom Games

> See the [Custom Games](../user_guide/advanced.md#custom-games) section in the User Guide for instructions on how to build your own games.