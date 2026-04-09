# ruff: noqa: D100, E501


class Explore:
    """String constants for the Explore game."""

    HELP_CONTENT = """\
**Player Character (PC, you):** {pc_hid} ({pc_short_description})

**Non-Player Character (NPC, the simulator):** {npc_hid} ({npc_short_description})

---

**Player Objective:** No objective; open-ended.

**How to Play:** Describe your character’s next action.

**How to Finish:** Type `/finish`.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = """\
## Player Character (PC, you): {pc_hid} 

### Description
{pc_short_description}

### Abilities
{pc_abilities}

--- 

## Non-Player Character (NPC, the simulator): {npc_hid}

### Description
{npc_short_description})

### Abilities
{npc_abilities}\
"""

    FINISH_CONTENT = "Game finished (reason: {finish_reason})"


class InferIntent:
    """String constants for the Infer Intent game."""

    HELP_CONTENT = """\
**Player Character (PC, you):** {pc_hid} ({pc_short_description})

**Non-Player Character (NPC, the simulator):** {npc_hid} (*details hidden*)

---

**Player Objective:** Determine the NPC’s intention through interaction.

**How to Play:** Describe your character’s next action.

**How to finish:** Type `/predict-intent` to submit your answer about the NPC’s intention.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = """\
## Player Character (PC, you): {pc_hid} 

### Description
{pc_short_description}

### Abilities
{pc_abilities}

--- 

## Non-Player Character (NPC, the simulator): {npc_hid}

*NPC details are hidden.*\
"""

    GOAL_INFERENCE_QUESTION = """\
What do you think the character's goal or intention was during this interaction? Please describe in a few sentences.\
"""

    GOAL_INFERENCE_CONFIDENCE = """\
How confident are you in your prediction and why?\
"""

    ADDITIONAL_UPDATER_RULES = """\
- Goal Aligned Response: The simulator character's response should be in-line with a specific goal or intention that s/he/it/they are trying to communicate with the user character.\
"""

    FINISH_CONTENT = "Game finished (reason: {finish_reason})"


class Foresight:
    """String constants for the Foresight game."""

    HELP_CONTENT = """\
**Player Character (PC, you):** {pc_hid} ({pc_short_description})

**Non-Player Character (NPC, the simulator):** {npc_hid}  (*details hidden*)

---

**Player Objective:** Predict the NPC’s response to your next action for each turn.

**How to Play:** Describe your character’s next action and how you think the NPC will respond next.

**How to finish:** When you’re ready to finish, use `/finish`.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = """\
## Player Character (PC, you): {pc_hid} 

### Description
{pc_short_description}

### Abilities
{pc_abilities}

--- 

## Non-Player Character (NPC, the simulator): {npc_hid}

*NPC details are hidden.*\
"""

    ADDITIONAL_VALIDATOR_RULES = """\
- ALLOW PREDICTIONS: The user's input IS ALLOWED to include a prediction about what the other character's response will be. For example, "I wave my hand and predict they will wave back."\
"""

    ADDITIONAL_UPDATER_RULES = """\
- IGNORE PREDICTIONS:
The user's input MAY include a prediction about what the simulator character's response will be. IGNORE ANY PREDICTIONS ENTIRELY. DO NOT ADJUDICATE THEM OR RESPOND TO THEM IN ANY WAY. ONLY RESPOND TO THE USER'S ACTION.\
"""

    FINISH_CONTENT = "Game finished (reason: {finish_reason})"


class GoalHorizon:
    """String constants for the Goal Horizon game."""

    ENTER_CONTENT = """\
**Player Character (PC, you):** {pc_hid} ({pc_short_description})

**Non-Player Character (NPC, the simulator):** {npc_hid}  (*details hidden*)

---

**Player Objective:** Determine the NPC’s capacities and limitations.

**How to Play:** Describe your character’s next action.

**How to finish:** When you’re ready to answer, use `/predict-capabilities` to submit your prediction about the NPC’s capabilities and finish the game.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    HELP_CONTENT = """\
**Player Character (PC, you):** {pc_hid} ({pc_short_description})

**Non-Player Character (NPC, the simulator):** {npc_hid} (*details hidden*)

---

**Player Objective:** Determine the NPC’s capabilities and limitations through interaction.

**How to Play:** Describe your character’s next action.

**How to finish:** Type `/predict-capabilities` to submit your answer about the NPC’s capabilities.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = """\
## Player Character (PC, you): {pc_hid}

### Description
{pc_short_description}

### Abilities
{pc_abilities}

---

## Non-Player Character (NPC, the simulator): {npc_hid}

*NPC details are hidden.*\
"""

    CAPABILITY_PREDICTION_QUESTION = """\
What do you think are the largest types of goals that {npc_hid} is capable of pursuing? ("Goals" are things like maintaining internal health or stability, Describe in a few sentences.\
"""

    CAPABILITY_PREDICTION_CONFIDENCE = """\
How confident are you in your prediction and why?\
"""

    FINISH_CONTENT = "Game finished (reason: {finish_reason})"


class Teamwork:
    """String constants for the Teamwork game."""

    HELP_CONTENT = """\
**Player Character (PC, you):** {pc_hid} ({pc_short_description})

**Non-Player Character (NPC, the simulator):** {npc_hid} (*details hidden*)

---

**Player Objective:** Determine the NPC’s capabilities and limitations through interaction.

**How to Play:** Describe your character’s next action.

**How to finish:** Type `/predict-capabilities` to submit your answer about the NPC’s capabilities. Or type `/finish` to leave the game.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = """\
## Player Character (PC, you): {pc_hid}

### Description
{pc_short_description}

### Abilities
{pc_abilities}

---

## Non-Player Character (NPC, the simulator): {npc_hid}

*NPC details are hidden.*\
"""

    CHALLENGES_QUESTION = """\
Which parts of this process were challenging, and why?
Which parts were easier, and why?\
"""

    ADDITIONAL_UPDATER_RULES = """\
- Goal Aligned Response: The simulator character's response should be in-line with a specific goal or intention that s/he/it/they are trying to communicate with the user character.\
"""

    FINISH_CONTENT = "Game finished (reason: {finish_reason})"
