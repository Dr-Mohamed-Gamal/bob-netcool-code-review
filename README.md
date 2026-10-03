# IBM Bob on Netcool Code — Pilot Use Cases

Three pilot use cases for a telecom operator, run with **IBM Bob** in its built-in Agent mode on the operator's real Netcool code and data: generating probe rules for a new device from its MIBs, adding a device to an Impact dashboard, and analysing, fixing and standardizing existing Impact policies and probe rules. Each use case is a short series of prompts that ran right the first time in Bob, steered by a generic skill whose scripts do the mechanical work and whose gates check every step.

> The operator's code, data, documents and the reports made from them are not published here. This repository describes, for each use case, the inputs and why each is used, the method, every prompt in detail, and what the runs showed.

## Use Cases

| # | Use case | What Bob does | Inputs | Prompts | Clean run in Bob |
|---|---|---|---|---|---|
| **1** | [New integration: from MIBs to probe rules](use-case-1-new-integration/) | Catalogues a trap list against the vendors' MIBs, generates the probe rules and lookups in the operator's folder tree, and reviews them with a rules simulator | A trap-list workbook, 63 vendor MIB files, a business requirement, the operator's rules standards | 3 (+2 when the review finds something) | All 3 gates first time, ~3.5 min, ~2 Bob coins |
| **3** | [Add a device to a dashboard, and debug it](use-case-3-dashboard/) | Adds a device exactly like an existing one, reviews the change, fixes and reviews again; traces a reported fault to its line | The production Operator View page, the request, a reported fault | 4 in a loop + 1 for debugging | All 5 gates first time, ~12 min, ~15 Bob coins |
| **5** | [Code analysis, standardization and optimization](use-case-5-code-review/) | Writes a defect register, fixes, removes commented-out code, standardizes names and paths, and reviews the whole change | A production Impact policy and probe rules file, each with the operator's requirement or standards document | 5, each on both inputs | All 10 gates, untouched, ~44 min, ~53 Bob coins |

The numbers follow the operator's list of use cases. Use case 1 is the largest share of the work: the operator rates it at about 80% of the effort.

## How Bob Is Steered

Each use case has a Bob workspace that holds the inputs and two small things:

| Part | What it does |
|---|---|
| **A skill** in `.bob/skills/` | Instructions for the tasks of the use case and Python scripts that do the mechanical work: they read the inputs, propose every decision, write every report and every changed or generated file, and compare the result with the original |
| **A short rule** in `.bob/rules/` | Tells Bob to use the skill, to run its commands from the workspace root, and to check where the work stands before every reply |

Every task runs the same way:

1. **First run** — the script reads the inputs and writes a **notes file**: the facts, and every decision to make with a proposal.
2. **Bob's notes** — Bob decides, in the notes file; it never types a report, a rule or a line of changed code itself.
3. **Next run** — the script applies the notes, writes the report and the files, and checks them.
4. **Gate** — every command ends with a `Gate:` line; a task is finished only when it prints `Gate: passed`.

Every prompt has the same three parts: the verb of the task and what it works on, `Write` and the report, `Do not` and the limit. The verb tells Bob which task of the skill to run.

## The Skills

| Skill | Used in | What it covers |
|---|---|---|
| [SKILLS/code-review](SKILLS/code-review/) | Use cases 3 and 5 | Review code, fix findings, change existing code (clean-ups, renames, rules over many lines, splits, copies), review a change, diagnose a failure — in any language |
| [SKILLS/trap-rules](SKILLS/trap-rules/) | Use case 1 | Catalogue a trap list against MIBs, generate the rules and lookups of an SNMP trap probe, review them with a rules simulator |

Each skill folder follows the Bob marketplace layout: `README.md` (the listing), `SKILL.md` (what Bob loads), `scripts/` (the work) and `tests/`. Install one by copying its folder into a workspace's `.bob/skills/`, or clone its own repository: [bob-code-review-skill](https://github.com/Dr-Mohamed-Gamal/bob-code-review-skill), [bob-trap-rules-skill](https://github.com/Dr-Mohamed-Gamal/bob-trap-rules-skill).

Both skills are generic: they name no client, and they take a project's rules from the documents placed next to its inputs.

## Repository Structure

```
bob-netcool-code-review/
├── README.md                              # this overview
├── SKILLS/                                # the two skills, in the Bob marketplace layout
│   ├── code-review/                       # use cases 3 and 5
│   │   ├── README.md                      #   the listing: what it does, when to use it, install
│   │   ├── SKILL.md                       #   what Bob loads: tasks, rules and gates
│   │   ├── scripts/                       #   run.py and the scripts that do the work
│   │   └── tests/                         #   669 tests on small synthetic samples
│   └── trap-rules/                        # use case 1
│       ├── README.md
│       ├── SKILL.md
│       ├── scripts/                       #   MIB and workbook readers, catalogue, generator, review, simulator
│       └── tests/                         #   48 tests on synthetic MIBs and trap lists
├── use-case-1-new-integration/
│   ├── README.md                          # the inputs and why, the method, every prompt in detail, results
│   └── prompts/
│       ├── 01-catalogue.md
│       ├── 02-generate.md
│       ├── 03-review.md
│       └── 04-05-fix-and-review-fix.md
├── use-case-3-dashboard/
│   ├── README.md
│   └── prompts/
│       ├── 01-add-device.md
│       ├── 02-review-change.md
│       ├── 03-fix.md
│       ├── 04-review-fix.md
│       └── 05-debug.md
├── use-case-5-code-review/
│   ├── README.md
│   └── prompts/
│       ├── 01-defect-register.md
│       ├── 02-fix.md
│       ├── 03-clean-up.md
│       ├── 04-standardize.md
│       └── 05-code-review.md
└── index.html, dashboard.html, integration.html   # the same use cases as web pages
```

Each prompt file holds the prompt to copy and, under it, what the prompt reads, what the scripts do, what Bob decides, what the gate refuses, what it writes, and why its words are chosen.

## Web Pages

The same use cases as web pages, published with GitHub Pages: [use case 5](https://dr-mohamed-gamal.github.io/bob-netcool-code-review/), [use case 3](https://dr-mohamed-gamal.github.io/bob-netcool-code-review/dashboard.html), [use case 1](https://dr-mohamed-gamal.github.io/bob-netcool-code-review/integration.html).

## What the Runs Teach

- **Where a script makes the change, the result is the same and right every time**; where Bob writes new code itself, it varies from run to run. The prompts keep to what the scripts make reliable.
- **A gate proves the work is complete and accounted for, not that it is right.** Each step's report is read before the next prompt is sent.
- **Bob accepts the proposals it is given**, so the scripts' proposals carry the judgement, and a block is left open only where Bob must write something itself.
- **A stand-in dry run first.** An AI agent playing Bob, with only the rule and the skill, found the most serious gaps before any Bob coins were spent.
- **Leave the operator's decisions to the operator.** Every report ends with the questions only the operator can answer.
