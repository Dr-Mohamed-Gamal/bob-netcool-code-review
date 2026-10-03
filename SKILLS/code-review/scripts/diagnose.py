#!/usr/bin/env python3
"""Diagnose a failure: from the symptom to the line that causes it, without changing the code.

    python3 diagnose.py <code file or folder> --out <report.md>

The first run writes the notes file next to the report. In it the person diagnosing writes the symptom, the
names it involves ("Look for"), the evidence, and the causes. Each run lists every line of the code that names
what is looked for, with the scan hits on those lines, and writes the report from the notes. A cause quotes the
line it is on and says whether the evidence shows it, rules it out, or which test decides it. The report is
complete when a cause is shown, or the open causes each name the test that would decide.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notes as notes_file  # noqa: E402
import scan_code  # noqa: E402

TITLE = "# Diagnosis"
NOT_PASSED = 3
STATUS = re.compile(r"^(shown|ruled out|open)\s*:\s*(.*)$", re.I)
CAUSE = re.compile(r"^#{3,4}\s*cause\s*:?\s*(?:(?P<file>[^:#\s]+?\.[A-Za-z0-9]+)\s*:\s*)?(?:line\s*)?(?P<line>\d+)\s*$", re.I)
SECTIONS = {"symptom": "symptom", "look for": "look", "evidence": "evidence", "causes": "causes", "cause": "causes",
            "fix proposed": "fix", "fix": "fix", "questions for the owner": "questions", "questions": "questions",
            "not checked": "not_checked"}
PER_TERM = 40                                    # lines listed for each name looked for


def cell(text):
    return re.sub(r"\s+", " ", str(text)).replace("|", "\\|").strip()


def code(text):
    return cell(text).replace("`", "'")


def around(line, term, width=220):
    """The part of a long line around the first place that holds the term."""
    if len(line) <= width:
        return line
    at = max(0, line.lower().find(term.lower()) - width // 3)
    return ("..." if at else "") + line[at:at + width] + ("..." if at + width < len(line) else "")


def read_notes(path):
    """The parts of the notes file: free text by section, and the cause blocks."""
    out = {k: [] for k in set(SECTIONS.values())}
    out["blocks"] = []
    if not path.is_file():
        return out, False
    text = re.sub(r"<!--.*?-->", lambda m: "\n" * m.group(0).count("\n"),
                  path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n"), flags=re.S)
    section, block, key = None, None, None
    for n, line in enumerate(text.split("\n"), 1):
        m = re.match(r"^##\s+(.*)$", line)
        if m and not line.startswith("###"):
            title = m.group(1).strip().lower()
            section = next((v for k, v in SECTIONS.items() if title.startswith(k)), None)
            block, key = None, None
            continue
        if section == "causes":
            m = CAUSE.match(line.strip())
            if m:
                block = {"file": m.group("file"), "line": int(m.group("line")), "at": n}
                out["blocks"].append(block)
                key = None
                continue
            k = re.match(r"^(quote|how|status)\s*:\s*(.*)$", line.strip(), re.I)
            if block is not None and k:
                key = k.group(1).lower()
                block[key] = k.group(2).strip()
            elif block is not None and key and line.strip():
                block[key] += " " + line.strip()
            elif line.strip() and not line.startswith("#"):
                out["causes"].append("line %d of the notes is not inside a block \"### cause line <number>\": %s"
                                     % (n, line.strip()[:80]))
            continue
        if section and line.strip():
            out[section].append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line.strip()))
    return out, True


def skeleton(report, command, scan, files):
    hits = sum(len(set(scan.hits[k])) for k, _, _ in scan_code.CHECKS)
    return "\n".join([
        "# Notes for the diagnosis %s" % report.name, "",
        "The report is written by the script from the code and from these notes. The code is not changed. After you",
        "change this file, run the command again:", "", "    %s" % command, "",
        "## Symptom",
        "<!-- One or two sentences: what goes wrong, where it is seen, in the words of the person who reported it. -->", "",
        "## Look for",
        "<!-- One per line: a name, a value or a text the symptom involves (an id, a field, a device, a message). The",
        "     script lists every line of the code that holds it, with the scan hits on those lines. -->", "",
        "## Evidence",
        "<!-- One per line: what is known besides the code (an error text, a log line, the input that triggers it, a",
        "     recent change), quoted, with where it comes from. Say what evidence is missing. -->", "",
        "## Causes",
        "<!-- One block for each possible cause, the most likely first:",
        "",
        "### cause line 120             (or ### cause rules.js: 120 when the code is several files)",
        "quote: a few words that are on that line",
        "how: how this line produces the symptom, following the value or the flow from the input to what is seen",
        "status: shown: <the evidence that shows it>",
        "        or ruled out: <the evidence that contradicts it>",
        "        or open: <the test that would decide it, and what each outcome means>",
        "",
        "     The diagnosis is complete when one cause is shown, or when every cause that is not ruled out names the",
        "     test that decides it. A scan hit on the path is a cause to consider, not yet the cause. -->", "",
        "## Fix proposed",
        "<!-- Optional: what would correct the cause, for the owner to decide. Nothing is changed by this task. -->", "",
        "## Questions for the owner",
        "<!-- One per line. -->", "",
        "## Not checked",
        "<!-- One per line. -->", "",
        "## Facts of the code (written by the script; not read back)",
        "%d file(s), %d scan hit(s). Run the command again after \"Look for\" is written: the report then lists every line "
        "that names what you look for." % (len(files), hits), ""])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("code")
    ap.add_argument("--out", required=True, help="the diagnosis report to write (Markdown)")
    ap.add_argument("--command", help="the command to show in the notes as the one to run again")
    ap.add_argument("--hash-comments", action="store_true")
    args = ap.parse_args()
    report = Path(args.out)
    notes_at = notes_file.notes_path(report)
    command = args.command or "python3 %s %s --out %s" % (sys.argv[0], args.code, args.out)
    scan, files = scan_code.run([args.code], args.hash_comments)
    if not files:
        raise SystemExit("no code found in %s" % args.code)
    by_name = {Path(str(f)).name: str(f) for f in files}
    lines = {str(f): [l.rstrip("\r") for l in scan.lines[str(f)]] for f in files}
    notes, exists = read_notes(notes_at)
    if not exists:
        notes_at.parent.mkdir(parents=True, exist_ok=True)
        notes_at.write_text(skeleton(report, command, scan, files), encoding="utf-8")
    problems = [p for p in notes["causes"] if p.startswith("line ")]
    many = len(files) > 1
    where = lambda f, n: "%s:%d" % (Path(f).name, n) if many else str(n)

    # ---- every line that names what is looked for, and the scan hits on those lines
    terms = [t.strip("`\"' ") for t in notes["look"] if t.strip("`\"' ")]
    named, missing = [], []
    for t in terms:
        found = [(f, n, l) for f in lines for n, l in enumerate(lines[f], 1) if t.lower() in l.lower()]
        (named.append((t, found)) if found else missing.append(t))
    on_path = {(f, n) for _, found in named for f, n, _ in found}
    titles = {k: title for k, title, _ in scan_code.CHECKS}
    hits = sorted({(f, n, titles.get(k, k), note) for k in scan.hits for f, n, note in set(scan.hits[k])
                   if (f, n) in on_path}, key=lambda h: (h[0], h[1]))

    # ---- the causes
    causes = []
    for i, b in enumerate(notes["blocks"], 1):
        cid, label = "K-%02d" % i, "the cause on line %d (line %d of the notes)" % (b["line"], b["at"])
        target = by_name.get(Path(b["file"]).name) if b["file"] else (str(files[0]) if len(files) == 1 else None)
        if target is None:
            problems.append("%s: say which file, as in \"### cause rules.js: %d\"." % (label, b["line"]))
            continue
        text = lines[target][b["line"] - 1] if 0 < b["line"] <= len(lines[target]) else ""
        want = re.sub(r"\s+", " ", (b.get("quote") or "").strip().strip("`\""))
        if not want or want not in re.sub(r"\s+", " ", text):
            problems.append("%s: \"quote:\" must be words that are on line %d of %s. That line reads: %s"
                            % (label, b["line"], Path(target).name, text.strip()[:160] or "(no such line)"))
        if len(b.get("how", "")) < 20:
            problems.append("%s: \"how:\" is missing or too short: say how the line produces the symptom." % label)
        st = STATUS.match(b.get("status", "").strip())
        if not st or len(st.group(2).strip()) < 10:
            problems.append("%s: \"status:\" is \"shown: <evidence>\", \"ruled out: <evidence>\" or \"open: <the test "
                            "that decides>\"." % label)
        causes.append((cid, where(target, b["line"]), text.strip(), b.get("how", ""),
                       st.group(1).lower() if st else "", st.group(2).strip() if st else b.get("status", "")))
    if exists:
        if len(" ".join(notes["symptom"])) < 15:
            problems.append("\"Symptom\" is not written: one or two sentences, in the words of the person who reported it.")
        if not terms:
            problems.append("\"Look for\" is empty: one name, value or text per line that the symptom involves.")
        if not causes:
            problems.append("No cause is written yet under \"Causes\".")
        elif not any(s in ("shown", "open") for _, _, _, _, s, _ in causes):
            problems.append("Every cause is ruled out: look further along the path, and write the next cause.")

    # ---- the report
    shown = [c for c in causes if c[4] == "shown"]
    opened = [c for c in causes if c[4] == "open"]
    verdict = ("The cause is shown: %s." % "; ".join("%s (line %s)" % (c[0], c[1]) for c in shown) if shown else
               "The cause is not shown yet; %d cause(s) are open, each with the test that decides it." % len(opened)
               if opened else "No cause is shown or open yet.")
    md = [TITLE + " — %s" % args.code, "",
          "Written by the diagnosis script from the code and from the notes in %s. The code is not changed. Do not edit "
          "this file: write in the notes and run the script again." % notes_at.name, "",
          "## Verdict", verdict + " Nothing was run.", "",
          "## Symptom", " ".join(notes["symptom"]) or "Not written yet.", "",
          "## Causes", "| ID | Line | The line, quoted | How it produces the symptom | Status | Evidence or test |",
          "|---|---|---|---|---|---|"]
    md += ["| %s | %s | `%s` | %s | %s | %s |" % (c[0], c[1], code(c[2][:200]), cell(c[3]), c[4] or "NOT GIVEN", cell(c[5]))
           for c in causes] or ["| | | | Not written yet. | | |"]
    md += ["", "## Lines that name what the symptom involves"]
    for t, found in named:
        md += ["", "`%s` — %d line(s)%s:" % (code(t), len(found), ", the first %d shown" % PER_TERM if len(found) > PER_TERM else ""), ""]
        md += ["- line %s: `%s`" % (where(f, n), code(around(l.strip(), t))) for f, n, l in found[:PER_TERM]]
    if missing:
        md += ["", "Not found anywhere in the code: %s. What the symptom names there comes from outside this code "
               "(the data, another file, the platform)." % ", ".join("`%s`" % code(t) for t in missing)]
    if not terms:
        md += ["", "Nothing is looked for yet."]
    md += ["", "## Scan hits on those lines", "| Line | Kind | Note |", "|---|---|---|"]
    md += ["| %s | %s | %s |" % (where(f, n), cell(k), cell(note)) for f, n, k, note in hits] or ["| | None | |"]
    md += ["", "## Evidence"] + (["- %s" % e for e in notes["evidence"]] or ["- None given."])
    md += ["", "## Fix proposed"] + ([" ".join(notes["fix"])] if notes["fix"] else ["None proposed. Nothing was changed."])
    md += ["", "## Questions for the owner of the code"] + (["%d. %s" % (i, q) for i, q in enumerate(notes["questions"], 1)]
                                                           or ["1. None."])
    md += ["", "## Not checked", "- Nothing was run. The diagnosis is a reading of the code and of the evidence given."]
    md += ["- %s" % x for x in notes["not_checked"]]
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("Diagnosis: %s (written by this command; do not edit it)" % report)
    print("  Looked for: %s" % (", ".join("%s (%d line(s))" % (t, len(f)) for t, f in named) or "nothing yet")
          + ("; not in the code: %s" % ", ".join(missing) if missing else ""))
    print("  Scan hits on those lines: %d. Causes: %d (%d shown, %d open, %d ruled out)."
          % (len(hits), len(causes), len(shown), len(opened), sum(1 for c in causes if c[4] == "ruled out")))
    print("Your notes: %s%s" % (notes_at, " (written now)" if not exists else ""))
    if problems:
        print("To correct in the notes:")
        for p in problems:
            print("  - %s" % p)
    if not exists:
        print("\nResult: not complete. This is expected on the first run: write the symptom and what to look for in %s."
              % notes_at)
        sys.exit(0)
    if problems:
        print("\nResult: not complete. Correct what is listed, in %s." % notes_at)
        sys.exit(NOT_PASSED)
    print("\nResult: complete")
    sys.exit(0)


if __name__ == "__main__":
    main()
