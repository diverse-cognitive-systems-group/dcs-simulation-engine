# ruff: noqa: D100, E501


class ExploreV2:
    """String constants for the new-style Explore game (Python format strings, not Jinja2)."""

    HELP_CONTENT = """\
##### Objective
There is no predefined objective or task in this game. You can just engage freely with the other character.

##### Rules
The only rules in this simulation are to stay within your character's abilities and make sure your inputs describe actions
your character takes.
- For example, if your character is non-verbal, you can type actions like "I gesture towards the door" or "I point at the object".

##### Commands
Type '/help' to see this message again.
Type '/feedback' followed by your comments to submit feedback about the game. (Eg. '/feedback This reply doesn't make sense because...')
Type '/exit' or '/quit' to leave the game.
Type '/abilities' to see your character's abilities.\
"""

    ABILITIES_CONTENT = """\
**User Character:** {pc_hid} ({pc_short_description})
**Simulator Character:** {npc_hid} ({npc_short_description})

##### User Character Abilities
{pc_abilities}

##### Simulator Character Abilities
{npc_abilities}\
"""

    ENTER_CONTENT = """\
*Welcome, in this game there is no predefined objective or task. You can just engage freely with the other character by describing what actions your character takes.*

- You are playing as: {pc_hid} ({pc_short_description})
- The simulator is playing as: {npc_hid} ({npc_short_description})

**Remember** if you need help at any time, just type '/help'.\
"""

    EXIT_CONTENT = "Game exited with reason: {exit_reason}"


class ForesightV2:
    """String constants for the new-style Foresight game (Python format strings, not Jinja2)."""

    ENTER_CONTENT = """\
*Welcome, in this game you take on the role of a character whose aim is to understand the other \
character well enough to predict their actions.*

Engage with the other character using your abilities. When you feel ready, include a prediction \
alongside your action — for example: "I wave my hand and predict they will wave back."

- You are playing as: {pc_hid} ({pc_short_description})

Type '/help' for instructions. Type '/complete' when you are done to submit your notes.\
"""

    HELP_CONTENT = """\
##### Objective
Interact with the other character and learn to predict their responses.

##### Actions and Predictions
Describe an action your character takes (and optionally include a prediction about the other character's response).
- Eg. "I look around the room and walk to the door."
- Eg. "I look around the room and walk to the door, and I predict they will follow me."

##### Commands
Type '/help' to see this message again.
Type '/feedback' followed by your comments to submit feedback about the game.
Type '/complete' to end the game and submit your prediction notes.
Type '/exit' or '/quit' to leave without submitting notes.\
"""

    COMPLETE_QUESTION = """\
Thanks for playing! Before you go, please share any notes about your predictions:

Were any predictions particularly interesting or challenging? Describe in a few sentences \
(or type 'none' to skip).\
"""

    ADDITIONAL_VALIDATOR_RULES = """\
- ALLOW PREDICTIONS: The user's input IS ALLOWED to include a prediction about what the \
other character's response will be. For example, "I wave my hand and predict they will wave back."\
"""

    ADDITIONAL_UPDATER_RULES = """\
- IGNORE PREDICTIONS:
The user's input MAY include a prediction about what the simulator character's response will be. \
IGNORE ANY PREDICTIONS ENTIRELY. DO NOT ADJUDICATE THEM OR RESPOND TO THEM IN ANY WAY. \
ONLY RESPOND TO THE USER'S ACTION.\
"""


class InferIntentV2:
    """String constants for the new-style Infer Intent game (Python format strings, not Jinja2)."""

    ENTER_CONTENT = """\
*Welcome, in this game you interact with an unknown character and try to infer their goal or intention.*

Engage with the other character using your abilities. When you think you understand their goal, \
type '/guess' to submit your inference.

- You are playing as: {pc_hid} ({pc_short_description})

Type '/help' for instructions. Type '/abilities' to see your character's abilities.\
"""

    HELP_CONTENT = """\
##### Objective
Interact with the other character and figure out their goal or intention. \
When you feel confident, type '/guess' to submit your inference.

##### Rules
Describe an action that makes sense in the context of the scene and uses your character's abilities.
- For example, if your character can see and move, you might say "I look around the room and walk to the door."

##### Commands
Type '/help' to see this message again.
Type '/feedback' followed by your comments to submit feedback about the game.
Type '/abilities' to see your character's abilities.
Type '/guess' when you think you understand the NPC's goal to end the interaction and submit your inference.
Type '/exit' or '/quit' to leave the game without submitting an inference.\
"""

    ABILITIES_CONTENT = """\
##### Your Character Abilities
{pc_abilities}\
"""

    GOAL_INFERENCE_QUESTION = """\
What do you think the NPC's goal or intention was during this interaction? \
Please describe in a few sentences.\
"""

    OTHER_FEEDBACK_QUESTION = "Do you have any other feedback about this experience?"

    ADDITIONAL_UPDATER_RULES = """\
- Goal Aligned Response: The simulator character's response should be in-line with a specific \
goal or intention that s/he/it/they are trying to communicate with the user character.\
"""


class GoalHorizonV2:
    """String constants for the new-style Goal Horizon game (Python format strings, not Jinja2)."""

    ENTER_CONTENT = """\
*Welcome, in this game you interact with an unknown character across multiple scenes to understand the bounds and structure of their goals.*

Engage with the other character using your abilities. There is no predefined objective — explore freely.

- You are playing as: {pc_hid} ({pc_short_description})
- The simulator is playing as: {npc_hid} ({npc_short_description})

Type '/help' for instructions. Type '/abilities' to see your character's abilities.\
"""

    HELP_CONTENT = """\
##### Objective
Interact with the other character across multiple scenes to understand the scope and structure of their goals.

##### Rules
Describe an action that makes sense in the context of the scene and uses your character's abilities.
- For example, if your character can see and move, you might say "I look around the room and walk to the door."

##### Commands
Type '/help' to see this message again.
Type '/feedback' followed by your comments to submit feedback about the game.
Type '/abilities' to see your character's abilities.
Type '/exit' or '/quit' to leave the game.\
"""

    ABILITIES_CONTENT = """\
**User Character:** {pc_hid} ({pc_short_description})
**Simulator Character:** {npc_hid} ({npc_short_description})

##### User Character Abilities
{pc_abilities}

##### Simulator Character Abilities
{npc_abilities}\
"""


class Explore:
    """String constants for the Explore game."""

    HELP_CONTENT = """\
    ##### Objective
    There is no predefined objective or task in this game. You can just engage freely with the other character.

    ##### Rules
    The only rules in this simulation are to stay within your character's abilities and make sure
    your inputs describe actions your character takes.
    - For example, if your character is non-verbal, you can type actions like
      "I gesture towards the door" or "I point at the object".

    ##### Commands
    Type '/help' to see this message again.
    Type '/feedback' followed by your comments to submit feedback about the game.
    (Eg. '/feedback This reply doesn't make sense because...')
    Type '/guess' when you think you understand the NPC's goal to end the interaction
    and submit your inference.
    Type '/exit' or '/quit' to leave the game without submitting an inference.
    Type '/abilities' to see your character's abilities.\
    """

    ABILITIES_CONTENT = """\
    **User Character:** {{ pc.hid }} ({{ pc.short_description }})
    **Simulator Character:** {{ npc.hid }} ({{ npc.short_description }})

    ##### User Character Abilities
    {{ pc.abilities }}

    ##### Simulator Character Abilities
    {{ npc.abilities }}\
    """

    ENTER_CONTENT = """\
    *Welcome, in this game there is no predefined objective or task. You can just engage freely
    with the other character by describing what actions your character takes.*

    - You are playing as: {{ pc.hid }} ({{ pc.short_description }})
    - The simulator is playing as: {{ npc.hid }} ({{ npc.short_description }})

    **Remember** if you need help at any time, just type '/help'.\
    """

    EXIT_CONTENT = "Game exited with reason: {{ exit_reason }}"

    COMPLETE_CONTENT = "# Game Complete\nThe game has completed after {{ len(history) }} total turns."

    ERROR_IN_LIFECYCLE = "An unhandled lifecycle status was reached: {{ lifecycle }}"


class Foresight:
    """String constants for the Foresight game."""

    HELP_CONTENT = """\
    Describe an action...(and optionally include a prediction about what the other character's response will be).
    - Eg. If your character can see and move you might say "I look around the room and walk to the door."
    - Eg. If you want to include a prediction you might say
      "I look around the room and walk to the door, and I predict they will follow me."

    User '/complete' to end the game and submit your predictions.

    Here is are reminder of your character's abilities:
    {{ pc.abilities }}\
    """

    ENTER_CONTENT = """\
    Welcome, in this game, you take on the role of a character whose aim is to understand the other
    character well enough to be able to predict their actions before they make them. Engage with the
    other character using your abilities and if/when you feel like you know the character well enough
    to predict their response well, state your prediction.

    For example, you might say "I wave my hand." Or "I wave my hand and predict they will wave back."

    Your character ({{ pc.short_description }}) has the following abilities:
    {{ pc.abilities }}\
    """

    EXIT_CONTENT = "Game exited with reason: {{ exit_reason }}"

    COMPLETE_CONTENT = "Game Completed after {{ len(history) }} turns."

    ERROR_IN_LIFECYCLE = "An unhandled lifecycle status was reached: {{ lifecycle }}"

    ADDITIONAL_VALIDATOR_RULES = """\
    - ALLOW PREDICTIONS: The user's input IS ALLOWED to include a prediction about what the \
    other character's response will be. For example, "I wave my hand and predict they will wave back."\
    """

    ADDITIONAL_UPDATER_RULES = """\
    - IGNORE PREDICTIONS:
    The user's input MAY include a prediction about what the simulator character's response will be. \
    IGNORE ANY PREDICTIONS ENTIRELY. DO NOT ADJUDICATE THEM OR RESPOND TO THEM IN ANY WAY. \
    ONLY RESPONSE TO THE USERS ACTION.\
    """


class InferIntent:
    """String constants for the Infer Intent game."""

    HELP_CONTENT = """\
    ##### Objective
    Your task in this simulation is use your abilities to interact with another character and figure
    the intention or goal they are trying to communicate. When you feel like you understand their
    goal, type "/guess" to end the interaction and submit your inference.

    ##### Rules
    Describe an action that makes sense in the context of the scene and uses your character's abilities.
    - For example, if your character can see and move in a human-like way, you might say
      "I look around the room and walk to the door."

    ##### Commands
    Type '/help' to see this message again.
    Type '/guess' when you think you understand the NPC's goal to end the interaction and submit your inference.
    Type '/exit' or '/quit' to leave the game without submitting an inference.
    Type '/abilities' to see your character's abilities.\
    """

    ABILITIES_CONTENT = """\
    ##### User Character Abilities
    {{ pc.abilities }}\
    """

    ENTER_CONTENT = """\
    Welcome, in this game, you take on the role of a character whose aim is to use your abilities
    to interact with another character and figure the intention or goal they are trying to
    communicate. When you feel like you understand their goal, type "/guess" to end the interaction
    and submit your inference.

    Your character is: {{ pc.short_description }} {% if pc.hid != "human-normative" %}
    Abilities:
    {{ pc.abilities }}{% endif %}

    For help at any time, type "/help"\
    """

    EXIT_CONTENT = "Game exited with reason: {{ exit_reason }}"

    COMPLETE_CONTENT = "Game Completed after {{ len(history) }} turns."

    ERROR_IN_LIFECYCLE = "An unhandled lifecycle status was reached: {{ lifecycle }}"

    ADDITIONAL_UPDATER_RULES = """\
    - Goal Aligned Response: The simulator character's response should be in-line with a specific \
    goal or intention that s/he/it/they are trying to communicate with the user character.\
    """
