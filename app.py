from __future__ import annotations

import base64
from copy import deepcopy
import random
import re
import time
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import streamlit as st
import streamlit.components.v1 as components

from src.answer_generator import AnswerGenerator
from src.charts import comparison_figure, rank_figure, trend_figure
from src.data_service import HealthDataRepository
from src.llm_client import LLMClient, LLMConfig, config_from_mapping
from src.query_parser import QueryParser
from src.report import build_health_brief
from src.text_utils import escape, title_case

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data/health_data.csv"
METADATA_PATH = ROOT / "data/indicator_metadata.csv"
LOGO_PATH = ROOT / "assets/nashvillehealth_logo.png"
MAP_PATH = ROOT / "assets/tennessee_duotone.png"
PARTHENON_PATH = ROOT / "assets/parthenon_line.svg"
CSS_PATH = ROOT / "assets/brand.css"

EXAMPLES = [
    "How does Nashville's obesity rate compare with the peer-city average?",
    "How has adult smoking changed in Nashville since 2015?",
    "Are Nashvillians living shorter lives than people in similar cities?",
    "How does Nashville compare with Austin and Denver on life expectancy?",
    "Is poor mental health getting better or worse in Nashville over time?",
    "Which peer city performs best on access to exercise, and where does Nashville rank?",
    "What did Nashville's infant mortality data show in the 2025 CHR&R release?",
    "Why does housing affordability matter for health in Nashville?",
    "What are Nashville's biggest health challenges compared with peer cities?",
]

SUPPORTED_COMMUNITIES = [
    "Nashville",
    "Austin",
    "Raleigh",
    "Durham",
    "Charlotte",
    "Denver",
    "Atlanta",
    "Fort Worth",
    "Dallas",
]
SUPPORTED_COMMUNITIES_TEXT = ", ".join(SUPPORTED_COMMUNITIES)

st.set_page_config(
    page_title="NashvilleHealth | Understanding Nashville's Health Through Data",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _load_css() -> None:
    st.markdown(
        f"<style>{CSS_PATH.read_text(encoding='utf-8')}</style>",
        unsafe_allow_html=True,
    )


def _uri(path: Path) -> str:
    mime = "image/svg+xml" if path.suffix.lower() == ".svg" else "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{encoded}"


@st.cache_resource(show_spinner=False)
def _repo() -> HealthDataRepository:
    return HealthDataRepository(DATA_PATH, METADATA_PATH)


@st.cache_resource(show_spinner=False)
def _client(
    provider: str,
    url: str,
    model: str,
    key: str,
    gemini_key: str,
    gemini_model: str,
) -> LLMClient:
    return LLMClient(
        LLMConfig(
            provider=provider,
            ollama_url=url,
            ollama_model=model,
            ollama_api_key=key,
            gemini_api_key=gemini_key,
            gemini_model=gemini_model,
        )
    )


def _secrets() -> dict[str, Any]:
    try:
        return dict(st.secrets)
    except Exception:
        return {}


def _queue(question: str) -> None:
    st.session_state["pending_question"] = question
    st.session_state["main_view"] = "Ask"


def _conversation_title(messages: list[dict[str, Any]]) -> str:
    if not messages:
        return "Untitled Conversation"
    title = str(messages[0].get("question") or "Nashville Health Conversation").strip()
    return title if len(title) <= 58 else f"{title[:55].rstrip()}..."


def _save_current_conversation() -> None:
    """Keep a compact in-session history without writing user chats to disk."""

    messages = list(st.session_state.get("messages") or [])
    if not messages:
        return

    conversation_id = str(
        st.session_state.setdefault("active_conversation_id", uuid4().hex)
    )
    entry = {
        "id": conversation_id,
        "title": _conversation_title(messages),
        "updated_at": time.strftime("%b %d, %I:%M %p"),
        "messages": deepcopy(messages),
        "current_indicator": str(st.session_state.get("current_indicator") or ""),
    }
    history = [
        item
        for item in list(st.session_state.get("conversation_history") or [])
        if str(item.get("id") or "") != conversation_id
    ]
    st.session_state["conversation_history"] = [entry, *history][:10]


def _restore_conversation(conversation_id: str) -> None:
    _save_current_conversation()
    match = next(
        (
            item
            for item in list(st.session_state.get("conversation_history") or [])
            if str(item.get("id") or "") == conversation_id
        ),
        None,
    )
    if not match:
        return

    st.session_state["messages"] = deepcopy(list(match.get("messages") or []))
    st.session_state["current_indicator"] = str(match.get("current_indicator") or "")
    st.session_state["active_conversation_id"] = conversation_id
    st.session_state["main_view"] = "Ask"
    st.session_state.pop("pending_question", None)
    st.session_state.pop("animate_answer_index", None)
    st.session_state["_scroll_to_conversation"] = True


def _clear_history() -> None:
    st.session_state["conversation_history"] = []


def _new() -> None:
    _save_current_conversation()
    st.session_state["messages"] = []
    st.session_state["current_indicator"] = ""
    st.session_state["active_conversation_id"] = uuid4().hex
    st.session_state.pop("pending_question", None)
    st.session_state.pop("animate_answer_index", None)
    st.session_state["main_view"] = "Ask"
    st.session_state["prompt_example"] = random.choice(EXAMPLES)
    st.session_state["_scroll_to_question"] = True


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    return slug[:60] or "nashville_health_brief"


def _pause(animated: bool, seconds: float = 0.32) -> None:
    if animated:
        time.sleep(seconds)


def _scroll_script(target_id: str | None = None) -> None:
    target = re.sub(r"[^a-zA-Z0-9_-]", "", str(target_id or ""))
    if target:
        command = f"""
        const node = doc.getElementById('{target}');
        if (node) {{ node.scrollIntoView({{behavior: 'auto', block: 'start'}}); }}
        """
    else:
        command = """
        const containers = [
          doc.querySelector('[data-testid="stAppViewContainer"]'),
          doc.querySelector('section.main'),
          doc.scrollingElement
        ];
        for (const container of containers) {
          if (container && container.scrollTo) {
            container.scrollTo({top: 0, left: 0, behavior: 'auto'});
          }
        }
        """
    components.html(
        f"""
        <script>
          const doc = window.parent.document;
          setTimeout(() => {{ {command} }}, 60);
        </script>
        """,
        height=0,
        width=0,
    )


def _header() -> str:
    st.session_state.setdefault("main_view", "Ask")
    if st.session_state["main_view"] not in {"Ask", "Browse Topics"}:
        st.session_state["main_view"] = "Ask"

    st.markdown(
        f"""
        <header class="nh-topbar">
          <div class="nh-brand-lockup">
            <img src="{_uri(LOGO_PATH)}" alt="NashvilleHealth" />
          </div>
        </header>
        """,
        unsafe_allow_html=True,
    )

    nav_col, history_col, action_col = st.columns([4.75, 1.35, 1.35])
    with nav_col:
        view = st.radio(
            "Navigation",
            ["Ask", "Browse Topics"],
            horizontal=True,
            label_visibility="collapsed",
            key="main_view",
        )
    with history_col:
        with st.popover("Chat History", use_container_width=True):
            st.caption("Saved only for this browser session.")
            current_messages = list(st.session_state.get("messages") or [])
            active_id = str(st.session_state.get("active_conversation_id") or "")
            if current_messages:
                st.markdown("**Current Conversation**")
                st.caption(_conversation_title(current_messages))

            previous = [
                item
                for item in list(st.session_state.get("conversation_history") or [])
                if str(item.get("id") or "") != active_id
            ]
            if previous:
                st.markdown("**Earlier Conversations**")
                for item in previous:
                    label = str(item.get("title") or "Nashville Health Conversation")
                    updated = str(item.get("updated_at") or "")
                    st.button(
                        label,
                        key=f"restore_{item.get('id')}",
                        help=f"Last updated {updated}" if updated else None,
                        use_container_width=True,
                        on_click=_restore_conversation,
                        args=(str(item.get("id") or ""),),
                    )
                st.button(
                    "Clear Saved Chats",
                    key="clear_chat_history",
                    use_container_width=True,
                    on_click=_clear_history,
                )
            elif not current_messages:
                st.caption("No conversations have been saved yet.")
    with action_col:
        st.button(
            "New Conversation",
            use_container_width=True,
            on_click=_new,
        )
    return view


def _hero() -> str | None:
    st.markdown(
        f"""
        <section class="nh-hero-shell">
          <div class="nh-hero-copy">
            <h1>Understanding Nashville's Health Through Data</h1>
            <p>
              Ask about health outcomes, access to care, and the conditions that shape life
              in Nashville. Get a clear answer, see how Nashville compares, and explore what
              the data means.
            </p>
            <div class="nh-hero-coverage">
              <b>Communities available in this tool</b>
              <span>{escape(SUPPORTED_COMMUNITIES_TEXT)}</span>
            </div>
          </div>
          <div class="nh-hero-visual" aria-hidden="true">
            <div class="nh-map-ripples"><span></span><span></span><span></span></div>
            <div class="nh-map-wrap">
              <img class="nh-tn-map" src="{_uri(MAP_PATH)}" alt="" />
              <div class="nh-map-label">
                <b>Nashville</b>
                <small>Davidson County</small>
              </div>
            </div>
            <img class="nh-parthenon" src="{_uri(PARTHENON_PATH)}" alt="" />
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <section id="nh-question-tool" class="nh-question-intro">
          <div class="nh-section-kicker">ASK NASHVILLE HEALTH</div>
          <h2>What Would You Like to Know?</h2>
        </section>
        """,
        unsafe_allow_html=True,
    )

    with st.form("hero_form", clear_on_submit=True):
        question = st.text_area(
            "Ask",
            placeholder=st.session_state["prompt_example"],
            height=86,
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Ask Nashville Health",
            type="primary",
            use_container_width=True,
        )

    st.markdown(
        '<div class="nh-suggestion-label">Questions to Try</div>',
        unsafe_allow_html=True,
    )
    suggestions = [
        "What are Nashville's biggest health challenges compared with peer cities?",
        "How has adult smoking changed in Nashville since 2015?",
        "Why does housing affordability matter for health in Nashville?",
    ]
    columns = st.columns(3)
    for index, suggestion in enumerate(suggestions):
        with columns[index]:
            st.button(
                suggestion,
                key=f"suggestion_{index}",
                use_container_width=True,
                on_click=_queue,
                args=(suggestion,),
            )

    return question.strip() if submitted and question.strip() else None


def _actions(items: list[str], heading: str, animated: bool = False) -> None:
    if not items:
        return
    _pause(animated, 0.38)
    st.markdown(
        f'<div class="nh-section-label">{escape(title_case(heading))}</div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(min(3, len(items)))
    for index, item in enumerate(items[:3]):
        with columns[index]:
            st.markdown(
                f"""
                <div class="nh-action-card">
                  <div class="nh-action-number">0{index + 1}</div>
                  <div class="nh-action-copy">{escape(item)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _stream_chunks(text: str, chunk_size: int = 3) -> Iterable[str]:
    words = str(text or "").split()
    for end in range(chunk_size, len(words) + chunk_size, chunk_size):
        yield " ".join(words[: min(end, len(words))])


def _answer_header(answer: dict[str, Any], animated: bool) -> None:
    headline = escape(title_case(answer.get("headline", "")))
    takeaway = str(answer.get("takeaway") or "").strip()
    category = title_case(answer.get("category") or "Nashville Health")

    if not animated or not takeaway:
        st.markdown(
            f"""
            <article class="nh-answer-card">
              <div class="nh-answer-meta">
                <span>{escape(category)}</span>
                <span>Verified Nashville Data</span>
              </div>
              <h2>{headline}</h2>
              <p class="nh-takeaway">{escape(takeaway)}</p>
            </article>
            """,
            unsafe_allow_html=True,
        )
        return

    placeholder = st.empty()
    chunks = list(_stream_chunks(takeaway, 3))
    for position, visible in enumerate(chunks):
        cursor = "<span class='nh-stream-cursor'></span>" if position < len(chunks) - 1 else ""
        placeholder.markdown(
            f"""
            <article class="nh-answer-card nh-answer-arriving">
              <div class="nh-answer-meta">
                <span>{escape(category)}</span>
                <span>Verified Nashville Data</span>
              </div>
              <h2>{headline}</h2>
              <p class="nh-takeaway">{escape(visible)}{cursor}</p>
            </article>
            """,
            unsafe_allow_html=True,
        )
        time.sleep(0.18)


def _render_explanation(answer: dict[str, Any], animated: bool) -> None:
    explanation = str(answer.get("explanation") or "").strip()
    if not explanation:
        return
    heading = title_case(answer.get("explanation_heading") or "Putting This Result in Context")
    _pause(animated, 0.34)

    if not animated:
        st.markdown(
            f"""
            <div class="nh-body-copy">
              <b>{escape(heading)}</b>
              <div>{escape(explanation)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    placeholder = st.empty()
    chunks = list(_stream_chunks(explanation, 3))
    for position, visible in enumerate(chunks):
        cursor = "<span class='nh-stream-cursor'></span>" if position < len(chunks) - 1 else ""
        placeholder.markdown(
            f"""
            <div class="nh-body-copy nh-answer-arriving">
              <b>{escape(heading)}</b>
              <div>{escape(visible)}{cursor}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        time.sleep(0.16)


def _render_metrics(metrics: Iterable[dict[str, Any]], animated: bool) -> None:
    metrics = list(metrics or [])[:3]
    if not metrics:
        return
    _pause(animated, 0.38)
    columns = st.columns(len(metrics))
    for column, metric in zip(columns, metrics):
        with column:
            st.markdown(
                f"""
                <div class="nh-metric-card">
                  <div class="nh-metric-label">{escape(title_case(metric.get('label')))}</div>
                  <div class="nh-metric-value">{escape(metric.get('value'))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_highlights(answer: dict[str, Any], animated: bool) -> None:
    highlights = list(answer.get("highlights") or [])[:4]
    if not highlights:
        return
    _pause(animated, 0.32)
    heading = title_case(answer.get("highlights_heading") or "Key Takeaways From the Data")
    st.markdown(
        f'<div class="nh-section-label">{escape(heading)}</div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(min(3, len(highlights)))
    for index, highlight in enumerate(highlights):
        with columns[index % min(3, len(highlights))]:
            st.markdown(
                f"""
                <div class="nh-highlight-card">
                  <div class="nh-highlight-title">{escape(title_case(highlight.get('title')))}</div>
                  <div class="nh-highlight-value">{escape(highlight.get('value'))}</div>
                  <div class="nh-highlight-detail">{escape(highlight.get('detail'))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_chart(answer: dict[str, Any], index: int, animated: bool) -> None:
    chart_data = list(answer.get("chart_data") or [])
    comparison_data = list(answer.get("comparison_data") or [])
    rank_data = list(answer.get("rank_data") or [])
    if not chart_data and not comparison_data and not rank_data:
        return

    title = title_case(answer.get("chart_title") or "Nashville Health Comparison")
    subtitle = str(answer.get("chart_subtitle") or "").strip()
    unit = str(answer.get("chart_unit") or "")
    _pause(animated, 0.45)
    st.markdown(
        '<div class="nh-section-label">Explore the Data</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="nh-chart-heading">
          <h3>{escape(title)}</h3>
          {f'<p>{escape(subtitle)}</p>' if subtitle else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if rank_data:
        figure = rank_figure(rank_data, "", "")
        key = f"rank_{index}"
    elif chart_data:
        figure = trend_figure(chart_data, "", "", unit)
        key = f"trend_{index}"
    else:
        figure = comparison_figure(comparison_data, "", "", unit)
        key = f"comparison_{index}"

    st.plotly_chart(
        figure,
        use_container_width=True,
        config={"displayModeBar": False},
        key=key,
    )


def _render_measure_details(answer: dict[str, Any]) -> None:
    definition = str(answer.get("definition") or "").strip()
    why = str(answer.get("why_it_matters") or "").strip()
    if not definition and not why:
        return

    with st.expander("Understand This Measure"):
        left, right = st.columns(2)
        with left:
            if definition:
                st.markdown(
                    f"""
                    <div class="nh-explainer">
                      <b>What This Measure Means</b><br />
                      {escape(definition)}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        with right:
            if why:
                st.markdown(
                    f"""
                    <div class="nh-why">
                      <b>Why It Matters</b><br />
                      {escape(why)}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )


def _render_resources(answer: dict[str, Any], index: int) -> None:
    resources = list(answer.get("local_resources") or [])[:2]
    if not resources:
        return
    st.markdown(
        '<div class="nh-section-label">Local Resources to Explore</div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(len(resources))
    for resource_index, resource in enumerate(resources):
        with columns[resource_index]:
            resource_title = title_case(resource.get("title") or "Open Local Resource")
            resource_url = str(resource.get("url") or "")
            if resource_url:
                st.link_button(
                    resource_title,
                    resource_url,
                    use_container_width=True,
                )
            st.markdown(
                f"""
                <div class="nh-resource-card">
                  <div class="nh-resource-copy">{escape(resource.get('description'))}</div>
                  <div class="nh-resource-hint">Click the button above to open this resource.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.caption(
        "These links are curated from public agencies and local organizations; they are not generated by AI."
    )


def _render_related(answer: dict[str, Any], index: int) -> None:
    related = list(answer.get("related_indicators") or [])[:3]
    if not related:
        return
    st.markdown(
        '<div class="nh-section-label">Related Measures to Explore</div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(min(3, len(related)))
    for related_index, name in enumerate(related):
        label = title_case(name)
        with columns[related_index]:
            st.button(
                label,
                key=f"related_{index}_{related_index}",
                use_container_width=True,
                on_click=_queue,
                args=(f"How does Nashville compare on {name}?",),
            )


def _render_sources(answer: dict[str, Any]) -> None:
    source_note = str(answer.get("source_note") or "").strip()
    selection_note = str(answer.get("selection_note") or "").strip()
    if not source_note and not selection_note:
        return

    with st.expander("Source and Date Details"):
        if selection_note:
            st.info(selection_note)
        if source_note:
            st.markdown(source_note)
        st.caption(
            "The CHR&R release year is when the value was published. The data date "
            "range is when the information was collected."
        )


def _render_followups(answer: dict[str, Any], index: int) -> None:
    questions = list(answer.get("suggested_questions") or [])[:3]
    if not questions:
        return
    st.markdown(
        '<div class="nh-section-label">Continue the Conversation</div>',
        unsafe_allow_html=True,
    )
    columns = st.columns(min(3, len(questions)))
    for question_index, question in enumerate(questions):
        with columns[question_index]:
            st.button(
                question,
                key=f"followup_{index}_{question_index}",
                use_container_width=True,
                on_click=_queue,
                args=(question,),
            )


def _answer(answer: dict[str, Any], index: int, animated: bool = False) -> None:
    anchor = f"nh-answer-{index}"
    st.markdown(f'<div id="{anchor}" class="nh-scroll-anchor"></div>', unsafe_allow_html=True)
    if animated:
        _scroll_script(anchor)

    _answer_header(answer, animated)
    _render_explanation(answer, animated)
    _render_metrics(answer.get("metrics") or [], animated)
    _render_highlights(answer, animated)
    _render_chart(answer, index, animated)
    _render_measure_details(answer)
    _actions(
        list(answer.get("action_items") or []),
        str(answer.get("action_heading") or "From Insight to Action"),
        animated,
    )
    _render_resources(answer, index)
    _render_related(answer, index)
    _render_sources(answer)
    _render_followups(answer, index)


def _conversation() -> str | None:
    messages = st.session_state["messages"]
    animate_index = st.session_state.pop("animate_answer_index", None)

    st.markdown(
        """
        <section id="nh-conversation" class="nh-conversation-heading">
          <div class="nh-section-kicker">YOUR NASHVILLE HEALTH CONVERSATION</div>
          <h1>Clear Findings, With the Data Behind Them</h1>
        </section>
        """,
        unsafe_allow_html=True,
    )

    for index, message in enumerate(messages):
        st.markdown(
            f"""
            <div class="nh-user-row">
              <div class="nh-user-bubble">{escape(message.get('question'))}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _answer(
            dict(message.get("answer") or {}),
            index,
            animated=index == animate_index,
        )
        st.markdown('<div class="nh-thread-divider"></div>', unsafe_allow_html=True)

    latest = dict(messages[-1].get("answer") or {})
    pdf = build_health_brief(messages, LOGO_PATH, MAP_PATH)

    st.markdown(
        """
        <section class="nh-download-panel">
          <div class="nh-section-kicker">TAKE THE STORY WITH YOU</div>
          <h3>Download a NashvilleHealth Data Brief</h3>
          <p>
            The brief includes every question and follow-up in this conversation, with the main
            findings, key numbers, charts, context, practical next steps, and local resources.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )
    download_col, note_col = st.columns([1.8, 4.2])
    with download_col:
        st.download_button(
            "Download Data Brief (PDF)",
            pdf,
            file_name=(
                f"{_slug(latest.get('title'))}_brief.pdf"
                if len(messages) == 1
                else "nashville_health_conversation_brief.pdf"
            ),
            mime="application/pdf",
            use_container_width=True,
        )
    with note_col:
        st.caption(
            "Every question and follow-up in this conversation is included on its own page."
            if len(messages) > 1
            else "This topic is included as a complete, shareable health story."
        )

    st.markdown(
        '<div class="nh-section-label nh-followup-label">Ask a Follow-Up</div>',
        unsafe_allow_html=True,
    )
    with st.form(f"followup_form_{len(messages)}", clear_on_submit=True):
        follow_up = st.text_input(
            "Ask a follow-up question about Nashville health",
            placeholder="Ask about another measure, a trend, or a peer-community comparison...",
            label_visibility="collapsed",
            key=f"followup_question_{len(messages)}",
        )
        submitted = st.form_submit_button(
            "Ask Follow-Up",
            type="primary",
            use_container_width=True,
        )
    return follow_up.strip() if submitted and follow_up.strip() else None


def _compact_definition(value: Any, limit: int = 122) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    shortened = text[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;:")
    return f"{shortened}..."


def _browse(repo: HealthDataRepository) -> None:
    st.markdown(
        """
        <section class="nh-page-intro nh-page-intro-compact">
          <div class="nh-section-kicker">BROWSE TOPICS</div>
          <h1>Start With an Issue That Matters to You</h1>
        </section>
        """,
        unsafe_allow_html=True,
    )

    metadata = repo.metadata.copy()
    categories = metadata["category"].drop_duplicates().tolist()
    st.markdown(
        '<div class="nh-select-heading">Choose a Topic Area</div>',
        unsafe_allow_html=True,
    )
    category = st.selectbox(
        "Choose a Topic Area",
        categories,
        format_func=title_case,
        label_visibility="collapsed",
    )

    subset = metadata[metadata["category"] == category]
    columns = st.columns(4)
    for index, record in enumerate(subset.to_dict(orient="records")):
        name = title_case(record["plain_language_name"])
        definition = _compact_definition(record["plain_language_definition"])
        with columns[index % 4]:
            st.markdown(
                f"""
                <div class="nh-topic-card">
                  <div class="nh-topic-title">{escape(name)}</div>
                  <div class="nh-topic-copy">{escape(definition)}</div>
                  <div class="nh-topic-arrow">Explore →</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.button(
                f"Explore {name}",
                key=f"browse_{record['indicator']}",
                use_container_width=True,
                on_click=_queue,
                args=(f"How does Nashville compare with peer cities on {record['indicator']}?",),
            )


def _process(question: str, parser: QueryParser, generator: AnswerGenerator) -> None:
    with st.status("Understanding your question...", expanded=True) as status:
        status.write("Finding the most relevant NashvilleHealth measure...")
        plan = parser.parse(
            question,
            str(st.session_state.get("current_indicator") or ""),
        )

        if plan.indicators:
            measure_names = ", ".join(title_case(name) for name in plan.indicators)
            status.write(f"Checking Nashville and peer-community data for {measure_names}...")
        else:
            status.write("Checking the available Nashville health topics...")

        answer = generator.answer(question, plan)
        status.write("Organizing the checked results into a clear story...")
        status.update(label="Answer ready", state="complete", expanded=False)

    if plan.indicators:
        st.session_state["current_indicator"] = plan.indicators[0]

    st.session_state["messages"].append(
        {
            "role": "exchange",
            "question": question,
            "answer": answer.to_dict(),
            "plan": plan.to_dict(),
        }
    )
    st.session_state["animate_answer_index"] = len(st.session_state["messages"]) - 1
    _save_current_conversation()


def main() -> None:
    _load_css()
    repository = _repo()
    config = config_from_mapping(_secrets())
    llm = _client(
        config.provider,
        config.ollama_url,
        config.ollama_model,
        config.ollama_api_key,
        config.gemini_api_key,
        config.gemini_model,
    )
    parser = QueryParser(repository, llm)
    generator = AnswerGenerator(repository, llm)

    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("conversation_history", [])
    st.session_state.setdefault("active_conversation_id", uuid4().hex)
    st.session_state.setdefault("current_indicator", "")
    st.session_state.setdefault("prompt_example", random.choice(EXAMPLES))

    view = _header()
    previous_view = st.session_state.get("_last_rendered_view")
    if previous_view != view:
        st.session_state["_last_rendered_view"] = view
        _scroll_script()

    content = st.empty()

    if view == "Ask":
        pending = str(st.session_state.pop("pending_question", "") or "").strip()
        if pending:
            with content.container():
                _process(pending, parser, generator)
            content.empty()
            time.sleep(0.04)

        with content.container():
            question = _conversation() if st.session_state["messages"] else _hero()

        if st.session_state["messages"]:
            if st.session_state.pop("_scroll_to_conversation", False):
                _scroll_script("nh-conversation")
        elif st.session_state.pop("_scroll_to_question", False):
            _scroll_script("nh-question-tool")

        if question:
            content.empty()
            time.sleep(0.04)
            with content.container():
                _process(question, parser, generator)
            content.empty()
            time.sleep(0.04)
            with content.container():
                _conversation()

    else:
        with content.container():
            _browse(repository)

    st.markdown(
        '<footer class="nh-footer">Built for NashvilleHealth using County Health Rankings &amp; Roadmaps data.</footer>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
