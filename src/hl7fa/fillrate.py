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
        """Share of messages carrying at least one non-empty occurrence."""
        if self.total_messages == 0:
            return 0.0
        return self.populated_messages / self.total_messages

    @property
    def occurrence_fill_rate(self) -> float:
        """Share of individual occurrences that are non-empty.

        Diverges from fill_rate on repeating segments: a message with three
        OBX, one of them empty, is fully populated message-wise but only 2/3
        populated occurrence-wise. For OBX/DG1/IN1/NK1 analysis this is
        usually the number you want.
        """
        if self.total_occurrences == 0:
            return 0.0
        return self.populated_occurrences / self.total_occurrences


def analyze_field(
    messages: list[Message],
    spec: str,
    top: int = 20,
) -> FieldReport:
    """Compute fill rate and value distribution for one field spec.

    ``top`` caps the retained value distribution; 0 keeps every distinct value.
    """
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
        # most_common(0) returns nothing; None is what means 'all'
        top_values=values.most_common(top if top > 0 else None),
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
                "occ_populated": r.populated_occurrences,
                "occ_fill_rate": round(r.occurrence_fill_rate, 4),
                "unique_values": r.unique_values,
            }
        )
    return pd.DataFrame(rows)


def values_frame(report: FieldReport) -> pd.DataFrame:
    """Value-distribution DataFrame for a single field.

    The distribution is already capped by the ``top`` passed to analyze_field.
    """
    return pd.DataFrame(report.top_values, columns=["value", "count"])


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
                "occurrences": r.total_occurrences,
                "occ_fill_rate": round(r.occurrence_fill_rate, 4),
                "unique_values": r.unique_values,
            }
        )
    return pd.DataFrame(rows)
