"""Minimal, lenient HL7 v2.x parser.

Deliberately does NOT model HL7 structure semantics (segment groups, optionality,
data types). For feed analysis we only need positional field extraction by
``SEG-N`` / ``SEG-N.C`` / ``SEG-N.C.S`` notation, which is pure delimiter
splitting. This keeps the tool zero-dependency and impossible to break on
"weird but legal" messages.

Delimiters are read from each message's MSH segment rather than assumed, so
non-standard encoding characters are handled. Parsing is lenient: anything that
doesn't look like a segment is skipped, never raised.

If you prefer a full library, ``python-hl7`` or ``hl7apy`` can be swapped in
behind ``Message.field()`` — the rest of the tool only depends on that method.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Iterator


# Default HL7 encoding characters (MSH-1 is field sep '|', MSH-2 is '^~\&').
DEFAULT_FIELD_SEP = "|"
DEFAULT_COMPONENT_SEP = "^"
DEFAULT_REPETITION_SEP = "~"
DEFAULT_ESCAPE = "\\"
DEFAULT_SUBCOMPONENT_SEP = "&"


@dataclass
class Delimiters:
    field: str = DEFAULT_FIELD_SEP
    component: str = DEFAULT_COMPONENT_SEP
    repetition: str = DEFAULT_REPETITION_SEP
    escape: str = DEFAULT_ESCAPE
    subcomponent: str = DEFAULT_SUBCOMPONENT_SEP

    @classmethod
    def from_msh(cls, msh_line: str) -> "Delimiters":
        """Derive delimiters from a raw MSH segment line.

        MSH-1 is the field separator (the char right after 'MSH'); MSH-2 holds
        the component, repetition, escape, and subcomponent separators.
        """
        d = cls()
        if len(msh_line) < 4 or not msh_line.startswith("MSH"):
            return d
        d.field = msh_line[3]
        enc = msh_line[4:].split(d.field, 1)[0]  # MSH-2, up to next field sep
        if len(enc) >= 1:
            d.component = enc[0]
        if len(enc) >= 2:
            d.repetition = enc[1]
        if len(enc) >= 3:
            d.escape = enc[2]
        if len(enc) >= 4:
            d.subcomponent = enc[3]
        return d


@dataclass
class Message:
    """One parsed HL7 message: its raw segments plus derived delimiters."""

    segments: list[list[str]]  # each segment already split into fields
    delimiters: Delimiters
    raw: str = ""

    @property
    def message_type(self) -> str:
        """MSH-9 as 'MSG^TRIGGER' (e.g. 'ADT^A01'), best-effort."""
        val = self.field("MSH-9")
        return val or ""

    @property
    def trigger_event(self) -> str:
        """MSH-9.2 trigger event (e.g. 'A01'), best-effort."""
        return self.field("MSH-9.2") or ""

    def segment(self, seg_id: str) -> list[list[str]]:
        """All segments with the given 3-char id (e.g. every 'DG1')."""
        return [s for s in self.segments if s and s[0] == seg_id]

    def field(self, spec: str, repetition: int = 0) -> str:
        """Extract a value by 'SEG-N', 'SEG-N.C', or 'SEG-N.C.S' notation.

        Returns the first matching segment's value. For repeating segments use
        :meth:`field_all`. MSH is special-cased: MSH-1 is the field separator
        itself, and the encoding-chars field shifts subsequent numbering, which
        this handles so MSH-9 etc. behave as users expect.

        Missing/out-of-range positions return '' (lenient).
        """
        vals = self.field_all(spec)
        if not vals:
            return ""
        if repetition < len(vals):
            return vals[repetition]
        return ""

    def field_all(self, spec: str) -> list[str]:
        """Like :meth:`field` but returns every repetition (~-separated) and,
        for repeating segments, every segment occurrence flattened in order."""
        seg_id, f_idx, c_idx, s_idx = _parse_spec(spec)
        out: list[str] = []
        for seg in self.segment(seg_id):
            raw = _get_field_raw(seg, seg_id, f_idx, self.delimiters)
            for rep in raw.split(self.delimiters.repetition):
                out.append(_narrow(rep, c_idx, s_idx, self.delimiters))
        return out

    def is_populated(self, spec: str) -> bool:
        """True if any occurrence of the field has a non-empty value."""
        return any(v.strip() for v in self.field_all(spec))


def _parse_spec(spec: str) -> tuple[str, int, int | None, int | None]:
    """'PID-3.1' -> ('PID', 3, 1, None). Component/subcomponent are 1-based in
    HL7 notation; field index is 1-based too. Returns raw (1-based) indices."""
    spec = spec.strip().upper()
    if "-" not in spec:
        raise ValueError(f"Bad field spec {spec!r}; expected SEG-N[.C[.S]]")
    seg_id, rest = spec.split("-", 1)
    parts = rest.split(".")
    f_idx = int(parts[0])
    c_idx = int(parts[1]) if len(parts) > 1 else None
    s_idx = int(parts[2]) if len(parts) > 2 else None
    return seg_id, f_idx, c_idx, s_idx


def _get_field_raw(seg: list[str], seg_id: str, f_idx: int, d: Delimiters) -> str:
    """Return the raw (still component/rep-delimited) field string at 1-based
    f_idx, accounting for the MSH numbering quirk."""
    if seg_id == "MSH":
        # In MSH, field 1 is the field separator char, field 2 is the encoding
        # chars. seg[0]=='MSH', seg[1]==encoding-chars (because splitting 'MSH|^~\&|..'
        # on '|' yields ['MSH','^~\&',...]). So MSH-1 -> the separator itself,
        # MSH-2 -> seg[1], MSH-N (N>=2) -> seg[N-1].
        if f_idx == 1:
            return d.field
        idx = f_idx - 1
    else:
        idx = f_idx
    if 0 <= idx < len(seg):
        return seg[idx]
    return ""


def _narrow(value: str, c_idx: int | None, s_idx: int | None, d: Delimiters) -> str:
    """Drill into component / subcomponent if requested (1-based)."""
    if c_idx is None:
        return value
    comps = value.split(d.component)
    if not (1 <= c_idx <= len(comps)):
        return ""
    comp = comps[c_idx - 1]
    if s_idx is None:
        return comp
    subs = comp.split(d.subcomponent)
    if not (1 <= s_idx <= len(subs)):
        return ""
    return subs[s_idx - 1]


def _split_segments(text: str, d: Delimiters) -> list[list[str]]:
    segments = []
    # HL7 segments are CR-delimited by spec, but real feeds use \n or \r\n too.
    for line in text.replace("\r\n", "\r").replace("\n", "\r").split("\r"):
        line = line.strip()
        if not line:
            continue
        segments.append(line.split(d.field))
    return segments


def parse_message(text: str) -> Message:
    """Parse one message's text into a :class:`Message`."""
    text = text.strip()
    # Find MSH to derive delimiters; fall back to defaults if absent.
    msh_line = ""
    for line in text.replace("\r\n", "\r").replace("\n", "\r").split("\r"):
        if line.startswith("MSH"):
            msh_line = line
            break
    delims = Delimiters.from_msh(msh_line) if msh_line else Delimiters()
    segments = _split_segments(text, delims)
    return Message(segments=segments, delimiters=delims, raw=text)
