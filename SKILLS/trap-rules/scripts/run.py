"""The skill's single entry point.

  python3 run.py catalogue <trap list .xlsx|.csv> <MIB file or folder>... --out reports/trap-catalogue.md
  python3 run.py generate <catalogue .md> --out <rules folder> --report reports/rules-generated.md [--standards <document>]
  python3 run.py review <rules folder> <catalogue .md> --out reports/rules-review.md
  python3 run.py status
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STATUS = os.path.join(".trap-rules", "status.json")


def record(task, report, passed):
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    st = {}
    if os.path.exists(STATUS):
        try:
            st = json.load(open(STATUS))
        except ValueError:
            st = {}
    st[report] = {"task": task, "passed": passed, "at": time.strftime("%H:%M:%S")}
    json.dump(st, open(STATUS, "w"), indent=1)


def args_out(argv, flag):
    if flag in argv:
        i = argv.index(flag)
        val = argv[i + 1] if i + 1 < len(argv) else None
        return argv[:i] + argv[i + 2:], val
    return argv, None


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "catalogue":
        rest, out = args_out(rest, "--out")
        if len(rest) < 2 or not out:
            print("usage: run.py catalogue <trap list> <MIB file or folder>... --out <report .md>")
            return 2
        import catalogue
        text, ok = catalogue.run(rest[0], rest[1:], out)
        print(text)
        record("catalogue", out, ok)
        return 0 if ok else 1
    if cmd == "generate":
        rest, out = args_out(rest, "--out")
        rest, report = args_out(rest, "--report")
        rest, standards = args_out(rest, "--standards")
        if len(rest) != 1 or not out or not report:
            print("usage: run.py generate <catalogue .md> --out <rules folder> --report <report .md> [--standards <document>]")
            return 2
        if standards and not os.path.exists(standards):
            print("%s not found.\nGate: not passed." % standards)
            return 2
        import generate
        text, ok = generate.run(rest[0], out, report, standards)
        print(text)
        record("generate", report, ok)
        return 0 if ok else 1
    if cmd == "review":
        rest, out = args_out(rest, "--out")
        if len(rest) != 2 or not out:
            print("usage: run.py review <rules folder> <catalogue .md> --out <report .md>")
            return 2
        import review
        text, ok = review.run(rest[0], rest[1], out)
        print(text)
        record("review", out, ok)
        return 0 if ok else 1
    if cmd == "status":
        st = json.load(open(STATUS)) if os.path.exists(STATUS) else {}
        if not st:
            print("No task was started in this workspace: start the task the latest request asks for.")
            print("Gate: not passed. No task was started.")
            return 1
        bad = 0
        for rep, v in st.items():
            print("  %-12s %-10s %-8s %s" % ("passed" if v["passed"] else "NOT passed", v["task"], v["at"], rep))
            bad += 0 if v["passed"] else 1
        print("This list holds only the tasks that were started: if the latest request asks for a report that is "
              "not in it, that task is not done yet. Start it before you reply.")
        print("Gate: passed. Every task that was started has passed its gate." if not bad else
              "Gate: not passed. %d task(s) have not passed their gate: run their command again." % bad)
        return 0 if not bad else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
