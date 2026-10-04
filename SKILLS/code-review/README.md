# Code Review — Agent Skill

Equip IBM Bob to review, fix, change and debug existing code in a way that is **repeatable and verifiable**: the skill's scripts do the mechanical work, Bob does the judging, and every step ends with a gate.

> Generic by design: it names no product, platform or language, reads code as text in any language, and takes a project's rules from the documents placed next to its code.

## What It Does

| Capability | Use it for |
|------------|------------|
| **Review code** | A defect register: every scan hit decided, findings that quote their line, the effect of each defect, the fix, and the questions for the owner |
| **Fix findings** | A corrected copy and a change log; corrections with one possible form are made by the script, and what is the owner's to decide is proposed, not applied |
| **Change existing code** | Clean-ups, renames, rules over many lines, splits into files, and copies: a new item made exactly like an existing one, wherever the model appears |
| **Review a change** | A review written by the script: the change line by line, every difference judged, and the claims of the earlier reports checked |
| **Diagnose a failure** | From a symptom to the line: every line that names what the symptom involves, and each possible cause shown, ruled out, or open with the test that decides it |

## When to Use It

Activate the skill with short prompts in three parts: a first line that starts with the verb of the task and says what and where, then `Write <report>.`, then a `Do not ...` line.

- *"Review src/billing.js. Write reports/review.md. Do not change the code."*
- *"Fix the findings of reports/review.md in a copy of src under fixed/. Write reports/change-log.md. Do not decide what is the owner's to decide."*
- *"Add the item NEW, modelled on the item OLD, to a copy of src/page.html under changed/. Write reports/add-item.md. Do not change src."*
- *"Review changed/ against src/page.html. Write reports/code-review.md. Do not fix anything."*
- *"Diagnose src/page.html: the NEW tiles open the alerts of OLD. Write reports/diagnosis.md. Do not fix anything."*

| The prompt starts with | Task |
|---|---|
| Review `<code>` | B · Review code |
| Fix | D · Fix findings |
| Clean up, Standardize, Rename, Split, Add | E · Change existing code |
| Review `<changed>` against `<baseline>` | A · Review a change |
| Diagnose `<code>`: `<symptom>` | C · Diagnose a failure |

A typical change runs as a closed loop: **change → review → fix → review the fix**, repeating the last two until the review is clean. When the review finds nothing, the fix passes at once without changing anything.

## What You Get

Every task writes its report, and a notes file next to it that holds Bob's judgement:

| Step | Output |
|------|--------|
| 1 · First run | The script scans the code and writes the notes file: the facts to start from and the form to fill |
| 2 · Bob's notes | Decisions, corrections, a plan or causes, written by Bob in the notes file; Bob never writes the report or the changed code itself |
| 3 · Next run | The script applies the notes, writes the report and the changed copy, compares the copy with the original, and lists what is still open |
| 4 · Gate | Repeat until the command prints `Gate: passed`; `run.py status` lists every task in the workspace and whether its gate passed |

## Why It's Reliable

- **The scripts make the changes.** Corrections, removals, renames and copies are applied by code from Bob's notes, so the same notes always give the same result.
- **Every claim is checked.** A finding must quote words that are on the line it cites; a review must judge every difference; a diagnosis must show a cause or name the test that decides it.
- **Nothing changes unnoticed.** The new version is compared with the old one: a new call, operator, string or non-ASCII character, a file left with half a block, or a requirement left unaccounted for stops the gate until it is explained or corrected.
- **Copies cannot drift.** A copy that still holds a name of its model in any letter case, reuses a name the code already has, is not a whole block, or keeps a style value that does not fit the new name is refused.
- **The owner decides what is the owner's.** Choices the code and the documents do not settle become specific questions, not guesses.

A gate that passed means the work is complete and accounted for, not that the code is right where it runs: every report says what still needs a test there.

## Install

Copy the skill into your workspace's skills directory:

```bash
git clone https://github.com/Dr-Mohamed-Gamal/bob-code-review-skill.git .bob/skills/code-review
```

Then add a rule file, for example `.bob/rules/review-and-change-code.md`:

```markdown
Before you review code, fix a defect, or optimize, restructure or split code, activate the `code-review` skill and follow it. Say in one line which of its tasks you are doing.

Run the skill's commands from the workspace root as `python3 .bob/skills/code-review/scripts/run.py <task> ...`. A task is finished when its command prints `Gate: passed`.

Before every reply, run `python3 .bob/skills/code-review/scripts/run.py status`. It lists only the tasks that were started: compare it with every report the latest request asks for, start the missing ones, finish the ones not passed, then reply about the latest request only.

The reports the user asks for are written by those commands: give the command the file name the user asked for.
```

Put each body of code in its own folder, with the documents that came with it (a requirement, coding standards, lists of names).

## Structure

```
code-review/
├── SKILL.md                 # the skill: tasks, rules and gates, loaded by Bob
├── README.md                # this listing
├── scripts/                 # the work: run.py is the single entry point
│   ├── run.py               # review · fix · edit · change · diagnose · status · look · check
│   ├── scan_code.py         # the scan: 41 kinds of defect, any language
│   ├── write_register.py    # review report from the scan and Bob's notes
│   ├── fix_code.py          # corrected copy and change log
│   ├── edit_code.py         # changes: corrections, rules, renames, splits, copies
│   ├── write_review.py      # review of a change, line by line
│   ├── compare_code.py      # the gate's comparison of two versions
│   ├── diagnose.py          # from a symptom to the line
│   └── ...                  # helpers: notes, inventory, trace, report rows, strings
└── tests/
    └── run_tests.py         # 669 tests on small synthetic samples
```

## Requirements

- Python 3.9 or later. No other packages.
- IBM Bob in Agent mode, with skills enabled.

## Tests

```bash
python3 tests/run_tests.py
```

## Guiding Principle

**Bob brings the judgement; the scripts make every result repeatable and auditable.** Script what can be scripted, leave to Bob what needs reading and deciding, and let nothing count as done until a gate has checked it.
