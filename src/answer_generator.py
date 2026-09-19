from __future__ import annotations

import json
import re
from typing import Any

from .data_service import HealthDataRepository
from .llm_client import LLMClient
from .models import AnswerCard, QueryPlan
from .resources import GENERAL_DIRECTORY, resources_for
from .text_utils import title_case


class AnswerGenerator:
    def __init__(self, repository: HealthDataRepository, llm: LLMClient):
        self.repository = repository
        self.llm = llm

    @staticmethod
    def _chart_axis_label(indicator: str, title: str, unit: str) -> str:
        """Return a public-facing axis label that explains what the number represents."""

        labels = {
            "Life Expectancy": "Average Life Expectancy (Years)",
            "Infant Mortality": "Infant Deaths per 1,000 Live Births",
            "Poor or Fair Health": "Percent (%) of Adults Reporting Poor or Fair Health",
            "Poor Physical Health Days": "Average Poor Physical Health Days per Month",
            "Poor Mental Health Days": "Average Poor Mental Health Days per Month",
            "Adult Obesity": "Percent (%) of Adults With Obesity",
            "Diabetes Prevalence": "Percent (%) of Adults With Diabetes",
            "Adult Smoking": "Percent (%) of Adults Who Smoke",
            "Physical Inactivity": "Percent (%) of Adults Reporting No Leisure-Time Physical Activity",
            "Excessive Drinking": "Percent (%) of Adults Reporting Excessive Drinking",
            "Insufficient Sleep": "Percent (%) of Adults Getting Less Than 7 Hours of Sleep",
            "Food Insecurity": "Percent (%) of People Experiencing Food Insecurity",
            "Drug Overdose Deaths": "Drug Overdose Deaths per 100,000 People",
            "Access to Exercise Opportunities": "Percent (%) of People With Access to Exercise Opportunities",
            "Uninsured": "Percent (%) of People Under Age 65 Without Health Insurance",
            "Primary Care Physicians": "Residents per Primary Care Physician",
            "Mental Health Providers": "Residents per Mental Health Provider",
            "Preventable Hospital Stays": "Preventable Hospital Stays per 100,000 Medicare Enrollees",
            "Children in Poverty": "Percent (%) of Children Living in Poverty",
            "Unemployment": "Percent (%) of People Age 16+ Unemployed and Seeking Work",
            "Median Household Income": "Median Household Income (USD)",
            "High School Completion": "Percent (%) of Adults Age 25+ With a High School Diploma",
            "Income Inequality": "Income Ratio (80th Percentile to 20th Percentile)",
            "Severe Housing Problems": "Percent (%) of Households With Severe Housing Problems",
            "Air Pollution – Particulate Matter": "Average PM2.5 Concentration (µg/m³)",
            "Suicide Rate": "Suicide Deaths per 100,000 People",
            "Teen Birth Rate": "Births per 1,000 Females Ages 15-19",
            "Injury Deaths": "Injury Deaths per 100,000 People",
            "Broadband Access": "Percent (%) of Households With Broadband Internet",
            "Severe Housing Cost Burden": "Percent (%) of Households Spending 50%+ of Income on Housing",
        }
        if indicator in labels:
            return labels[indicator]

        normalized_unit = str(unit or "").strip()
        if normalized_unit == "%":
            return f"Percent (%) for {title_case(title)}"
        if normalized_unit:
            return title_case(normalized_unit)
        return title_case(title)

    @staticmethod
    def _measure_subject(indicator: str, title: str) -> str:
        subjects = {
            "Life Expectancy": "The average life expectancy in Nashville",
            "Infant Mortality": "Nashville's infant mortality rate",
            "Poor or Fair Health": "The share of Nashville adults reporting poor or fair health",
            "Poor Physical Health Days": "Nashville adults' average number of poor physical health days",
            "Poor Mental Health Days": "Nashville adults' average number of poor mental health days",
            "Adult Obesity": "Nashville's adult obesity rate",
            "Diabetes Prevalence": "The share of Nashville adults with diabetes",
            "Adult Smoking": "Nashville's adult smoking rate",
            "Physical Inactivity": "Nashville's physical inactivity rate",
            "Excessive Drinking": "Nashville's excessive drinking rate",
            "Insufficient Sleep": "The share of Nashville adults not getting enough sleep",
            "Food Insecurity": "Nashville's food insecurity rate",
            "Drug Overdose Deaths": "Nashville's drug overdose death rate",
            "Access to Exercise Opportunities": "The share of Nashville residents with access to exercise opportunities",
            "Uninsured": "The share of Nashville residents under age 65 without health insurance",
            "Primary Care Physicians": "Nashville's primary care physician ratio",
            "Mental Health Providers": "Nashville's mental health provider ratio",
            "Preventable Hospital Stays": "Nashville's rate of preventable hospital stays",
            "Children in Poverty": "The share of Nashville children living in poverty",
            "Unemployment": "Nashville's unemployment rate",
            "Median Household Income": "Nashville's median household income",
            "High School Completion": "Nashville's high school completion rate",
            "Income Inequality": "Nashville's income gap",
            "Severe Housing Problems": "The share of Nashville households with severe housing problems",
            "Air Pollution – Particulate Matter": "Nashville's average fine-particle air pollution level",
            "Suicide Rate": "Nashville's suicide death rate",
            "Teen Birth Rate": "Nashville's teen birth rate",
            "Injury Deaths": "Nashville's injury death rate",
            "Broadband Access": "The share of Nashville households with broadband internet",
            "Severe Housing Cost Burden": "The share of Nashville households spending at least half of their income on housing",
        }
        return subjects.get(indicator, f"Nashville's {str(title or indicator).lower()}")

    @staticmethod
    def _period_note(period: str) -> str:
        text = str(period or "").strip()
        if not text:
            return "The data period is not listed."
        years = re.findall(r"(?:19|20)\d{2}", text)
        if len(set(years)) >= 2:
            return f"Data period: {text} (one estimate summarizes the full period)."
        return f"Data year: {text}."

    def answer(self, question: str, plan: QueryPlan) -> AnswerCard:
        if plan.needs_clarification:
            return AnswerCard(
                question=question,
                intent="clarification",
                title="A Little More Detail Is Needed",
                headline="Which Health Topic Would You Like to Explore?",
                takeaway=plan.clarification,
                suggested_questions=[
                    "How does Nashville compare on adult smoking?",
                    "Are Nashvillians getting enough sleep compared with peer cities?",
                    "Why does housing affordability matter for health in Nashville?",
                ],
            )
        if plan.intent == "overview":
            return self._overview(question)
        if not plan.indicators:
            return AnswerCard(
                question=question,
                intent="clarification",
                title="A Little More Detail Is Needed",
                headline="Which Health Topic Would You Like to Explore?",
                takeaway=(
                    "Name one health issue and I will explain Nashville's latest result "
                    "and how it compares with peer communities."
                ),
            )
        if len(plan.indicators) > 1:
            return self._multi(question, plan)

        indicator = plan.indicators[0]
        if plan.intent == "trend":
            return self._trend(question, indicator, plan)
        if plan.intent == "related":
            return self._related(question, indicator)
        return self._current(question, indicator, plan)

    def _current(self, question: str, indicator: str, plan: QueryPlan) -> AnswerCard:
        facts = self.repository.current_facts(
            indicator,
            plan.requested_year,
            plan.comparison_cities,
        )
        metadata = facts.get("metadata", {})
        title = str(metadata.get("plain_language_name") or indicator)

        if not facts.get("available"):
            return AnswerCard(
                question=question,
                intent=plan.intent,
                title=title,
                category=str(metadata.get("category") or ""),
                headline="No Usable Value Was Found",
                takeaway=(
                    "This measure is not available for the requested period in the current "
                    "prototype dataset."
                ),
            )

        rank = int(facts["rank"])
        count = int(facts["city_count"])
        headline = self._comparison_headline(facts, title)
        value_relation = self._value_relation(facts)
        subject = self._measure_subject(indicator, title)
        takeaway = (
            f"{subject} is {facts['nashville_value_display']}, which is "
            f"{value_relation} the peer community average of {facts['peer_average_display']}. "
            f"{self._direction_sentence(facts)} Nashville ranks {rank} of {count} communities "
            f"and performs {facts['comparison']} the peer community average."
        )
        explanation = self._comparison_explanation(facts)

        if plan.intent == "why":
            headline = f"{title_case(title)}: Why It Matters"
            why_text = str(metadata.get("why_it_matters") or "").strip()
            if why_text:
                why_text = why_text[0].lower() + why_text[1:]
                takeaway = f"{title_case(indicator)} is important because {why_text}"
            explanation = (
                f"In the latest usable comparison, Nashville is at "
                f"{facts['nashville_value_display']} and ranks {rank} of {count}. "
                f"The peer community average is {facts['peer_average_display']}."
            )
        elif plan.intent == "extremes":
            headline = f"{facts['best_city']} Has the Strongest Result in This Comparison"
            takeaway = (
                f"The strongest result is {facts['best_value_display']} in {facts['best_city']}. "
                f"The weakest is {facts['worst_value_display']} in {facts['worst_city']}."
            )
            explanation = (
                f"Nashville is at {facts['nashville_value_display']} and ranks {rank} of {count}. "
                f"{self._direction_sentence(facts)}"
            )

        # Core comparisons stay deterministic. A language model can interpret the
        # user's question, but it is not allowed to rewrite the verified direction,
        # rank, or values. This prevents inversions such as describing 18.5% as lower
        # than a 13.8% peer average.

        related = self._related_names(metadata)
        trend = self.repository.trend_facts(
            indicator,
            plan.start_year,
            plan.end_year,
            plan.comparison_cities,
        )
        trend_data = self._trend_data(trend) if trend.get("available") else []
        period = str(facts.get("data_period") or "Not listed")
        release = facts.get("release_year")
        chart_scope = str(facts.get("comparison_scope") or "Nashville and peer communities")

        return AnswerCard(
            question=question,
            intent=plan.intent,
            title=title,
            category=str(metadata.get("category") or ""),
            headline=headline,
            takeaway=takeaway,
            definition=str(metadata.get("plain_language_definition") or ""),
            metrics=[
                {"label": "Nashville", "value": facts["nashville_value_display"]},
                {"label": "Peer Community Average", "value": facts["peer_average_display"]},
                {"label": "Nashville's Rank", "value": f"{rank} of {count}"},
            ],
            explanation=explanation,
            explanation_heading="Putting This Result in Context",
            why_it_matters=str(metadata.get("why_it_matters") or ""),
            action_items=self._actions(str(metadata.get("category") or ""), title, indicator),
            action_heading="What You Can Explore Next",
            source_note=self._source(facts),
            related_indicators=related,
            suggested_questions=self._suggestions(indicator, related),
            selection_note=str(facts.get("selection_note") or ""),
            comparison_data=list(facts.get("comparison_rows") or []),
            report_trend_data=trend_data,
            chart_title=f"How Nashville and Peer Communities Compare on {title_case(title)}",
            chart_subtitle=(
                f"{chart_scope}. {self._period_note(period)} "
                f"Published in the {release} CHR&R release."
            ),
            chart_unit=self._chart_axis_label(
                indicator,
                title,
                str(facts.get("unit") or ""),
            ),
            comparison_scope=chart_scope,
            local_resources=resources_for(indicator, str(metadata.get("category") or "")),
        )

    def _trend(self, question: str, indicator: str, plan: QueryPlan) -> AnswerCard:
        trend = self.repository.trend_facts(
            indicator,
            plan.start_year,
            plan.end_year,
            plan.comparison_cities,
        )
        metadata = trend.get("metadata", {})
        title = str(metadata.get("plain_language_name") or indicator)
        current = self.repository.current_facts(
            indicator,
            plan.requested_year,
            plan.comparison_cities,
        )

        if not trend.get("available"):
            return AnswerCard(
                question=question,
                intent="trend",
                title=title,
                category=str(metadata.get("category") or ""),
                headline="There Are Not Enough Distinct Periods for a Clear Trend",
                takeaway=(
                    f"The latest available Nashville value is "
                    f"{current.get('nashville_value_display', 'not available')}."
                ),
                source_note=self._source(current) if current.get("available") else "",
                comparison_data=list(current.get("comparison_rows") or []),
                chart_title=f"How Nashville and Peer Communities Compare for {title_case(title)}",
                chart_subtitle=self._current_subtitle(current),
                chart_unit=self._chart_axis_label(
                    indicator,
                    title,
                    str(current.get("unit") or ""),
                ),
            )

        first = trend["first"]
        latest = trend["latest"]
        headline = (
            f"{title_case(title)} Has {str(trend['trend_label']).title()} in Nashville"
        )
        subject = self._measure_subject(indicator, title)
        takeaway = (
            f"{subject} moved from {first['value_display']} for {first['label']} to "
            f"{latest['value_display']} for {latest['label']}."
        )
        periods_are_ranges = any(
            len(set(re.findall(r"(?:19|20)\d{2}", str(row.get("label") or "")))) >= 2
            for row in trend.get("rows", [])
        )
        period_explanation = (
            "Each point is one estimate that summarizes the full date range shown, not a separate value for every year."
            if periods_are_ranges
            else "Each point shows the estimate for the year listed."
        )
        explanation = (
            f"The latest peer community average is {latest['peer_average_display']}. "
            f"{period_explanation}"
        )
        if trend["overlapping_periods"]:
            explanation += " Some date ranges overlap, so small changes should be read cautiously."

        # Trend statements are also built only from checked values and direction.

        related = self._related_names(metadata)
        chart = self._trend_data(trend)
        return AnswerCard(
            question=question,
            intent="trend",
            title=title,
            category=str(metadata.get("category") or ""),
            headline=headline,
            takeaway=takeaway,
            definition=str(metadata.get("plain_language_definition") or ""),
            metrics=[
                {"label": "Earlier Period", "value": first["value_display"]},
                {"label": "Latest Period", "value": latest["value_display"]},
                {"label": "Overall Direction", "value": str(trend["trend_label"]).capitalize()},
            ],
            explanation=explanation,
            explanation_heading="How to Read This Trend",
            why_it_matters=str(metadata.get("why_it_matters") or ""),
            action_items=self._actions(str(metadata.get("category") or ""), title, indicator),
            action_heading="What You Can Explore Next",
            source_note=(
                f"County Health Rankings & Roadmaps. Data periods shown: {first['label']} "
                f"through {latest['label']}."
            ),
            related_indicators=related,
            suggested_questions=self._suggestions(indicator, related),
            chart_data=chart,
            report_trend_data=chart,
            comparison_data=list(current.get("comparison_rows") or []),
            chart_title=f"How {title_case(title)} Has Changed in Nashville",
            chart_subtitle=(
                f"Data periods: {first['label']} through {latest['label']}. "
                f"{period_explanation} The dotted line is the peer community average."
            ),
            chart_unit=self._chart_axis_label(
                indicator,
                title,
                str(latest.get("unit") or ""),
            ),
            comparison_scope=str(current.get("comparison_scope") or ""),
            local_resources=resources_for(indicator, str(metadata.get("category") or "")),
        )

    def _multi(self, question: str, plan: QueryPlan) -> AnswerCard:
        facts = [
            self.repository.current_facts(indicator, plan.requested_year, plan.comparison_cities)
            for indicator in plan.indicators
        ]
        usable = [fact for fact in facts if fact.get("available")]
        if not usable:
            return AnswerCard(
                question=question,
                intent=plan.intent,
                title="Nashville Health Comparison",
                headline="No Usable Values Were Found",
                takeaway=(
                    "The selected measures are not available for the requested period in the "
                    "current prototype dataset."
                ),
            )

        highlights = [
            {
                "title": str(
                    fact.get("metadata", {}).get("plain_language_name") or fact["indicator"]
                ),
                "value": fact["nashville_value_display"],
                "detail": (
                    f"Rank {fact['rank']} of {fact['city_count']}; "
                    f"{fact['comparison']} the peer community average."
                ),
            }
            for fact in usable
        ]
        rank_data = [
            {
                "Measure": str(
                    fact.get("metadata", {}).get("plain_language_name") or fact["indicator"]
                ),
                "Rank": int(fact["rank"]),
                "City count": int(fact["city_count"]),
                "Value display": fact["nashville_value_display"],
            }
            for fact in usable
        ]
        best = min(usable, key=lambda fact: fact["rank"])
        weakest = max(usable, key=lambda fact: fact["rank"])
        takeaway = (
            f"Among these measures, Nashville's strongest relative result is "
            f"{str(best.get('metadata', {}).get('plain_language_name') or best['indicator']).lower()} "
            f"at rank {best['rank']} of {best['city_count']}. Its weakest is "
            f"{str(weakest.get('metadata', {}).get('plain_language_name') or weakest['indicator']).lower()} "
            f"at rank {weakest['rank']} of {weakest['city_count']}."
        )
        explanation = (
            "The measures use different units, so comparing their raw numbers would be misleading. "
            "The rank chart puts them on the same scale: rank 1 is the strongest result and the "
            "highest rank is the weakest among the same comparison communities."
        )
        scope = str(usable[0].get("comparison_scope") or "Nashville and peer communities")

        return AnswerCard(
            question=question,
            intent=plan.intent,
            title="Nashville Across Selected Health Measures",
            headline="Nashville's Standing Varies Across the Measures You Selected",
            takeaway=takeaway,
            explanation=explanation,
            explanation_heading="How to Read This Comparison",
            action_items=self._actions(
                "Health outcomes / well-being",
                "Nashville's selected health measures",
                "",
            ),
            action_heading="What You Can Explore Next",
            source_note=(
                "Latest usable County Health Rankings & Roadmaps value for each selected measure; "
                "the available date ranges may differ by measure."
            ),
            highlights=highlights,
            highlights_heading="Selected Measures",
            rank_data=rank_data,
            chart_title="Where Nashville Ranks Across the Selected Health Measures",
            chart_subtitle=(
                f"{scope}. Rank 1 is strongest; higher rank numbers indicate weaker results."
            ),
            comparison_scope=scope,
            suggested_questions=[
                f"How has {indicator.lower()} changed over time?"
                for indicator in plan.indicators[:3]
            ],
            local_resources=[dict(GENERAL_DIRECTORY)],
        )

    def _related(self, question: str, indicator: str) -> AnswerCard:
        metadata = self.repository.metadata_for(indicator)
        facts = self.repository.related_facts(indicator)
        highlights: list[dict[str, str]] = []
        for fact in facts:
            if fact.get("available"):
                highlights.append(
                    {
                        "title": str(
                            fact.get("metadata", {}).get("plain_language_name")
                            or fact["indicator"]
                        ),
                        "value": fact["nashville_value_display"],
                        "detail": (
                            f"Rank {fact['rank']} of {fact['city_count']}; "
                            f"{fact['comparison']} the peer community average."
                        ),
                    }
                )
        related = [fact["indicator"] for fact in facts if fact.get("available")]
        title = str(metadata.get("plain_language_name") or indicator)
        return AnswerCard(
            question=question,
            intent="related",
            title=title,
            category=str(metadata.get("category") or ""),
            headline=f"Three Measures That Add Context to {title_case(title)}",
            takeaway=(
                "These measures can be explored together, but the data alone do not prove that "
                "one causes another."
            ),
            definition=str(metadata.get("plain_language_definition") or ""),
            explanation=(
                "Looking across related measures can show whether a health issue appears alongside "
                "differences in access, behavior, or social and economic conditions."
            ),
            explanation_heading="Why Look at These Measures Together?",
            why_it_matters=str(metadata.get("why_it_matters") or ""),
            action_items=self._actions(str(metadata.get("category") or ""), title, indicator),
            action_heading="What You Can Explore Next",
            source_note="Latest available County Health Rankings & Roadmaps values.",
            related_indicators=related,
            suggested_questions=[
                f"How does Nashville compare on {name}?" for name in related[:3]
            ],
            highlights=highlights,
            highlights_heading="Related Measures to Explore",
            local_resources=resources_for(indicator, str(metadata.get("category") or "")),
        )

    def _overview(self, question: str) -> AnswerCard:
        overview = self.repository.overview_facts()
        if not overview.get("available"):
            return AnswerCard(
                question=question,
                intent="overview",
                title="Nashville Health at a Glance",
                headline="The Overview Could Not Be Calculated",
                takeaway="Too few current peer-community comparisons were available.",
            )

        challenges = overview["challenges"]
        strengths = overview["strengths"]
        highlights = [
            {
                "title": str(
                    fact.get("metadata", {}).get("plain_language_name") or fact["indicator"]
                ),
                "value": fact["nashville_value_display"],
                "detail": f"Rank {fact['rank']} of {fact['city_count']} communities.",
            }
            for fact in challenges[:3]
        ]
        combined = list(dict.fromkeys([fact["indicator"] for fact in [*challenges, *strengths]]))
        facts_by_indicator = {fact["indicator"]: fact for fact in [*challenges, *strengths]}
        rank_data = [
            {
                "Measure": str(
                    facts_by_indicator[name].get("metadata", {}).get("plain_language_name")
                    or name
                ),
                "Rank": int(facts_by_indicator[name]["rank"]),
                "City count": int(facts_by_indicator[name]["city_count"]),
                "Value display": facts_by_indicator[name]["nashville_value_display"],
            }
            for name in combined[:7]
        ]

        headline = "Several Measures Deserve a Closer Look Compared With Peer Communities"
        takeaway = (
            "The clearest challenges in the latest usable data are "
            + ", ".join(
                str(
                    fact.get("metadata", {}).get("plain_language_name") or fact["indicator"]
                ).lower()
                for fact in challenges[:3]
            )
            + "."
        )
        explanation = (
            "Nashville's strongest relative results include "
            + ", ".join(
                str(
                    fact.get("metadata", {}).get("plain_language_name") or fact["indicator"]
                ).lower()
                for fact in strengths[:2]
            )
            + ". The chart compares ranks rather than raw values because the measures use "
            "different units."
        )

        # The overview remains deterministic so the ranking interpretation cannot
        # be altered by a generative rewrite.

        return AnswerCard(
            question=question,
            intent="overview",
            title="Nashville Health at a Glance",
            headline=headline,
            takeaway=takeaway,
            explanation=explanation,
            explanation_heading="How to Read This Overview",
            action_items=self._actions(
                "Health outcomes / well-being",
                "Nashville's health priorities",
                "",
            ),
            action_heading="What You Can Explore Next",
            source_note=(
                "Latest usable County Health Rankings & Roadmaps value for each measure; "
                "the available date ranges vary by measure."
            ),
            highlights=highlights,
            highlights_heading="Priority Areas to Explore",
            rank_data=rank_data,
            chart_title="Where Nashville Ranks Across Key Health Measures",
            chart_subtitle=(
                "Rank 1 is strongest; higher rank numbers indicate weaker results among the "
                "same nine communities. Each measure uses its latest usable data period."
            ),
            suggested_questions=[
                f"Why does {challenges[0]['indicator'].lower()} matter?",
                f"How has {challenges[1]['indicator'].lower()} changed over time?",
                f"What is related to {challenges[2]['indicator'].lower()}?",
            ],
            local_resources=[dict(GENERAL_DIRECTORY)],
        )

    @staticmethod
    def _comparison_headline(facts: dict[str, Any], title: str) -> str:
        rank = facts["rank"]
        count = facts["city_count"]
        measure = title_case(title)
        if rank == 1:
            return f"Nashville Has the Strongest Result for {measure}"
        if rank == count:
            return f"Nashville Has the Weakest Result for {measure}"
        if rank <= max(2, count // 3):
            return f"Nashville Performs Better Than Most Peers on {measure}"
        if rank > count * 2 / 3:
            return f"Nashville Performs Worse Than Most Peers on {measure}"

        comparison = str(facts.get("comparison") or "").lower()
        gap = abs(float(facts.get("percent_difference") or 0))
        qualifier = "Slightly " if 0.5 <= gap < 10 else ""
        if comparison == "better than":
            return f"Nashville Is {qualifier}Better Than the Peer Average on {measure}"
        if comparison == "worse than":
            return f"Nashville Is {qualifier}Worse Than the Peer Average on {measure}"
        return f"Nashville Is Close to the Peer Average on {measure}"

    @staticmethod
    def _direction_sentence(facts: dict[str, Any]) -> str:
        return (
            "For this measure, higher values are considered stronger."
            if facts.get("higher_is_better")
            else "For this measure, lower values are considered stronger."
        )

    @staticmethod
    def _value_relation(facts: dict[str, Any]) -> str:
        """Describe the raw value gap without confusing it with performance."""

        difference = facts.get("difference")
        if difference is None or abs(float(difference)) < 1e-12:
            return "about the same as"
        return "higher than" if float(difference) > 0 else "lower than"

    def _comparison_explanation(self, facts: dict[str, Any]) -> str:
        rank = int(facts["rank"])
        count = int(facts["city_count"])
        percent = facts.get("percent_difference")

        if percent is None or abs(float(percent)) < 0.5:
            gap = "Nashville is very close to the peer community average."
        else:
            direction = "higher" if float(percent) > 0 else "lower"
            gap = (
                f"Nashville's value is about {abs(float(percent)):.0f}% {direction} than the "
                "peer community average."
            )

        if rank == 1:
            standing = f"Nashville has the strongest result among the {count} communities compared."
        elif rank == count:
            standing = f"Nashville has the weakest result among the {count} communities compared."
        else:
            stronger = rank - 1
            weaker = count - rank
            standing = (
                f"{stronger} {'community has' if stronger == 1 else 'communities have'} a stronger result, "
                f"and {weaker} {'community has' if weaker == 1 else 'communities have'} a weaker result."
            )
        return f"{gap} {standing} {self._direction_sentence(facts)}"


    def _source(self, facts: dict[str, Any]) -> str:
        period = str(facts.get("data_period") or "").strip()
        release = facts.get("release_year")
        period_note = self._period_note(period)
        return f"County Health Rankings & Roadmaps. {period_note} Published in the {release} CHR&R release."

    def _current_subtitle(self, facts: dict[str, Any]) -> str:
        if not facts or not facts.get("available"):
            return "Latest usable peer-community comparison."
        period = str(facts.get("data_period") or "")
        return (
            f"{facts.get('comparison_scope', 'Nashville and peer communities')}. "
            f"{self._period_note(period)} Published in the {facts.get('release_year')} CHR&R release."
        )

    @staticmethod
    def _related_names(metadata: dict[str, Any]) -> list[str]:
        return [
            name
            for name in (
                str(metadata.get("related_indicator_1") or ""),
                str(metadata.get("related_indicator_2") or ""),
                str(metadata.get("related_indicator_3") or ""),
            )
            if name
        ]

    @staticmethod
    def _suggestions(indicator: str, related: list[str]) -> list[str]:
        return (
            [f"How has {indicator.lower()} changed over time in Nashville?"]
            + [f"How does Nashville compare on {name}?" for name in related[:2]]
        )[:3]

    @staticmethod
    def _trend_data(trend: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "Period": row["label"],
                "Period end": row["end_year"],
                "Nashville": row["value"],
                "Peer average": row["peer_average"],
                "Release year": row["release_year"],
            }
            for row in trend.get("rows", [])
        ]

    @staticmethod
    def _actions(category: str, topic: str, indicator: str) -> list[str]:
        indicator_actions: dict[str, list[str]] = {
            "Adult Smoking": [
                "Help residents find free quit support, and make sure outreach reaches communities with the highest smoking rates.",
                "Look at related barriers such as stress, mental health, insurance, and access to care.",
                "Track smoking rates and use of quit-support services as new data become available.",
            ],
            "Adult Obesity": [
                "Look at access to affordable food, safe places to be active, transportation, and diabetes prevention.",
                "Ask residents which barriers make healthy eating or regular activity difficult.",
                "Work with parks, schools, clinics, and community groups, then track whether rates improve.",
            ],
            "Physical Inactivity": [
                "Look at whether residents have safe, affordable, and nearby places to walk, exercise, or join recreation programs.",
                "Ask residents what makes regular activity difficult, such as cost, time, transportation, or safety.",
                "Track physical activity together with obesity, diabetes, and access to exercise opportunities.",
            ],
            "Food Insecurity": [
                "Compare food insecurity with pantry locations, transportation, hours, and access to food-support programs.",
                "Ask residents which barriers matter most: cost, location, hours, eligibility, or awareness.",
                "Track food insecurity together with housing costs and child poverty.",
            ],
            "Poor Mental Health Days": [
                "Look at access to counseling, wait times, insurance, transportation, and social support.",
                "Ask residents where they face the biggest barriers to getting help early.",
                "Track mental health together with housing, income, sleep, and overdose measures.",
            ],
            "Mental Health Providers": [
                "Look beyond the provider count to appointment wait times, location, insurance acceptance, and language access.",
                "Ask residents and care partners where referrals or follow-up care are breaking down.",
                "Track provider access together with poor mental health days, suicide deaths, and overdose deaths.",
            ],
            "Drug Overdose Deaths": [
                "Review access to treatment, naloxone, recovery support, transportation, and follow-up care.",
                "Ask residents and service providers where people are most likely to lose contact with support.",
                "Track overdose deaths together with mental health and injury measures.",
            ],
            "Severe Housing Cost Burden": [
                "Look at rent, income, eviction risk, transportation costs, and access to housing support by neighborhood.",
                "Ask residents and housing partners which supports are hardest to find or use.",
                "Track housing costs together with food insecurity, child poverty, and mental health.",
            ],
            "Severe Housing Problems": [
                "Use neighborhood data to see where crowding, high costs, plumbing problems, or kitchen problems are most common.",
                "Connect residents with repair, rental, utility, and housing-support programs that fit the problem.",
                "Track housing conditions together with income, food access, and health measures.",
            ],
            "Uninsured": [
                "Look for neighborhoods where residents may need help enrolling in coverage or finding affordable care.",
                "Review barriers such as cost, transportation, language, and clinic availability.",
                "Track insurance coverage together with primary care access and preventable hospital stays.",
            ],
            "Primary Care Physicians": [
                "Look at where clinics are located, how long appointments take to get, and which insurance plans are accepted.",
                "Ask residents where routine care is hardest to reach or continue.",
                "Track primary care access together with preventable hospital stays and chronic health conditions.",
            ],
            "Preventable Hospital Stays": [
                "Identify which health problems and communities account for the most hospital stays that may have been avoided.",
                "Look at primary care, insurance, transportation, medication access, and follow-up care.",
                "Track hospital stays as access-to-care efforts change.",
            ],
            "Broadband Access": [
                "Look at which neighborhoods lack reliable or affordable internet for telehealth, school, work, and public services.",
                "Ask residents whether cost, equipment, reliability, or digital skills are the largest barriers.",
                "Track broadband access together with income, education, and health-care access.",
            ],
            "Access to Exercise Opportunities": [
                "Map parks, trails, community centers, and transit routes to see where exercise options are limited.",
                "Check whether facilities are affordable, safe, accessible, and open when residents can use them.",
                "Track access together with physical inactivity and related health outcomes.",
            ],
        }
        if indicator in indicator_actions:
            return indicator_actions[indicator]

        topic_lower = str(topic or indicator).lower()
        return [
            f"Look at related health, care, housing, income, and community conditions before treating {topic_lower} as a one-cause problem.",
            "Use data broken down by neighborhood, age, race, income, or other groups when available to see who may need the most support.",
            "Share the finding with residents and local partners, choose a practical next step, and track the measure as new data are released.",
        ]


    def _rewrite_current(
        self,
        question: str,
        facts: dict[str, Any],
        metadata: dict[str, Any],
        intent: str,
    ) -> dict[str, str] | None:
        if not self.llm.available:
            return None
        system = (
            "Use only the verified facts. Write for community members with no data background. "
            "Do not add statistics, causes, diagnoses, or policy claims. Use short plain sentences. "
            "The explanation must directly explain the peer-community average, the rank, and whether "
            "higher or lower values are stronger. Do not use the phrase 'comparison average'. Return "
            "JSON only with headline, takeaway, and explanation."
        )
        raw = self.llm.chat(
            system=system,
            user=json.dumps(
                {
                    "question": question,
                    "intent": intent,
                    "indicator": facts["indicator"],
                    "definition": metadata.get("plain_language_definition"),
                    "nashville": facts["nashville_value_display"],
                    "peer_community_average": facts["peer_average_display"],
                    "rank": f"{facts['rank']} of {facts['city_count']}",
                    "comparison": facts["comparison"],
                    "higher_is_better": facts.get("higher_is_better"),
                    "best": facts["best_city"],
                    "worst": facts["worst_city"],
                    "period": facts["data_period"],
                }
            ),
            json_mode=True,
            temperature=0.2,
        )
        return self._parse(raw)

    def _rewrite_trend(
        self,
        question: str,
        trend: dict[str, Any],
        metadata: dict[str, Any],
    ) -> dict[str, str] | None:
        if not self.llm.available:
            return None
        raw = self.llm.chat(
            system=(
                "Use only the supplied facts. Write a plain-language trend summary. Do not call "
                "overlapping periods independent annual observations. Explain the first and latest "
                "periods and the latest peer-community average. Return JSON only with headline, "
                "takeaway, and explanation."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "indicator": trend["indicator"],
                    "trend": trend["trend_label"],
                    "first": trend["first"],
                    "latest": trend["latest"],
                    "overlap": trend["overlapping_periods"],
                    "definition": metadata.get("plain_language_definition"),
                }
            ),
            json_mode=True,
            temperature=0.2,
        )
        return self._parse(raw)

    def _rewrite_overview(
        self,
        question: str,
        challenges: list[dict[str, Any]],
        strengths: list[dict[str, Any]],
    ) -> dict[str, str] | None:
        if not self.llm.available:
            return None

        def compact(items: list[dict[str, Any]]) -> list[dict[str, str]]:
            return [
                {
                    "indicator": item["indicator"],
                    "value": item["nashville_value_display"],
                    "rank": f"{item['rank']} of {item['city_count']}",
                }
                for item in items
            ]

        raw = self.llm.chat(
            system=(
                "Write a short neutral Nashville public-health overview using only the supplied "
                "rankings and values. Explain which measures are relatively weaker and which are "
                "stronger. Do not imply causation. Return JSON only with headline, takeaway, and "
                "explanation."
            ),
            user=json.dumps(
                {
                    "question": question,
                    "challenges": compact(challenges),
                    "strengths": compact(strengths),
                }
            ),
            json_mode=True,
            temperature=0.2,
        )
        return self._parse(raw)

    @staticmethod
    def _is_useful_explanation(value: str) -> bool:
        text = str(value or "").strip()
        return len(text) >= 65 and bool(re.search(r"\d", text))

    @staticmethod
    def _parse(raw: str | None) -> dict[str, str] | None:
        if not raw:
            return None
        text = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.I).strip()
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                return None
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
        if not isinstance(payload, dict):
            return None
        return {
            key: str(payload.get(key) or "").strip()
            for key in ("headline", "takeaway", "explanation")
        }
