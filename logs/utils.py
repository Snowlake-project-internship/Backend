from __future__ import annotations

import re
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def now_ms() -> float:
    return time.perf_counter() * 1000


def duration_ms(start_ms: float) -> int:
    return max(0, int(now_ms() - start_ms))


@contextmanager
def measure_duration() -> Iterator[callable]:
    start = now_ms()
    yield lambda: duration_ms(start)


def stacktrace_from_exception(exc: BaseException) -> str:
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def exception_frame(exc: BaseException) -> traceback.FrameSummary | None:
    frames = traceback.extract_tb(exc.__traceback__)
    return frames[-1] if frames else None


def exception_type_name(exc: BaseException) -> str:
    return type(exc).__name__


def function_name_from_exception(exc: BaseException, fallback: str | None = None) -> str | None:
    frame = exception_frame(exc)
    return frame.name if frame else fallback


def error_path_from_exception(exc: BaseException, fallback: str | None = None) -> str | None:
    frame = exception_frame(exc)
    if not frame:
        return fallback
    path = Path(frame.filename)
    try:
        display_path = str(path.relative_to(Path.cwd()))
    except ValueError:
        display_path = str(path)
    return f"{display_path} -> {frame.name}()"


def service_name_from_path(path: str | None, fallback: str = "backend") -> str:
    if not path:
        return fallback
    normalized = path.replace("\\", "/")
    if "/services/" in normalized or normalized.startswith("services/"):
        return Path(normalized).stem
    if "/routes/" in normalized or normalized.startswith("routes/"):
        return Path(normalized).stem
    if "/middleware/" in normalized or normalized.startswith("middleware/"):
        return Path(normalized).stem
    return fallback


def infer_operation_type(query: str) -> str:
    normalized = re.sub(r"\s+", " ", (query or "").strip()).upper()
    if normalized.startswith("CREATE TABLE"):
        return "CREATE_TABLE"
    if normalized.startswith("CREATE DATABASE"):
        return "CREATE_DATABASE"
    if normalized.startswith("CREATE SCHEMA"):
        return "CREATE_SCHEMA"
    if normalized.startswith("INSERT"):
        return "INSERT"
    if normalized.startswith("UPDATE"):
        return "UPDATE"
    if normalized.startswith("DELETE"):
        return "DELETE"
    if normalized.startswith("DROP"):
        return "DROP"
    if normalized.startswith("SELECT") or normalized.startswith("SHOW") or normalized.startswith("USE"):
        return "SELECT"
    if normalized.startswith("COPY INTO"):
        return "COPY_INTO"
    if normalized.startswith("MERGE"):
        return "MERGE"
    return "SNOWFLAKE_QUERY"


def infer_table_name(query: str) -> str | None:
    normalized = re.sub(r"\s+", " ", (query or "").strip())
    patterns = [
        r"CREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_\".$]+)",
        r"INSERT\s+INTO\s+([A-Za-z0-9_\".$]+)",
        r"UPDATE\s+([A-Za-z0-9_\".$]+)",
        r"DELETE\s+FROM\s+([A-Za-z0-9_\".$]+)",
        r"DROP\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z0-9_\".$]+)",
        r"MERGE\s+INTO\s+([A-Za-z0-9_\".$]+)",
        r"COPY\s+INTO\s+([A-Za-z0-9_\".$]+)",
        r"FROM\s+([A-Za-z0-9_\".$]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, re.IGNORECASE)
        if match:
            return match.group(1).split(".")[-1].replace('"', "")
    return None
