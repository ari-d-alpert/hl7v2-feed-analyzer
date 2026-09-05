# hl7v2-feed-analyzer

Population-level analysis for HL7 v2 feeds. Report field **fill rates** and value distributions across a whole corpus, and **reconstruct encounters and patients** from an ADT stream, the questions you have to answer before you can build against a new interface.

> **Why this exists.** Parsing HL7 v2 is a solved problem. There are excellent libraries in every language (HAPI, hl7apy, python-hl7) and a dozen single-message viewers that pretty-print one message into readable segments. But those stop at the message. None of them answer *population-level* questions across a feed, and none reconstruct encounters from an ADT stream. That logic lives inside proprietary integration engines, or in a script each of us rewrites at every job. This is that script, made into a tool.

## What it does

**Fill rates** — for any field you name (in `SEG-N[.C[.S]]` notation), across every message in the feed: how often it's populated, how many unique values, and the value distribution. Handles repeating segments (DG1, IN1, NK1, OBX) and repeating fields, and can break a field's fill rate down by MSH-9 trigger event.

**Encounter reconstruction** — group messages into encounters (by **account number** *or* **visit number**, your choice per run) and encounters into patients (by MRN). Surfaces the data-quality problems that matter: admits with no discharge, discharges with no admit, orphaned messages with no encounter key, and the same visit/account number colliding across two MRNs.

## Install

```bash
# create and activate a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1     # Windows (PowerShell)
source .venv/bin/activate      # macOS / Linux

pip install -e .
# or, with dev deps for the test suite:
pip install -e ".[dev]"
```

This installs an `hl7fa` command onto the activated environment's PATH. Without
activating, call it by path instead: `.venv/bin/hl7fa` (or
`.venv\Scripts\hl7fa.exe` on Windows).

## Usage

The synthetic sample feed (safe, fabricated data) ships with the repo at
`sample/adt_feed.hl7`. Regenerate it if you want to:

```bash
python sample/generate_sample.py
```

Generation is seeded, so the IDs used in the examples below stay stable.

### Fill rates

```bash
# fill rate + unique counts for several fields
hl7fa fillrate sample/adt_feed.hl7 PID-3.1 PV1-2 PID-18 PV1-19

# show the value distribution for a field
hl7fa fillrate sample/adt_feed.hl7 PV1-2 --values --top 10

# break a field's fill rate down by message type (e.g. PV1-19 on A01 vs A08)
hl7fa fillrate sample/adt_feed.hl7 PV1-19 --by-message-type

# export instead of printing
hl7fa fillrate sample/adt_feed.hl7 PID-3.1 --format csv --out fillrates.csv
```

### Encounters

```bash
# headline summary, grouping by visit number
hl7fa encounters sample/adt_feed.hl7 --encounter-key visit

# same feed, grouped by account number — results differ, which is the point
hl7fa encounters sample/adt_feed.hl7 --encounter-key account

# per-encounter admit/discharge integrity table
hl7fa encounters sample/adt_feed.hl7 --encounter-key visit --integrity

# ordered event timeline for one patient or one encounter
hl7fa encounters sample/adt_feed.hl7 --timeline mrn:MRN1000

# encounter timelines are looked up under the active --encounter-key,
# so pass the same key the ID belongs to
hl7fa encounters sample/adt_feed.hl7 --encounter-key visit --timeline enc:VN9000
```

Field specs for MRN, account, and visit are configurable (`--mrn-spec`, `--account-spec`, `--visit-spec`) for sites with non-standard PID-3 usage.

## Design notes

The parser is intentionally minimal and **lenient** — it does positional field extraction by delimiter, reading the encoding characters from each message's MSH rather than assuming them, and skips anything malformed instead of raising. It does *not* model HL7 structure semantics (segment groups, data types), because fill-rate and encounter analysis don't need them. This keeps the tool zero-dependency at the parsing layer and impossible to break on "weird but legal" messages. If you need full structural parsing, `python-hl7` or `hl7apy` can be dropped in behind the one `Message.field()` method the rest of the tool depends on.

## Privacy & PHI

Runs entirely locally, no network calls. But **"does not exfiltrate" is not "HIPAA-compliant"** — no encryption at rest, no audit logging, no formal review. Use on real feeds only where you're authorized, and clear it with your compliance process first. See [SECURITY.md](SECURITY.md). The `.gitignore` blocks real HL7 files by default so you can't commit a feed by accident.

## Tests

```bash
pytest
```

Covers parser edge cases (MSH numbering, repeating segments, components, custom delimiters, malformed input) and the encounter logic (admit-without-discharge detection, account-vs-visit collision behavior).

## Roadmap

- HTML report output for sharing fill-rate and integrity summaries.
- Cross-field validation (e.g. PV1-19 populated but PID-18 empty, or MRN present without either key).
- Optional pluggable parser backend (`python-hl7` / `hl7apy`).

## License

MIT — see [LICENSE](LICENSE).
