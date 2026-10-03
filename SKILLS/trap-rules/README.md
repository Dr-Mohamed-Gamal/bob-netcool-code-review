# SNMP Trap Integration — Agent Skill

Equip IBM Bob to integrate a new device that sends SNMP traps: from the trap list a vendor or an operator supplies and the vendor's MIBs, to the rules and lookup tables of a trap probe, and to a review of those rules — **repeatable and verifiable**: the skill's scripts do the mechanical work, Bob does the judging, and every step ends with a gate.

> Generic by design: the trap list is any spreadsheet or CSV with a name and an OID column, the MIBs are any SMIv1 or SMIv2 files, and the rules follow the folder tree and conventions of the standards document placed in the workspace.

## What It Does

| Capability | Use it for |
|------------|------------|
| **Catalogue the traps** | Every row of every sheet matched to a MIB trap by OID and by name: typos, names that differ from the MIB, traps no MIB defines, traps listed twice with two severities, alarms that arrive inside another trap, and which trap clears which — each one a decision with its facts and a proposal |
| **Generate the rules** | A rules folder from the catalogue: one case per trap with its variables named, AlertKey and Summary from the trap list's texts or the MIB, and every value that is data (severity, type, group, expiry, flags, alarm names) in lookup tables |
| **Review the rules** | A check of any rules folder against the catalogue, without trusting how it was made: syntax, paths, logs, commented-out code, one case per trap, event ids, severities and types, variables, the key of each problem and its clear |
| **Simulate** | A test trap of every kind sent through the rules by a small interpreter, without a probe: the event each one gives, and whether each clear lands on its problem |

## When to Use It

Activate the skill with short prompts in three parts: a first line that starts with the verb of the task and says what and where, then `Write <report>.`, then a `Do not ...` line.

- *"Catalogue the traps of inputs/traps.xlsx against the MIBs in inputs/mibs. Write reports/trap-catalogue.md. Do not write any rules."*
- *"Generate the rules for reports/trap-catalogue.md under rules/, following inputs/standards.txt. Write reports/rules-generated.md. Do not decide what is the client's to decide."*
- *"Review rules/ against reports/trap-catalogue.md. Write reports/rules-review.md. Do not fix anything."*

| The prompt starts with | Task |
|---|---|
| Catalogue `<trap list>` against `<MIBs>` | 1 · Catalogue |
| Generate the rules for `<catalogue>` | 2 · Generate |
| Review `<rules>` against `<catalogue>` | 3 · Review |
| Fix the findings of `<review>` | 4 · Fix (in the notes, then generate and review again) |

## What You Get

Every task writes its report, and a notes file next to it that holds Bob's decisions:

| Step | Output |
|------|--------|
| 1 · First run | The script reads the inputs and writes the notes file: one block per open decision, each with its facts and a proposal |
| 2 · Bob's notes | Bob decides each block, in one edit, in the notes file's `## Your decisions` section; Bob never writes a report, a rules file or a lookup |
| 3 · Next run | The script applies the decisions, writes the report (and the rules), checks them, and lists what is still open |
| 4 · Gate | Repeat until the command prints `Gate: passed`; `run.py status` lists every task and whether its gate passed |

## Why It's Reliable

- **The scripts write everything.** The catalogue, the rules and the lookups come from Bob's decisions, so the same decisions always give the same files.
- **Proposals that carry the judgement.** The scripts pair a problem with its clear by name and by opposite states (Removal and Insertion, Offline and Online, Off and On), split a group when each problem has its own clear, find the clear a trap carries in one of its own variables (a recovery or normal value the MIB defines), propose the standard event MIB's triggers for a table of threshold objects, and leave a block without a proposal only where Bob must write something, such as a summary whose source text names the wrong variables.
- **Clears that cannot cross.** Every clear group gets its own AlertGroup; a name two groups would share is refused by the gate, so one clear can never close another group's problem.
- **The MIB is the reference.** A row whose OID is one digit from a MIB trap, or whose name and OID point to two different traps, is shown with both descriptions; nothing is guessed silently.
- **Data stays out of the code.** Severity, type, group, expiry, flags and alarm names live in lookup tables; the cases only name the variables and build the key and summary.
- **Every rule is checked, and run.** The review reads the rules as text and checks them against the catalogue; the simulator sends one test trap of every kind through them and replays every problem with its clear.
- **The owner decides what is the owner's.** A severity that two sheets disagree on, a MIB that was not supplied, a field the operator must choose: each becomes a question in the report.

A gate that passed means the rules match the catalogue and the decisions, not that a device sends what its MIB says: every report says what still needs a test on a probe.

## Install

```bash
git clone https://github.com/Dr-Mohamed-Gamal/bob-trap-rules-skill.git .bob/skills/trap-rules
```

Then add a rule file, for example `.bob/rules/trap-integration.md`:

```markdown
Before you catalogue a trap list against MIBs, generate rules from a catalogue, or review or fix such rules, activate the `trap-rules` skill and follow it. Say in one line which of its tasks you are doing.

Run the skill's commands from the workspace root as `python3 .bob/skills/trap-rules/scripts/run.py <task> ...`. A task is finished when its command prints `Gate: passed`.

Before every reply run `python3 .bob/skills/trap-rules/scripts/run.py status`; finish what is not passed, then reply about the latest request only.
```

Put the trap list, the MIB folder and any standards document in the workspace, for example under `inputs/`.

## Structure

```
trap-rules/
├── SKILL.md              # the skill: tasks, decisions and gates, loaded by Bob
├── README.md             # this listing
├── scripts/              # the work: run.py is the single entry point
│   ├── run.py            # catalogue · generate · review · status
│   ├── mib.py            # MIB reader: SMIv1 traps, SMIv2 notifications, OIDs, variables, enums, indexes
│   ├── sheet.py          # trap list reader: .xlsx (every sheet) and .csv, no packages
│   ├── catalogue.py      # rows matched to the MIBs, decision blocks, the catalogue
│   ├── generate.py       # the rules folder and its lookups, from the catalogue and the decisions
│   ├── review.py         # the check of a rules folder against the catalogue
│   └── simulate.py       # a small interpreter that sends test traps through the rules
└── tests/
    └── run_tests.py      # tests on small synthetic MIBs and trap lists
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
