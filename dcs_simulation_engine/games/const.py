# ruff: noqa: D100, E501


class Explore:
    """String constants for the new-style Explore game (Python format strings, not Jinja2)."""

    HELP_CONTENT = """\
##### Objective
There is no predefined objective or task in this game. You can just engage freely with the other character.

##### Rules
The only rules in this simulation are to stay within your character's abilities and make sure your inputs describe actions
your character takes.
- For example, if your character is non-verbal, you can type actions like "I gesture towards the door" or "I point at the object".

##### Commands
Type `/help` to see this message again.
Type `/exit` to leave the game.
Type `/abilities` to see your character's abilities.\
"""

    ABILITIES_CONTENT = """\
### User Character
{pc_hid} ({pc_short_description})

### Simulator Character
{npc_hid} ({npc_short_description})

## User Character Abilities
{pc_abilities}

## Simulator Character Abilities
{npc_abilities}\
"""

    ENTER_CONTENT = """\
*Welcome, in this game there is no predefined objective or task. You can just engage freely with the other character by describing what actions your character takes.*

- You are playing as: {pc_hid} ({pc_short_description})
- The simulator is playing as: {npc_hid} ({npc_short_description})

**Remember** if you need help at any time, just type `/help`.\
"""

    EXIT_CONTENT = "Game exited with reason: {exit_reason}"


class Foresight:
    """String constants for the new-style Foresight game (Python format strings, not Jinja2)."""

    ENTER_CONTENT = """\
*Welcome, in this game you take on the role of a character whose aim is to understand the other character well enough to predict their actions.*

Engage with the other character using your abilities. When you want to record a prediction, type `/predict-next` to say what you think the simulator character will do next.

- You are playing as: {pc_hid} ({pc_short_description})
- **Goal:** Make up to **{max_predictions}** predictions. At least **{min_predictions}** prediction is required to complete the session.
- The game ends automatically after {max_predictions} predictions, or you can type `/exit` to leave early.

Type `/help` for instructions. Type `/predict-next` whenever you want to log another prediction.\
"""

    HELP_CONTENT = """\
##### Objective
Interact with the other character and learn to predict their next action. Make at least 1 prediction to complete the session (up to 3 total).

##### Actions
Describe an action your character takes.
- Eg. "I look around the room and walk to the door."

##### Predictions
Use `/predict-next` whenever you want to record what you think the simulator character will do next.
- Eg. `/predict-next I think they will follow me to the door.`

##### Commands
Type `/help` to see this message again.
Type `/predict-next` to record a prediction. You can also use `/predict-next <prediction>` to submit it immediately.
Type `/exit` to leave the game early.\
"""

    EXIT_CONTENT = "Game ended. {exit_note}"

    PREDICT_NEXT_QUESTION = """\
What do you predict the simulator character will do next?

Describe your prediction in a sentence or two.\
"""

    PREDICT_NEXT_CONFIRMATION = "Prediction noted. Continue interacting, or use `/predict-next` again anytime."

    ADDITIONAL_VALIDATOR_RULES = """\
- ALLOW PREDICTIONS: The user's input IS ALLOWED to include a prediction about what the other character's response will be. For example, "I wave my hand and predict they will wave back."\
"""

    ADDITIONAL_UPDATER_RULES = """\
- IGNORE PREDICTIONS:
The user's input MAY include a prediction about what the simulator character's response will be. IGNORE ANY PREDICTIONS ENTIRELY. DO NOT ADJUDICATE THEM OR RESPOND TO THEM IN ANY WAY. ONLY RESPOND TO THE USER'S ACTION.\
"""


class InferIntent:
    """String constants for the new-style Infer Intent game (Python format strings, not Jinja2)."""

    ENTER_CONTENT = """\
*Welcome, in this game you interact with an unknown character and try to infer their goal or intention.*

Engage with the other character using your abilities. When you think you understand their goal, type `/predict-intent` to submit your inference and end the game.

- You are playing as: {pc_hid} ({pc_short_description})

Type `/help` for instructions. Type `/predict-intent` when you are ready to answer.\
"""

    HELP_CONTENT = """\
##### Objective
Interact with the other character and figure out their goal or intention. When you feel confident, type `/predict-intent` to submit your inference and end the game.

##### Rules
Describe an action that makes sense in the context of the scene and uses your character's abilities.
- For example, if your character can see and move, you might say "I look around the room and walk to the door."

##### Commands
Type `/help` to see this message again.
Type `/predict-intent` when you think you understand the character's intent to end the interaction and submit your inference.
Type `/exit` to leave the game without submitting an inference.\
"""

    ABILITIES_CONTENT = """\
## Your Character Abilities
{pc_abilities}\
"""

    GOAL_INFERENCE_QUESTION = """\
What do you think the character's goal or intention was during this interaction? Please describe in a few sentences.\
"""

    OTHER_FEEDBACK_QUESTION = "Do you have any other feedback about this experience?"

    ADDITIONAL_UPDATER_RULES = """\
- Goal Aligned Response: The simulator character's response should be in-line with a specific goal or intention that s/he/it/they are trying to communicate with the user character.\
"""


class GoalHorizon:
    """String constants for the new-style Goal Horizon game (Python format strings, not Jinja2)."""

    ENTER_CONTENT = """\
*Welcome, in this game you interact with an unknown character across multiple scenes to understand the bounds and structure of their goals.*

Engage with the other character using your abilities. When you think you understand the character's limits, type `/predict-capabilities` to submit your answer and end the game.

- You are playing as: {pc_hid} ({pc_short_description})
- The simulator is playing as: {npc_hid} ({npc_short_description})

Type `/help` for instructions. Type `/predict-capabilities` when you are ready to answer.\
"""

    HELP_CONTENT = """\
##### Objective
Interact with the other character across multiple scenes to understand the scope and limits of their goals and capabilities.

##### Rules
Describe an action that makes sense in the context of the scene and uses your character's abilities.
- For example, if your character can see and move, you might say "I look around the room and walk to the door."

##### Commands
Type `/help` to see this message again.
Type `/predict-capabilities` when you think you understand the character's limits. This ends the game.
Type `/exit` to leave the game.\
"""

    ABILITIES_CONTENT = """\
### User Character
{pc_hid} ({pc_short_description})

### Simulator Character
{npc_hid} ({npc_short_description})

## User Character Abilities
{pc_abilities}

## Simulator Character Abilities
{npc_abilities}\
"""

    CAPABILITY_PREDICTION_QUESTION = """\
What do you think this character's limits or capabilities are?

Describe the bounds you inferred in a few sentences.\
"""
