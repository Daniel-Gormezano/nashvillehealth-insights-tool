from __future__ import annotations

import io
import re
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageTemplate,
    PageBreak,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from .text_utils import title_case

NAVY = colors.HexColor("#0B3D5E")
DEEP = colors.HexColor("#07354A")
BLUE = colors.HexColor("#12BDD2")
GREEN = colors.HexColor("#CAD92D")
PALE_BLUE = colors.HexColor("#EAF9FB")
PALE_GREEN = colors.HexColor("#F3F7D8")
LIGHT = colors.HexColor("#F7FAFB")
INK = colors.HexColor("#173642")
MID = colors.HexColor("#64777E")
LINE = colors.HexColor("#DCE9EC")
WHITE = colors.white


def _clean(value: Any) -> str:
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .strip()
    )


def _short(value: Any, length: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= length else text[: length - 1].rsplit(" ", 1)[0] + "..."


def _comparison_png(
    rows: list[dict[str, Any]],
    value_axis_title: str = "Measure Value",
) -> bytes | None:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return None
    frame = frame.sort_values("Rank", ascending=False)
    palette = [
        "#12BDD2" if row.get("Is Nashville") else ("#CAD92D" if row.get("Is best") else "#B7D6DE")
        for row in frame.to_dict(orient="records")
    ]
    figure, axis = plt.subplots(figsize=(9.4, 3.25), dpi=190)
    bars = axis.barh(frame["City"], frame["Value"], color=palette, edgecolor="white")
    for bar, display, is_nashville in zip(
        bars,
        frame["Value display"],
        frame["Is Nashville"],
    ):
        axis.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            "  " + str(display),
            va="center",
            fontsize=8.2,
            color="#173642",
            fontweight="bold" if bool(is_nashville) else "normal",
        )
    axis.grid(axis="x", color="#DCE9EC")
    axis.set_axisbelow(True)
    axis.set_xlabel(value_axis_title or "Measure Value", fontsize=7.8, color="#64777E", labelpad=7)
    axis.set_ylabel("Peer Community", fontsize=7.8, color="#64777E", labelpad=7)
    axis.tick_params(axis="y", labelsize=8.3, colors="#173642")
    axis.tick_params(axis="x", labelsize=7.2, colors="#64777E")
    for spine in axis.spines.values():
        spine.set_visible(False)
    max_value = float(frame["Value"].max())
    min_value = float(frame["Value"].min())
    span = max(max_value - min_value, abs(max_value) * 0.25, 1)
    axis.set_xlim(min(0, min_value), max_value + span * 0.34)
    plt.tight_layout(pad=0.8)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return buffer.getvalue()


def _trend_png(
    rows: list[dict[str, Any]],
    value_axis_title: str = "Measure Value",
) -> bytes | None:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return None
    figure, axis = plt.subplots(figsize=(9.4, 3.0), dpi=190)
    x_values = list(range(len(frame)))
    axis.plot(
        x_values,
        frame["Nashville"],
        color="#12BDD2",
        linewidth=3,
        marker="o",
        markersize=6,
        label="Nashville",
    )
    if "Peer average" in frame and frame["Peer average"].notna().any():
        axis.plot(
            x_values,
            frame["Peer average"],
            color="#CAD92D",
            linewidth=2.2,
            marker="o",
            markersize=4,
            linestyle="--",
            label="Peer community average",
        )
    axis.set_xticks(x_values)
    axis.set_xticklabels(frame["Period"], rotation=22, ha="right", fontsize=7.2, color="#64777E")
    axis.set_xlabel("Year", fontsize=7.8, color="#64777E", labelpad=7)
    axis.set_ylabel(value_axis_title or "Measure Value", fontsize=7.8, color="#64777E", labelpad=7)
    axis.grid(axis="y", color="#DCE9EC")
    axis.set_axisbelow(True)
    axis.tick_params(axis="y", labelsize=7.2, colors="#64777E")
    for spine in axis.spines.values():
        spine.set_visible(False)
    axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.14),
        frameon=False,
        fontsize=7.5,
        ncol=2,
    )
    plt.tight_layout(pad=0.9)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return buffer.getvalue()


def _rank_png(rows: list[dict[str, Any]]) -> bytes | None:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return None
    frame = frame.sort_values("Rank", ascending=False)
    colors_list = []
    for row in frame.to_dict(orient="records"):
        rank = float(row["Rank"])
        count = max(float(row["City count"]), 1)
        if rank <= max(2, count / 3):
            colors_list.append("#CAD92D")
        elif rank >= count * 2 / 3:
            colors_list.append("#12BDD2")
        else:
            colors_list.append("#B7D6DE")
    figure, axis = plt.subplots(figsize=(9.4, 3.0), dpi=190)
    bars = axis.barh(frame["Measure"], frame["Rank"], color=colors_list, edgecolor="white")
    for bar, rank, count in zip(bars, frame["Rank"], frame["City count"]):
        axis.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"  {int(rank)} of {int(count)}",
            va="center",
            fontsize=8,
            color="#173642",
            fontweight="bold",
        )
    max_count = max(int(frame["City count"].max()), 1)
    axis.set_xlim(0, max_count + 1.2)
    axis.set_xlabel("Nashville rank (1 = strongest)", fontsize=7.6, color="#64777E")
    axis.set_ylabel("Health Measure", fontsize=7.6, color="#64777E")
    axis.grid(axis="x", color="#DCE9EC")
    axis.set_axisbelow(True)
    axis.tick_params(axis="y", labelsize=8.1, colors="#173642")
    axis.tick_params(axis="x", labelsize=7.2, colors="#64777E")
    for spine in axis.spines.values():
        spine.set_visible(False)
    plt.tight_layout(pad=0.8)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", facecolor="white")
    plt.close(figure)
    return buffer.getvalue()


def _specific_takeaway(answer: dict[str, Any]) -> str:
    """Return a finding that names the measure instead of saying only 'the value'."""

    takeaway = re.sub(r"\s+", " ", str(answer.get("takeaway") or "")).strip()
    title = str(answer.get("title") or "this measure").strip()
    subject_map = {
        "Life Expectancy": "The average life expectancy in Nashville",
        "Adult Smoking": "Nashville's adult smoking rate",
        "Adult Obesity": "Nashville's adult obesity rate",
        "Physical Inactivity": "Nashville's physical inactivity rate",
        "Poor Mental Health Days": "Nashville adults' average number of poor mental health days",
        "Poor Physical Health Days": "Nashville adults' average number of poor physical health days",
        "Infant Mortality": "Nashville's infant mortality rate",
        "Food Insecurity": "Nashville's food insecurity rate",
        "Uninsured": "The share of Nashville residents under age 65 without health insurance",
        "Median Household Income": "Nashville's median household income",
    }
    subject = subject_map.get(title_case(title), f"Nashville's {title.lower()}")
    if takeaway.lower().startswith("the value moved"):
        return re.sub(r"^The value", subject, takeaway, flags=re.I)
    if takeaway.lower().startswith("nashville's value is"):
        return re.sub(r"^Nashville's value", subject, takeaway, flags=re.I)
    return takeaway or f"{subject} is summarized in this brief."


def _concise(value: Any, limit: int = 245) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept: list[str] = []
    for sentence in sentences:
        candidate = " ".join([*kept, sentence]).strip()
        if len(candidate) > limit:
            break
        kept.append(sentence)
    if kept:
        return " ".join(kept)
    return _short(text, limit)


def build_health_brief(
    messages: list[dict[str, Any]],
    logo_path: Path,
    map_path: Path | None = None,
) -> bytes:
    """Create a branded multi-page brief containing every conversation exchange."""

    buffer = io.BytesIO()
    page_width, page_height = letter
    exchanges = [message for message in messages if message.get("role") == "exchange"]
    if not exchanges:
        exchanges = [{"question": "", "answer": {}}]

    first_answer = dict(exchanges[0].get("answer") or {})
    multi_page_conversation = len(exchanges) > 1
    document_title = (
        "Your Nashville Health Conversation"
        if multi_page_conversation
        else title_case(first_answer.get("headline") or "Nashville Health Brief")
    )

    doc = BaseDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.52 * inch,
        rightMargin=0.52 * inch,
        topMargin=1.72 * inch,
        bottomMargin=0.36 * inch,
        title=_short(document_title, 120),
        author="NashvilleHealth",
    )
    first_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        page_height - doc.topMargin - doc.bottomMargin,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="first",
    )
    later_frame = Frame(
        doc.leftMargin,
        doc.bottomMargin,
        doc.width,
        page_height - 0.82 * inch - doc.bottomMargin,
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
        id="later",
    )

    styles = getSampleStyleSheet()
    kicker = ParagraphStyle(
        "kicker",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=8.4,
        textColor=BLUE,
        spaceAfter=3,
        letterSpacing=0.65,
    )
    topic_kicker = ParagraphStyle(
        "topic_kicker",
        parent=kicker,
        textColor=GREEN,
        spaceAfter=4,
    )
    topic_heading = ParagraphStyle(
        "topic_heading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=18,
        textColor=NAVY,
        spaceAfter=7,
    )
    section = ParagraphStyle(
        "section",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.2,
        leading=12,
        textColor=NAVY,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.25,
        leading=10.8,
        textColor=INK,
        spaceAfter=3,
    )
    small = ParagraphStyle(
        "small",
        parent=body,
        fontSize=6.65,
        leading=8.25,
        textColor=MID,
    )
    metric_label = ParagraphStyle(
        "metric_label",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=6.6,
        leading=7.8,
        textColor=MID,
        uppercase=True,
    )
    metric_value = ParagraphStyle(
        "metric_value",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13.5,
        leading=15,
        textColor=NAVY,
    )
    action_number = ParagraphStyle(
        "action_number",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=8,
        textColor=GREEN,
    )
    action_body = ParagraphStyle(
        "action_body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.1,
        leading=9.2,
        textColor=WHITE,
    )

    def draw_page_number(canvas: Any, current_doc: Any) -> None:
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(MID)
        canvas.drawRightString(
            page_width - doc.rightMargin,
            0.18 * inch,
            f"Page {current_doc.page}",
        )

    def draw_first_page(canvas: Any, current_doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, page_height - 1.52 * inch, page_width, 1.52 * inch, fill=1, stroke=0)
        canvas.setFillColor(DEEP)
        canvas.circle(page_width - 0.35 * inch, page_height - 0.18 * inch, 1.18 * inch, fill=1, stroke=0)
        canvas.setFillColor(colors.Color(0.07, 0.74, 0.82, alpha=0.16))
        canvas.circle(0.28 * inch, page_height - 1.38 * inch, 1.05 * inch, fill=1, stroke=0)
        canvas.setFillColor(GREEN)
        canvas.rect(0, page_height - 1.57 * inch, page_width, 0.05 * inch, fill=1, stroke=0)
        if map_path and map_path.exists():
            canvas.saveState()
            canvas.setFillAlpha(0.25)
            canvas.drawImage(
                str(map_path),
                4.60 * inch,
                page_height - 1.37 * inch,
                width=2.70 * inch,
                height=0.64 * inch,
                preserveAspectRatio=True,
                mask="auto",
            )
            canvas.restoreState()
        canvas.setFont("Helvetica-Bold", 7.3)
        canvas.setFillColor(GREEN)
        canvas.drawString(doc.leftMargin, page_height - 0.35 * inch, "NASHVILLEHEALTH DATA BRIEF")
        title_paragraph = Paragraph(
            _clean(_short(document_title, 112)),
            ParagraphStyle(
                "cover_title",
                fontName="Helvetica-Bold",
                fontSize=18.2,
                leading=20.0,
                textColor=WHITE,
            ),
        )
        title_paragraph.wrapOn(canvas, 4.92 * inch, 0.72 * inch)
        title_paragraph.drawOn(canvas, doc.leftMargin, page_height - 1.00 * inch)
        if logo_path.exists():
            canvas.drawImage(
                str(logo_path),
                page_width - 2.05 * inch,
                page_height - 0.47 * inch,
                width=1.50 * inch,
                height=0.23 * inch,
                preserveAspectRatio=True,
                mask="auto",
            )
        draw_page_number(canvas, current_doc)
        canvas.restoreState()

    def draw_later_page(canvas: Any, current_doc: Any) -> None:
        canvas.saveState()
        canvas.setFillColor(NAVY)
        canvas.rect(0, page_height - 0.68 * inch, page_width, 0.68 * inch, fill=1, stroke=0)
        canvas.setFillColor(GREEN)
        canvas.rect(0, page_height - 0.73 * inch, page_width, 0.05 * inch, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 7.1)
        canvas.setFillColor(BLUE)
        canvas.drawString(doc.leftMargin, page_height - 0.28 * inch, "NASHVILLEHEALTH DATA BRIEF")
        canvas.setFont("Helvetica-Bold", 9.2)
        canvas.setFillColor(WHITE)
        canvas.drawString(doc.leftMargin, page_height - 0.48 * inch, "Conversation Follow-Up")
        if logo_path.exists():
            canvas.drawImage(
                str(logo_path),
                page_width - 1.95 * inch,
                page_height - 0.47 * inch,
                width=1.35 * inch,
                height=0.20 * inch,
                preserveAspectRatio=True,
                mask="auto",
            )
        draw_page_number(canvas, current_doc)
        canvas.restoreState()

    doc.addPageTemplates(
        [
            PageTemplate(
                id="first",
                frames=[first_frame],
                onPage=draw_first_page,
                autoNextPageTemplate="later",
            ),
            PageTemplate(id="later", frames=[later_frame], onPage=draw_later_page),
        ]
    )

    story: list[Any] = []

    for exchange_index, exchange in enumerate(exchanges):
        answer = dict(exchange.get("answer") or {})
        if exchange_index > 0:
            story.append(PageBreak())

        # In a multi-question brief, every page receives its own visible topic title.
        if multi_page_conversation or exchange_index > 0:
            story.extend(
                [
                    Paragraph(
                        "FIRST QUESTION" if exchange_index == 0 else f"FOLLOW-UP {exchange_index}",
                        topic_kicker,
                    ),
                    Paragraph(
                        _clean(title_case(answer.get("headline") or answer.get("title") or "Nashville Health Finding")),
                        topic_heading,
                    ),
                ]
            )

        summary = Table(
            [
                [
                    Paragraph("THE MAIN FINDING", kicker),
                    Paragraph(_clean(_specific_takeaway(answer)), body),
                ]
            ],
            colWidths=[1.28 * inch, doc.width - 1.28 * inch],
        )
        summary.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
                    ("BOX", (0, 0), (-1, -1), 0.7, BLUE),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([summary, Spacer(1, 7)])

        metrics = list(answer.get("metrics") or [])[:3]
        if metrics:
            metric_cells: list[Any] = []
            for metric_index, metric in enumerate(metrics):
                card = Table(
                    [
                        [Paragraph(_clean(title_case(metric.get("label"))), metric_label)],
                        [Paragraph(_clean(metric.get("value")), metric_value)],
                    ],
                    colWidths=[doc.width / len(metrics) - 0.04 * inch],
                )
                card.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), PALE_GREEN if metric_index == 2 else LIGHT),
                            ("BOX", (0, 0), (-1, -1), 0.55, GREEN if metric_index == 2 else LINE),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 8),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                            ("TOPPADDING", (0, 0), (-1, -1), 6),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                metric_cells.append(card)
            metric_row = Table([metric_cells], colWidths=[doc.width / len(metric_cells)] * len(metric_cells))
            metric_row.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            story.extend([metric_row, Spacer(1, 7)])

        chart_image: bytes | None = None
        value_axis_title = str(answer.get("chart_unit") or "Measure Value")
        if answer.get("rank_data"):
            chart_image = _rank_png(list(answer.get("rank_data") or []))
        elif answer.get("chart_data"):
            chart_image = _trend_png(list(answer.get("chart_data") or []), value_axis_title)
        elif answer.get("comparison_data"):
            chart_image = _comparison_png(list(answer.get("comparison_data") or []), value_axis_title)

        if chart_image:
            chart_title = title_case(answer.get("chart_title") or "How Communities Compare")
            chart_subtitle = _concise(answer.get("chart_subtitle") or "", 245)
            chart_heading = [
                Paragraph(_clean(chart_title), section),
                Paragraph(_clean(chart_subtitle), small),
                Spacer(1, 2),
                Image(io.BytesIO(chart_image), width=doc.width, height=2.08 * inch),
            ]
            story.extend([KeepTogether(chart_heading), Spacer(1, 5)])

        why = _concise(answer.get("why_it_matters") or answer.get("explanation"), 205)
        explanation = _concise(answer.get("explanation") or answer.get("definition"), 220)
        definition = _concise(answer.get("definition"), 145)
        left_content = [Paragraph("WHY THIS MATTERS", kicker), Paragraph(_clean(why), body)]
        right_content = [
            Paragraph("HOW TO READ THE RESULT", kicker),
            Paragraph(_clean(explanation), body),
        ]
        if definition and definition.lower() not in explanation.lower():
            right_content.append(Paragraph(_clean(f"Measure: {definition}"), small))
        context_table = Table(
            [[left_content, right_content]],
            colWidths=[doc.width / 2, doc.width / 2],
        )
        context_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), PALE_GREEN),
                    ("BACKGROUND", (1, 0), (1, 0), LIGHT),
                    ("BOX", (0, 0), (0, 0), 0.55, GREEN),
                    ("BOX", (1, 0), (1, 0), 0.55, LINE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 9),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.extend([context_table, Spacer(1, 7)])

        actions = list(answer.get("action_items") or [])[:3]
        if actions:
            story.append(
                Paragraph(
                    _clean(title_case(answer.get("action_heading") or "What You Can Explore Next")),
                    section,
                )
            )
            cards: list[Any] = []
            for action_index, item in enumerate(actions):
                content = [
                    Paragraph(f"0{action_index + 1}", action_number),
                    Paragraph(_clean(_concise(item, 160)), action_body),
                ]
                card = Table([[content]], colWidths=[doc.width / 3 - 0.05 * inch])
                card.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), NAVY),
                            ("BOX", (0, 0), (-1, -1), 0.55, DEEP),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 9),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
                            ("TOPPADDING", (0, 0), (-1, -1), 8),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ]
                    )
                )
                cards.append(card)
            actions_row = Table([cards], colWidths=[doc.width / 3] * len(cards))
            actions_row.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 2),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            story.extend([actions_row, Spacer(1, 6)])

        resources = list(answer.get("local_resources") or [])[:2]
        if resources:
            resource_cells = []
            for resource in resources:
                resource_title = _clean(title_case(resource.get("title") or "Local Resource"))
                description = _clean(_concise(resource.get("description") or "", 115))
                url = str(resource.get("url") or "")
                link = (
                    f'<link href="{url}" color="#0B3D5E"><b>{resource_title}</b></link>'
                    if url
                    else f"<b>{resource_title}</b>"
                )
                resource_cells.append(
                    [
                        Paragraph(link, body),
                        Paragraph(description, small),
                        Paragraph("Click the resource name above to learn more.", small),
                    ]
                )
            resource_table = Table(
                [resource_cells],
                colWidths=[doc.width / len(resource_cells)] * len(resource_cells),
            )
            resource_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
                        ("BOX", (0, 0), (-1, -1), 0.55, BLUE),
                        ("INNERGRID", (0, 0), (-1, -1), 0.35, LINE),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ]
                )
            )
            story.extend([Paragraph("LOCAL PLACES TO START", kicker), resource_table])

    doc.build(story)
    return buffer.getvalue()
