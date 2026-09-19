from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

ALLOWED_INTENTS = {
    "current",
    "comparison",
    "trend",
    "extremes",
    "why",
    "related",
    "overview",
}


@dataclass(slots=True)
class QueryPlan:
    indicators: list[str] = field(default_factory=list)
    intent: str = "current"
    requested_year: int | None = None
    start_year: int | None = None
    end_year: int | None = None
    comparison_cities: list[str] = field(default_factory=list)
    needs_clarification: bool = False
    clarification: str = ""
    matched_by: str = "fallback"

    def __post_init__(self) -> None:
        if self.intent not in ALLOWED_INTENTS:
            self.intent = "current"
        self.indicators = list(
            dict.fromkeys(str(value).strip() for value in self.indicators if str(value).strip())
        )[:3]
        self.comparison_cities = list(
            dict.fromkeys(
                str(value).strip() for value in self.comparison_cities if str(value).strip()
            )
        )
        for name in ("requested_year", "start_year", "end_year"):
            value = getattr(self, name)
            if value is not None:
                try:
                    setattr(self, name, int(value))
                except (TypeError, ValueError):
                    setattr(self, name, None)
        if self.start_year and self.end_year and self.start_year > self.end_year:
            self.start_year, self.end_year = self.end_year, self.start_year

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AnswerCard:
    question: str
    intent: str
    title: str
    headline: str
    takeaway: str
    category: str = ""
    definition: str = ""
    metrics: list[dict[str, str]] = field(default_factory=list)
    explanation: str = ""
    explanation_heading: str = "Putting This Result in Context"
    why_it_matters: str = ""
    action_items: list[str] = field(default_factory=list)
    action_heading: str = "From Insight to Action"
    source_note: str = ""
    related_indicators: list[str] = field(default_factory=list)
    suggested_questions: list[str] = field(default_factory=list)
    chart_data: list[dict[str, Any]] = field(default_factory=list)
    comparison_data: list[dict[str, Any]] = field(default_factory=list)
    rank_data: list[dict[str, Any]] = field(default_factory=list)
    report_trend_data: list[dict[str, Any]] = field(default_factory=list)
    chart_title: str = ""
    chart_subtitle: str = ""
    chart_unit: str = ""
    highlights: list[dict[str, str]] = field(default_factory=list)
    highlights_heading: str = "Key Takeaways From the Data"
    selection_note: str = ""
    comparison_scope: str = ""
    local_resources: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
