"""Field fill-rate and value-distribution analysis across a message corpus."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pandas as pd

from .parser import Message


@dataclass
class FieldReport:
    spec: str
    total_messages: int
    populated_messages: int      # messages with >=1 non-empty occurrence
    total_occurrences: int       # counting repeats (repeating segs / ~ reps)
    populated_occurrences: int
    unique_values: int
    top_values: list[tuple[str, int]]

    @property
    def fill_rate(self) -> float:
        if self.total_messages == 0:
            return 0.0
        return self.populated_messages / self.total_messages


def analyze_field(
    messages: list[Message],
    spec: str,
    top: int = 20,
) -> FieldReport:
    """Compute fill rate and value distribution for one field spec."""
    populated_messages = 0
    total_occurrences = 0
    populated_occurrences = 0
    values: Counter[str] = Counter()

    for msg in messages:
        occ = msg.field_all(spec)
        total_occurrences += len(occ)
        msg_has = False
        for v in occ:
            if v.strip():
                populated_occurrences += 1
                values[v] += 1
                msg_has = True
        if msg_has:
            populated_messages += 1

    return FieldReport(
        spec=spec,
        total_messages=len(messages),
        populated_messages=populated_messages,
        total_occurrences=total_occurrences,
        populated_occurrences=populated_occurrences,
        unique_values=len(values),
        top_values=values.most_common(top),
    )


def fillrate_frame(reports: list[FieldReport]) -> pd.DataFrame:
    """Summary DataFrame, one row per field spec."""
    rows = []
    for r in reports:
        rows.append(
            {
                "field": r.spec,
                "messages": r.total_messages,
                "populated": r.populated_messages,
                "fill_rate": round(r.fill_rate, 4),
                "occurrences": r.total_occurrences,
                "unique_values": r.unique_values,
            }
        )
    return pd.DataFrame(rows)


def values_frame(report: FieldReport, all_values: bool = False) -> pd.DataFrame:
    """Value-distribution DataFrame for a single field."""
    items = report.top_values
    if all_values:
        # top_values already holds most_common(top); for --all-values the caller
        # should have requested top=0 (unbounded). Guard anyway.
        pass
    return pd.DataFrame(items, columns=["value", "count"])


def fillrate_by_message_type(
    messages: list[Message],
    spec: str,
) -> pd.DataFrame:
    """Break one field's fill rate down by MSH-9 trigger event.

    Surfaces cases like PV1-19 being well-populated on A01 but empty on A08.
    """
    by_type: dict[str, list[Message]] = {}
    for msg in messages:
        key = msg.message_type or "(unknown)"
        by_type.setdefault(key, []).append(msg)

    rows = []
    for mtype, msgs in sorted(by_type.items()):
        r = analyze_field(msgs, spec, top=0)
        rows.append(
            {
                "message_type": mtype,
                "field": spec,
                "messages": r.total_messages,
                "populated": r.populated_messages,
                "fill_rate": round(r.fill_rate, 4),
                "unique_values": r.unique_values,
            }
        )
    return pd.DataFrame(rows)
