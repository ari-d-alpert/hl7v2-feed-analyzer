"""Parser and field-extraction tests, including the edge cases that bite:
MSH numbering, repeating segments, components/subcomponents, custom delimiters,
and lenient handling of malformed input."""
from hl7fa import parse_message
from hl7fa.parser import Delimiters


SAMPLE = (
    "MSH|^~\\&|SEND|FAC|RECV|RFAC|20260101120000||ADT^A01|CTRL1|P|2.5\r"
    "PID|1|MRN123|MRN123^^^HOSP^MR~ALT99^^^OTHER^MR||Doe^Jane^Q||19800101|F|||"
    "1 Main St^^Boston^MA^02118|||||||ACC777\r"
    "PV1|1|I|WEST^101^A||||||||||||||||VISIT555\r"
    "DG1|1||I10^Essential hypertension^ICD10\r"
    "DG1|2||E11.9^Type 2 diabetes^ICD10\r"
)


def test_basic_field():
    m = parse_message(SAMPLE)
    assert m.field("PID-3.1") == "MRN123"
    assert m.field("PV1-2") == "I"
    assert m.field("PID-18") == "ACC777"
    assert m.field("PV1-19") == "VISIT555"


def test_msh_numbering_quirk():
    """MSH-9 must resolve to the message type despite the field-separator offset."""
    m = parse_message(SAMPLE)
    assert m.field("MSH-9") == "ADT^A01"
    assert m.field("MSH-9.1") == "ADT"
    assert m.field("MSH-9.2") == "A01"
    assert m.field("MSH-10") == "CTRL1"
    assert m.trigger_event == "A01"
    assert m.message_type == "ADT^A01"


def test_components_and_subcomponents():
    m = parse_message(SAMPLE)
    assert m.field("PID-5.1") == "Doe"
    assert m.field("PID-5.2") == "Jane"
    assert m.field("PID-5.3") == "Q"


def test_repetitions():
    """PID-3 repeats (~); field_all should return every repetition."""
    m = parse_message(SAMPLE)
    all_ids = m.field_all("PID-3.1")
    assert all_ids == ["MRN123", "ALT99"]
    assert m.field("PID-3.1", repetition=1) == "ALT99"


def test_repeating_segments():
    """Two DG1 segments; field_all flattens across occurrences."""
    m = parse_message(SAMPLE)
    codes = m.field_all("DG1-3.1")
    assert codes == ["I10", "E11.9"]
    assert len(m.segment("DG1")) == 2


def test_missing_field_is_empty():
    m = parse_message(SAMPLE)
    assert m.field("PID-99") == ""
    assert m.field("ZZZ-3") == ""
    assert m.is_populated("PID-99") is False


def test_custom_delimiters():
    msg = "MSH#@%\\&#SEND#FAC#RECV#RFAC#20260101##ADT@A04#C2#P#2.5"
    m = parse_message(msg)
    assert m.delimiters.field == "#"
    assert m.delimiters.component == "@"
    assert m.field("MSH-9.2") == "A04"


def test_lenient_on_garbage():
    """Malformed input parses to something, never raises."""
    m = parse_message("not really hl7\r@@@@\r")
    assert m.field("PID-3") == ""  # no PID, empty, no crash


def test_crlf_and_lf_terminators():
    lf = SAMPLE.replace("\r", "\n")
    crlf = SAMPLE.replace("\r", "\r\n")
    assert parse_message(lf).field("PID-3.1") == "MRN123"
    assert parse_message(crlf).field("PID-3.1") == "MRN123"
