"""Generate a synthetic HL7 v2 ADT corpus for testing hl7fa.

Deliberately seeds anomalies so the analyzer has something to find:
- an admit with no discharge,
- a discharge with no admit,
- a message with no visit number (orphan),
- a visit number reused across two MRNs (collision),
- variable fill on PV1-19 across message types.

NO REAL PHI. All names/numbers are fabricated. Run:
    python sample/generate_sample.py
writes sample/adt_feed.hl7
"""
from __future__ import annotations

import os
import random

random.seed(42)

MSH = "MSH|^~\\&|SENDING_APP|SENDING_FAC|RECEIVING_APP|RECEIVING_FAC|{dt}||ADT^{trig}|{ctrl}|P|2.5"
EVN = "EVN|{trig}|{dt}"
PID = "PID|1|{mrn}|{mrn}^^^HOSP^MR||{last}^{first}||{dob}|{sex}|||{street}^^{city}^{state}^{zip}|||||||{acct}"
PV1 = "PV1|1|{cls}|{loc}||||||||||||||||{visit}"

FIRST = ["Alex", "Sam", "Jordan", "Casey", "Riley", "Morgan", "Taylor"]
LAST = ["Rivera", "Chen", "Okafor", "Nguyen", "Patel", "Munoz", "Kowalski"]
CITIES = [("Boston", "MA", "02118"), ("Providence", "RI", "02903"),
          ("Worcester", "MA", "01608"), ("Portland", "ME", "04101")]


def msg(trig, mrn, acct, visit, cls, seq):
    dt = f"202607{random.randint(10,28):02d}{random.randint(0,23):02d}{random.randint(0,59):02d}00"
    ctrl = f"MSG{seq:05d}"
    city, state, zc = random.choice(CITIES)
    lines = [
        MSH.format(dt=dt, trig=trig, ctrl=ctrl),
        EVN.format(trig=trig, dt=dt),
        PID.format(mrn=mrn, last=random.choice(LAST), first=random.choice(FIRST),
                   dob=f"19{random.randint(50,99)}{random.randint(1,12):02d}{random.randint(1,28):02d}",
                   sex=random.choice(["M", "F"]),
                   street=f"{random.randint(1,999)} Main St",
                   city=city, state=state, zip=zc, acct=acct),
        PV1.format(cls=cls, loc="3W^301^A", visit=visit),
    ]
    return "\r".join(lines)


def build():
    out = []
    seq = 1
    # 20 normal encounters: admit -> update -> discharge
    for i in range(20):
        mrn = f"MRN{1000+i}"
        acct = f"ACC{5000+i}"
        visit = f"VN{9000+i}"
        cls = random.choice(["I", "O", "E"])
        for trig in ["A01", "A08", "A03"]:
            out.append(msg(trig, mrn, acct, visit, cls, seq)); seq += 1

    # anomaly 1: admit, no discharge
    out.append(msg("A01", "MRN2001", "ACC6001", "VN9101", "I", seq)); seq += 1
    out.append(msg("A08", "MRN2001", "ACC6001", "VN9101", "I", seq)); seq += 1

    # anomaly 2: discharge, no admit
    out.append(msg("A03", "MRN2002", "ACC6002", "VN9102", "O", seq)); seq += 1

    # anomaly 3: orphan — no visit number and no account
    m = msg("A08", "MRN2003", "", "", "O", seq); seq += 1
    out.append(m)

    # anomaly 4: same visit number under two different MRNs (collision)
    out.append(msg("A01", "MRN2004", "ACC6004", "VN9104", "I", seq)); seq += 1
    out.append(msg("A01", "MRN2005", "ACC6005", "VN9104", "I", seq)); seq += 1

    return "\r\r".join(out)  # blank line between messages


if __name__ == "__main__":
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "adt_feed.hl7")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build())
    print(f"wrote {path}")
