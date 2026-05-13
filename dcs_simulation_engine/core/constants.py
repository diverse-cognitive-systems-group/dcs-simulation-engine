"""Constants for core module."""

OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
PLAYER_TURN_VALIDATION_FAILED: str = "player_turn_validation_failed"
SIMULATOR_TURN_VALIDATION_RETRY_EXHAUSTED: str = "simulator_turn_validation_retry_exhausted"
SIMULATOR_RECOVERY_BUDGET_EXHAUSTED: str = "simulator_recovery_budget_exhausted"
INTERNAL_ERROR: str = "internal_error"
MODEL_PROVIDER_ERROR: str = "model_provider_error"

WELCOME_MSG: str = """
# Welcome

This is a textual scenario-based simulation engine that is part of a Georgia
Tech research project. We are studying how different cognitive systems engage
and interact to understand each other—particularly in cases where their
abilities diverge from standard normative assumptions.
"""

USAGE_MSG: str = """
# Instructions

To participate in our research, you'll need to *sign a consent form to receive
an access token*.

With a token, you can start in Benchmarking Mode, which lets us run an
run and collect anonymous data about how you engaged with the other
beings you encountered in the simulator.

Alternatively, you can play around in Demo Mode (lower fidelity) without any
data collection.
"""
