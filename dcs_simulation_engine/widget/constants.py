"""Constants for the widget package."""

# Tunables
LONG_RESPONSE_THRESHOLD = 25.0  # seconds before we warn it's taking longer
RESPONSE_TIMEOUT = 60.0  # hard timeout for a response
POLL_INTERVAL = 1  # how often we check for completion
MAX_INPUT_LENGTH = 1000  # max length of user input string in characters

GATE_MD = """
## Welcome

You've been given this access link to play a game as part of your participation
in our study.

### Instructions

To continue, please enter your access token below.

- If you don't have an access token, or you've lost it, you'll need to complete
  the participant consent form again.
- For privacy and security reasons, we do not store access tokens and cannot
  recover them for you.
- Please keep your token somewhere safe.

*If you need help, have questions, or encounter any issues, please email
McKinnley Workman at mworkman9@gatech.edu*
"""

USER_FRIENDLY_EXC = (
    "Whoa...something went sideways."
    " Our engineers have been alerted and are investigating.\n"
    "This session can’t continue, but we appreciate your understanding"
    " while we sort it out."
)
