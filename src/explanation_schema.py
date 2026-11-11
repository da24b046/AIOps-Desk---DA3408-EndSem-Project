"""Bounded explanation schema and independent failure handling."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator


class TermContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    term: str = Field(min_length=1, max_length=2000)
    contribution: float = Field(allow_inf_nan=False)
    direction: Literal["supports_prediction", "supports_alternative"]


class LinearExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    predicted_class: str = Field(min_length=1, max_length=64)
    alternative_class: str = Field(min_length=1, max_length=64)
    top_terms: list[TermContribution] = Field(max_length=5)
    intercept_contribution: float = Field(allow_inf_nan=False)
    remaining_terms_contribution: float = Field(allow_inf_nan=False)
    decision_margin: float = Field(ge=0, allow_inf_nan=False)
    margin_reconstruction_verified: StrictBool
    note: str = Field(max_length=300)

    @model_validator(mode="after")
    def check_contributions(self):
        if self.predicted_class == self.alternative_class:
            raise ValueError("Explanation classes must differ.")
        if not self.margin_reconstruction_verified:
            raise ValueError("Margin was not verified.")

        for term in self.top_terms:
            expected = (
                "supports_prediction"
                if term.contribution > 0 else "supports_alternative"
            )
            if term.contribution == 0 or term.direction != expected:
                raise ValueError("Contribution direction does not match its sign.")

        total = (
            self.intercept_contribution
            + self.remaining_terms_contribution
            + sum(term.contribution for term in self.top_terms)
        )
        if not math.isclose(
            total, self.decision_margin, rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError("Contributions do not reconstruct the margin.")
        return self


class PredictionExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["available", "unavailable"]
    category: LinearExplanation | None = None
    priority: LinearExplanation | None = None

    @model_validator(mode="after")
    def check_availability(self):
        both_present = self.category is not None and self.priority is not None
        both_absent = self.category is None and self.priority is None
        if self.status == "available" and not both_present:
            raise ValueError("Available explanations must contain both targets.")
        if self.status == "unavailable" and not both_absent:
            raise ValueError("Unavailable explanations must omit both targets.")
        return self


def parse_explanation(raw, prediction, policy):
    unavailable = {
        "status": "unavailable",
        "category": None,
        "priority": None,
    }
    if not isinstance(raw, str) or len(raw) > 20000:
        return unavailable

    try:
        explanation = PredictionExplanation.model_validate_json(raw)
        if explanation.status == "available":
            allowed = {
                "category": set(policy["category_to_team"]),
                "priority": set(policy["priority_labels"]),
            }
            for target in ("category", "priority"):
                detail = getattr(explanation, target)
                if (
                    detail.predicted_class != getattr(prediction, target)
                    or detail.predicted_class not in allowed[target]
                    or detail.alternative_class not in allowed[target]
                ):
                    raise ValueError("Explanation labels do not match prediction.")
        return explanation.model_dump()
    except (ValueError, TypeError):
        return unavailable
