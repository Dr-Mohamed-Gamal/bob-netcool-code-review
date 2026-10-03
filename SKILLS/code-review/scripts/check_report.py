#!/usr/bin/env python3
"""Check that a review report accounts for every hit of the scan.

    python3 check_report.py <report file> <code file-or-folder>

Runs scan_code.py on the code and looks in the report for each hit: its
line number must be there, and for a hit about a name, the name as well.
A hit may be in the findings or in the table of scan hits that are not
defects; this check only asks that nothing was left out.

Prints what is missing and ends with "Result: complete" or "Result: not
complete". Exit code 0 only when complete. It checks that each hit is
mentioned, not that what the report says about it is right.
"""
import argparse
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import report_rows  # noqa: E402
import scan_code  # noqa: E402

NAME_CHECKS = ("unset", "unread", "once", "unlisted", "twice", "writeback", "discard", "reapplied")


def cited_lines(text):
    """Every line number the report cites, ranges of up to 50 lines included."""
    cited = set()
    for a, b in re.findall(r"(?<![\w.])(\d{1,7})\s*(?:-|–|—|to)\s*(\d{1,7})(?![\w.])", text):
        a, b = int(a), int(b)
        if 0 < b - a <= 50:
            cited.update(range(a, b + 1))
    cited.update(int(x) for x in re.findall(r"(?<![\w.])(\d{1,7})(?![\w.])", text))
    return cited


def cited_in(cell):
    """The file named in a Line cell, if any, and the line numbers it cites (ranges of up to 50 lines included)."""
    m = re.match(r"^\s*([^:|]+?\.[A-Za-z0-9]+)\s*:", cell)
    return (m.group(1).strip() if m else None), cited_lines(cell[m.end():] if m else cell)


def wrong_quotes(text, scan):
    """Rows whose quoted code is not on the line they cite, nor within two lines of it."""
    flat = lambda t: re.sub(r"\s+", " ", re.sub(r"\\+\|", "|", t).replace("`", "'")).strip()
    wrong = []
    for _, c, cols in report_rows.rows(text.split("\n")):
        if "code" not in cols or cols["code"] >= len(c):
            continue
        spans = re.findall(r"`([^`]+)`", c[cols["code"]])
        fname, numbers = cited_in(c[cols["line"]])
        if not spans or not numbers:
            continue                                  # nothing quoted, or no line to look at
        files = [f for f in scan.lines if fname and Path(f).name == fname] or list(scan.lines)
        near = " ".join(flat(scan.lines[f][k - 1]) for f in files for n in sorted(numbers)
                        for k in range(n - 2, n + 3) if 0 < k <= len(scan.lines[f]))
        for span in spans:
            # a quote may be shortened with ... or hold several lines joined with / : one piece of it
            # that is on a cited line is enough; a quote with no piece there is wrong
            parts = [flat(x) for x in re.split(r"\s*(?:\.\.\.|\u2026|\s/\s)\s*", span) if len(x.strip()) >= 6] or [flat(span)]
            parts += [flat(x) for x in re.findall(r"'[^']{6,}'|\"[^\"]{6,}\"", span)]     # or a text it names
            if not any(part in near for part in parts):
                wrong.append((c[cols["id"]], c[cols["line"]], span))
                break
    return wrong


def account(scan, text):
    """Look in a report for every place the scan points at: (places, places found, what is missing)."""
    cited = cited_lines(text)
    total = found = 0
    missing = []
    for key, title, _ in scan_code.CHECKS:
        for f, line, note in sorted(set(scan.hits[key])):
            name = note.split(" — ")[0].split(" (")[0] if key in NAME_CHECKS else ""
            lines = [line]
            m = re.search(r"\bon lines? ([\d, ]+)", note)
            if m:
                lines = [int(x) for x in m.group(1).replace(" ", "").split(",") if x]
            name_there = not name or re.search(r"(?<![\w@$%%])%s(?!\w)" % re.escape(name), text) is not None
            for n in lines:
                total += 1
                if n in cited and name_there:
                    found += 1
                else:
                    what = "%s: line %d" % (name, n) if name else "line %d" % n
                    why = "the name is not in the report" if not name_there else "the line is not in the report"
                    code = scan.lines[f][n - 1].strip() if 0 < n <= len(scan.lines[f]) else ""
                    missing.append("%s — %s (%s)\n      %s" % (title, what, why, code[:140]))
    return total, found, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("report")
    ap.add_argument("code", nargs="+")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    ap.add_argument("--intent", help="the requirement document: the report must then say, requirement by "
                                     "requirement, what was found for it")
    args = ap.parse_args()

    report = Path(args.report)
    if not report.is_file():
        raise SystemExit("report not found: %s" % args.report)
    text = report.read_text(encoding="utf-8", errors="replace")
    scan, _ = scan_code.run(args.code, args.hash_comments)
    total, found, missing = account(scan, text)

    open_rows = [report_rows.join(c) for _, c, cols in report_rows.rows(text.split("\n"))
                 if (c[cols["decision"]] if "decision" in cols else c[-2]) == "To judge"]
    quotes = wrong_quotes(text, scan)
    severities = {"High": 0, "Medium": 0, "Low": 0}
    for _, c, cols in report_rows.rows(text.split("\n")):
        decision = c[cols["decision"]] if "decision" in cols else "Finding"
        level = c[cols["severity"]].split()[0].strip(":;,") if "severity" in cols and c[cols["severity"]] else ""
        if decision.startswith("Finding") and level in severities:
            severities[level] += 1
    intent_rows = None
    if args.intent:                              # the table under "Coverage of the intent" must have rows
        section = re.search(r"^## Coverage of the intent\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        table = [l for l in (section.group(1).split("\n") if section else []) if l.startswith("|")]
        intent_rows = max(0, len(table) - 2)
    print("Report: %s" % args.report)
    print("Places the scan points at: %d. In the report: %d. Missing: %d. Rows still marked \"To judge\": %d"
          % (total, found, len(missing), len(open_rows)))
    print("(A place is one line of one scan hit. One row of the report can cover several places.)")
    print("Findings by severity: %s." % ", ".join("%s %d" % (k, v) for k, v in severities.items()))
    if quotes:
        print("Rows whose quoted code is not on the line they cite, or within two lines of it: %d" % len(quotes))
        for row_id, where, span in quotes:
            print("  %s cites line %s for: %s" % (row_id, where, span[:110]))
    for m in missing:
        print("  %s" % m)
    for row in open_rows:
        print("  To judge: %s" % " | ".join(c.strip() for c in row.split("|")[1:4]))
    if intent_rows:
        print("Coverage of the intent: %d row(s) for %s." % (intent_rows, args.intent))
    if intent_rows == 0:
        print("  The table under \"Coverage of the intent\" is empty: add one row for each requirement of %s, "
              "with what was found for it or \"none found\"." % args.intent)
    done = not missing and not open_rows and intent_rows != 0 and not quotes
    print("Result: %s" % ("complete" if done else "not complete"))
    sys.exit(0 if done else 1)


if __name__ == "__main__":
    main()
