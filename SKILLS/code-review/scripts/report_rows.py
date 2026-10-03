#!/usr/bin/env python3
"""Read the rows of the findings tables of a review report.

Used by settle_rows.py and fix_code.py. The columns are found by the names
in the header row of each table (ID, Severity, Line or Where, Code, Kind or
What is wrong, Fix, Decision), so a report whose other columns were renamed, added or moved is
still read correctly. Python standard library only.
"""
import re

CELL = re.compile(r"(?<!\\)\|")
WANTED = (("id", lambda h: h in ("id", "#")), ("severity", lambda h: h.startswith("severity")),
          ("line", lambda h: h.startswith("line") or h == "where"), ("code", lambda h: "code" in h or "quoted" in h),
          ("kind", lambda h: h.startswith("kind") or h.startswith("what is wrong")), ("fix", lambda h: h.startswith("fix")),
          ("decision", lambda h: h.startswith("decision")))     # "Where" and "What is wrong": the review of a change


def cells(row):
    return [c.strip() for c in CELL.split(row)]


def columns(header):
    """Where each known column is in a header row: {"line": 3, ...}; empty when it is not a findings table."""
    found = {}
    for i, h in enumerate(cells(header)):
        for name, test in WANTED:
            if name not in found and h and test(h.lower()):
                found[name] = i
    return found if "id" in found and "line" in found else {}


def rows(lines):
    """Yield (index of the line, its cells, the column map) for every row of a findings table."""
    cols = {}
    for i, line in enumerate(lines):
        if not line.startswith("|"):
            cols = {} if line.strip() else cols          # a table ends at the first line that is not a row
            continue
        c = cells(line)
        if columns(line):
            cols = columns(line)
        elif cols and len(c) > cols["id"] and re.match(r"[A-Z]-\d+$", c[cols["id"]]):
            yield i, c, cols


def join(c):
    return "| " + " | ".join(c[1:-1]) + " |"
