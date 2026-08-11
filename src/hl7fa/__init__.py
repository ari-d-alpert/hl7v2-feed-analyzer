"""hl7fa — HL7 v2 feed analyzer.

Population-level fill-rate and encounter-reconstruction analysis for HL7 v2
message corpora. Parsing is intentionally minimal and lenient; the value is in
the aggregation the message-level tools don't do.
"""
from .parser import Message, parse_message, Delimiters
from .loader import load, iter_messages, LoadResult
from .fillrate import analyze_field, fillrate_frame, values_frame, fillrate_by_message_type, FieldReport
from .encounters import group, integrity_frame, summary, timeline, GroupingResult

__version__ = "0.1.0"

__all__ = [
    "Message", "parse_message", "Delimiters",
    "load", "iter_messages", "LoadResult",
    "analyze_field", "fillrate_frame", "values_frame",
    "fillrate_by_message_type", "FieldReport",
    "group", "integrity_frame", "summary", "timeline", "GroupingResult",
]
