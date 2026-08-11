# Security & Privacy

## No-network guarantee

`hl7v2-feed-analyzer` makes **zero network requests**. It reads local files,
computes statistics in memory, and writes output to your terminal or to files
you name. It does not phone home, fetch remote resources, upload messages, or
emit telemetry. The dependencies (`pandas`, `click`, `rich`) are local
computation and terminal-rendering libraries.

You can confirm this by reading the source — there is no HTTP client, socket,
or URL anywhere in the package.

## How your data is handled

- Messages are read from the path you pass and held in memory for the duration
  of the run. Nothing is written unless you pass `--out`.
- No caching, no persistent store, no history. The process exits and the data
  is gone.

## What this tool is NOT

**"Does not exfiltrate" is not the same as "HIPAA-compliant."** This tool does
**not** encrypt files at rest, does not log or audit access, and has not been
through any formal security review. The HL7 files on your disk are the real
exposure, and protecting them is your responsibility.

## Guidance for real PHI

- **Synthetic data**: the included `sample/` corpus is fabricated and safe to
  use anywhere. Regenerate it with `python sample/generate_sample.py`.
- **Real feeds**: run only on a workstation you are already authorized to
  handle that data on, and clear it with whoever owns your organization's
  HIPAA/compliance process first. Do not treat this document as sign-off.
- The `.gitignore` in this repo blocks `*.hl7`, `*.txt`, `*.dat`, and
  `*.ndjson` by default (whitelisting only `sample/*.hl7`) specifically so you
  cannot accidentally `git add` a real feed. Keep that guard in place.

## Reporting a concern

If you find any behavior that transmits or persists data unexpectedly, please
open an issue describing what you observed.
