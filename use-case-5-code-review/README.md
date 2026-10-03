# Use Case 5 — Code Analysis, Standardization and Optimization

Five prompts that take a production Netcool Impact policy and a production probe rules file from a defect register to fixed, cleaned, standardized and reviewed code, with IBM Bob in its built-in Agent mode and the [code-review skill](../SKILLS/code-review/).

> Pilot use case for a telecom operator. The operator's code, documents and reports are not published here: this page describes the inputs, the method and the prompts.

## Overview

Impact policies and probe rules grow over years: new network domains and alarm types are added in place, blocks are switched off and left in, names follow three styles, paths are written out in full, and defects nobody has listed sit in code nobody re-reads whole. The operator asked for Bob to analyse such code, fix it, clean it up and standardize it, without changing the tickets and events it produces.

The use case runs on two pieces of production code at once, each with the operator's own document saying what the code should become. Each prompt does its step for the policy and then for the rules; each step works on the output of the one before, in a copy, so the original files never change.

## The Input Data

The operator sent **production code, not samples**: a policy and a rules file that run today, each with its own document. That pairing is the point of the use case. The code shows how the system works now, with everything years of changes left in it; the document is the operator's own definition of "done", so every change can be checked against something the operator wrote rather than against Bob's taste.

| Input | What it is | What is in it | Why it is used |
|---|---|---|---|
| **The Impact policy** | One production Netcool Impact policy (IPL), about 3,300 lines | The whole path from an alarm flagged for a ticket to the incident sent to the ticketing system: it checks whether the alarm may raise a ticket, turns the alarm's times into local dates, sets the ticket's fields (requester, severity, impact, urgency, service level), builds the ticket's title and work log with formatting rules per network domain and per alarm type, assembles an XML envelope, sends it asynchronously, and marks the alarm's ticket state in the event store | It is the code to analyse and improve: all five prompts work on it. A defect in a ticketing policy shows up far away, as a wrong or empty field in a ticket, and the file is long enough that nobody re-reads it whole by hand |
| **The policy's refactoring requirement** | The operator's document, about 430 lines of text | What the policy does, in four core functions; the refactoring agenda: defects to fix (variable case mismatches, misspelt event fields, malformed XML entities), database lookups to merge, a logging standard (every line prefixed with the event's serial, no noisy field dumps, every state change logged), dead code to remove, camelCase names that reveal intent, and a three-tier modular structure with its target folder tree | It is the yardstick for the policy. The review judges each defect by its effect on the ticket the document describes; the clean-up and the renames do the items of its section 3; the gate checks that every requirement a change touches is done or explicitly left to the operator |
| **The probe rules** | One production rules file for the probe that receives the alarms of one network element manager, about 1,900 lines | Ten table declarations with absolute paths, the classification of alarm types, the mapping of each alarm to the event's fields (node, key, group, severity, type, summary), enrichment from lookup tables, flags for automatic tickets, filters that discard noise, and code switched off during past changes | A second, different kind of Netcool code, so the same prompts are shown to work beyond one language. Probe rules decide what every alarm looks like in the event list, so a defect here changes events rather than tickets |
| **The ten lookup and include files** | Data and small rule files the rules read, from under 100 bytes to about 540 KB each | Alarm names, pre-classification of alarm types, enrichment by node and port, automatic-ticket rules, node lists, the alarms included in service-level monitoring | Context, not code to change. Bob reads them when a finding depends on them (a table used but not declared, a key that cannot match); the commands are given the rules file only. The path change edits the lines that point to them, never the files |
| **The rules code standards** | The operator's document, about 55 lines | Five standards: no hard-coded values (lists of nodes, ports or alarm identifiers moved into lookups); every path through `$NC_RULES_HOME` and all table declarations in one place; one key=value log format naming the rules file and the node; no commented-out code; a standard folder tree for a probe's rules | The yardstick for the rules. The clean-up does standard 4 and the path change does standard 2. Standards 1, 3 and 5 need new code written and were kept out of the five prompts; [use case 1](../use-case-1-new-integration/) generates new rules directly in the tree of standard 5 |

### The files, one by one

The operator sent 14 files: two pieces of code, two documents, and ten files the rules read. Each is described by its role; the operator's file names are not published.

**The Impact policy and its document**

| # | File | Size | What it is | Role in the use case |
|---|---|---|---|---|
| 1 | The ticketing policy (`.ipl`) | ~3,300 lines | The production policy that turns an alarm flagged for a ticket into an incident: eligibility check, local dates, ticket fields, per-domain and per-alarm title and work log, XML envelope, asynchronous send, ticket state written back to the event. It queries the event store and reference tables a dozen times, logs on about 90 lines, and carries about 160 lines of commented-out code | The code all five prompts work on, in copies (`step-1-fixed` → `step-2-cleaned` → `step-3-standardized`); the original stays as the baseline for the final review |
| 2 | The refactoring requirement (`.txt`) | ~430 lines | The operator's own brief for this policy: what it does, the defects to fix, the database and logging work, dead-code removal, camelCase naming, and the three-tier modular target | The yardstick: prompt 1 judges defects by their effect on the ticket it describes; prompts 3 and 4 do the items of its section 3; the gate checks every requirement a change touches |

**The probe rules, their document and the files they read**

| # | File | Size | What it is | Role in the use case |
|---|---|---|---|---|
| 3 | The probe rules file (`.rules`) | ~1,900 lines | The production rules of the probe that receives an IP VPN element manager's alarms: table declarations with absolute paths, alarm classification, field mapping, enrichment, automatic-ticket flags, about 25 discard filters, and about 340 comment lines, many of them switched-off code | The second body of code; the same five prompts work on it in copies |
| 4 | The rules code standards (`.txt`) | ~55 lines | Five standards for rules files: no hard-coded values, paths through `$NC_RULES_HOME` and one place for tables, one log format, no commented-out code, a standard folder tree | The yardstick for the rules: prompt 3 does standard 4, prompt 4 does standard 2. Reused in [use case 1](../use-case-1-new-integration/) as the target layout of new rules |
| 5 | Alarm-name and code tables (`.lookup`) | ~13,700 lines, 6 tables | Inline tables that turn the element manager's numeric codes into names (alarm names and other code maps) | Read by the rules on every event; context for findings about names and codes |
| 6 | Pre-classification table (`.lookup`) | ~3,700 lines, 1 table | Each event id mapped to a pre-class number used for correlation | Context; the review checks the rules use the table they declare |
| 7 | Link enrichment table (`.lookup`) | ~9,300 lines, 1 table | Node and port mapped to the link's designation (its type and speed) | Context for enrichment findings |
| 8 | Automatic-ticket routing (`.lookup`) | ~170 rows, 4 columns | Alarm name → raise a ticket or not, the team that receives it, and the delay before it is raised | Context; its declaration line is one of the paths prompt 4 standardizes |
| 9 | IP VPN alarm classes (`.lookup`) | ~60 rows | Alarm name → the class of alarms the rules treat as IP VPN alarms | Context; path standardized in prompt 4 |
| 10 | Service-level inclusion (`.lookup`) | 4 rows | The alarms that count for service-level monitoring | Context; path standardized in prompt 4 |
| 11 | Topology enrichment include (`.rules`) | ~630 lines | Rules that split an affected object's name (port, card) into shelf, slot and port for topology correlation | Included by the rules; context |
| 12 | Older enrichment include (`.rules`) | ~260 lines | An earlier enrichment of alarm names | Referenced only from a commented-out line, so it is not used today; prompt 3 removes that line as commented-out code |
| 13 | Service alarm classes (`.lookup`) | 14 rows | Alarm name → class, for another set of alarms | Not referenced by the rules file: sent as context; nothing in the prompts depends on it |
| 14 | Node group list (`.lookup`) | 84 rows | Node names that belong to one group of nodes | Not referenced by the rules file: sent as context |

**Referenced by the rules but not sent:** fourteen more files — customer-tier lists by node, shelf, slot and port (four tiers), service-level tables by node, shelf, slot and port (four), two dashboard topology maps, a special-events table, a ticket-domain table, a second automatic-ticket table, and a common include. The prompts do not need their contents: the review checks how the rules declare and use them, and the path change rewrites only the lines that point to them.

### Why this kind of input

- **Production code** carries the conditions in which a careless edit silently breaks a ticket or an event: repeated branches, switched-off blocks, near-identical names. A clean demo file would hide that risk.
- **The operator's own documents** turn "make it better" into checkable items. Every report refers to a section or a standard number, so the operator can see which of their requirements each change serves.
- **Two kinds of code** (a policy and probe rules) show that the method is not tied to one language: the skill reads code as text.

### What was not sent

No running Impact server or probe, no sample alarms or tickets, no event-store schema. Every prompt therefore claims only what the code itself shows, and every report ends with what still needs a test where the code runs.

## How It Works

Bob is opened on one workspace folder that holds both inputs, each in its own folder with its document. Two small things in that folder steer it:

| Part | What it does |
|---|---|
| **The skill** (`.bob/skills/code-review/`) | Instructions for five tasks (review code, fix, change existing code, review a change, diagnose) and Python scripts that do the mechanical work. Generic: it names no client, product or language |
| **A short rule** (`.bob/rules/`) | Tells Bob to use the skill before any review or change, to run its commands from the workspace root, and to check where the work stands before every reply |

Each task is one command, run two or three times. The first run scans the code and writes a **notes file** with everything Bob has to decide. Bob writes its judgements there. The next run applies the notes, writes the report and the changed copy, and compares the new version with the old one. Every command ends with a `Gate:` line; a task is finished only when it prints `Gate: passed`.

```
bob-workspace/
├── .bob/
│   ├── rules/review-and-change-code.md
│   └── skills/code-review/          # SKILL.md + scripts/
├── impact-policy/
│   ├── inputs/                      # <policy>.ipl + the refactoring requirement
│   ├── refactored/                  # step-1-fixed/ → step-2-cleaned/ → step-3-standardized/
│   └── reports/                     # one report (and its notes file) per prompt
└── probe-rules/
    ├── inputs/                      # <rules>.rules + include-lookups/ + the code standards
    ├── refactored/
    └── reports/
```

## The Prompts

Every prompt has three parts: the verb of the task and what it works on, `Write` and the report, `Do not` and the limit. The verb tells Bob which task of the skill to run. The operator's file names are replaced here by `<policy>.ipl` and `<rules>.rules`; the prompt files are in [prompts/](prompts/).

### 1 · Defect register — review, no change

```text
Review impact-policy/inputs/<policy>.ipl and probe-rules/inputs/<rules>.rules for defects, one after the other, each with the document from the client next to it as the guide.
Write impact-policy/reports/defect-register.md and probe-rules/reports/defect-register.md, with the effect of each defect on the ticket for the policy and on the event for the rules.
Do not change the policy or the rules file.
```

| | |
|---|---|
| **Why this step** | Before anything changes, list what is wrong and what each defect does to a ticket or an event. The operator sees the size of the problem, and every later step refers back to this list |
| **Reads** | The original policy and rules file, each with its document; the lookup files when a finding depends on them |
| **The scripts** | Scan the code for 37 kinds of defect (a name misspelt, read before it is set or never used; a single `=` where a comparison is meant; an XML entity or tag not closed; brackets that do not balance; branches that repeat each other; code that cannot run), say for each hit where its value goes, and write the notes file with every hit to decide |
| **Bob decides** | Whether each hit is a real defect, with a reason the workspace shows; what reading adds that the scan cannot see; for each finding its effect, the fix and how sure it is; the questions only the operator can answer |
| **The gate refuses** | A hit left undecided; a finding whose quoted words are not on the line it cites; a "not a defect" without the evidence that settles it |
| **Writes** | A defect register per input, with the notes file that holds Bob's judgements |
| **Why these words** | "The effect on the ticket / on the event" makes the register speak the operator's language; "Do not change" keeps the step read-only |

### 2 · Fix — corrected copy and change log

```text
Fix the defects of impact-policy/inputs/<policy>.ipl in a copy under impact-policy/refactored/step-1-fixed and of probe-rules/inputs/<rules>.rules in a copy under probe-rules/refactored/step-1-fixed, one after the other.
Write impact-policy/reports/change-log.md and probe-rules/reports/change-log.md.
Do not decide what is the client's to decide.
```

| | |
|---|---|
| **Why this step** | Correct what is plainly wrong, in a copy, so the original stays as the baseline and every change is written down |
| **Reads** | The original file and its defect register |
| **The scripts** | Make every correction that has only one possible form, apply Bob's corrections, and compare the copy with the original. A correction tagged with the wrong finding is refused; switching commented-out code back on becomes a question, not a fix |
| **Bob decides** | The correction of each finding the code itself settles, and a specific question for each one only the operator can settle (a filter switched off on purpose, an address written into the code) |
| **The gate refuses** | A High finding with neither a correction nor a specific question; a new call, operator or non-ASCII character the original did not have, unless its reason is written; notes left untouched |
| **Writes** | The corrected copy (step 1) and a change log per input |
| **Why these words** | "Do not decide what is the client's to decide" turns business choices into questions instead of silent changes |

### 3 · Clean up — commented-out code removed

```text
Clean up a copy of each step-1-fixed, one after the other.
Policy: in a copy of impact-policy/refactored/step-1-fixed under impact-policy/refactored/step-2-cleaned, remove the commented-out code as section 3 of the requirement document asks.
Rules: in a copy of probe-rules/refactored/step-1-fixed under probe-rules/refactored/step-2-cleaned, remove the commented-out code as standard 4 of the code standards document asks.
Write impact-policy/reports/clean-up.md and probe-rules/reports/clean-up.md.
Do not change the ticket content or the events.
```

| | |
|---|---|
| **Why this step** | Remove the code switched off over the years, so engineers read only what runs. Both documents ask for it, and it is the change most often done carelessly by hand |
| **Reads** | The step-1 copy and the document's item on commented-out code |
| **The scripts** | List every commented-out line and block, telling them apart from comments that explain live code; remove what Bob confirms, in a copy; refuse to remove a comment that stands right above a live line that stays; compare the copy with step 1 |
| **Bob decides** | Which commented-out code goes (normally all of it), and which comment is an explanation to keep |
| **The gate refuses** | A removal that changes a live line or leaves half a block; an item of the document left unaccounted for |
| **Writes** | The cleaned copy (step 2) and a clean-up report per input |
| **Why these words** | "Do not change the ticket content or the events" states the safety condition the comparison checks |

### 4 · Standardize — names and paths

```text
Standardize a copy of each step-2-cleaned, one after the other.
Policy: in a copy of impact-policy/refactored/step-2-cleaned under impact-policy/refactored/step-3-standardized, rename the variables to camelCase as section 3 of the requirement document asks.
Rules: in a copy of probe-rules/refactored/step-2-cleaned under probe-rules/refactored/step-3-standardized, replace the absolute path prefix /opt/IBM/tivoli/netcool/omnibus/etc/probes/rules with $NC_RULES_HOME in every include and table line, as standard 2 of the code standards document asks.
Write impact-policy/reports/standards.md and probe-rules/reports/standards.md.
Do not change the ticket content or the events, or any folder or file name after the path prefix.
```

| | |
|---|---|
| **Why this step** | Names that say what the data is, and paths that move with the installation: the two standardizations the documents ask for that a script can make reliably |
| **Reads** | The step-2 copy and the document's item on names (policy) or paths (rules) |
| **The scripts** | Propose a camelCase name for every local variable and apply the map; refuse to rename a name another component may read (event fields, names read before they are set, names that may come from outside); for the rules, replace the prefix with one rule on the include and table lines only |
| **Bob decides** | Which proposed names to take, which to adjust, and which to leave for the operator to confirm |
| **The gate refuses** | A rename that merges two names or touches an event field; a path line where anything other than the prefix changed |
| **Writes** | The standardized copy (step 3) and a standards report per input |
| **Why these words** | The exact prefix and "any folder or file name after the path prefix" were added after a run where a looser prompt also changed folder names |

### 5 · Code review — the final copy against the original

```text
Review impact-policy/refactored/step-3-standardized against impact-policy/inputs/<policy>.ipl, and probe-rules/refactored/step-3-standardized against probe-rules/inputs/<rules>.rules, one after the other.
Write impact-policy/reports/code-review.md and probe-rules/reports/code-review.md.
Do not fix anything.
```

| | |
|---|---|
| **Why this step** | An independent check of the final copy against the original: everything that changed, judged, before anyone deploys it |
| **Reads** | The final copy, the original, and every earlier report and notes file |
| **The scripts** | Compare the two versions line by line, count the defects before and after, group the differences (corrections, removals, renames, path changes), and check the claims of the earlier reports |
| **Bob decides** | For each difference: no change of behaviour, intended (and by which report), or unintended; what reading adds; the operator's open decisions as questions |
| **The gate refuses** | Any difference left unjudged; a claim of an earlier report that the files do not bear out |
| **Writes** | A review of the whole change per input |
| **Why these words** | "Do not fix anything" keeps the reviewer and the author apart, even when both are Bob |

### What the prompts leave out, and why

The operator's documents also ask for a split into a modular structure, merged database queries, rewritten log statements and lookup files for hard-coded values. Those were tried and kept aside: where Bob had to write new code itself, the result varied from run to run and was sometimes wrong while its gate passed. The five prompts keep to what the scripts make reliable.

## From Input to Output

| Prompt | Reads | Writes |
|---|---|---|
| 1 · Defect register | Each original file and its document | A defect register per input |
| 2 · Fix | Each original file and its register | A corrected copy (step 1) and a change log |
| 3 · Clean up | The step-1 copy and the document's item on commented-out code | A cleaned copy (step 2) and a clean-up report |
| 4 · Standardize | The step-2 copy and the document's item on names or paths | A standardized copy (step 3) and a standards report |
| 5 · Code review | The step-3 copy, the original, every earlier report | A review of the whole change |

## Results

| Run | Result |
|---|---|
| First run, full scope | Register and fix usable; the split into modules passed its gate and was wrong. The split, the log rewrite and the lookup files were taken out of the prompts |
| Clean runs 1–4 | Each closed a gap: the path change limited to the prefix, the review written by the script, comments that explain live code kept, commands given the file the prompt names |
| **Clean run 5, untouched** | **All ten gates passed with no intervention**: nothing typed but the five prompts, 44 minutes, about 53 Bob coins. Every step checked by hand was right; the final reviews found no unintended change and raised the operator's open decisions as questions |

**Lessons:** where a script makes the change, the result is the same and right every time; where Bob writes new code itself, it varies. A gate proves the work is complete and accounted for, not that it is right, so each step's report is read before the next prompt.

## Running It

1. Open the workspace folder itself in IBM Bob, not its parent.
2. In Bob's settings, raise the limit on the number of turns of a task above its default of 100.
3. Start a new chat in the built-in **Agent** mode and send the five prompts in order, and nothing else.
4. After each prompt, Bob's commands should have printed `Gate: passed` twice, once for each input. Read the reports before sending the next prompt.
