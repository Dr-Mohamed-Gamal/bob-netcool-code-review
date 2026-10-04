# Use Case 3 — Add a Device to a Dashboard, and Debug It

Prompts that let IBM Bob add a new device to an existing Netcool Impact dashboard with exactly the same tiles, filters and selection as the devices already on it, review that change, fix what the review finds and review the fix, and, apart from that loop, trace a fault reported on the dashboard to its line. Bob uses the same generic [code-review skill](../SKILLS/code-review/) as in [use case 5](../use-case-5-code-review/).

> Pilot use case for a telecom operator. The operator's page, device names and reports are not published here: this page describes the inputs, the method and the prompts.

## Overview

The operator's dashboard is an Impact Operator View page: HTML with inline JavaScript, fed every minute by an Impact policy. It lists the network devices of one area. Each device has a checkbox that adds it to the overview counts, and three tiles, Critical, Major and Minor, that open the Event Viewer filtered on that device's alarms. Every device is also named in the page's "select all" and "unselect all" functions.

The request: when a device comes into service, Bob must be able to add it so that it has **the same dashboard attributes** as the others. The operator also wants faults reported on the dashboard to be traced to their cause.

## The Input Data

The input is **the operator's production dashboard page itself**, the file the operations team opens and edits by hand today, together with the request for the new device and, for the debug prompt, a fault as an operator would report it.

| Input | What it is | What is in it | Why it is used |
|---|---|---|---|
| **The dashboard page** | One Netcool Impact Operator View page, about 690 lines and 145 KB: HTML, inline JavaScript and the event attributes of its controls | 22 device rows. Each row has a checkbox that adds the device to the overview counts, three tiles (Critical, Major, Minor) that each open the Event Viewer filtered on that device's alarms by its device type, and a label placed with a style value. Four functions: add a filter, open a link, select all, unselect all; the last two name every device. The page loads seven scripts and two style sheets from the server | It is the code to change. One existing row is the model the new device is copied from; the two select lists must name the new device too; the review compares the changed copy with this page; the debug prompt reads the tiles' filters |
| **The request** | The new device's name and device type, and the existing device to model it on | A new platform coming into service (the one integrated in [use case 1](../use-case-1-new-integration/)), to be added with the same attributes as the others | It is the operator's real next need. The model is a device whose names are its own, so the copy cannot inherit a filter another device shares; the review shows anything shared anyway |
| **A reported fault** (debug prompt only) | A symptom in an operator's words: one device's tiles open another device's alarms | No line number and no cause, only what an operator sees | It shows Bob going from a symptom to the line without changing anything, which is how dashboard faults arrive in practice |

### The files, one by one

The operator sent **one file**: the dashboard page. The operator's file and device names are not published.

| # | File | Size | What it is | Role in the use case |
|---|---|---|---|---|
| 1 | The dashboard page (`.html`) | ~690 lines, ~145 KB | A Netcool Impact Operator View page: the layout of the area's dashboard, 22 device rows, about 100 click handlers on the tiles, and four functions (add a filter, open a link, select all, unselect all) in inline JavaScript | The only code: prompt 1 copies a model row in a copy of this page; prompts 2 and 4 compare the copies with it; prompt 5 reads it to trace a fault |

**Referenced by the page but not sent:**

| What | How many | What it does on the live system | Effect on the use case |
|---|---|---|---|
| Scripts loaded by the page | 7 (a UI framework, its plugins, and three of the operator's own scripts) | Fetch the alarm counts, build the device filter from the ticked checkboxes, and draw the tiles | The new device's counts stay at 0 until these scripts know its device type; the review asks the operator to confirm. The prompts claim nothing about them |
| Style sheets and images | 2 style sheets and the images they use | The look of the page | For the before-and-after picture, the page was opened locally with mock styles |
| The Impact policy that feeds the page | 1 | Computes the counts per device every minute | Not needed to add the device to the page; needed for its counts on a live system |

The use case was defined as "complete code package and existing code, with mock data": only the page came, so the prompts work on the page alone and say so in every report.

### Why this kind of input

- **The production page, not a simplified copy.** Adding a device by hand means copying about ten lines from a row that works and changing every name in them. The real page has twenty-odd rows that look almost the same, filter names that differ by one word, and style values that depend on the length of each label. That is where hand edits go wrong unseen, and exactly what a simplified copy would hide.
- **A real next device.** The device added is the platform the operator is integrating now, so the demonstration matches work the team will do.
- **A fault in an operator's words.** Faults are reported by what people see, not by line numbers; the debug prompt starts from the same place.

### What was not sent

The page's own scripts (those that fetch the counts and build the device filter), its style sheets and images, and the Impact policy that feeds it every minute. So the prompts claim only what the page shows; the new device's counts will stay at 0 on a live system until those scripts and the policy know its device type, and the review raises that as a question. For the before-and-after picture, the page was opened locally with mock counts and mock styles.

## How It Works

The skill's change task has a **copy** operation. Bob names the model device, the block of lines that is its row, and the other spellings of its name; the script does the rest. A made-up example of what Bob writes in its notes:

```text
### copy sw1 as sw2
lines: 40-47
replace:
  F_SW1_ -> F_SW2_
  SW1 -> SW2
why: the owner asks for the device SW2, with the same tiles, filters and selection as SW1.
```

The script then copies the model's block right after itself with only those replacements, finds every other line of the page that names the model (the select lists) and copies each one right after itself the same way, and **refuses** the copy while:

- it still holds any name of the model, in any letter case, so no tile can keep an old filter;
- a new name is already used in the page, so ids and filter names stay unique;
- the block is not whole (a tag or bracket opened and not closed), so the layout cannot break;
- a style value that varies between the rows does not fit the new label.

In a web page the scanner reads only the scripts and the event attributes (`onclick`, `onchange`), keeping the page's line numbers; on this page that took the scan from 110 places, almost all markup noise, to 2.

```
uc3-dashboard/
├── .bob/
│   ├── rules/review-and-change-code.md
│   └── skills/code-review/          # SKILL.md + scripts/
├── inputs/                          # <page>.html
├── refactored/                      # step-1-device-added/ → step-2-fixed/
└── reports/                         # add-device, code-review, change-log, code-review-2, diagnosis
```

## The Prompts

A closed loop of four prompts: add, review, fix, review the fix. Prompts 3 and 4 repeat until the review is clean; when the review finds nothing, the fix passes at once without changing anything. Debugging is a separate prompt, used whenever a fault is reported. Names in angle brackets are filled in for the device being added and the fault being reported. The prompt files are in [prompts/](prompts/).

### 1 · Add the device — a copy, under names of its own

```text
Add the device <NEW DEVICE>, with DeviceType '<NEW DEVICE>', modelled on the <MODEL> device, to a copy of inputs/<page>.html under refactored/step-1-device-added: the same tiles, filters and selection, under names of its own.
Write reports/add-device.md.
Do not change inputs.
```

| | |
|---|---|
| **Why this step** | Make the change the operator asked for: a new device with exactly the same tiles, filters and selection as an existing one, under names of its own |
| **Reads** | The page; the plan file shows the model device's row lines and every other line that names the model |
| **The scripts** | Copy the model's block right after itself with only the replacements Bob lists, copy each other line that names the model (the select lists) right after itself the same way, and account for every string and call the copy repeats |
| **Bob decides** | The model, the new names, the lines of the model's block, the replacements, and any style value that depends on the label (the value used by rows whose label is as long as the new one) |
| **The gate refuses** | A copy that still holds any name of the model; a new name the page already uses; a block that is not whole; a second block for the same model; a style value that does not fit the new label |
| **Writes** | The changed copy (step 1) and a report of the copy |
| **Why these words** | "In a copy … under refactored/…" keeps the original as the baseline; "Do not change inputs" protects it; "under names of its own" rules out sharing the model's filters |

#### What if the new device is not exactly like the model?

The copy repeats the model's lines and changes only the names Bob lists. So the new device gets the model's tiles, filters and selection, and nothing else.

- **A value that depends on the label**, such as the margin that lines the tiles up after the label, is taken from the rows whose label has the same number of characters as the new one, and the report names those rows. If no row has a label of that length, the model's value stays and the report asks the owner.
- **Anything the model does not have**, such as another tile or another condition in the filter, cannot come from a copy. Bob writes it as a question for the owner; nothing is invented.
- **The gate refuses** a copy that still holds any name of the model, a new name the page already uses, or a block that is not whole.

**The limits.** The copy is checked as text. The page's own scripts, which fetch the counts and build the device filter, were not sent, so whether they pick up the new device cannot be checked here; the report asks the owner. Nothing was opened on the live system.

### 2 · Review the change — the copy against the original

```text
Review refactored/step-1-device-added against inputs/<page>.html.
Write reports/code-review.md.
Do not fix anything.
```

| | |
|---|---|
| **Why this step** | Check the change independently: every line that differs between the copy and the page, and nothing else |
| **Reads** | The step-1 copy, the original page and the add report |
| **The scripts** | Compare the two versions line by line, keeping strings in the alignment so near-identical rows are not mismatched, and list every difference with the strings and calls it adds |
| **Bob decides** | For each difference: intended or not, with the reason; what only the owner can confirm (for example, whether the page's scripts pick up the new checkbox) |
| **The gate refuses** | Any difference left unjudged |
| **Writes** | A review of the change |
| **Why these words** | "Do not fix anything" keeps the reviewer and the author apart |

#### What does the review check, and what can it miss?

The review works in two passes:

1. **The comparison (a script)** lists every line that differs between the copy and the original page, with the strings and calls each difference adds or removes. Nothing that changed can be left out of the list, not even a lost line or a changed line ending.
2. **Bob** judges each difference: intended (part of the request) or unintended, with the reason. It also reads the changed lines and the lines that use the same names, such as the select lists, for problems a comparison cannot show, such as a tile that still opens the model's filter.

The gate does not pass while any difference is left unjudged.

**The limits.** The review sees only this page. It cannot see the scripts the page loads from the server, and it does not open the page in a browser. What only the owner can confirm goes into the report as a question.

### 3 · Fix — the findings of the review

```text
Fix the findings of reports/code-review.md in a copy of refactored/step-1-device-added under refactored/step-2-fixed.
Write reports/change-log.md.
Do not decide what is the client's to decide.
```

| | |
|---|---|
| **Why this step** | Correct what the review found, if anything, in a new copy |
| **Reads** | The review's findings and the step-1 copy |
| **The scripts** | Apply the corrections from Bob's notes in a copy and compare it with step 1. With no finding, the fix passes at once and the copy is unchanged |
| **Bob decides** | The correction of each finding, or a question for the owner |
| **The gate refuses** | A finding with neither a correction nor a question |
| **Writes** | The fixed copy (step 2) and a change log |
| **Why these words** | "Do not decide what is the client's to decide" leaves design questions with the owner |

### 4 · Review the fix — the fixed copy against the original

```text
Review refactored/step-2-fixed against inputs/<page>.html.
Write reports/code-review-2.md.
Do not fix anything.
```

| | |
|---|---|
| **Why this step** | Close the loop: the fixed copy reviewed against the original page. Prompts 3 and 4 repeat until the review is clean |
| **Reads** | The step-2 copy and the original page |
| **The scripts** | The same comparison as prompt 2 |
| **Bob decides** | The same judgements as prompt 2 |
| **The gate refuses** | Any difference left unjudged |
| **Writes** | A second review |
| **Why these words** | The same three-part form as every other prompt, so Bob picks the task from the first word |

### 5 · Debug — from a reported symptom to the line (separate)

```text
Diagnose inputs/<page>.html: the <DEVICE> tiles open the alarms of <OTHER DEVICE> instead of those of <DEVICE>.
Write reports/diagnosis.md.
Do not fix anything.
```

| | |
|---|---|
| **Why this step** | Show how a reported fault is traced to its cause without touching the page |
| **Reads** | The original page and the symptom in the operator's words |
| **The scripts** | List every line that names what the symptom involves (the two devices, their filters), with the scan hits on those lines |
| **Bob decides** | Each possible cause with its line, a quote that is on that line, how the line produces the symptom, and whether it is shown, ruled out, or open with the test that decides it |
| **The gate refuses** | A quote that is not on its line; a diagnosis with no cause shown and an open cause that names no test |
| **Writes** | A diagnosis |
| **Why these words** | The symptom is given as reported; "Do not fix anything" keeps the page unchanged, since the cause may be by design |

#### How is the cause found, and what if it is not in the page?

The diagnosis works in two passes:

1. **The script** lists every line that names what the symptom involves (the two devices, their tiles, their filters), with the scan's hits on those lines.
2. **Bob** reads those lines and compares the faulty tiles with tiles that work. Each possible cause gets its line, a quote from that line, how it produces the symptom, and a status: **shown** (the line itself proves it), **ruled out**, or **open**, with the test that would decide it. The gate checks that every quote is on its line.

- **If the cause is not in the page**, because it is in a script the page loads, in the Impact policy or in the events, the diagnosis says that no cause is shown in the page and names the test that would decide it.
- **If the code may be doing what its owner intended**, for example a filter that covers two devices on purpose, the diagnosis asks the owner instead of calling it a bug. That is why the prompt says "Do not fix anything".

**The limits.** The diagnosis is a reading of the code; nothing is run.

## From Input to Output

| Prompt | Reads | Writes |
|---|---|---|
| 1 · Add the device | The page and the request | A copy with the new device (step 1) and a report of the copy |
| 2 · Review the change | The step-1 copy, the original page, the add report | A review of every difference |
| 3 · Fix | The review's findings and the step-1 copy | A fixed copy (step 2) and a change log; with no finding, the copy unchanged |
| 4 · Review the fix | The step-2 copy and the original page | A second review |
| 5 · Debug | The original page and the symptom | A diagnosis: the cause on its line, or the test that decides it |

## The Output of Each Prompt

After the five prompts, the workspace holds the original page, two copies of it and five reports.

```
uc3-dashboard/
├── inputs/<page>.html                     # the original: never changed
├── refactored/
│   ├── step-1-device-added/<page>.html    # prompt 1: the page with the new device
│   └── step-2-fixed/<page>.html           # prompt 3: step 1 with the review's findings fixed, the deliverable
└── reports/
    ├── add-device.md                      # prompt 1
    ├── code-review.md                     # prompt 2
    ├── change-log.md                      # prompt 3
    ├── code-review-2.md                   # prompt 4
    └── diagnosis.md                       # prompt 5
```

### Device added, fixed

Each step is a whole copy of the page, made from the step before it. The original is never changed. The examples below are made up.

| Step | What it means | Example | Does anything else change? |
|---|---|---|---|
| **step-1-device-added** | The original page plus the new device. The device gets its own row: a checkbox with its label and three severity tiles (critical, major, minor), each opening the event list through its own filter. It also gets one line in each of the scripts that select or clear all devices. Each new line is a copy of the model device's line, with only the model's names replaced | The model's tile `id="sw1Critical"` with filter `F_SW1_Critical` and `DeviceType = 'SW1'` gives a new tile `id="sw2Critical"` with filter `F_SW2_Critical` and `DeviceType = 'SW2'` | No. Every other line stays byte for byte, including its line ending |
| **step-2-fixed** | Step 1 with the findings of the review corrected. When the review finds nothing to fix, as in the clean runs, this copy is identical to step 1 | A tile that kept the model's filter name would be given the new device's own | No. Only the lines of the findings change |

The diagnosis (prompt 5) changes no file. It reads the original page and names the line that causes the reported symptom.

### The reports

Every report starts with a **Verdict** and ends with **Checks performed**, **Not checked** and **Questions for the owner of the code**. Each has a notes file beside it (`<report>.notes.md`) where Bob writes its decisions. The script writes the report from those notes.

| Prompt | Report | What it tells the reader | Main parts |
|---|---|---|---|
| 1 | `add-device.md` | Exactly which lines were added for the new device, and from which model lines | Changes made (each new line and the model line it copies); copies made (the model's lines, the replacements); every string the copy wrote; the style value chosen for the new label and why |
| 2 | `code-review.md` | Whether the copy can replace the original page | The two versions in numbers; what the change consists of (lines added, rewritten, removed); every difference, judged intended or unintended; findings, each with its line quoted |
| 3 | `change-log.md` | What was fixed in step 2, and what was left to the owner | Changes made (line, before, after); findings not corrected and why |
| 4 | `code-review-2.md` | The same review for the fixed copy | Same parts as the first review |
| 5 | `diagnosis.md` | Why the symptom happens, without changing the page | The symptom; the causes (line, quoted code, how it produces the symptom, status: shown or likely); every line that names what the symptom involves; the evidence; the fix proposed, not made |

## Results

| Run | Result |
|---|---|
| First run | The copy was right, and Bob noticed by itself that each tile's margin follows the length of its label. It also showed what to tighten: the copy could land in the wrong folder, a second copy block for the same device was not refused, and Bob chose a margin no other row uses. Each became a check in the skill |
| Standardized prompts, full loop | **All five gates passed at the first attempt** (add, review, debug, fix, review the fix), in one new chat: 12 minutes and about 15 Bob coins. The review found nothing to fix, so the fix passed in seconds with the copy unchanged |
| Clean run | **All three gates passed at the first attempt**, about 10 minutes and 10 Bob coins. Checked by hand: the copy added exactly the new row and its two select lines, with its own filter names and the right margin, and changed nothing else; the diagnosis showed the cause on its line and left the owner's question open |

Still to come: the counts of the new device on a live system, which need the Impact policy and the page's scripts to know its device type.

## Running It

1. Open the dashboard's workspace folder in IBM Bob. It holds the page under `inputs/` and the skill under `.bob/`.
2. Start a new chat in the built-in **Agent** mode and send the prompts in order, with the names filled in.
3. After each prompt, Bob's command should end with `Gate: passed`. Read the report it names before sending the next one.
