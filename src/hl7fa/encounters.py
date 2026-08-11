"""Reconstruct encounters and patients from a flat HL7 v2 ADT stream.

Messages -> encounters (by account OR visit number) -> patients (by MRN).
Surfaces the data-quality questions that motivate the whole tool:
admits without discharges, discharges without admits, orphaned messages,
and visit/account numbers colliding across MRNs.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field as dc_field

import pandas as pd

from .parser import Message


# Default field specs. MRN and the two encounter keys are configurable at the
# CLI so sites with non-standard PID-3 usage can adapt.
DEFAULT_MRN_SPEC = "PID-3.1"          # first component of first PID-3 rep
DEFAULT_ACCOUNT_SPEC = "PID-18.1"     # account number
DEFAULT_VISIT_SPEC = "PV1-19.1"       # visit number

ADMIT_TRIGGERS = {"A01", "A04"}       # admit / register
DISCHARGE_TRIGGERS = {"A03"}          # discharge
CANCEL_ADMIT_TRIGGERS = {"A11"}       # cancel admit


@dataclass
class Encounter:
    key: str
    mrn: str
    messages: list[Message] = dc_field(default_factory=list)

    @property
    def triggers(self) -> list[str]:
        return [m.trigger_event for m in self.messages]

    @property
    def has_admit(self) -> bool:
        return any(t in ADMIT_TRIGGERS for t in self.triggers)

    @property
    def has_discharge(self) -> bool:
        return any(t in DISCHARGE_TRIGGERS for t in self.triggers)


@dataclass
class GroupingResult:
    encounters: dict[str, Encounter]                 # key -> Encounter
    patient_encounters: dict[str, set[str]]          # mrn -> {encounter keys}
    orphaned: list[Message]                          # no encounter key
    key_collisions: dict[str, set[str]]              # enc key -> {mrns}
    encounter_key_spec: str
    mrn_spec: str


def group(
    messages: list[Message],
    encounter_key: str = "account",
    mrn_spec: str = DEFAULT_MRN_SPEC,
    account_spec: str = DEFAULT_ACCOUNT_SPEC,
    visit_spec: str = DEFAULT_VISIT_SPEC,
) -> GroupingResult:
    """Group messages into encounters and patients.

    ``encounter_key`` is 'account' or 'visit' — the explicit per-run choice.
    """
    if encounter_key == "account":
        key_spec = account_spec
    elif encounter_key == "visit":
        key_spec = visit_spec
    else:
        raise ValueError("encounter_key must be 'account' or 'visit'")

    encounters: dict[str, Encounter] = {}
    patient_encounters: dict[str, set[str]] = defaultdict(set)
    orphaned: list[Message] = []
    key_to_mrns: dict[str, set[str]] = defaultdict(set)

    for msg in messages:
        mrn = msg.field(mrn_spec).strip()
        key = msg.field(key_spec).strip()
        if not key:
            orphaned.append(msg)
            continue
        enc = encounters.get(key)
        if enc is None:
            enc = Encounter(key=key, mrn=mrn)
            encounters[key] = enc
        enc.messages.append(msg)
        if mrn:
            patient_encounters[mrn].add(key)
            key_to_mrns[key].add(mrn)

    collisions = {k: v for k, v in key_to_mrns.items() if len(v) > 1}

    return GroupingResult(
        encounters=encounters,
        patient_encounters=dict(patient_encounters),
        orphaned=orphaned,
        key_collisions=collisions,
        encounter_key_spec=key_spec,
        mrn_spec=mrn_spec,
    )


def integrity_frame(result: GroupingResult) -> pd.DataFrame:
    """One row per encounter with admit/discharge status flags."""
    rows = []
    for key, enc in result.encounters.items():
        rows.append(
            {
                "encounter": key,
                "mrn": enc.mrn,
                "messages": len(enc.messages),
                "has_admit": enc.has_admit,
                "has_discharge": enc.has_discharge,
                "admit_no_discharge": enc.has_admit and not enc.has_discharge,
                "discharge_no_admit": enc.has_discharge and not enc.has_admit,
                "triggers": ",".join(t for t in enc.triggers if t),
            }
        )
    return pd.DataFrame(rows)


def summary(result: GroupingResult) -> dict:
    """Headline counts for the feed."""
    encs = list(result.encounters.values())
    msgs_per_enc = [len(e.messages) for e in encs]
    admit_no_dis = [e for e in encs if e.has_admit and not e.has_discharge]
    dis_no_admit = [e for e in encs if e.has_discharge and not e.has_admit]
    encs_per_pt = [len(v) for v in result.patient_encounters.values()]
    return {
        "patients": len(result.patient_encounters),
        "encounters": len(encs),
        "orphaned_messages": len(result.orphaned),
        "key_collisions": len(result.key_collisions),
        "admits_without_discharge": len(admit_no_dis),
        "discharges_without_admit": len(dis_no_admit),
        "avg_messages_per_encounter": round(
            sum(msgs_per_enc) / len(msgs_per_enc), 2
        ) if msgs_per_enc else 0,
        "max_messages_per_encounter": max(msgs_per_enc) if msgs_per_enc else 0,
        "avg_encounters_per_patient": round(
            sum(encs_per_pt) / len(encs_per_pt), 2
        ) if encs_per_pt else 0,
    }


def timeline(result: GroupingResult, *, mrn: str | None = None,
             encounter: str | None = None) -> pd.DataFrame:
    """Ordered event sequence for one patient (by MRN) or one encounter."""
    rows = []
    if encounter is not None:
        enc = result.encounters.get(encounter)
        targets = [enc] if enc else []
    elif mrn is not None:
        keys = result.patient_encounters.get(mrn, set())
        targets = [result.encounters[k] for k in keys if k in result.encounters]
    else:
        targets = []

    for enc in targets:
        for m in enc.messages:
            rows.append(
                {
                    "encounter": enc.key,
                    "mrn": enc.mrn,
                    "message_type": m.message_type,
                    "trigger": m.trigger_event,
                    "msh_datetime": m.field("MSH-7"),
                    "control_id": m.field("MSH-10"),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty and "msh_datetime" in df.columns:
        df = df.sort_values("msh_datetime", kind="stable").reset_index(drop=True)
    return df
