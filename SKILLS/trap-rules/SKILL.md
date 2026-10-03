---
name: trap-rules
description: >-
  Use when asked to integrate a device or system that sends SNMP traps: to
  catalogue a trap list against the vendor's MIBs, to generate the rules and
  lookup tables of a trap probe from that catalogue, or to review or fix such
  rules. Also triggered by prompts that start with Catalogue, Generate, or
  Review <rules> against <catalogue>, and by Fix the findings of a rules review.
metadata:
  enabled: true
  author: Dr-Mohamed-Gamal
  version: "1.0.0"
---

# Skill: SNMP Trap Integration — Catalogue, Rules and Review

This skill guides Bob through a new integration of a device that sends SNMP traps: from the trap list a vendor or an operator supplies, and the vendor's MIBs, to the rules and lookup tables a trap probe needs, and to a review of those rules.

It is generic: the trap list is any spreadsheet or CSV with a name and an OID column, the MIBs are any SMIv1 or SMIv2 files, and the rules follow the folder tree and conventions of a standards document when the workspace has one.

---

## Background: Why Scripts and Gates?

A trap list and a set of MIBs disagree in many small ways: a typo in an OID, a name that differs from the MIB's, a trap listed twice with two severities, an alarm that arrives inside another trap, a text that names a variable the trap does not have. Written by hand, rules carry those mistakes into production. This skill splits the work:

| Who | Does what |
|---|---|
| Bob | Judges: which row of the list is right when it disagrees with the MIB, which trap clears which, what a summary should say, what only the owner can settle |
| The scripts | Read every MIB and every sheet, match them, propose every decision, write the catalogue, the rules, the lookups and the reports from Bob's notes, and check the rules against the catalogue |

---

The scripts do the work. They write every report, every rules file and every lookup; you write only the `decision:` and `overrides:` lines of a **notes file**. A task is finished when its command prints `Gate: passed`.

## The scripts
They are in the `scripts` folder next to this file. Run them from the workspace root as `python3 .bob/skills/trap-rules/scripts/run.py <task> ...`. They need only Python and give the same output every time.

| Command | What it does |
|---|---|
| `run.py catalogue <trap list> <MIB folder or files>... --out <report>` | Reads every sheet of the trap list and every MIB, matches each row to a MIB trap by OID and by name, and writes `<report>.notes.md` with one block per open decision, each with its facts and the script's proposal. Each later run applies your decisions and writes the catalogue report and `<report>.json` |
| `run.py generate <catalogue report> --out <rules folder> --report <report> [--standards <document>]` | From the catalogue: proposes the layout, the files, the expiry, and every trap's group, AlertKey and Summary in `<report>.notes.md`; writes the rules folder and the report from your decisions, then checks the rules and sends a test trap of every kind through them. Give `--standards` the standards document the prompt names: the layout block quotes its folder tree |
| `run.py review <rules folder> <catalogue report> --out <report>` | Checks a rules folder against the catalogue without trusting how it was made: syntax, paths, logs, commented-out code, one case per trap, event ids, severities and types, variables, keys of each clear group, alarm IDs. Each finding needs your decision in `<report>.notes.md` |
| `run.py status` | Lists every task started in this workspace and whether its gate passed. A task never started is not in the list: compare it with every report the latest request asks for |

## The rules that keep a run short
- **Write every decision in one edit.** Put them in the `## Your decisions` section at the top of the notes file, one line per block: `- <block title>: <decision>` (the title is the text after `### `), and `- <block title> > <name>: <decision>` for one trap or file of a block. The next run moves each line onto its block. A decision on a block's own `decision:` or `overrides:` lines counts too; write nowhere else. The command rewrites the notes file on every run, and writes every report and rules file itself. Never write or edit a report, a rules file or a lookup.
- **Do not open the MIBs, the trap list or the reports of your own task.** The notes hold the facts each decision needs (the row, the MIB's trap, its variables, the text), and each command prints the questions for the owner before its gate. When a block needs one more fact, search the MIB for that one name; do not read a MIB file through.
- **One pass, then the gate.** Read the notes file once, write every decision in one go, run the command again. A run can add new blocks that follow from your decisions (a trap that now needs a severity, a group to check): decide them and run again. Expect two or three runs.
- **`as proposed` is a decision.** Take the proposal when the facts support it; write your own value when they do not. A proposal is the script's best guess from names and numbers; you read what the words mean.
- **The gate decides.** The last line a command prints starts with `Gate:`. If a command ends with no `Gate:` line, the script failed: tell the user the command and what it printed.
- **Know where the work stands.** Before every reply run `status`; finish what is not passed; reply about the latest request only.

## Pick the task
Prompts follow one form: a first line that starts with the verb and says what and where, then `Write <report>.`, then a `Do not ...` line. Run the task's command at once with the report the prompt names.

| The prompt starts with | Task |
|---|---|
| Catalogue `<trap list>` against `<MIBs>` | 1. Catalogue |
| Generate the rules for `<catalogue>` under `<folder>` | 2. Generate |
| Review `<rules folder>` against `<catalogue>` | 3. Review |
| Fix the findings of `<review>` | 4. Fix |

Say which one you are doing, in one line, before you start.

---

## 1. Catalogue
Run `catalogue`, read `<report>.notes.md`, decide each block:

| Block | How to decide |
|---|---|
| `table` | `traps` for a list of traps. `flag <word>` for a table whose traps are all in another table: it marks them (for example the service-impacting ones). `objects` for a table of variables, not traps; when its rows are values a server sends on a threshold (disk, CPU, memory), write `objects in <trap>, <trap>` naming the MIB traps that carry another object's OID and value (the facts list them). `skip` for anything else |
| `row` | The MIB is the reference. `mib` takes the MIB's trap; `oid` or `name` (when the sheet's name and OID point to two MIB traps) takes the one whose description matches the sheet's description; `drop` removes the row |
| `missing` | No MIB defines these traps. `sheet` keeps them from the sheet (variables not named); the report asks the owner for the MIB |
| `remark` | A note in the sheet about a trap ("to be removed") is the owner's decision written down: follow it |
| `severity` | For each severity word of the sheet: `<0-5> problem`, `<0-5> resolution` or `<0-5> information` (5 critical, 4 major, 3 minor, 2 warning, 1 indeterminate or clear). When the word is plainly wrong for one trap (a clear word on a trap that reports a failure), give that trap its own: `- <trap>: <0-5> <type>` under the block's overrides |
| `severity-of` | A trap the sheet gives no severity: the MIB's when it states one, else from what the trap means |
| `conflict` | The same trap listed with two severities: the facts show each row's text; choose one; the report asks the owner to confirm |
| `aggregated` | Rows that carry an alarm ID instead of an OID arrive inside one trap: name that trap, the index variable that holds the alarm ID, and the trap that clears (`<trap>, alarm id <index>, cleared by <trap>`). Read the sheet's rows that describe the format: they are in the facts |
| `groups` | A clear clears every problem of its group, on the same node and key. Check that each clear undoes the problems it is grouped with; move a trap with `- <trap>: group <words>`. Put a problem and its clear together when their names differ (Over Temperature and Temperature OK) |
| `unpaired` | A problem with no clear stays open until someone clears it. Name its clear: `cleared by <trap>`, or `clear when <variable> = <value>` when the trap carries its own state (the proposal lists the values the MIB defines, such as normal or recovery); else `none` or `information` |
| `unpaired-clear` | A clear with no problem: `information`, or `clears <trap>` |

## 2. Generate
Run `generate`, read `<report>.notes.md`, decide each block:

| Block | How to decide |
|---|---|
| `layout` | `name <word>, path <path under $NC_RULES_HOME>`. The path follows the folder tree the facts quote from the standards document (for example `probes/<domain>/<name>`); the domain is the owner's to confirm, and the report asks |
| `files` | One rules file per vendor. Rename a file named by a number (`enterprise-<n>`) to the vendor when the sheet says which it is |
| `expiry` | Seconds before an information event, or a problem without a clear, expires; 0 means never |
| `fields` | Every trap's group, key and summary. The group becomes @AlertGroup, which a clear matches on with the node and the key: each clear group of the catalogue has its own, and two groups may not share one (the gate refuses it). Read the list: a summary should say what happened and where; a key should name the part that failed (an interface, a board, a bay), and a problem and its clear must have the same key. For one trap that is wrong, write `- <trap>: group <words>; key <template>; summary <template>` (any of the three). In a template `{name}` is a variable of the trap, `{n}` the n-th variable, `{name.instance}` the index part of that variable's OID, and `key none` an empty key |
| `text` | The sheet's text disagrees with the MIB (a variable it does not have, a word that names another variable). Read the MIB's variables in the facts and write the summary the text meant: `summary <template>` |

The rules follow the standards the workspace documents: every path through `$NC_RULES_HOME`, every table declared in `config/<name>.master.include.rules`, data in lookups (severity, type, group, expiry, flags, alarm names), one log format with the rules file and the node, no commented-out code.

## 3. Review
Run `review`. With no finding, the gate passes at once. Otherwise decide each finding in `<report>.notes.md`: `fix` (the rules are wrong), `owner` (only the owner can settle it), or `not a defect: <why>` with the reason the files show.

## 4. Fix
A finding marked `fix` is corrected where the rules come from, never in a rules file: change the decision in the notes of the catalogue or of the generate task that caused it, run that command again (and `generate` after a catalogue change), then run `review` again with the same report name.

## When you finish
Reply in a few lines: what the command printed (the counts and the gate), and the questions for the owner as the report lists them. Do not repeat the report.
