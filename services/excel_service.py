from __future__ import annotations

import io
import os
import re
import unicodedata
from typing import Dict

import numpy as np
import pandas as pd
from pandas.api import types as pdt


def sanitize_name(value: str, fallback: str = "OBJECT") -> str:
    """
    Convert business names, filenames, sheets, and columns into safe Snowflake
    identifiers: uppercase, ASCII, underscores, no extensions, no special chars.
    """
    base = os.path.splitext(str(value or ""))[0]
    normalized = unicodedata.normalize("NFKD", base)
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_").upper()

    if not normalized:
        normalized = fallback
    if normalized[0].isdigit():
        normalized = f"N_{normalized}"
    return normalized[:255]


def _deduplicate_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique_names: list[str] = []

    for name in names:
        count = seen.get(name, 0) + 1
        seen[name] = count
        if count == 1:
            unique_names.append(name)
            continue

        suffix = f"_{count}"
        unique_names.append(f"{name[:255 - len(suffix)]}{suffix}")

    return unique_names


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean a sheet dataframe before Snowflake table creation and insertion."""
    cleaned = df.copy()
    cleaned = cleaned.dropna(how="all").dropna(axis=1, how="all")

    if cleaned.empty and len(cleaned.columns) == 0:
        return cleaned

    cleaned.columns = _deduplicate_names(
        [sanitize_name(str(column), fallback=f"COLUMN_{index + 1}") for index, column in enumerate(cleaned.columns)]
    )

    invalid_count = 0
    invalid_examples: list[dict[str, object]] = []
    invalid_markers = {"", "NULL", "N/A", "NA", "#N/A", "#VALUE!", "#REF!", "#DIV/0!"}

    for column in cleaned.columns:
        if pdt.is_object_dtype(cleaned[column]) or pdt.is_string_dtype(cleaned[column]):
            values = cleaned[column].map(lambda value: value.strip() if isinstance(value, str) else value)
            marker_mask = values.map(
                lambda value: isinstance(value, str) and value.strip().upper() in invalid_markers
            )
            invalid_count += int(marker_mask.sum())
            for row_index, raw_value in values[marker_mask].head(3).items():
                invalid_examples.append(
                    {
                        "column": str(column),
                        "row": int(row_index) + 2,
                        "value": str(raw_value),
                    }
                )
            cleaned[column] = (
                values
                .replace({"": None, "NULL": None, "N/A": None, "NA": None, "#N/A": None})
            )

    duplicate_count = int(cleaned.duplicated(keep="first").sum())
    cleaned = cleaned.drop_duplicates(keep="first")
    cleaned = cleaned.replace({np.nan: None, pd.NaT: None})
    cleaned = cleaned.convert_dtypes()
    cleaned.attrs["duplicate_count"] = duplicate_count
    cleaned.attrs["invalid_count"] = invalid_count
    cleaned.attrs["invalid_examples"] = invalid_examples[:10]
    return cleaned


def read_excel_file(file_bytes: bytes) -> Dict[str, pd.DataFrame]:
    """Read every Excel sheet into a cleaned dataframe keyed by original sheet name."""
    try:
        workbook = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None)
    except Exception as exc:
        raise ValueError(f"Invalid Excel file: {exc}") from exc

    if not workbook:
        raise ValueError("The Excel file does not contain any sheets.")

    cleaned_sheets: Dict[str, pd.DataFrame] = {}
    for sheet_name, dataframe in workbook.items():
        cleaned_sheets[sheet_name] = clean_dataframe(dataframe)

    return cleaned_sheets
