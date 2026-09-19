from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

NAVY = "#0B3D5E"
BLUE = "#12BDD2"
GREEN = "#CAD92D"
INK = "#173642"
GRID = "#DCE9EC"
MUTED = "#64777E"
SOFT = "#B9D7DE"


def _title_block(title: str, subtitle: str = "") -> str:
    if not subtitle:
        return f"<b>{title}</b>"
    return (
        f"<b>{title}</b><br>"
        f"<span style='font-size:12px;color:{MUTED};font-weight:400'>{subtitle}</span>"
    )


def trend_figure(
    chart_data: list[dict],
    title: str,
    subtitle: str = "",
    unit: str = "",
) -> go.Figure:
    frame = pd.DataFrame(chart_data)
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=frame["Period"],
            y=frame["Nashville"],
            mode="lines+markers",
            name="Nashville",
            line={"color": BLUE, "width": 4, "shape": "spline"},
            marker={"size": 9, "color": BLUE, "line": {"color": "white", "width": 2}},
            customdata=frame[["Release year"]],
            hovertemplate=(
                "Nashville: %{y:.1f}<br>Date range: %{x}<br>"
                "CHR&R release: %{customdata[0]}<extra></extra>"
            ),
        )
    )
    if "Peer average" in frame and frame["Peer average"].notna().any():
        figure.add_trace(
            go.Scatter(
                x=frame["Period"],
                y=frame["Peer average"],
                mode="lines+markers",
                name="Peer Community Average",
                line={"color": GREEN, "width": 3, "dash": "dot", "shape": "spline"},
                marker={"size": 7, "color": GREEN},
                hovertemplate=(
                    "Peer community average: %{y:.1f}<br>Date range: %{x}<extra></extra>"
                ),
            )
        )
    figure.update_layout(
        title=(
            {
                "text": _title_block(title, subtitle),
                "font": {"size": 20, "color": INK},
                "x": 0.01,
                "xanchor": "left",
                "y": 0.97,
                "yanchor": "top",
            }
            if title
            else None
        ),
        height=410 if not title else 455,
        margin={"l": 58, "r": 24, "t": 24 if not title else 112, "b": 92},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "color": INK},
        legend={
            "orientation": "h",
            "y": -0.24,
            "yanchor": "top",
            "x": 0.5,
            "xanchor": "center",
            "font": {"size": 12, "color": INK},
            "bgcolor": "rgba(255,255,255,0)",
        },
        hovermode="x unified",
    )
    figure.update_xaxes(
        showgrid=False,
        title={"text": "Year", "standoff": 12},
        tickfont={"color": MUTED},
        title_font={"color": MUTED, "size": 14},
    )
    figure.update_yaxes(
        gridcolor=GRID,
        zeroline=False,
        title={"text": unit or "Measure Value", "standoff": 10},
        tickfont={"color": MUTED},
        title_font={"color": MUTED, "size": 14},
    )
    return figure


def comparison_figure(
    data: list[dict],
    title: str,
    subtitle: str = "",
    unit: str = "",
) -> go.Figure:
    frame = pd.DataFrame(data)
    if frame.empty:
        return go.Figure()
    frame = frame.sort_values("Rank", ascending=False)
    colors = [
        BLUE if row.get("Is Nashville") else (GREEN if row.get("Is best") else SOFT)
        for row in frame.to_dict(orient="records")
    ]
    figure = go.Figure(
        go.Bar(
            x=frame["Value"],
            y=frame["City"],
            orientation="h",
            marker={"color": colors, "line": {"color": "rgba(255,255,255,.8)", "width": 1}},
            customdata=frame[["Value display", "Rank"]],
            text=frame["Value display"],
            textposition="outside",
            cliponaxis=False,
            hovertemplate=(
                "%{y}<br>%{customdata[0]}<br>Rank %{customdata[1]}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title=(
            {
                "text": _title_block(title, subtitle),
                "font": {"size": 20, "color": INK},
                "x": 0.01,
                "xanchor": "left",
                "y": 0.97,
                "yanchor": "top",
            }
            if title
            else None
        ),
        height=max(380, 54 * len(frame) + (70 if not title else 145)),
        margin={"l": 70, "r": 118, "t": 22 if not title else 112, "b": 70},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "color": INK},
        showlegend=False,
    )
    figure.update_xaxes(
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        title={"text": unit or "Measure Value", "standoff": 12},
        tickfont={"color": MUTED},
        title_font={"color": MUTED, "size": 14},
    )
    figure.update_yaxes(
        showgrid=False,
        tickfont={"color": INK, "size": 12},
        title={"text": "Peer Community", "standoff": 10},
        title_font={"color": MUTED, "size": 14},
    )
    return figure


def rank_figure(
    data: list[dict],
    title: str,
    subtitle: str = "",
) -> go.Figure:
    frame = pd.DataFrame(data)
    if frame.empty:
        return go.Figure()
    frame = frame.sort_values("Rank", ascending=False)
    colors = [
        BLUE if rank >= max(1, count * 2 / 3) else (GREEN if rank <= max(2, count / 3) else SOFT)
        for rank, count in zip(frame["Rank"], frame["City count"])
    ]
    labels = [f"{int(rank)} of {int(count)}" for rank, count in zip(frame["Rank"], frame["City count"])]
    figure = go.Figure(
        go.Bar(
            x=frame["Rank"],
            y=frame["Measure"],
            orientation="h",
            marker={"color": colors, "line": {"color": "white", "width": 1}},
            text=labels,
            textposition="outside",
            customdata=frame[["Value display", "City count"]],
            hovertemplate=(
                "%{y}<br>Nashville rank: %{x} of %{customdata[1]}<br>"
                "Nashville value: %{customdata[0]}<extra></extra>"
            ),
            cliponaxis=False,
        )
    )
    max_count = int(frame["City count"].max())
    figure.update_layout(
        title=(
            {
                "text": _title_block(title, subtitle),
                "font": {"size": 20, "color": INK},
                "x": 0.01,
                "xanchor": "left",
                "y": 0.97,
                "yanchor": "top",
            }
            if title
            else None
        ),
        height=max(360, 58 * len(frame) + (72 if not title else 145)),
        margin={"l": 62, "r": 100, "t": 24 if not title else 112, "b": 72},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "color": INK},
        showlegend=False,
    )
    figure.update_xaxes(
        range=[0, max_count + 0.8],
        dtick=1,
        showgrid=True,
        gridcolor=GRID,
        zeroline=False,
        title={"text": "Nashville Rank (1 = Strongest)", "standoff": 12},
        tickfont={"color": MUTED},
        title_font={"color": MUTED, "size": 14},
    )
    figure.update_yaxes(
        showgrid=False,
        tickfont={"color": INK, "size": 12},
        title={"text": "Health Measure", "standoff": 10},
        title_font={"color": MUTED, "size": 14},
    )
    return figure
