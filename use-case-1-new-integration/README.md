# Use Case 1 — New Integration: from MIBs to Probe Rules

Three prompts that let IBM Bob integrate a new device into Netcool from what an integration team receives — a trap list and the vendors' MIBs — into a checked catalogue of every trap, the probe rules and lookups in the operator's own folder tree, and a review that sends a test trap of every kind through the rules. Bob uses the [trap-rules skill](../SKILLS/trap-rules/), a second generic skill made for this use case.

> Pilot use case for a telecom operator. The operator's trap list, MIB set, business requirement, rules and reports are not published here: this page describes the inputs, the method and the prompts.

## Overview

A new network platform comes into service: a cluster of deep-packet-inspection appliances with their management server, subscriber manager, data mediator and analytics nodes, plus the switches and servers they run on. Its alarms must reach Netcool. From a trap list and the vendors' MIBs, an engineer writes the rules of the SNMP trap probe: one case per trap, the fields of each event, and which trap clears which. The operator rates this as the largest share of the pilot's effort, and today it is done by hand.

The request: Bob should generate those rules from the MIBs and the trap list, following the operator's coding standard for rules files (the same standard as in [use case 5](../use-case-5-code-review/): a fixed folder tree, every path through `$NC_RULES_HOME`, data in lookups rather than in conditions, one log format, no commented-out code).

## The Input Data

The operator sent the **integration package exactly as an integration team receives it**: a business requirement, a workbook of the traps in scope, and a zip of vendor MIBs. Nothing was cleaned up for the pilot, because the disagreements inside such a package are what make the work slow and error-prone.

| Input | What it is | What is in it | Why it is used |
|---|---|---|---|
| **The trap list** | An Excel workbook prepared for the integration, nine sheets, of which seven are used | The operator's selection of traps, sheet by sheet (detailed below): names, OIDs, severities, components, the vendor's alarm numbers, descriptions, and the event text the vendor recommends | It holds the **business decisions**: which traps matter, how severe each is, and what the event should say. But it is typed by hand, so it is checked against the MIBs rather than trusted |
| **The vendors' MIBs** | 63 MIB files in three vendor kits: the platform's application MIBs (with the standard MIBs they import), a server management controller's alert MIBs, and a server vendor's full MIB kit | 2,116 trap definitions, all read, with their OIDs, the variables each trap carries in order, the meaning of coded values, table indexes, and summary and severity hints | A MIB is the **device's own definition** of its traps. The rules need it to name each trap's variables and build its key; the catalogue uses it to check every row of the hand-typed list |
| **The business requirement** | The operator's requirement document for the platform | The platform's node types and sites, and the scope: integrate the platform's alarms and the hardware alarms of its switches and servers | It sets the **scope**: it explains why the switch and server sheets are part of the work. It is read by Bob and the engineer, not by the scripts; it names staff, so it stays in the private workspace |
| **The rules code standards** | The operator's standard for rules files, reused from use case 5 and copied into this workspace | The folder tree for a probe's rules, every path through `$NC_RULES_HOME`, all tables declared in one place, data in lookups, one log format, no commented-out code | It defines the **target layout**: the rules are generated directly in the tree the operator wants, instead of being refactored into it later |

### The trap list, sheet by sheet

| Sheet | Rows | What it holds | How the use case uses it |
|---|---|---|---|
| Service-impacting alarms | 67 | Name, severity, OID, component, label with the vendor's alarm number, description, expected event text | Every row is also in the next sheet, so the catalogue treats this sheet as a **flag** that marks the service-impacting traps, rather than as a second list |
| All application traps | 166 | The full list, with clears and information events, alarm numbers and expected texts | The **main list** of traps the rules must handle |
| Management server alarm format | 2 traps + a 37-line explanation | How the management server forwards every node's alarms: inside one rising and one falling trap, with the alarm number hidden in the index of the variables, and a severity table | Without it, 58 rows whose "OID" is really an alarm number would match nothing. With it, the rules read the number from the variable's index and look the alarm up |
| Server resource thresholds | 17 | Disk, CPU, memory and interface objects with their OIDs, not traps | These values arrive inside the standard event MIB's trigger traps; the catalogue proposes those traps for them |
| Switch traps | 24 in two tables | Standard traps and chassis traps, with severities in syslog terms, and a remark that two of them are to be removed | The requirement's switches. No switch MIB was sent, so these traps are kept from the sheet with their variables unnamed, and the report asks for the MIB; the remark is followed |
| Server hardware, vendor A | 25 variables + 27 traps | The management controller's alert traps and the variables they carry | The requirement's servers; matched to the vendor's MIB. Recovery comes on the same trap with a "recovery" value, which the catalogue finds in the MIB |
| Server hardware, vendor B | 18 traps + 3 variables | Health and network-card traps of the second server vendor | The requirement's servers; matched to the vendor's MIB kit, where OID typos and rows naming one trap but citing another's OID were found |
| *(two sheets removed)* | — | SNMPv3 users and passwords, and probe addresses | **Credentials.** They were removed before anything entered the workspace; the full file stays with its owner |

### Why this kind of input

- **The trap list as received, typos included.** A list typed by hand disagrees with the MIBs in small ways: an OID one digit off, a name that is not the MIB's, a trap listed twice with two severities, an event text that names a variable the trap does not have. Each of those becomes an alarm that never clears, or clears the wrong problem, if it reaches the rules. Using the real list shows the skill catching them.
- **The MIBs as the reference.** Only the MIB says which variables a trap carries, in which order, and what their values mean. The rules cannot name a variable, decode a status or build a key without it.
- **The operator's standard as the target.** Generating straight into the operator's tree means the rules need no second refactoring before review.
- **Three vendors and a management server.** A platform's own traps, two server vendors and a switch vendor, plus alarms forwarded by a management server, cover the cases an integration meets in practice.

### What was not received

The switch vendor's chassis MIB and the resource MIB of the servers' SNMP agent (their traps are kept from the sheet, and the report asks for the MIBs), and the "Perl mapping" the use case named. No probe or sample traps: the rules are checked by a review and a simulator, and the report says what still needs a test on a probe.

## How It Works

The **trap-rules** skill is generic: any trap list (a spreadsheet or CSV with a name and an OID column), any SMIv1 or SMIv2 MIBs, and the folder tree of the standards document in the workspace. It has three tasks, each a command that ends with a gate. The scripts read the inputs and propose every decision; Bob decides in a notes file, in one edit; the scripts write the catalogue, the rules and the reports.

**Bob accepts proposals readily**, so the proposals carry the judgement: the scripts pair a problem with its clear by name and by opposite states (Removal and Insertion, Offline and Online, Off and On), find the clear a trap carries in its own variables, propose the standard event triggers for threshold objects, and leave a block open only where Bob must write something itself.

```
uc1-new-integration/
├── .bob/
│   ├── rules/trap-integration.md
│   └── skills/trap-rules/              # SKILL.md + scripts/
├── inputs/
│   ├── <trap list>.xlsx                # credential sheets removed
│   ├── <business requirement>.docx
│   ├── rules_file_code_standards.txt   # reused from use case 5
│   └── mibs/                           # three vendor kits, 63 files
├── reports/                            # trap-catalogue, rules-generated, rules-review (+ notes)
└── rules/<name>/                       # the generated rules, in the operator's tree:
    ├── <name>.master.rules             #   entry point: dispatch by trap, then the fields
    ├── config/                         #   table declarations, constants
    ├── transformation_rules/           #   one file per vendor + field normalization
    └── lookups/                        #   trap catalogue, alarm numbers, value maps
```

## The Prompts

Three prompts in the same three-part form as the other use cases: the verb and what, `Write` and the report, `Do not` and the limit. A fix and a second review follow only when the review finds something; a fix changes a decision in the notes and generates again, never the rules by hand. The prompt files are in [prompts/](prompts/).

### 1 · Catalogue — the trap list against the MIBs

```text
Catalogue the traps of inputs/<trap list>.xlsx against the MIBs in inputs/mibs.
Write reports/trap-catalogue.md.
Do not write any rules.
```

| | |
|---|---|
| **Why this step** | Turn a hand-typed list and a pile of MIBs into one checked list of traps before any rule is written, so every disagreement is settled once, in writing |
| **Reads** | Every sheet of the workbook and every MIB file |
| **The scripts** | Find the trap tables in each sheet; read every MIB (both SMIv1 and SMIv2 traps) and resolve OIDs, variables, value maps and table indexes; match each row by OID and by name; detect OID typos (one digit from a MIB OID), names that differ from the MIB, rows whose name and OID point to two traps, traps no MIB defines, rows that are variables rather than traps, alarm numbers, and remarks; map severity words; find traps listed with two severities; pair problems and clears; write one block per decision, each with its facts and a proposal |
| **Bob decides** | The role of each sheet, each row that disagrees with the MIBs, the severity words, the conflicts, the trap that carries the alarm numbers, the clear groups, and the problems with no clear |
| **The gate refuses** | Any block without a valid decision; any trap left without a severity |
| **Writes** | The catalogue (every trap with its SNMPv1 form, severity, type, clear group and flags; the alarm-number table; the decisions; where the list and the MIBs differ; the questions for the operator) and a machine-readable copy for the next step |
| **Why these words** | "Do not write any rules" keeps one concern per step: the list is settled before anything is generated from it |

### 2 · Generate — the rules, in the operator's folder tree

```text
Generate the rules for reports/trap-catalogue.md under rules/, following inputs/rules_file_code_standards.txt.
Write reports/rules-generated.md.
Do not decide what is the client's to decide.
```

| | |
|---|---|
| **Why this step** | Write the rules from the catalogue only, in the operator's layout, with every value that is data in lookups |
| **Reads** | The catalogue and the standards document, whose folder tree the layout follows |
| **The scripts** | Propose the layout, one rules file per vendor, the expiry of events, and every trap's group, key and summary (from the trap list's text, the MIB's summary or the description); flag texts that name a variable the trap does not have or the wrong one; after the decisions, write the entry point, the table declarations, one case per trap, the field normalization and the lookups; then check them and send a test trap of every kind through the simulator |
| **Bob decides** | The folder path, the file names, the expiry, any group, key or summary to change, and the summaries the scripts could not propose |
| **The gate refuses** | An open block; a template that names a variable the trap does not have; two clear groups sharing one AlertGroup (a clear of one would close the other's problem); any finding of the check or the simulator |
| **Writes** | The rules folder and a report with the files, how to install them, every trap's key and summary, and the questions for the operator |
| **Why these words** | "Following" the standards document sets the target tree; "Do not decide what is the client's to decide" turns the domain folder, the field for the service-impact flag and the severity conflicts into questions |

### 3 · Review — the rules against the catalogue, with the simulator

```text
Review rules/ against reports/trap-catalogue.md.
Write reports/rules-review.md.
Do not fix anything.
```

| | |
|---|---|
| **Why this step** | Check the rules independently of how they were made, so the same review also works on rules edited by hand later |
| **Reads** | The rules folder and the catalogue |
| **The scripts** | Check the rules as text (syntax, paths through `$NC_RULES_HOME`, the log format, commented-out code, one case per trap, event ids, severities and types, variables, the key of each problem and its clear, the alarm numbers), then run the **simulator**: a small interpreter of the rules language sends one test trap per trap, one per alarm number, each problem followed by its clear, each clear-by-value, and an unknown trap, and compares the events with the catalogue |
| **Bob decides** | For each finding: fix, a question for the owner, or not a defect with the reason the files show |
| **The gate refuses** | A finding without a decision |
| **Writes** | The review |
| **Why these words** | "Do not fix anything" keeps the reviewer apart from the generator; a fix goes back through the notes and prompt 2 |

### 4 · Fix and 5 · Review the fix — only when the review finds something

```text
Fix the findings of reports/rules-review.md in rules/.
Write reports/rules-generated.md.
Do not decide what is the client's to decide.
```

```text
Review rules/ against reports/trap-catalogue.md.
Write reports/rules-review-2.md.
Do not fix anything.
```

A finding marked "fix" is corrected where the rules come from — the decision in the notes of the catalogue or of the generation — and the rules are generated again, then reviewed again. In the runs below the review found nothing, so these two prompts were not needed.

## From Input to Output

| Prompt | Reads | Writes |
|---|---|---|
| 1 · Catalogue | The trap list and the MIBs | The trap catalogue and its machine-readable copy |
| 2 · Generate | The catalogue and the standards document | The rules folder and the generation report |
| 3 · Review | The rules folder and the catalogue | The review, with the simulator's results |

## Results

| Step | Result |
|---|---|
| The inputs | 2,116 trap definitions read from 63 MIB files, every one placed; the catalogue holds 174 traps and 165 alarm numbers |
| A stand-in before Bob | An AI agent standing in for Bob, reading only the workspace rule and the skill, ran the three prompts and reported what was unclear. Its most serious point: two clear groups could get the same AlertGroup, so a clear of one would close the other's problem. The gate and the simulator now refuse it |
| The review's own test | Eleven defects planted in a copy of the rules were all found |
| First prompt in Bob | The gate passed in a minute, but Bob had accepted every proposal, so some judgement calls were missing. **A gate is only as good as the proposals Bob accepts**: the scripts now propose those judgements themselves |
| **Clean run** | **All three gates passed at the first attempt**, in one new chat with nothing typed but the three prompts: about three and a half minutes and about 2 Bob coins. 13 rules files with 174 cases; the review found nothing, with 172 test traps, 165 test alarms and 54 problem/clear pairs replayed |

### Questions the run leaves for the operator

Which domain folder the rules belong in; whether alarms forwarded by the management server keep the server as their node; whose severity wins when the trap list and the alarm disagree; the MIBs not supplied; the traps listed with two severities; rows whose name and OID point to two different traps; and the problems with no clear that would stay open.

Still to come: loading the rules in a test probe, its syntax check, and a test trap of each kind, which need the operator's environment.

## Running It

1. Open the integration's workspace folder in IBM Bob. It holds the trap list, the MIBs and the standards document under `inputs/`, and the skill under `.bob/`.
2. Start a new chat in the built-in **Agent** mode and send the three prompts in order.
3. After each prompt, Bob's command should end with `Gate: passed`. Read the report it names, and its questions for the operator, before sending the next one.
4. Before production: load the rules in a test probe, run its rules syntax check, and send a test trap of each kind.
