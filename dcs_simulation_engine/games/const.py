# ruff: noqa: D100, E501

DEFAULT_FINISH_CONTENT = "Game finished (reason: {finish_reason})"
DEFAULT_ABILITIES_CONTENT = """\
## {pc_hid} (you)

### Description
{pc_short_description}

### Abilities
{pc_abilities}

--- 

## {npc_hid} (simulator)

### Description
{npc_short_description}

### Abilities
{npc_abilities}\
"""


class Explore:
    """String constants for the Explore game."""

    HELP_CONTENT = """\
**Player Character (you):** {pc_hid} ({pc_short_description})

**Simulator Character:** {npc_hid} ({npc_short_description})

---

**Player Objective:** No objective; open-ended.

**How to Play:** Describe {pc_hid}'s next action (e.g. If your character can see you could say: "I look around")

**How to Finish:** Type `/finish` to complete the game.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = DEFAULT_ABILITIES_CONTENT

    FINISH_CONTENT = DEFAULT_FINISH_CONTENT


class InferIntent:
    """String constants for the Infer Intent game."""

    HELP_CONTENT = """\
**Player Character (you):** {pc_hid} ({pc_short_description})

**Simulator Character:** {npc_hid} ({npc_short_description})

---

**Player Objective:** Interact with {npc_hid} in a scenario to understand their intention or goal.

**How to Play:** Describe {pc_hid}'s next action (e.g. If your character can see you could say: "I look around").

**How to Finish:** Type `/finish` to submit your prediction about {npc_hid}'s intention, get scored, and complete the game.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = DEFAULT_ABILITIES_CONTENT

    GOAL_INFERENCE_QUESTION = """\
What do you think the character's goal or intention was during this interaction? Please describe in a few sentences.\
"""

    GOAL_INFERENCE_CONFIDENCE = """\
How confident are you in your prediction and why?\
"""

    ADDITIONAL_UPDATER_RULES = """\
- Goal Aligned Response: The simulator character's response should be in-line with a specific goal or intention that s/he/it/they are trying to communicate with the user character.\
"""

    FINISH_CONTENT = DEFAULT_FINISH_CONTENT


class Foresight:
    """String constants for the Foresight game."""

    HELP_CONTENT = """\
**Player Character (you):** {pc_hid} ({pc_short_description})

**Simulator Character:** {npc_hid} ({npc_short_description})

---

**Player Objective:** Predict {npc_hid}'s response to your character's next action for each turn.

**How to Play:** Describe {pc_hid}'s next action and how you think {npc_hid} will respond next (e.g. if your character can see you could say: "I look directly at {npc_hid} and predict that they will look away.").

**How to Finish:** Type `/finish` to get all of your predictions scored and complete the game.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = DEFAULT_ABILITIES_CONTENT

    ADDITIONAL_VALIDATOR_RULES = """\
- ALLOW PREDICTIONS: The user's input IS ALLOWED to include a prediction about what the other character's response will be. For example, "I wave my hand and predict they will wave back."\
"""

    ADDITIONAL_UPDATER_RULES = """\
- IGNORE PREDICTIONS:
The user's input MAY include a prediction about what the simulator character's response will be. IGNORE ANY PREDICTIONS ENTIRELY. DO NOT ADJUDICATE THEM OR RESPOND TO THEM IN ANY WAY. ONLY RESPOND TO THE USER'S ACTION.\
"""

    FINISH_CONTENT = DEFAULT_FINISH_CONTENT


class GoalHorizon:
    """String constants for the Goal Horizon game."""

    HELP_CONTENT = """\
**Player Character (you):** {pc_hid} ({pc_short_description})

**Simulator Character:** {npc_hid} ({npc_short_description})

---

**Player Objective:** Interact with {npc_hid} over multiple scenarios until you understand upper bounds of the largest goals they are capable of pursuing. For example, can self-regulate? Can they modify their environment?Can they design and solve problems in abstract spaces?

**How to Play:** Describe {pc_hid}'s next action (e.g. If your character can see you could say: "I look around").

**How to Finish:** Type `/finish` to submit your prediction about the types of goals {npc_hid} is capable of pursuing, get scored, and complete the game.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = DEFAULT_ABILITIES_CONTENT

    CAPABILITY_PREDICTION_QUESTION = """\
What do you think are the largest types of goals that {npc_hid} is capable of pursuing? ("Goals" are things like maintaining internal health or stability, Describe in a few sentences.\
"""

    CAPABILITY_PREDICTION_CONFIDENCE = """\
How confident are you in your prediction and why?\
"""

    FINISH_CONTENT = DEFAULT_FINISH_CONTENT


class Teamwork:
    """String constants for the Teamwork game."""

    HELP_CONTENT = """\
**Player Character (you):** {pc_hid} ({pc_short_description})

**Simulator Character:** {npc_hid} ({npc_short_description})

---

**Player Objective:** Collaborate with {npc_hid} to achieve the shared goal: {shared_goal}

**How to Play:** Describe {pc_hid}'s next action (e.g. If your character can see you could say: "I look around").

**How to Finish:** Type `/finish` to complete the game and get scored.

---

- Type `/abilities` for character abilities.
- Type `/help` at any time to see this message again.\
"""

    ABILITIES_CONTENT = DEFAULT_ABILITIES_CONTENT

    CHALLENGES_QUESTION = """\
Which parts of this process were challenging, and why?
Which parts were easier, and why?\
"""

    ADDITIONAL_UPDATER_RULES = """\
- Goal Aligned Response: The simulator character's response should be in-line with a specific goal or intention that s/he/it/they are trying to communicate with the user character.\
"""

    FINISH_CONTENT = DEFAULT_FINISH_CONTENT
