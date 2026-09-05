"""CLI-level tests: argument handling, lookup misses, and exit codes."""
import pytest
from click.testing import CliRunner

from hl7fa.cli import main


def _msg(trig, mrn, acct, visit, ctrl):
    return (
        f"MSH|^~\\&|S|F|R|RF|202601011200{ctrl:02d}||ADT^{trig}|C{ctrl}|P|2.5\r"
        f"EVN|{trig}|2026010112000{ctrl}\r"
        f"PID|1|{mrn}|{mrn}^^^HOSP^MR||Doe^Jane||19800101|F||||||||||{acct}\r"
        f"PV1|1|I|W^1^A||||||||||||||||{visit}\r"
    )


@pytest.fixture
def feed(tmp_path):
    """Small feed whose account and visit numbers are deliberately distinct,
    so a lookup under the wrong --encounter-key is detectable."""
    msgs = [
        _msg("A01", "M1", "ACCT1", "VIS1", 1),
        _msg("A08", "M1", "ACCT1", "VIS1", 2),
        _msg("A03", "M1", "ACCT1", "VIS1", 3),
    ]
    p = tmp_path / "feed.hl7"
    p.write_text("\r\r".join(msgs), encoding="utf-8")
    return str(p)


def _run(*args):
    # wide terminal so rich doesn't wrap the messages we assert on
    return CliRunner().invoke(main, list(args), env={"COLUMNS": "200"})


# --- timeline: success paths ---

def test_timeline_by_mrn(feed):
    r = _run("encounters", feed, "--timeline", "mrn:M1")
    assert r.exit_code == 0
    assert "A01" in r.output and "A08" in r.output and "A03" in r.output


def test_timeline_by_encounter_under_matching_key(feed):
    r = _run("encounters", feed, "--encounter-key", "visit", "--timeline", "enc:VIS1")
    assert r.exit_code == 0
    assert "VIS1" in r.output


# --- timeline: lookup misses ---

def test_timeline_visit_id_under_account_key_suggests_visit(feed):
    """The README's original mistake: a visit number looked up while grouping
    by account used to print nothing at all."""
    r = _run("encounters", feed, "--timeline", "enc:VIS1")
    assert r.exit_code == 1
    assert "No encounter matching" in r.output
    assert "--encounter-key=visit" in r.output


def test_timeline_account_id_under_visit_key_suggests_account(feed):
    r = _run("encounters", feed, "--encounter-key", "visit", "--timeline", "enc:ACCT1")
    assert r.exit_code == 1
    assert "--encounter-key=account" in r.output


def test_timeline_unknown_encounter_offers_no_suggestion(feed):
    """An ID that exists under neither key must not get a misleading hint."""
    r = _run("encounters", feed, "--timeline", "enc:NOSUCH")
    assert r.exit_code == 1
    assert "No encounter matching" in r.output
    assert "rerun with that flag" not in r.output


def test_timeline_unknown_mrn(feed):
    r = _run("encounters", feed, "--timeline", "mrn:NOSUCH")
    assert r.exit_code == 1
    assert "No MRN matching" in r.output
    assert "encounter-key" not in r.output  # MRN grouping is key-independent


def test_timeline_bad_prefix(feed):
    r = _run("encounters", feed, "--timeline", "garbage")
    assert r.exit_code == 1
    assert "mrn:VALUE or enc:VALUE" in r.output


def test_timeline_id_is_not_parsed_as_rich_markup(feed):
    """A bracketed ID must print literally, not be swallowed as markup."""
    r = _run("encounters", feed, "--timeline", "enc:[bold]x")
    assert r.exit_code == 1
    assert "[bold]x" in r.output


# --- other commands: smoke coverage of the emit paths ---

def test_fillrate_table(feed):
    r = _run("fillrate", feed, "PID-3.1", "PV1-19")
    assert r.exit_code == 0
    assert "PID-3.1" in r.output and "PV1-19" in r.output


def test_fillrate_csv_to_file(feed, tmp_path):
    out = tmp_path / "fr.csv"
    r = _run("fillrate", feed, "PID-3.1", "--format", "csv", "--out", str(out))
    assert r.exit_code == 0
    assert "field,messages,populated" in out.read_text(encoding="utf-8")


def test_encounters_summary(feed):
    r = _run("encounters", feed, "--encounter-key", "visit")
    assert r.exit_code == 0
    assert "encounter key: visit" in r.output


def test_no_messages_parsed_exits_nonzero(tmp_path):
    empty = tmp_path / "empty.hl7"
    empty.write_text("", encoding="utf-8")
    r = _run("encounters", str(empty))
    assert r.exit_code == 1
    assert "No messages parsed" in r.output
