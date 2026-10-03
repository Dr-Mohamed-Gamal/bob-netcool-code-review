#!/usr/bin/env python3
"""One command for each step of the code-review skill.

    python3 run.py review <code> --out <report>
        Scan the code, merge the notes next to the report, write the report,
        and say whether the review is complete.
    python3 run.py check <report> <code> [--intent <requirement document>]
        Check a report on its own: every place the scan points at is in it,
        no row is left to judge, each quoted line is on the line it cites.
    python3 run.py fix <code> --out <folder> --log <change log> [--register <review report>]
        Make the corrections with one possible form and those of the notes in
        a copy, write the change log, compare the copy with the original.
    python3 run.py look <code>
        Count what is in the code and list what a change would look at.
    python3 run.py edit <code> --out <folder> --report <report> [--map <map file>]
        Apply the plan in the notes next to the report (corrections, rules,
        renames, new files) in a copy, write the report, then trace where
        each line went and compare the two versions. The gate of a change.
    python3 run.py change <before> <after> --out <review>
        Review a change: compare the two versions, write the review report and the
        notes file with every difference to judge; the gate of a review of a change.
    python3 run.py change <before> <after> [--map <map file>] [--report <report>] [--renames <file>] [--lines]
        Compare two versions made by other means: counts before and after,
        where each line went, and the gate of a change.
    python3 run.py status
        Where the work in this workspace stands: every task that was started,
        and whether its gate passed.

Each command runs the scripts next to this file in the right order and
prints their output. The last line starts with "Gate:" and states the
result; the first run of review, fix and edit writes the notes file and
stops at "Gate: not passed yet", which is expected.

Exit codes: 0, the command did its work and its gate passed; 3, the gate
was checked and has not passed yet, which is a result and not a failure;
any other code, the script itself failed. Python standard library only.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ME = "python3 %s" % sys.argv[0]              # this command as it was typed, to repeat in hints
NOT_PASSED = 3


def call(script, *args, expect=None, allow=(0,), show=None):
    """Run one script and show what it prints. Returns (its output, its exit code).

    A script that ends without the line it is expected to print, or with an exit code that is
    not a result, has failed: say so plainly and stop, so that a fault is never taken for a result.
    `show` is a function that shortens the output for the screen; the full output is still returned.
    """
    r = subprocess.run([sys.executable, "-B", str(HERE / script)] + [str(a) for a in args if a is not None],
                       capture_output=True, text=True)
    sys.stdout.write(show(r.stdout) if show and r.returncode in (0, NOT_PASSED) else r.stdout)
    sys.stderr.write(r.stderr)
    failed = (expect not in r.stdout) if expect else (r.returncode not in allow)
    if failed:
        refused = r.returncode != 0 and r.stderr.strip() and "Traceback" not in r.stderr
        if not refused:                           # the script stopped on a fault of its own
            print("\nThe script %s failed (exit code %d). This is a fault in the script, not in your work. "
                  "Nothing can be concluded from this run: tell the user, and do this step by hand."
                  % (script, r.returncode))
        sys.exit(1)
    return r.stdout, r.returncode


def title(text):
    print("\n==== %s ====" % text)


def brief_compare(out):
    """The comparison of two versions, for the screen: what changed and the gate, not every line.

    Kept: the scan counts that changed and the scan hits that are new; for calls, operators and strings the
    count of each group and its first lines; the gate in full, which names everything still to settle.
    """
    keep, section, shown, cut = [], None, 0, 0
    limits = {"1": 30, "2": 16, "3": 12, "4": 8, "5": 0}

    def close():
        if cut:
            keep.append("   ... %d more line(s) not shown; what needs settling is named in the gate below" % cut)

    for line in out.split("\n"):
        head = re.match(r"^(\d)\. ", line)
        if head or line.startswith("Gate"):
            close()
            section, shown, cut = (head.group(1) if head else "gate"), 0, 0
            keep.append(line)
            continue
        if section is None or section == "gate" or not line.strip():
            if section in (None, "gate") or keep[-1:] != [""]:
                keep.append(line)
            continue
        if section == "1":
            row = re.match(r"^   (.{40,}?)\s+(\d+)\s+(\d+)(\s+went up)?$", line)
            if row and row.group(2) == row.group(3):
                continue                           # a count that did not change
        if shown < limits[section]:
            keep.append(line)
            shown += 1
        else:
            cut += 1
    close()
    return "\n".join(keep) + ("" if out.endswith("\n") and keep[-1:] == [""] else "\n")


def brief_trace(out):
    """Where each line went, for the screen: the counts and the runs of lines, not every line number."""
    keep, section, shown, cut = [], None, 0, 0
    for line in out.split("\n"):
        head = re.match(r"^(\d)\. ", line)
        if head:
            if cut:
                keep.append("   ... %d more, in the map file" % cut)
            section, shown, cut = head.group(1), 0, 0
            keep.append(line)
        elif section == "1" and " <- " in line:
            keep.append(line.split(": ", 1)[0] + " (the line numbers are in the map file)")
        elif section in ("2", "3") and line.startswith("   "):
            if shown < 25:
                keep.append(line if len(line) <= 200 else line[:197] + "...")
                shown += 1
            else:
                cut += 1
        else:
            keep.append(line)
    if cut:
        keep.append("   ... %d more, in the map file" % cut)
    return "\n".join(keep)


def notes_of(report):
    report = Path(report)
    return report.with_name(report.stem + ".notes.md")


STATE = Path(".code-review-tasks.json")      # in the workspace: what was started here, and how each gate stands


def tasks():
    """The tasks started in this workspace, in the order they were started: {report: its record}."""
    try:
        known = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    # a task started before this file existed has its notes file, which holds its command
    for notes in sorted(Path(".").rglob("*.notes.md"), key=lambda f: f.stat().st_mtime):
        if set(notes.parts) & {".git", ".bob", "node_modules"}:
            continue
        report = str(notes.with_name(notes.name[:-len(".notes.md")] + ".md"))
        if report in known:
            continue
        try:
            m = re.search(r"^\s+(python3 \S*run\.py (review|fix|edit|change) .+)$", notes.read_text(encoding="utf-8"), re.M)
        except OSError:
            m = None
        if m:
            known[report] = {"task": m.group(2), "command": m.group(1).strip(), "gate": "not known"}
    return known


def finish(task, command, report, passed, code):
    """Record how the gate of a task stands, then end with the exit code."""
    known = {k: v for k, v in tasks().items() if v.get("gate") != "not known"}
    known.setdefault(str(report), {})
    known[str(report)].update({"task": task, "command": command, "gate": "passed" if passed else "not passed",
                               "at": time.time()})
    try:
        STATE.write_text(json.dumps(known, indent=1), encoding="utf-8")
    except OSError:
        pass                                     # the record is a help, not a result
    sys.exit(code)


def status():
    """Say where the work in this workspace stands."""
    known = tasks()
    if not known:
        print("No task has been started in this workspace.\n\nGate: passed, nothing is open.")
        sys.exit(0)
    words = {"passed": "passed", "not passed": "NOT PASSED", "not known": "not known"}
    print("Tasks started in this workspace, in the order they were started:")
    for report, r in known.items():
        print("  %-11s %-8s %s" % (words[r["gate"]], r["task"], report))
    todo = [(report, r) for report, r in known.items() if r["gate"] != "passed"]
    timed = sorted(((r.get("at", 0), report) for report, r in known.items() if r.get("at")), reverse=True)
    if timed:
        latest = [report for at, report in timed if timed[0][0] - at <= 1800][:4]
        print("\nLast worked on: %s. The request you are answering is the one these belong to: reply about it and its "
              "results, not about the first message of the conversation." % ", ".join(reversed(latest)))
        print("This list holds only the tasks that were started: if the latest request asks for a report that is not in it, "
              "that task is not done yet. Start it before you reply.")
    if not todo:
        print("\nGate: passed. Every task that was started has passed its gate.")
        sys.exit(0)
    print("\nNot finished. Do this one next: run it again and settle what it lists.")
    print("  %s" % todo[0][1]["command"])
    if len(todo) > 1:
        print("The %d after it build on it, so they wait: run status again when this one has passed, and do not reply "
              "to the user before status shows every task as passed." % (len(todo) - 1))
    print("\nGate: not passed yet. %d task(s) started in this workspace are not finished." % len(todo))
    sys.exit(NOT_PASSED)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="task", required=True)
    p = sub.add_parser("review")
    p.add_argument("code")
    p.add_argument("--out", required=True)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("report")
    p.add_argument("code")
    p.add_argument("--intent")
    p = sub.add_parser("fix")
    p.add_argument("code")
    p.add_argument("--out", required=True)
    p.add_argument("--log", required=True)
    p.add_argument("--register")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("look")
    p.add_argument("code")
    p = sub.add_parser("edit")
    p.add_argument("code")
    p.add_argument("--out", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--map")
    p.add_argument("--force", action="store_true")
    sub.add_parser("status")
    p = sub.add_parser("diagnose")
    p.add_argument("code")
    p.add_argument("--out", required=True)
    p = sub.add_parser("change")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--map")
    p.add_argument("--report")
    p.add_argument("--renames")
    p.add_argument("--lines", action="store_true")
    p.add_argument("--out")
    args = ap.parse_args()

    if args.task == "status":
        status()

    if args.task == "review":
        title("Scan, notes and report")
        cmd = "%s review %s --out %s" % (ME, args.code, args.out)
        out, code = call("write_register.py", args.code, "--out", args.out, "--command", cmd,
                         "--force" if args.force else None, expect="Gate:")
        finish("review", cmd, args.out, "Gate: passed" in out,
               0 if "Gate: passed" in out or "expected on the first run" in out else NOT_PASSED)

    if args.task == "diagnose":
        title("From the symptom to the line that causes it")
        cmd = "%s diagnose %s --out %s" % (ME, args.code, args.out)
        out, code = call("diagnose.py", args.code, "--out", args.out, "--command", cmd, expect="Result:")
        if "Result: complete" in out:
            print("\nGate: passed. The diagnosis in %s names its causes with their lines and evidence." % args.out)
            finish("diagnose", cmd, args.out, True, 0)
        print("\nGate: not passed yet. %s Then run this command again." % (
            "Write the symptom and what to look for in %s." % notes_of(args.out) if "expected on the first run" in out
            else "Correct what is listed, in %s." % notes_of(args.out)))
        finish("diagnose", cmd, args.out, False, 0 if "expected on the first run" in out else NOT_PASSED)

    if args.task == "check":
        out, _ = call("check_report.py", args.report, args.code, "--intent" if args.intent else None, args.intent,
                      expect="Result:")
        passed = "Result: complete" in out
        print("\nGate: %s" % ("passed" if passed else "not passed yet"))
        sys.exit(0 if passed else NOT_PASSED)

    if args.task == "fix":
        title("Corrections: the script's and those of the notes")
        cmd = "%s fix %s --out %s --log %s%s" % (ME, args.code, args.out, args.log,
                                                 " --register %s" % args.register if args.register else "")
        out, code = call("fix_code.py", args.code, "--out", args.out, "--log", args.log,
                         "--register" if args.register else None, args.register, "--command", cmd,
                         "--force" if args.force else None, expect="Result:",
                         show=lambda t: t.replace("Result: complete", "Corrections: complete").replace(
                             "Result: not complete", "Corrections: not complete"))
        first = "expected on the first run" in out
        title("Comparison of the copy with the original")
        out2, _ = call("compare_code.py", args.code, args.out, "--report", args.log, "--lines", expect="Result:",
                       show=brief_compare)
        if "Result: complete" in out and "Result: nothing to settle" in out2:
            nothing = re.search(r"^\s*0 line\(s\) corrected", out, re.M)
            print("\nGate: passed. %s" % ("No line was corrected: the copy is the same as the original, and every finding "
                                          "is left to the owner or left as it is. Say so in your reply." if nothing
                                          else "Every changed line is in the change log."))
            finish("fix", cmd, args.log, True, 0)
        print("\nGate: not passed yet. %s" % ("Write your corrections in %s, then run this command again." % notes_of(args.log)
                                             if first else "Correct what is listed above, in %s, then run this command again."
                                             % notes_of(args.log)))
        finish("fix", cmd, args.log, False, 0 if first else NOT_PASSED)

    if args.task == "look":
        call("inventory.py", args.code)
        print("\nGate: passed, nothing to settle: this command only counts.")
        sys.exit(0)

    if args.task == "edit":
        title("The plan, applied")
        cmd = "%s edit %s --out %s --report %s%s" % (ME, args.code, args.out, args.report,
                                                     " --map %s" % args.map if args.map else "")
        out, code = call("edit_code.py", args.code, "--out", args.out, "--report", args.report, "--command", cmd,
                         "--force" if args.force else None, expect="Result:",
                         show=lambda t: t.replace("Result: complete", "Plan: applied in full").replace(
                             "Result: not complete", "Plan: not complete"))
        if "expected on the first run" in out:
            print("\nGate: not passed yet. Write the plan in %s, then run this command again." % notes_of(args.report))
            finish("edit", cmd, args.report, False, 0)
        notes = notes_of(args.report)
        title("Where each line went")
        call("trace_code.py", args.code, args.out, "--out" if args.map else None, args.map, "--renames", notes,
             "--notes", notes, show=brief_trace)
        title("What the change did")
        out2, _ = call("compare_code.py", args.code, args.out, "--report", args.report, "--renames", notes, expect="Result:",
                       show=brief_compare)
        if "Result: complete" in out and "Result: nothing to settle" in out2:
            print("\nGate: passed. The plan is applied in full and every difference is explained in %s." % args.report)
            finish("edit", cmd, args.report, True, 0)
        print("\nGate: not passed yet. %s%s Then run this command again." % (
            "Correct the plan where the first block says so. " if "Result: complete" not in out else "",
            "Explain each difference marked TO SETTLE under \"Explanations\" in %s (name the call in backticks or by its count line, "
            "the operator in backticks, the string by its text), or change the plan." % notes if "nothing to settle" not in out2 else ""))
        finish("edit", cmd, args.report, False, NOT_PASSED)

    if args.task == "change" and args.out:
        # the review of a change, written by the script from the comparison and from the reviewer's notes
        title("The review of the change")
        cmd = "%s change %s %s --out %s%s" % (ME, args.before, args.after, args.out,
                                              " --renames %s" % args.renames if args.renames else "")
        out, _ = call("write_review.py", args.before, args.after, "--out", args.out,
                      "--renames" if args.renames else None, args.renames, "--command", cmd, expect="Result:")
        if "expected on the first run" in out:
            print("\nGate: not passed yet. This is expected on the first run: write your judgements in %s, then run this "
                  "command again." % notes_of(args.out))
            finish("change", cmd, args.out, False, 0)
        if "Result: complete" in out:
            print("\nGate: passed. Every difference has its class and the review is complete in %s." % args.out)
            finish("change", cmd, args.out, True, 0)
        print("\nGate: not passed yet. Correct what is listed above, in %s, then run this command again." % notes_of(args.out))
        finish("change", cmd, args.out, False, NOT_PASSED)

    if args.task == "change":
        title("Counts before and after")
        call("inventory.py", args.before, args.after)
        title("Where each line went")
        call("trace_code.py", args.before, args.after, "--out" if args.map else None, args.map,
             "--renames" if args.renames else None, args.renames, show=brief_trace if args.map else None)
        title("What the change did")
        out, _ = call("compare_code.py", args.before, args.after, "--review", "--report" if args.report else None, args.report,
                      "--lines" if args.lines else None, "--renames" if args.renames else None, args.renames,
                      expect="Result:", show=None if args.lines else brief_compare)
        cmd = "%s change %s %s%s%s%s%s" % (ME, args.before, args.after, " --map %s" % args.map if args.map else "",
                                           " --report %s" % args.report if args.report else "",
                                           " --renames %s" % args.renames if args.renames else "", " --lines" if args.lines else "")
        if "Result: nothing to settle" in out:
            print("\nGate: passed%s" % (". Every difference is in %s." % args.report if args.report else ", nothing to settle."))
            if args.report:
                finish("change", cmd, args.report, True, 0)
            sys.exit(0)
        if args.report:
            print("\nGate: not passed yet. Correct what is marked TO SETTLE, or explain it in %s by naming it "
                  "(the function in backticks or by its count line, the operator in backticks, the text of the string), "
                  "then run this command again." % args.report)
            finish("change", cmd, args.report, False, NOT_PASSED)
        else:
            print("\nGate: not passed yet. %d group(s) are marked TO SETTLE. Correct each one, or explain it in "
                  "the report; then run this command again with --report <the report> to have the explanations "
                  "checked." % out.count("TO SETTLE"))
        sys.exit(NOT_PASSED)


if __name__ == "__main__":
    main()
