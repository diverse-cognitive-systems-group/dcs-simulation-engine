"""Shared form models for experiment workflows."""

import re
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


def _normalize_identifier(value: str) -> str:
    """Normalize an identifier into lowercase snake_case."""
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text


class ExperimentFormQuestion(BaseModel):
    """Question model used by experiment forms."""

    model_config = ConfigDict(extra="forbid")

    key: str | None = None
    prompt: str
    answer_type: (
        Literal[
            "string",
            "bool",
            "single_choice",
            "multi_choice",
            "number",
            "email",
            "phone",
        ]
        | None
    ) = None
    options: list[Any] | None = None
    required: bool = False

    @model_validator(mode="after")
    def validate_question(self) -> "ExperimentFormQuestion":
        """Validate options vs answer type."""
        if self.answer_type in {"single_choice", "multi_choice"} and not self.options:
            raise ValueError("Choice questions require options.")
        if self.answer_type not in {"single_choice", "multi_choice"} and self.options is not None:
            raise ValueError("Only choice questions may declare options.")
        return self


class ExperimentForm(BaseModel):
    """Named experiment form shown before or after gameplay."""

    model_config = ConfigDict(extra="forbid")

    name: str
    before_or_after: Literal["before", "after"]
    questions: list[ExperimentFormQuestion] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_format(cls, value: str) -> str:
        """Normalize and validate form names."""
        normalized = _normalize_identifier(value)
        if not normalized:
            raise ValueError("Form names must contain letters or numbers.")
        return normalized

    @model_validator(mode="after")
    def assign_question_keys(self) -> "ExperimentForm":
        """Ensure every question has a stable key."""
        seen: set[str] = set()
        for index, question in enumerate(self.questions, start=1):
            candidate = question.key or _normalize_identifier(question.prompt.splitlines()[0])
            if not candidate:
                candidate = f"{self.name}_question_{index}"
            candidate = _normalize_identifier(candidate)
            if not candidate:
                candidate = f"{self.name}_question_{index}"
            if candidate in seen:
                candidate = f"{candidate}_{index}"
            question.key = candidate
            seen.add(candidate)
        return self
