#!/usr/bin/env python3
"""Write the review report of some code, and say whether the review is complete.

    python3 write_register.py <code file-or-folder> --out <report.md>

The report is written by this script every time it runs, from two sources:

  1. the scan (scan_code.py): one row for each place it points at, with the
     line, the code as written, the kind of defect, what it does, where it
     lands, the line as it would be after the fix, the confidence and the
     decision. The scan settles a row itself when the code, or a document
     next to the code (a list of names, with their types), shows the answer.
  2. the notes file next to the report (<report>.notes.md), written by the
     reviewer: the decision on each row the scan could not settle, the
     findings from reading the code, what was found for each requirement of
     the intent document, the verdict, and the questions for the owner.

Nobody edits the report: what a person has to say goes into the notes, and
this script is run again. The first run writes the notes file with the rows
to decide and the form of each part.

It ends with a line that starts with "Gate:". Exit code 0 when the review is
complete, 3 when it is not complete yet, anything else when the script itself
failed. Python standard library only.
"""
import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_report  # noqa: E402
import notes as notes_file  # noqa: E402
import scan_code  # noqa: E402

NOT_PASSED = 3
PROVEN = "Proven from the code"
TITLE = "# Review — "
# kind -> (severity, what it does, confidence)
TEXTS = {
    "cond": ("High",
             "The condition is written with a single =, which is the assignment operator. If the language "
             "assigns here, the value on the left is overwritten with the value on the right and the branch "
             "no longer depends on what the value was.",
             PROVEN + " that a single = is written. What it does inside a condition needs a test."),
    "prefix": ("High",
               "The name is read without its prefix. Nothing sets the name in this form, so the value used "
               "here is empty or undefined, not the one meant.",
               PROVEN + " that nothing sets it. What an unset name yields when read needs a test."),
    "prefix_set": ("High",
                   "The name is given a value without its prefix. The value goes to a name that nothing "
                   "reads, and the name that was meant is not set.",
                   PROVEN + " that nothing reads the name in this form."),
    "rename": ("High",
               "The name differs by letter case or by one letter from a name that is set earlier. Nothing "
               "sets this spelling, so the value used here is empty or undefined.",
               PROVEN + " that nothing sets it. What an unset name yields when read needs a test."),
    "quote": ("High",
              "The word is written without quotes, so it is read as a name, and nothing sets that name: the value "
              "used here is empty or undefined. The same word is written as text, in quotes, in other places of the code.",
              PROVEN + " that nothing sets it and that the code writes the same word as text elsewhere."),
    "unset": ("High if nothing else sets it",
              "Nothing in the scanned code sets this name. Unless the platform or another component sets "
              "it, the value used here is empty or undefined.",
              PROVEN + " for the scanned code. Whether something outside sets it is to be confirmed."),
    "unread": ("Low",
               "The value is set and never read in the scanned code. Unless another component reads it, "
               "the assignment does nothing.",
               PROVEN + " for the scanned code. Whether something outside reads it is to be confirmed."),
    "once": ("High if misspelt",
             "The name is used a single time and is one letter, or letter case, away from a name used more "
             "often. If it is a misspelling, the value read or written here is lost.",
             "Needs a check against the names that exist: a schema, a list of fields, or how the code uses "
             "the two names elsewhere."),
    "unlisted": ("High if the name does not exist",
                 "A document next to the code lists the names of this sort, and this one is not among them. "
                 "If it does not exist, the value read here is empty or undefined, and a value written here is lost.",
                 "Needs a check: the list may be incomplete."),
    "twice": ("Medium",
              "The value assigned on the line before is replaced here before anything reads it, so the "
              "first assignment has no effect.",
              PROVEN + "."),
    "entity": ("High",
               "The entity is not closed with ; so a reader of the markup does not decode it: the text "
               "arrives wrong or the document is rejected.",
               PROVEN + "."),
    "tag": ("High",
            "The tag is opened and never closed, so the markup built here is not well formed.",
            PROVEN + "."),
    "placeholder": ("Medium",
                    "The string holds placeholder text. If the string is output, stored or sent, the "
                    "placeholder goes with it.",
                    PROVEN + " that the text is there. Whether it is sent is to be confirmed by reading."),
    "brackets": ("High",
                 "A bracket is opened and never closed, or closed without being open. The code after it is "
                 "read differently from how it is laid out, or is rejected.",
                 PROVEN + "."),
    "mixed": ("Medium",
              "The condition mixes && and || with no brackets. Which parts belong together is decided by "
              "the language's order of evaluation, not by how the line reads.",
              PROVEN + " that the brackets are missing. Which grouping is meant is for the owner to say."),
    "orphan": ("High",
               "An else or else-if follows a block that is not the block of an if. The code is read "
               "differently from how it is laid out, or is rejected.",
               PROVEN + "."),
    "twins": ("Medium",
              "Two spellings of one name are both given a value and both read. If they are meant to be "
              "one name, each of them holds only part of the values.",
              PROVEN + " that both spellings are in use. Whether they are meant to be one name is to be "
              "confirmed by reading."),
    "repeat": ("High",
               "The same condition is tested earlier in the same chain, so this branch can never run.",
               PROVEN + "."),
    "self": ("High",
             "The comparison has the same value on both sides, or two fixed values, so its result never "
             "changes; or a name is assigned to itself, which does nothing.",
             PROVEN + "."),
    "empty": ("Low",
              "The block has no statements: the case is tested or handled, and nothing is done.",
              PROVEN + "."),
    "early": ("Medium",
              "The name is read on a line before the first line that sets it. Unless something sets it "
              "earlier when the code runs, the value read is empty or undefined.",
              PROVEN + " from the order of the lines. The order at run time is to be confirmed by reading."),
    "index": ("Medium",
              "The result of a call is indexed before its size or presence is checked. If the call returns "
              "nothing, this line fails or reads nothing.",
              PROVEN + " that no check comes before it. Whether the call can return nothing needs reading."),
    "loop": ("High",
             "Nothing inside the loop assigns what its condition tests. Unless a call inside the loop "
             "changes it, the loop never ends once it is entered.",
             PROVEN + " that the loop does not assign it. Whether a call changes it needs reading."),
    "handler": ("Medium",
                "The handler only logs. The failure is not passed on and the state is left as it was, so "
                "nothing after it can tell that the work failed.",
                PROVEN + " that the handler only logs. Whether that is enough is for the owner to say."),
    "query": ("Medium; High if the value can come from outside",
              "A query is built by joining text with a value. A quote or an unexpected character in the "
              "value changes the query.",
              PROVEN + " that the value is joined in. Whether it can hold such characters needs reading."),
    "secret": ("Medium",
               "The string holds an environment name, an address or a credential. It ties the code to one "
               "environment, or exposes a secret.",
               PROVEN + " that the text is there."),
    "nocall": ("Low",
               "The function is defined and nothing in the scanned code calls it.",
               PROVEN + " for the scanned code. Whether something outside calls it is to be confirmed."),
    "contra": ("High",
               "One name is compared with two different values, joined so that the condition can never be true, "
               "or is always true. The branch never runs, or always runs.",
               PROVEN + "."),
    "semi": ("High",
             "A ; follows the condition, so the condition controls nothing: what comes after it runs every time.",
             PROVEN + "."),
    "noeffect": ("High",
                 "The statement compares two values and does nothing with the result. If an assignment was "
                 "meant, the name keeps its earlier value.",
                 PROVEN + " that the result is not used. Whether an assignment was meant is to be confirmed."),
    "dupbranch": ("Low",
                  "Two branches of one chain hold the same statements. Either one of them was meant to do "
                  "something else, or the two conditions can be one.",
                  PROVEN + " that the statements are the same."),
    "dupcase": ("High",
                "The same label appears twice in one switch, so the second branch can never run.",
                PROVEN + "."),
    "dupfunc": ("Medium",
                "The function is defined more than once. One definition replaces the other, or is never used.",
                PROVEN + ". Which definition is used needs a test."),
    "unreach": ("Medium",
                "The line follows a statement that leaves the block, so it never runs.",
                PROVEN + "."),
    "strclose": ("High",
                 "A quote is opened and the line ends before it is closed. The rest of the line, or more, is "
                 "taken as text, or the code is rejected.",
                 PROVEN + "."),
    "bound": ("Medium",
              "An index is compared with <= to a size. If indexes start at 0, the last pass reads one place "
              "past the end.",
              PROVEN + " that <= is used. Whether indexes start at 0 here needs a test or the documentation."),
    "command": ("Medium; High if the value can come from outside",
                "A call that runs a command or evaluates code is given text joined with a value. An unexpected "
                "character in the value changes what is run.",
                PROVEN + " that the value is joined in. Whether it can hold such characters needs reading."),
    "writeback": ("Medium",
                  "The code assigns a value of the data it was given. If that data is written back when the code "
                  "ends, the change is kept for everything else that reads it; a value changed only for formatting "
                  "or for a message here replaces the stored one.",
                  PROVEN + " that the value is assigned. Whether the data is written back, and whether that is meant, "
                  "is for the owner to say."),
    "discard": ("Medium",
                "The value set on the earlier line is replaced on this line and nothing reads it in between, so what "
                "the earlier lines worked out is lost.",
                PROVEN + " from the order of the lines: this line runs whenever the earlier one ran, and no line "
                "between them reads the name."),
    "reapplied": ("Medium",
                  "The same replacement is made twice on one value, and the text it puts in holds the text it looks "
                  "for: the second pass changes what the first produced (an escaped character is escaped again).",
                  PROVEN + " that both replacements are written and that this line runs whenever the earlier one ran. "
                  "What the value holds between them needs reading."),
    "capped": ("Medium",
               "The replace call stops after the given number of replacements, so text with more occurrences keeps "
               "the rest unchanged. For an escape of markup, the text that follows is not well formed.",
               PROVEN + " that the count is written. Whether the text can hold more occurrences needs reading."),
}
# kinds the scan settles by itself as findings, with the correction to make
SETTLED = {
    "twice": "Decide which of the two assignments is meant; if the second was meant for another name, "
             "correct the name.",
    "tag": "Close the tag.",
    "unread": "Remove the assignment once it is confirmed that nothing else reads the name.",
    "brackets": "Add or remove the bracket so that every bracket has its pair.",
    "mixed": "Add brackets that show the grouping that is meant.",
    "repeat": "Correct the condition, or remove the branch.",
    "orphan": "Put the if back in front of it, or remove the else.",
    "self": "Compare with, or assign, the value that was meant.",
    "empty": "Do what the case needs, or remove the block.",
    "nocall": "Remove the function once it is confirmed that nothing else calls it.",
    "contra": "Correct the comparison: the name cannot hold both values.",
    "dupbranch": "Merge the two conditions, or correct the branch that was meant to differ.",
    "dupcase": "Correct the label, or remove the branch.",
    "dupfunc": "Keep one definition.",
    "unreach": "Remove the line, or move it before the statement that leaves the block.",
    "strclose": "Close the string.",
    "discard": "Decide which value is meant: use the earlier value before this line, or remove what builds it.",
    "reapplied": "Make the replacement in one place.",
}
# kinds that need a reader unless the scan has evidence: the correction, and the question to answer
TO_JUDGE = {
    "early": ("Set the name before this line, or move the read after the line that sets it.",
              "Is the read meant to see the value of the pass before, and is the first pass guarded?"),
    "index": ("Check the size of the result before this line.",
              "Can the call return nothing? If it can, this line fails or reads nothing."),
    "loop": ("Change the tested value inside the loop, or leave the loop when the work is done.",
             "Does a call inside the loop change what the condition tests?"),
    "handler": ("Set the failure state or pass the error on, if the caller has to know.",
                "Is logging enough for this failure?"),
    "query": ("Pass the value as a parameter, or escape it.",
              "Can the value joined in hold a quote, or text that comes from outside?"),
    "secret": ("Move it to configuration.",
               "Is the value tied to one environment, or a secret? A name that only looks like one is not a defect."),
    "noeffect": ("Use = if an assignment was meant; remove the line if not.",
                 "Was an assignment meant?"),
    "bound": ("Use < if indexes start at 0.", "Do indexes start at 0 here?"),
    "command": ("Pass the value as a separate argument, or check it before it is used.",
                "Can the value joined in hold text that comes from outside?"),
    "twins": ("If the two are one name, use one spelling everywhere.", "Are the two spellings meant to be one name?"),
    "unset": ("Decide: set it before this line, quote it if a fixed text was meant, or confirm what sets it.",
              "Does the platform, the caller or another file set this name? A name the platform provides is not a "
              "defect: say what shows it. If nothing can set it, it is a finding. If the workspace does not tell, owner."),
    "placeholder": ("Replace with the real value, which the owner of the code has to supply.",
                    "Is this text a placeholder that reaches the output, or real text?"),
    "unread": ("Confirm what reads it after it is filled; if nothing does, remove it.",
               "Does something outside this code read it after it is filled?"),
    "once": ("Check the name.", "Does the name exist? If it does not, it is misspelt."),
    "unlisted": ("Correct the name, or confirm that it exists and add it to the list.",
                 "The list does not hold this name. Does it exist?"),
    "writeback": ("Assign a variable of the code instead, if the change is only meant for use here.",
                  "Is the change meant to be stored?"),
    "mixed": ("Add brackets that show the grouping that is meant.", "Which parts belong together?"),
    "capped": ("Remove the count, or make it the largest number of occurrences the text can hold.",
               "Can the text hold more occurrences than the count?"),
}
NAME_KINDS = ("unset", "unread", "once", "unlisted", "twice", "early", "index", "twins", "nocall", "writeback",
              "discard", "reapplied")
LOG_LINE = re.compile(r"\s*(?:\w+\s*\.\s*)*(?:%s)\s*\(" % "|".join(sorted(scan_code.LOG_CALLS)), re.I)
FINDING, OWNER, OPEN, CLEARED = "Finding", "Finding, to be confirmed by the owner", "To judge", "Not a defect"
TITLES = {key: title for key, title, _ in scan_code.CHECKS}


def cell(text):
    return text.replace("|", "\\|").replace("\n", " ")


def code(text):
    return "`%s`" % cell(text.strip().replace("`", "'"))


def short(text, width=150):
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 3] + "..."


def spans(numbers):
    """[1, 2, 3, 7] -> '1-3, 7'"""
    out, start, prev = [], None, None
    for n in sorted(set(numbers)):
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append("%d" % start if start == prev else "%d-%d" % (start, prev))
            start = prev = n
    if start is not None:
        out.append("%d" % start if start == prev else "%d-%d" % (start, prev))
    return ", ".join(out)


NOWHERE = "Low: the value is not used"


def where_text(scan, f, line):
    """Where a line lands: what its statement does, where the value goes, and the blocks it is inside."""
    does, blocks = scan.where.get(f, {}).get(line, ("", []))
    went = scan_code.goes_to(scan, f, line) if does.startswith("sets") else None
    if went:
        name, direct, beyond, end = went
        show = lambda items: ", ".join("`%s`" % x for x in items[:3]) + (" and others" if len(items) > 3 else "")
        if end == "nowhere":
            does += ", which nothing in this code uses"
        elif direct:
            does += ", which goes into %s" % ", ".join("`%s` (line %d)" % (t, n) for t, n in direct[:3])
            if beyond:
                does += " and from there into %s" % show(beyond)
            handed = [k for k in [t for t, _ in direct] + beyond if k in scan.filled and not scan.reads.get(k)]
            if handed:
                does += "; `%s` is filled here and handed on, so something outside this code may read it" % handed[0]
        elif end == "handed on":
            does += ", which is filled here and handed on, so something outside this code may read it"
    parts = [does] if does else []
    if blocks:
        parts.append("inside " + ", in ".join("`%s` (line %d)" % (cell(text.replace("`", "'")), n) for text, n in blocks))
    return "; ".join(parts) if parts else "at the top level"


def scan_rows(scan, files):
    """One row for each scan hit, in the order of the checks and of the lines; settled by the scan where it can."""
    many = len(files) > 1
    fixed = {str(f): scan.corrected(str(f)).split("\n") for f in files}
    kinds_at = defaultdict(set)                    # (file, line) -> kinds of the corrections with one form
    for f, _, _, _, kind, line in scan.fixes:
        kinds_at[(f, line)].add(kind)
    rows = []

    def add(key, f, lines, note, hit, fix_kind=None):
        severity, effect, confidence = TEXTS[fix_kind or key]
        first = lines[0]
        where = ", ".join(str(n) for n in lines)
        if many:
            where = "%s: %s" % (Path(f).name, where)
        marker = (key,) + hit
        reason = question = ""
        if fix_kind or key in ("cond", "entity", "semi"):
            fix, decision = code(fixed[f][first - 1]), FINDING
        elif key == "tag" and "tag" in kinds_at[(f, first)]:
            fix, decision = code(fixed[f][first - 1]), FINDING
        elif marker in scan.cleared:
            fix, decision, reason = "None: not a defect.", CLEARED, scan.cleared[marker]
        elif key == "unlisted" and marker in scan.proven:
            fix, decision, confidence, severity = code(fixed[f][first - 1]), FINDING, scan.proven[marker], "High"
        elif marker in scan.proven:
            fix, decision, confidence = TO_JUDGE[key][0], FINDING, scan.proven[marker]
            m = re.search(r"its size is checked on line (\d+)", note)
            if m:
                fix = "Move this read after the size check on line %s." % m.group(1)
        elif marker in scan.for_owner:
            fix, decision, question = TO_JUDGE[key][0], OWNER, scan.for_owner[marker]
        elif key == "unread" and note.split(" (")[0].split(" — ")[0] in scan.filled:
            # an object that is filled and never read here is usually handed to something else
            fix, decision = TO_JUDGE["unread"][0], OPEN
        elif key in SETTLED:
            fix, decision = SETTLED[key], FINDING
        elif key == "once":
            proposal = fixed[f][first - 1]
            m = re.search(r"close to (\S+)", note)
            if m:
                proposal = proposal.replace(note.split(" — ")[0].lstrip("."), m.group(1).lstrip("."))
            fix = "If it is misspelt: %s" % code(proposal) if proposal != fixed[f][first - 1] else TO_JUDGE[key][0]
            decision = OPEN
        else:
            fix, decision = TO_JUDGE[key][0], OPEN
        if all(LOG_LINE.match(scan.lines[f][n - 1]) for n in lines) and key not in ("brackets", "orphan"):
            severity = "Low: only a log message is affected"
        if key == "discard" and note.endswith("to the same value"):
            severity = "Low: the same statement twice"
        went = scan_code.goes_to(scan, f, first) if scan.where.get(f, {}).get(first, ("", []))[0].startswith("sets") else None
        unused = went[0] if went and went[3] == "nowhere" and key not in ("brackets", "orphan", "strclose") else ""
        if unused:                                   # a defect in a value that nothing uses does nothing
            severity = NOWHERE
            if key == "secret" and decision == OPEN:
                fix, decision = "Remove the assignment once it is confirmed that nothing else reads the name.", OWNER
                question = "The value names %s and goes to `%s`, which nothing in this code uses. Is the assignment still needed?" % (
                    note or "an environment", unused)
        if not fix.startswith("`") and not fix.startswith("If it is misspelt: `"):
            fix = cell(fix)                          # an instruction; a line of code is already escaped
        name = note.split(" — ")[0].split(" (")[0] if key in NAME_KINDS else ""
        rows.append({"key": key, "file": f, "lines": lines, "where": where, "severity": severity,
                     "code": code(scan.lines[f][first - 1]), "kind": TITLES[key], "note": note,
                     "effect": effect, "fix": fix, "confidence": confidence, "decision": decision,
                     "reason": reason, "question": question, "by": "scan", "name": name, "unused": unused,
                     "ask": TO_JUDGE.get(key, ("", ""))[1], "lands": where_text(scan, f, first)})

    for key, _, _ in scan_code.CHECKS:
        for hit in sorted(set(scan.hits[key])):
            f, line, note = hit
            if key in ("unset", "capped", "writeback"):
                name = note.split(" — ")[0]
                m = re.search(r"\bon lines? ([\d, ]+)", note)
                lines = [int(x) for x in m.group(1).replace(" ", "").split(",") if x] if m else [line]
                kinds = {k for n in lines for k in kinds_at[(f, n)]} & {"prefix", "rename", "quote"} if key == "unset" else set()
                if kinds:                              # one row per line: each has its own corrected line
                    for n in lines:
                        add(key, f, [n], name, hit, fix_kind=sorted(kinds)[0])
                else:
                    add(key, f, lines, note, hit)
            elif key == "unread" and "prefix_set" in kinds_at[(f, line)]:
                add(key, f, [line], note, hit, fix_kind="prefix_set")
            else:
                add(key, f, [line], note, hit)
    for i, r in enumerate(rows, 1):
        r["id"] = "S-%02d" % i
    return rows


def mentions(scan, name):
    """Where the documents next to the code mention a name: 'file, line N', or ''."""
    bare = name.lstrip("@$%.")
    if len(bare) < 4:
        return ""
    for doc in scan.docs:
        try:
            lines = Path(doc).read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if re.search(r"(?<![\w])%s(?![\w])" % re.escape(bare), line):
                return "%s, line %d" % (Path(doc).name, n)
    return ""


def uses_of(scan, name, note):
    """Where the code sets and reads a name, and the names close to it: lines a decision needs."""
    out = []
    places = lambda d, k: ", ".join(str(n) for n in sorted({line for _, line in d.get(k, [])})[:12])
    for key in [name] + [m for m in re.findall(r"close to (\S+)", note) if m != name]:
        sets, reads = places(scan.assigns, key), places(scan.reads, key)
        if sets or reads:
            out.append("%s: %s%s" % (key, "set on line(s) %s" % sets if sets else "never set",
                                     "; read on line(s) %s" % reads if reads else ""))
    return out


def named_in_documents(scan, rows):
    """Names the documents give in backticks that the report has a row for: [(name, where it is named, row ids)]."""
    out, seen = [], set()
    by_name = defaultdict(list)
    for r in rows:
        if r.get("name") and r["decision"] != CLEARED:
            by_name[r["name"].lstrip("@$%.")].append(r["id"])
    for doc in scan.docs:
        try:
            lines = Path(doc).read_text(encoding="utf-8", errors="replace").split("\n")
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            for token in re.findall(r"`([@$%]?[A-Za-z_]\w*)`", line):
                bare = token.lstrip("@$%")
                if bare in by_name and bare not in seen:
                    seen.add(bare)
                    out.append((token, "%s, line %d" % (Path(doc).name, n), by_name[bare]))
    return out


def skeleton(report, command, rows, scan):
    """The notes file as it is first written: the rows to decide, and the form of each part."""
    md = ["# Notes for the review %s" % report.name, "",
          "Your part of the review goes in this file. The report itself is written by the script from the scan and",
          "from these notes: do not edit the report. After you change this file, run the command again:", "",
          "    %s" % command, "",
          "## Decisions",
          "<!-- The scan could not settle these rows. Read each line in the code, and what is around it, then",
          "     replace the ? with one of:",
          "       finding                      the code shows the defect",
          "       finding, Low                 the same, with the severity you give (High, Medium or Low)",
          "       not a defect: <reason>       the workspace shows why: say what shows it",
          "       owner: <question>            nothing in the workspace settles it -->", ""]
    todo = [r for r in rows if r["decision"] == OPEN]
    for r in todo:
        md.append("- %s, line %s — %s%s" % (r["id"], r["where"], r["kind"], ": " + r["note"] if r["note"] else ""))
        f, first = r["file"], r["lines"][0]
        for k in range(max(1, first - 3), min(len(scan.lines[f]), first + 3) + 1):
            md.append("  %s %5d  %s" % (">" if k == first else " ", k, short(scan.lines[f][k - 1].rstrip("\r"), 160)))
        if r["name"]:
            md += ["  %s" % x for x in uses_of(scan, r["name"], r["note"])]
        if r["lands"] != "at the top level":
            md.append("  where it lands: %s" % r["lands"].replace("`", ""))
        said = mentions(scan, r["name"]) if r["name"] else ""
        md.append("  to answer: %s%s" % (r["ask"], " The name is mentioned in %s." % said if said else ""))
        md.append("  Decision: ?")
        md.append("")
    if not todo:
        md += ["None: the scan settled every row.", ""]
    md += ["## Findings from reading",
           "<!-- What a scan cannot find: wrong logic, a missing check, a value set on only some paths, text built for",
           "     one format and placed into another, processing done twice, a failure that leaves state half-changed.",
           "     One block for each finding, in this form (the script quotes the line itself):",
           "",
           "### line 120",
           "severity: High, Medium or Low",
           "code: a few words that are on that line",
           "what: what is wrong, and what it does",
           "fix: what to do",
           "confidence: proven from the code, or: needs a test",
           "effect: what it does to the outcome the user asked about (only if \"column:\" below is filled in)",
           "",
           "     For several lines write \"### lines 120-124\". If reading finds nothing, write the word: none",
           "     Your findings are numbered R-01, R-02 ... in the order of the blocks. One sentence for each value.",
           "     DO NOT write a block for a line in the list below: the scan already has a row for it, and a block",
           "     there is only added to that row. Write what the scan cannot see: what happens ACROSS lines.",
           "     Lines that already have a scan row: %s -->" % (spans(n for r in rows if r["decision"] != CLEARED for n in r["lines"]) or "none"), "",
           "## Coverage of the intent"]
    if scan.docs:
        md += ["<!-- The document that says what the code should do: %s." % ", ".join(Path(d).name for d in scan.docs),
               "     One line for each requirement or kind of defect it names, with what was found for it:",
               "       <the requirement> | <the IDs or the count, or: none found> -->", ""]
    else:
        md += ["<!-- No document came with the code. If the user stated requirements, one line for each:",
               "       <the requirement> | <the IDs or the count, or: none found> -->", ""]
    kinds = list(dict.fromkeys(r["kind"] for r in rows if r["decision"] in (FINDING, OWNER, OPEN)))
    md += ["## Effect",
           "<!-- Only if the user asked what the defects do to an outcome (an order, an invoice, a report): after",
           "     \"column:\" write a short name for the column, for example: Effect on the order. Then say after each",
           "     kind, in one sentence, what findings of that kind do to it. Say only what the text proves: where it",
           "     depends on how the platform treats the defect, start with \"If\". Every kind below has rows in the",
           "     report. A row whose value nothing uses gets \"None\" from the script. -->", "",
           "column:"]
    for k in kinds:
        of_kind = [r for r in rows if r["kind"] == k and r["decision"] in (FINDING, OWNER, OPEN)]
        named = [r["name"] for r in of_kind if r["name"]]
        md.append("<!-- %d row(s): %s -->" % (len(of_kind), short("; ".join(
            "%s (line %s)" % (r["name"], r["where"]) for r in of_kind) if named else
            "lines %s" % spans(n for r in of_kind for n in r["lines"]), 300)))
        md.append("%s:" % k)
    md += ["",
           "## Lines read",
           "<!-- The lines of the code you read yourself, for example: 1-3338 -->", "",
           "## Questions for the owner",
           "<!-- One per line. The questions of the decisions above are added by the script. -->", "",
           "## Not checked",
           "<!-- One per line: what this review does not cover, and why. -->", ""]
    return "\n".join(md)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("code", nargs="+")
    ap.add_argument("--out", required=True, help="the report to write")
    ap.add_argument("--notes", help="the notes file (default: next to the report, <report>.notes.md)")
    ap.add_argument("--command", help="the command to show in the notes file as the one to run again")
    ap.add_argument("--force", action="store_true", help="replace a file at --out that is not a review report")
    ap.add_argument("--hash-comments", action="store_true", help="# starts a comment")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists() and not args.force \
            and not out.read_text(encoding="utf-8", errors="replace").lstrip().startswith(TITLE):
        raise SystemExit("%s exists and is not a review report written by this script. Name another file, or pass "
                         "--force to replace it." % out)
    notes_at = Path(args.notes) if args.notes else notes_file.notes_path(out)
    command = args.command or "python3 %s %s --out %s" % (sys.argv[0], " ".join(args.code), args.out)

    moved = ""
    if not notes_at.exists() and not args.notes:
        # the review was started under another report name: its notes belong to this report now
        earlier = [p for p in sorted(out.parent.glob("*.notes.md"))
                   if p.read_text(encoding="utf-8", errors="replace").startswith("# Notes for the review")] \
            if out.parent.is_dir() else []
        if len(earlier) == 1:
            old_report = earlier[0].with_name(earlier[0].name[:-len(".notes.md")] + ".md")
            earlier[0].rename(notes_at)
            if old_report.exists() and old_report.read_text(encoding="utf-8", errors="replace").lstrip().startswith(TITLE):
                old_report.unlink()
            moved = "The notes written for %s are now %s; this report replaces %s." % (old_report.name, notes_at.name, old_report.name)

    scan, files = scan_code.run(args.code, args.hash_comments)
    rows = scan_rows(scan, files)
    by_id = {r["id"]: r for r in rows}
    notes = notes_file.read(notes_at)
    first_run = not notes["exists"]
    problems = list(notes["problems"])

    # ---- the decisions of the reviewer, on the rows the scan left open or left to the owner
    for row_id, (kind, text, at) in sorted(notes["decisions"].items()):
        r = by_id.get(row_id)
        if r is None:
            problems.append("%s (line %d of the notes): the report has no row with this ID." % (row_id, at))
        elif r["by"] == "scan" and r["decision"] not in (OPEN, OWNER):
            agrees = (kind == "finding" and r["decision"] == FINDING) or (kind == "not" and r["decision"] == CLEARED)
            if kind != "open" and not agrees:
                problems.append("%s is settled by the scan (%s): the decision in the notes is not applied. If you "
                                "disagree, say so under \"Questions for the owner\"." % (row_id, r["decision"].lower()))
        elif kind == "unknown":
            problems.append("%s (line %d of the notes): the decision is not understood: \"%s\". Write: finding, or "
                            "not a defect: <reason>, or owner: <question>." % (row_id, at, short(text, 60)))
        elif kind == "not" and len(text) < 8:
            problems.append("%s (line %d of the notes): \"not a defect\" needs its reason after a colon." % (row_id, at))
        elif kind == "owner" and len(text) < 8:
            problems.append("%s (line %d of the notes): \"owner\" needs the question after a colon." % (row_id, at))
        elif kind != "open":
            r["by"] = "notes"
            if kind == "finding":
                given = re.match(r"^\(?\s*(High|Medium|Low)\b\s*\)?\s*[:,.—–-]?\s*(.*)$", text, re.I)
                if given:                              # "finding, Low: the value goes nowhere"
                    r["severity"], text = given.group(1).capitalize(), given.group(2)
                else:
                    r["severity"] = re.sub(r"^(High|Medium|Low)[ ;]+(?:High )?if .*$", r"\1", r["severity"])
                r["decision"] = FINDING
                r["fix"] = re.sub(r"^If it is misspelt:\s*", "", r["fix"])
                if text:
                    r["confidence"] = "%s Reviewer: %s" % (r["confidence"], cell(text))
            elif kind == "not":
                r["decision"], r["reason"] = CLEARED, text
            else:
                r["decision"], r["question"] = OWNER, text
                r["severity"] = re.sub(r"^(High|Medium|Low)[ ;]+(?:High )?if .*$", r"\1", r["severity"])

    # ---- the findings from reading
    read_rows, merged, final_id = [], [], {}      # final_id: the reviewer's number of a block -> the ID in the report
    by_name = {Path(f).name: str(f) for f in files}
    for i, b in enumerate(notes["findings"], 1):
        label = "the finding for line %d (line %d of the notes)" % (b["first"], b["at"])
        f = by_name.get(Path(b["file"]).name) if b["file"] else (str(files[0]) if len(files) == 1 else None)
        if f is None:
            problems.append("%s: say which file, as in \"### rules.js: %d\"." % (label, b["first"]))
            continue
        if not 0 < b["first"] <= len(scan.lines[f]) or not 0 < b["last"] <= len(scan.lines[f]):
            problems.append("%s: %s has %d lines." % (label, Path(f).name, len(scan.lines[f])))
            continue
        level = (b.get("severity") or "").split()[0].strip(".,:;").capitalize() if b.get("severity") else ""
        if level not in ("High", "Medium", "Low"):
            problems.append("%s: severity must be High, Medium or Low." % label)
            continue
        if not b.get("what"):
            problems.append("%s: \"what:\" is missing: say what is wrong and what it does." % label)
            continue
        flat = lambda t: re.sub(r"\s+", "", t.replace("`", "'"))          # spacing is not part of the evidence
        near = " ".join(flat(scan.lines[f][k - 1]) for k in range(b["first"] - 2, b["last"] + 3)
                        if 0 < k <= len(scan.lines[f]))
        quote = flat(b.get("code", "").strip("`"))
        pieces = [x for x in re.split(r"\s*(?:\.\.\.|\u2026)\s*", quote) if len(x.strip()) >= 4] or [quote]
        if len(quote) < 4 or not any(piece in near for piece in pieces):
            problems.append("%s: the words given after \"code:\" are not on line %d, nor within two lines of it. "
                            "Copy a few words from the line itself." % (label, b["first"]))
            continue
        # the line the words are really on: a finding cited one line off is put on its line
        true = [k for k in range(b["first"] - 2, b["last"] + 3) if 0 < k <= len(scan.lines[f])
                and any(piece in flat(scan.lines[f][k - 1]) for piece in pieces)]
        if b["first"] == b["last"] and true and b["first"] not in true:
            b["first"] = b["last"] = min(true, key=lambda k: abs(k - b["first"]))
        where = "%d" % b["first"] if b["first"] == b["last"] else "%d-%d" % (b["first"], b["last"])
        said = " ".join(str(b.get(k, "")) for k in ("kind", "what"))
        squash = lambda t: re.sub(r"\s+", "", re.sub(r"\\+\|", "|", t).replace("`", ""))
        here = [r for r in rows if r["file"] == f and r["decision"] != CLEARED
                and set(r["lines"]) & set(range(b["first"], b["last"] + 1))]
        # the same defect as a scan row: it gives the same corrected line, or it is about the name of that row.
        # A finding on one line that already has a scan row joins that row in any case: what it says is kept
        # there, and the defect is counted once. The row whose kind shares most words with the finding is taken.
        rank = {"High": 3, "Medium": 2, "Low": 1}
        words = lambda t: {w for w in re.findall(r"[a-z]{4,}", t.lower())}

        def likeness(r):
            """How much a scan row is about the same thing as the finding: its corrected line, its name, its words."""
            same_fix = r["fix"].startswith("`") and b.get("fix") and squash(r["fix"]) == squash(b["fix"])
            # the name counts when it is the subject of the row's kind, not when it is only what the line assigns
            named = r["key"] not in ("unread", "twice", "nocall") and len(r["name"].lstrip("@$%.")) >= 4 and re.search(
                r"(?<![\w])%s(?![\w])" % re.escape(r["name"].lstrip("@$%.")), said)
            return (100 if same_fix else 0) + (3 if named else 0) + len(words(r["kind"] + " " + r["effect"]) & words(said)), \
                rank.get(r["severity"].split()[0].strip(":;,"), 0)

        best = max(here, key=likeness) if here else None
        twin = best if best is not None and (b["first"] == b["last"] or likeness(best)[0] >= 3) else None
        if twin is not None:                          # the same defect as a scan row: one row, with both texts
            twin["effect"] = "%s Reviewer: %s" % (twin["effect"], cell(b["what"]))
            if twin["decision"] != OPEN and rank[level] > rank.get(twin["severity"].split()[0].strip(":;,"), 0):
                twin["severity"] = level
            if b.get("effect"):
                twin["own_effect"] = cell(b["effect"])
            merged.append("line %s -> %s" % (where, twin["id"]))
            final_id["R-%02d" % i] = twin["id"]
            continue
        final_id["R-%02d" % i] = "R-%02d" % (len(read_rows) + 1)
        read_rows.append({"id": "R-%02d" % (len(read_rows) + 1), "severity": level, "file": f, "lines": [b["first"]],
                          "where": "%s: %s" % (Path(f).name, where) if len(files) > 1 else where,
                          "code": code(scan.lines[f][b["first"] - 1]), "kind": cell(b.get("kind") or "Found by reading"),
                          "effect": cell(b["what"]), "fix": cell(b.get("fix") or "For the owner to decide."),
                          "confidence": cell(b.get("confidence") or "Not stated."), "decision": FINDING,
                          "lands": where_text(scan, f, b["first"]), "own_effect": cell(b.get("effect", "")),
                          "unused": (lambda w: w[0] if w and w[3] == "nowhere" else "")(
                              scan_code.goes_to(scan, f, b["first"])
                              if scan.where.get(f, {}).get(b["first"], ("", []))[0].startswith("sets") else None)})

    # the notes refer to the reviewer's findings by the order of the blocks: put the IDs of the report in their place
    renumber = lambda t: re.sub(r"\bR-0?(\d+)\b", lambda m: final_id.get("R-%02d" % int(m.group(1)), m.group(0)), t)
    notes["coverage"] = [(renumber(a), renumber(b)) for a, b in notes["coverage"]]
    for part in ("questions", "not_checked"):
        notes[part] = [renumber(x) for x in notes[part]]
    notes["verdict"] = renumber(notes["verdict"])
    notes["effects"] = {k: renumber(v) for k, v in notes["effects"].items()}
    for r in rows:
        r["confidence"], r["question"], r["reason"] = renumber(r["confidence"]), renumber(r["question"]), renumber(r["reason"])

    # ---- what the user asked for per finding: one text per kind, in a column of its own
    column, effects = notes["effect_column"], notes["effects"]
    kept = [r for r in rows if r["decision"] in (FINDING, OWNER, OPEN)]
    if column:
        without = [k for k in dict.fromkeys(r["kind"] for r in kept) if k.lower() not in effects]
        if without:
            problems.append("Under \"Effect\", these kinds of finding have no line yet: %s." % "; ".join(without))
        for kind in dict.fromkeys(r["kind"] for r in kept):
            said = effects.get(kind.lower(), "")
            if re.match(r"^\W*(none found|not applicable|n/?a\b|no findings?|nothing found)", said, re.I):
                problems.append("Under \"Effect\", the line for \"%s\" says there are none, and the report has %d row(s) "
                                "of that kind: say what they do to it, or \"None: <why they do nothing to it>\"."
                                % (kind, sum(1 for r in kept if r["kind"] == kind)))
        bare = [r["id"] for r in read_rows if not r["own_effect"]]
        if bare:
            problems.append("The findings from reading for line %s have no \"effect:\" line, and the report has "
                            "the column \"%s\"." % (", ".join(r["where"] for r in read_rows if not r["own_effect"]), column))

    counted = re.search(r"\b\d+\s+(?:[\w-]+\s+){0,2}(?:defects?|findings?|instances?|issues?|bugs?|errors?)\b"
                        r"|\b\d+\s+(?:are\s+|of\s+them\s+)?(?:High|Medium|Low)\b|\b(?:High|Medium|Low)\s*[:=(]?\s*\d+",
                        notes["verdict"])
    if counted:
        problems.append("The verdict holds a count (\"%s\"): take the numbers out. The script adds the counts, so that "
                        "they agree with the tables." % counted.group(0))

    # ---- compose the report
    counts = defaultdict(int)
    for r in rows:
        counts[r["decision"]] += 1
    for r in kept + read_rows:                     # a decision cannot raise what nothing uses
        if r.get("unused") and r["decision"] in (FINDING, OWNER):
            r["severity"] = NOWHERE

    severities = {"High": 0, "Medium": 0, "Low": 0}
    for r in kept + read_rows:
        level = r["severity"].split()[0].strip(":;,")
        if r["decision"] in (FINDING, OWNER) and level in severities:
            severities[level] += 1
    total_lines = scan.line_count()
    head = "| ID | Severity | Line | Code (quoted) | Kind | What it does | Where it lands |%s Fix: the line after the fix | Confidence | Decision |" \
        % (" %s |" % cell(column) if column else "")
    rule = "|" + "---|" * (head.count("|") - 1)

    def table_row(r):
        extra = ""
        if column:
            text = r.get("own_effect") or effects.get(r["kind"].lower(), "")
            if r.get("unused"):
                text = "None in this code: nothing uses `%s`." % r["unused"]
            elif text and re.search(r"needs a test|to be confirmed", r["confidence"]) \
                    and not re.search(r"\b(if|may|might|could|unless|whether|needs? a test)\b", text, re.I):
                text += " (This rests on how the platform treats the defect: it needs a test.)"
            extra = " %s |" % cell(text)
        return "| %s | %s | %s | %s | %s | %s | %s |%s %s | %s | %s |" % (
            r["id"], cell(r["severity"]), r["where"], r["code"],
            cell(r["kind"]) + (": " + cell(r["note"]) if r.get("note") else ""), cell(r["effect"]), r["lands"],
            extra, r["fix"], cell(r["confidence"]), r["decision"])

    script_verdict = (
        "The scan points at %d places in %d file(s), %d lines: %d are findings, %d are findings to be confirmed by "
        "the owner, %d are explained as not defects, and %d still need a decision. Reading the code added %d "
        "finding(s). Findings by severity: High %d, Medium %d, Low %d."
        % (len(rows), len(files), total_lines, counts[FINDING], counts[OWNER], counts[CLEARED], counts[OPEN],
           len(read_rows), severities["High"], severities["Medium"], severities["Low"]))
    high = defaultdict(int)
    for r in kept + read_rows:
        if r["decision"] in (FINDING, OWNER) and r["severity"].split()[0].strip(":;,") == "High":
            high[r["kind"]] += 1
    top = "The findings rated High are of these kinds: %s. " % "; ".join(
        "%s (%d)" % (k, n) for k, n in sorted(high.items(), key=lambda kv: -kv[1])) if high else ""
    script_verdict += " %sNothing was run: what a finding does when the code runs needs a test where it runs." % top
    md = [TITLE + ", ".join(Path(a).name for a in args.code), "",
          "Written by the review script from the scan and from the notes in %s. Do not edit this file: "
          "write in the notes and run the script again." % notes_at.name, "",
          "## Verdict", script_verdict]
    if notes["verdict"]:
        md += ["", "The reviewer's summary: %s" % notes["verdict"]]
    md += ["", "## Findings", head, rule]
    md += [table_row(r) for r in kept]
    md += ["", "## Findings from reading", head, rule]
    md += [table_row(r) for r in read_rows]
    if not read_rows:
        md.append("")
        md.append("None found by reading." if notes["none_found"] else "Not written yet.")
    md += ["", "## Scan hits that are not defects", "| Kind | Line | Reason it is not a defect |", "|---|---|---|"]
    grouped = {}                                   # rows cleared for the same reason share one line of the table
    for r in rows:
        if r["decision"] == CLEARED:
            grouped.setdefault((r["kind"], r["note"] if len(r["lines"]) == 1 else r["id"], r["reason"], r["by"]), []).append(r)
    for (kind, _, reason, by), same in grouped.items():
        md.append("| %s | %s | %s (%s, %s) |" % (cell(kind) + (": " + cell(same[0]["note"]) if same[0]["note"] else ""),
                                                 ", ".join(r["where"] for r in same), cell(reason),
                                                 ", ".join(r["id"] for r in same),
                                                 "settled by the scan" if by == "scan" else "decided by the reviewer"))
    md += ["", "## Checks performed", "| Check | How it was checked | Items examined | Findings |", "|---|---|---|---|"]
    per_kind = defaultdict(lambda: [0, 0])
    for r in rows:
        per_kind[r["key"]][r["decision"] != CLEARED] += 1
    for key, title, _ in scan_code.CHECKS:
        md.append("| %s | scan_code.py | %d hit(s) | %d row(s) among the findings, %d not a defect |"
                  % (cell(title), len(set(scan.hits[key])), per_kind[key][1], per_kind[key][0]))
    for doc, first, last, count in scan.name_lists:
        md.append("| Names checked against a list | %s, lines %d-%d | %d names listed | used by the checks on names "
                  "and on queries |" % (Path(doc).name, first, last, count))
    defined = defaultdict(int)
    for doc, _ in scan.given.values():
        defined[Path(doc).name] += 1
    for doc, count in sorted(defined.items()):
        md.append("| Names defined in an included file | %s | %d names defined | used by the check on names that are "
                  "never assigned |" % (doc, count))
    md += ["", "## Coverage of the code", "| File | Lines read by the scan | Lines read by the reviewer | Total lines |",
           "|---|---|---|---|"]
    for f in files:
        md.append("| %s | 1-%d | %s | %d |" % (f, scan.line_count(str(f)), cell(notes["lines_read"] or "not stated"),
                                               scan.line_count(str(f))))
    md += ["", "## Coverage of the intent", "| Requirement | What was found |", "|---|---|"]
    md += ["| %s | %s |" % (cell(a), cell(b)) for a, b in notes["coverage"]]
    for token, place, ids in named_in_documents(scan, rows + read_rows):
        md.append("| `%s`, named in %s | %s |" % (token, place, ", ".join(ids)))
    md += ["", "## Not checked",
           "- Nothing was run. Every row is a reading of the text of the code.",
           "- The scan reads names, conditions and text in strings. It does not follow the logic of the code."]
    md += ["- Line %d includes `%s`, which is not among the files given: what it defines and does was not checked."
           % (line, target) for _, line, target in scan.not_found]
    md += ["- %s" % x for x in notes["not_checked"]]
    questions = []
    for r in rows:
        if r["decision"] == OWNER and r["question"]:
            same = next((q for q in questions if q[1] == r["question"]), None)
            if same:
                same[0].append(r)
            else:
                questions.append(([r], r["question"]))
    md += ["", "## Questions for the owner of the code"]
    numbered = ["%s (line%s %s): %s" % (", ".join(r["id"] for r in rs), "s" if len(rs) > 1 else "",
                                         ", ".join(r["where"] for r in rs), q) for rs, q in questions]
    numbered += notes["questions"]
    md += ["%d. %s" % (i, q) for i, q in enumerate(numbered, 1)] or ["1. None."]
    md.append("")
    # the report must hold every place the scan points at, and quote each line as it is: checked, not assumed
    total, found, missing = check_report.account(scan, "\n".join(md))
    wrong = check_report.wrong_quotes("\n".join(md), scan)
    if missing or wrong:
        raise RuntimeError("the report this script composed does not account for the scan: %d place(s) missing, "
                           "%d quote(s) not on their line (%s)" % (len(missing), len(wrong), (missing + wrong)[:2]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    if first_run:
        notes_at.parent.mkdir(parents=True, exist_ok=True)
        notes_at.write_text(skeleton(out, command, rows, scan), encoding="utf-8")

    # ---- say where the review stands
    todo = [r for r in rows if r["decision"] == OPEN]
    read_done = bool(read_rows) or bool(merged) or notes["none_found"]
    needs_intent = bool(scan.docs)
    print("Review report: %s (written by this command; do not edit it)" % out)
    if moved:
        print("  %s" % moved)
    print("  The scan points at %d places: %d findings, %d for the owner to confirm, %d explained as not defects, "
          "%d to decide." % (len(rows), counts[FINDING], counts[OWNER], counts[CLEARED], len(todo)))
    print("  Findings by severity, scan and reading, those for the owner to confirm included: High %d, Medium %d, Low %d."
          % (severities["High"], severities["Medium"], severities["Low"]))
    for doc, first, last, count in scan.name_lists:
        print("  Names checked against the %d names listed in %s (lines %d-%d)." % (count, os.path.relpath(doc), first, last))
    for note in scan.notes:
        print("  note: %s" % note)
    print("Your notes: %s%s" % (notes_at, " (written now: it lists the rows to decide and the form of each part)"
                                if first_run else ""))
    state = [
        ("Decisions", not todo, "%d of %d made" % (sum(1 for r in rows if r["by"] == "notes"),
                                                   sum(1 for r in rows if r["by"] == "notes") + len(todo))
         + ("; still open: %s" % ", ".join(r["id"] for r in todo) if todo else "")),
        ("Findings from reading", read_done, ("%d" % len(read_rows) + (
            "; %d more restate a scan row and were added to it (%s)" % (len(merged), ", ".join(merged)) if merged else ""))
         if read_rows or merged else "none found" if notes["none_found"] else "not written: add them, or the word \"none\""),
        ("Coverage of the intent", bool(notes["coverage"]) or not needs_intent,
         "%d row(s)" % len(notes["coverage"]) if notes["coverage"] else
         "no rows yet: one line for each requirement of %s" % ", ".join(Path(d).name for d in scan.docs)
         if needs_intent else "no document came with the code: not needed"),
        ("Lines read", bool(notes["lines_read"]), notes["lines_read"] or "not stated"),
    ]
    for name, done, text in state:
        print("  %-23s %s  %s" % (name + ":", "done    " if done else "TO DO   ", text))
    if problems:
        print("To correct in the notes:")
        for p in problems:
            print("  - %s" % p)
    complete = all(done for _, done, _ in state) and not problems
    if complete:
        print("The report to hand over is %s. Do not write or copy another report file." % out)
        print("\nGate: passed")
        sys.exit(0)
    print("\nGate: not passed yet. %s Then run this command again." % (
        "This is expected on the first run: write your part in %s." % notes_at if first_run
        else "Complete what is marked TO DO and correct what is listed, in %s." % notes_at))
    sys.exit(0 if first_run else NOT_PASSED)


if __name__ == "__main__":
    main()
