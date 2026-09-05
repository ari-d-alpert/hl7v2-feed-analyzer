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


@pytest.fixture
def varied_feed(tmp_path):
    """Three distinct MRNs, so a value distribution has something to truncate."""
    p = tmp_path / "varied.hl7"
    p.write_text("\r\r".join([_msg("A01", f"M{i}", f"ACCT{i}", f"VIS{i}", i)
                              for i in (1, 2, 3)]), encoding="utf-8")
    return str(p)


def _value_rows(output):
    """Rows of the trailing value-distribution CSV, box-glyph independent."""
    lines = [ln for ln in output.splitlines() if ln.strip()]
    start = lines.index("value,count")
    return lines[start + 1:]


def test_values_top_zero_shows_all(varied_feed):
    """Regression: --top 0 is documented as 'all' but printed nothing,
    because Counter.most_common(0) returns an empty list."""
    r = _run("fillrate", varied_feed, "PID-3.1", "--values", "--top", "0",
             "--format", "csv")
    assert r.exit_code == 0
    assert len(_value_rows(r.output)) == 3


def test_values_top_n_truncates(varied_feed):
    r = _run("fillrate", varied_feed, "PID-3.1", "--values", "--top", "2",
             "--format", "csv")
    assert r.exit_code == 0
    assert len(_value_rows(r.output)) == 2


def test_negative_top_is_rejected(varied_feed):
    """A negative cap is nonsense; click should reject it rather than let it
    fall through to mean 'all'."""
    r = _run("fillrate", varied_feed, "PID-3.1", "--values", "--top", "-1")
    assert r.exit_code != 0


@pytest.fixture
def tree(tmp_path):
    """Three files at the top level, one more in a subdirectory."""
    (tmp_path / "sub").mkdir()
    for i, rel in enumerate(["a.txt", "b.txt", "c.txt", "sub/d.txt"], start=1):
        (tmp_path / rel).write_text(_msg("A01", f"M{i}", f"ACCT{i}", f"VIS{i}", i),
                                    encoding="utf-8")
    return tmp_path


def _mrns(output):
    rows = [ln for ln in output.splitlines() if ln.startswith("M")]
    return sorted(r.split(",")[0] for r in rows)


def _distribution(tmp_path_args):
    return ["fillrate", *tmp_path_args, "-f", "PID-3.1", "--values",
            "--format", "csv", "--top", "0"]


def test_multiple_paths_aggregate(tree):
    """The point of -f: a shell glob expands to many paths, all analyzed."""
    files = [str(tree / n) for n in ("a.txt", "b.txt", "c.txt")]
    r = _run(*_distribution(files))
    assert r.exit_code == 0
    assert _mrns(r.output) == ["M1", "M2", "M3"]


def test_directory_is_recursive_by_default(tree):
    r = _run(*_distribution([str(tree)]))
    assert _mrns(r.output) == ["M1", "M2", "M3", "M4"]


def test_no_recursive_skips_subdirectories(tree):
    r = _run(*_distribution([str(tree)]), "--no-recursive")
    assert _mrns(r.output) == ["M1", "M2", "M3"]


def test_overlapping_paths_are_counted_once(tree):
    """A file named twice, and also reachable via a directory argument, must
    not inflate the counts."""
    both = _run(*_distribution([str(tree / "a.txt"), str(tree / "a.txt"), str(tree)]))
    dir_only = _run(*_distribution([str(tree)]))
    assert _mrns(both.output) == _mrns(dir_only.output)
    assert "from 4 file(s)" in both.output


def test_legacy_positional_form_still_works(tree):
    """PATH FIELD... predates -f and is all over the README."""
    r = _run("fillrate", str(tree / "a.txt"), "PID-3.1", "--format", "csv")
    assert r.exit_code == 0
    assert "from 1 file(s)" in r.output


def test_positional_form_requires_a_field(tree):
    r = _run("fillrate", str(tree / "a.txt"))
    assert r.exit_code != 0
    assert "at least one field" in r.output


def test_encounters_accepts_multiple_paths(tree):
    files = [str(tree / n) for n in ("a.txt", "b.txt")]
    r = _run("encounters", *files, "--encounter-key", "visit", "--format", "csv")
    assert r.exit_code == 0
    assert "from 2 file(s)" in r.output


def test_encounters_no_recursive(tree):
    deep = _run("encounters", str(tree), "--format", "csv")
    flat = _run("encounters", str(tree), "--no-recursive", "--format", "csv")
    assert "from 4 file(s)" in deep.output
    assert "from 3 file(s)" in flat.output
