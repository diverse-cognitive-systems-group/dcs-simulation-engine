class Explore:
    """String constants for the Explore game."""

    HELP_CONTENT = """\
    ##### Objective
    There is no predefined objective or task in this game. You can just engage freely with the other character.

    ##### Rules
    The only rules in this simulation are to stay within your character's abilities and make sure your inputs describe actions your character takes.
    - For example, if your character is non-verbal, you can type actions like "I gesture towards the door" or "I point at the object".

    ##### Commands
    Type '/help' to see this message again.
    Type '/feedback' followed by your comments to submit feedback about the game. (Eg. '/feedback This reply doesn't make sense because...')
    Type '/guess' when you think you understand the NPC's goal to end the interaction and submit your inference.
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
    *Welcome, in this game there is no predefined objective or task. You can just engage freely with the other character by describing what actions your character takes.*

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
    - Eg. If you want to include a prediction you might say "I look around the room and walk to the door, and I predict they will follow me."

    User '/complete' to end the game and submit your predictions.

    Here is are reminder of your character's abilities:
    {{ pc.abilities }}\
    """

    ENTER_CONTENT = """\
    Welcome, in this game, you take on the role of a character whose aim is to understand the other character well enough to be able to predict their actions before they make them. Engage with the other character using your abilities and if/when you feel like you know the character well enough to predict their response well, state your prediction.

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
    Your task in this simulation is use your abilities to interact with another character and figure the the intention or goal they are trying to communicate. When you feel like you understand their goal, type "/guess" to end the interaction and submit your inference.

    ##### Rules
    Describe an action that makes sense in the context of the scene and uses your character's abilities.
    - For example, if your character can see and move in a human-like way, you might say "I look around the room and walk to the door."

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
    Welcome, in this game, you take on the role of a character whose aim is to use your abilities to interact with another character and figure the the intention or goal they are trying to communicate. When you feel like you understand their goal, type "/guess" to end the interaction and submit your inference.

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
