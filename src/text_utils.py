from __future__ import annotations

import html
import re
from typing import Any

import pandas as pd


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9%$]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_years(value: Any) -> list[int]:
    return [int(item) for item in re.findall(r"\b(?:19|20)\d{2}\b", str(value or ""))]


def period_end_year(value: Any, fallback: int | None = None) -> int:
    years = extract_years(value)
    if years:
        return max(years)
    return int(fallback or 0)


def period_contains_year(value: Any, year: int) -> bool:
    years = extract_years(value)
    if not years:
        return False
    if len(years) == 1:
        return years[0] == year
    return min(years) <= year <= max(years)


def safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def title_case(value: Any) -> str:
    """Capitalize every display-title word while preserving common acronyms."""
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""

    titled = text.title()
    replacements = {
        "Pm2.5": "PM2.5",
        "Bmi": "BMI",
        "Chrr&R": "CHR&R",
        "Ai": "AI",
        "Pdf": "PDF",
        "Csv": "CSV",
        "Sql": "SQL",
        "Api": "API",
        "U.S.": "U.S.",
        "Nashvillehealth": "NashvilleHealth",
    }
    for source, target in replacements.items():
        if source.isalpha():
            titled = re.sub(rf"\b{re.escape(source)}\b", target, titled)
        else:
            titled = titled.replace(source, target)

    # Python's str.title() turns possessives such as "Nashville's" into
    # "Nashville'S". Restore the conventional lowercase possessive ending.
    titled = re.sub(r"(?<=\w)'S\b", "'s", titled)
    return titled
