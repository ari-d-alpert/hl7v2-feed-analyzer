"""Loader, fill-rate, and encounter-reconstruction tests."""
import os
import textwrap

import pytest

from hl7fa import (
    load,
    analyze_field,
    fillrate_by_message_type,
    group,
    summary,
    integrity_frame,
    timeline,
)
from hl7fa.parser import parse_message


def _msg(trig, mrn, acct, visit, ctrl):
    return (
        f"MSH|^~\\&|S|F|R|RF|202601011200{ctrl:02d}||ADT^{trig}|C{ctrl}|P|2.5\r"
        f"EVN|{trig}|2026010112000{ctrl}\r"
        f"PID|1|{mrn}|{mrn}^^^HOSP^MR||Doe^Jane||19800101|F||||||||||{acct}\r"
        f"PV1|1|I|W^1^A||||||||||||||||{visit}\r"
    )


@pytest.fixture
def feed(tmp_path):
    msgs = [
        _msg("A01", "M1", "A1", "V1", 1),
        _msg("A08", "M1", "A1", "V1", 2),
        _msg("A03", "M1", "A1", "V1", 3),
        _msg("A01", "M2", "A2", "V2", 4),   # admit, no discharge
        _msg("A03", "M3", "A3", "V3", 5),   # discharge, no admit
        _msg("A08", "M4", "", "", 6),        # orphan
        _msg("A01", "M5", "A5", "VDUP", 7),  # collision on visit
        _msg("A01", "M6", "A6", "VDUP", 8),
    ]
    p = tmp_path / "feed.hl7"
    p.write_text("\r\r".join(msgs), encoding="utf-8")
    return str(p)


def test_load(feed):
    r = load(feed)
    assert len(r.messages) == 8
    assert r.skipped == 0
    assert r.files_read == 1


def test_load_directory(feed, tmp_path):
    # a second file in the same dir
    (tmp_path / "extra.hl7").write_text(_msg("A01", "M9", "A9", "V9", 9), encoding="utf-8")
    r = load(str(tmp_path))
    assert len(r.messages) == 9
    assert r.files_read == 2


def test_fillrate(feed):
    r = load(feed)
    acct = analyze_field(r.messages, "PID-18")
    assert acct.total_messages == 8
    assert acct.populated_messages == 7  # one orphan blank
    assert abs(acct.fill_rate - 7 / 8) < 1e-9


def test_fillrate_by_message_type(feed):
    r = load(feed)
    df = fillrate_by_message_type(r.messages, "PV1-19")
    a01 = df[df["message_type"] == "ADT^A01"].iloc[0]
    assert a01["messages"] == 4


def test_encounter_grouping_visit(feed):
    r = load(feed)
    g = group(r.messages, encounter_key="visit")
    s = summary(g)
    assert s["orphaned_messages"] == 1
    assert s["key_collisions"] == 1           # VDUP under M5 and M6
    assert s["admits_without_discharge"] >= 1
    assert s["discharges_without_admit"] == 1


def test_encounter_grouping_account_vs_visit(feed):
    """The collision exists on visit (VDUP shared) but not on account (A5/A6 distinct)."""
    r = load(feed)
    by_visit = summary(group(r.messages, encounter_key="visit"))
    by_acct = summary(group(r.messages, encounter_key="account"))
    assert by_visit["key_collisions"] == 1
    assert by_acct["key_collisions"] == 0


def test_admit_without_discharge_flag(feed):
    r = load(feed)
    g = group(r.messages, encounter_key="account")
    df = integrity_frame(g)
    m2 = df[df["encounter"] == "A2"].iloc[0]
    assert bool(m2["admit_no_discharge"]) is True
    m1 = df[df["encounter"] == "A1"].iloc[0]
    assert bool(m1["admit_no_discharge"]) is False


def test_timeline(feed):
    r = load(feed)
    g = group(r.messages, encounter_key="account")
    df = timeline(g, encounter="A1")
    assert list(df["trigger"]) == ["A01", "A08", "A03"]  # sorted by MSH-7


def test_multi_message_batch_split(tmp_path):
    """Two messages in one file, blank-line separated, both parse."""
    blob = _msg("A01", "M1", "A1", "V1", 1) + "\r\r" + _msg("A03", "M1", "A1", "V1", 2)
    p = tmp_path / "batch.hl7"
    p.write_text(blob, encoding="utf-8")
    r = load(str(p))
    assert len(r.messages) == 2
