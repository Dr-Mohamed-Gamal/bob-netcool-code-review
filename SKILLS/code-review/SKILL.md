---
name: code-review
description: >-
  Use when asked to review code or a code change, to find the cause of a
  defect or failure, to fix a finding, or to optimize, restructure, split or
  migrate existing code while keeping its behaviour, in any language. Covers
  reviewing a change against the version it started from, reviewing code that
  has no earlier version, diagnosing a failure, making a fix, and changing
  existing code safely. Also triggered by prompts that start with Review, Fix,
  Clean up, Standardize, Rename, Split, Add or Diagnose.
metadata:
  enabled: true
  author: Dr-Mohamed-Gamal
  version: "1.0.0"
---

# Skill: Code Review, Diagnosis and Change

This skill guides Bob through work on existing code that must be repeatable and verifiable: reviewing code, fixing findings, changing code without changing what it does, reviewing a change against the version it started from, and diagnosing a failure.

It is generic: it names no product, platform or language, and reads code as text. The rules of a project come from the documents placed next to its code, which the scripts read by themselves.

---

## Background: Why Scripts and Gates?

When an assistant edits code freely, the result can vary from run to run, and it can say "done" while a line is wrong. This skill splits the work so that each part is done by what does it best:

| Who | Does what |
|---|---|
| Bob | Judges: which scan hit is a real defect, which correction is right, what to copy and under which names, which difference is intended, what only the owner can settle |
| The scripts | Scan, write every report and every changed file from Bob's notes, compare the new version with the old one line by line, and refuse to finish while anything is unexplained |

---

The scripts of this skill do the work. They write every report, every corrected copy and every new file; you write a short **notes file** that holds only what a reader of the code can say: a decision, a finding, a correction, a plan. A task is finished when its command prints `Gate: passed`.

Work from what the files show, not from what anyone says about them. When you wrote the code yourself earlier in the conversation, put that memory aside and read the files again.

## The scripts
They are in the `scripts` folder next to this file; the commands below are written as `scripts/run.py`, so when you run them from another folder, put the path of this skill's folder in front. They read code as text, in any language (in a web page, its scripts and event attributes), need only Python, and give the same output every time. Where a workspace holds more than one body of code, each in its own folder with its own documents, give every path with that folder in front: the scripts then use the documents of that code only, and print the ones they left out. Give a command the file the request names, not the folder it is in: other files next to it (lookup tables, includes, data) are context to read when needed, not code to review. Give a folder only when the request names the folder, or the code is spread over its files.

| Command | What it does |
|---|---|
| `python3 scripts/run.py review <code> --out <report>` | Scans the code, reads the documents that came with it in the workspace (the requirement, lists of names with their types) and uses them by itself, merges your notes, writes the review report and says what is still to do. The first run writes the notes file `<report>.notes.md` with the rows to decide and the form of each part |
| `python3 scripts/run.py fix <code> --out <folder> --log <change log> --register <review report>` | Writes a corrected copy with the corrections that have one form plus those in your notes, writes the change log, compares the copy with the original. The first run writes `<change log>.notes.md` with the findings still open |
| `python3 scripts/run.py look <code>` | Counts what is in the code: repeated calls, calls inside loops, logging, unused names, commented-out code, line endings |
| `python3 scripts/run.py edit <code> --out <folder> --report <report> --map <map file>` | Applies the plan in `<report>.notes.md` (corrections, rules, renames, new files) in a copy, writes the report, traces where every line went (the map) and compares the two versions. The first run writes the plan file with the facts of the code to start from |
| `python3 scripts/run.py change <before> <after> --out <review>` | Reviews a change: compares the two versions, writes the review report (both versions in numbers, the scan counts before and after, every difference) and the notes file `<review>.notes.md` with each difference to judge and the form of each part. Without `--out`, with `--map` or `--report`, it only prints the comparison |
| `python3 scripts/run.py diagnose <code> --out <report>` | Diagnoses a failure without changing the code: lists every line that names what the symptom involves, with the scan hits on those lines, and writes the diagnosis from your notes (the symptom, the evidence, each cause with its line, how it produces the symptom, and whether it is shown, ruled out or open). The first run writes `<report>.notes.md` |
| `python3 scripts/run.py status` | Lists every task started in this workspace, whether its gate passed, and the command of each one that is not finished. A task never started is not in the list: compare it with every report the latest request asks for |
| `python3 scripts/run.py check <report> <code> --intent <requirement document>` | Checks a review report on its own: every scan place is in it, no row is left to judge, every quoted line is on the line it cites |

The scan behind these commands looks for 37 kinds of defect. Names: read and never assigned, assigned and never read, misspelt, not in the list of names a document gives, written in two letter cases, read before they are set, overwritten at once, replaced before anything reads them. Conditions: a single = where a comparison is meant, a ; straight after the condition, the same condition twice in one chain, comparisons that contradict each other, && and || mixed without brackets, a value compared with itself, a comparison whose result is not used. Structure: brackets that do not balance, an else with no if, an empty block, branches with the same statements, the same label twice in a switch, a function defined twice or never called, code after a return, a loop that nothing ends, a loop bound that includes the size, a result indexed before its size is checked, an error handler that only logs. Text in strings: an entity or a tag not closed, a string not closed, placeholder text, an environment name or a credential, a query or a command joined with a value. Data: a value given to the code that the code changes, a replacement limited to a count, a replacement made twice on the same value. For each row it also says where the line lands: what it sets, where that value goes, and which blocks it is inside.

## The rules that keep a run short
- **Never edit a report, a copy or a map, and never write one yourself.** They are written by the scripts and written again on every run; what you type into them is lost. Everything you have to say goes into the notes file. The file the user asks for is the file the command writes: give the command that name with `--out`, `--log` or `--report`. Do not produce a second, shorter or reworded version of a report under any name.
- **Do not open the reports of your own task, and never count by hand.** The notes file and what the command prints hold all you need: the rows to decide with their code, the lines that already have a scan row, the findings still open, the state (done, to do, to correct) and the counts. Copy the counts as printed. Never look a report up row by row. The exception is the review of a change: there the author's reports and notes are what you check, so open them.
- **One pass.** Read the notes file the command wrote, read the code once from the first line to the last in large pieces, write the whole notes file in one go, run the command again. If it lists something to correct, correct the notes and run again, in the same turn. Expect two runs of the command, three at most.
- **Do not re-type code.** A correction is the new line in the notes; a change of many lines is a rule, a rename or a plan of line ranges. The script writes the files.
- **The gate decides.** The last line a command prints starts with `Gate:`; do not judge the result yourself. The first run of `review`, `fix` and `edit` writes the notes file and stops at `Gate: not passed yet`: that is expected. Later, exit code 3 means not passed yet, which is a result, not a failure. If a command says a script failed, or ends with no `Gate:` line, the script has a fault: tell the user which command and what it printed, and do that step by hand, saying so in your reply.
- **Know where the work stands.** A conversation may hold several requests and may be summarized on the way. The request to work on is the latest message of the user. When you are not sure what is finished, and before every reply, run `status`: finish what it shows as not passed, and reply about the latest request only.
- **Short values.** One sentence for each value you write in a notes file. The reports are read by an engineer who wants the finding, not an essay.

## Pick the task
Prompts follow one form: a first line that starts with the verb of the task and says what and where, then `Write <report>.`, then a `Do not ...` line. The verb picks the task; run its command at once, with the report the prompt names.

| The prompt starts with | The user asks for | Use |
|---|---|---|
| Review `<code>` | A review of code with no earlier version | B. Review code |
| Fix | A correction to findings or defects | D. Fix |
| Clean up, Standardize, Rename, Split, Add (an item modelled on another) | An optimization, clean-up, restructuring, split, rename, migration or addition to existing code | E. Change existing code |
| Review `<changed>` against `<baseline>` | A review of a change, when the earlier version exists | A. Review a change |
| Diagnose `<code>`: `<symptom>` | The cause of a failure, an error or a wrong result | C. Diagnose |

Say which one you are doing, in one line, before you start. If more than one applies, do them in the order C, D, E, A.

## What you write, in every task
- **Evidence.** A finding names the file and line and a few words that are on that line; the script quotes the line itself and refuses words that are not there.
- **Disprove before you report.** Follow the value or the control flow in the files; report a finding only if it survives.
- **Say what the text shows, not what you assume the runtime does.** How a language treats an operator, an unset name or a mismatch of types "needs a test", unless a document in the workspace or the code itself settles it. If your reading means the code could never have worked, and it is known to be in use, doubt your reading.
- **A reason that the workspace shows.** "Not a defect" needs the evidence: the list of names that holds it, the handler that sets it, the caller that reads it. A guess about a platform or a legacy variable is not a reason; when nothing in the workspace settles it, it goes to the owner with the question.
- **Never say tested, verified or working** unless you ran it and can show the output. Claim only what you checked; a review that says a requirement is "done" has done nothing.
- **Never change the original.** Every change is made in a copy by the script; the original stays as the baseline. The script keeps the line endings and the encoding.
- **One concern at a time.** A fix, an optimization and a restructuring are separate tasks with separate reports, even when one request asks for two of them.

---

## B. Review code with no earlier version

1. **Run** `python3 scripts/run.py review <code> --out <report>`, where `<report>` is the file the user asked for. It writes the report and the notes file, and prints what is to do. If you started under another name, run the command again with the right name: your notes are taken over.
2. **Read the notes file.** Under "Decisions" it lists each row the scan could not settle, with the code around it, where the name is set and read, and the question to answer. Decide each one from that context and from the document (a list of names, a schema) if there is one: `finding`, `not a defect: <what shows it>`, or `owner: <the question>`.
3. **Read the code once, in order,** for what a scan cannot find, and write each finding as a block under "Findings from reading" (line, severity, a few words of the line, what it does, the fix, the confidence). Start from the intent document if there is one: every kind of defect it names and every example it gives must be in the report or reported as "none found". Do not describe again what the scan already has: the notes file lists those lines. Look for what happens across lines: a condition that tests the wrong thing; a value set on only some of the paths that reach its use; a later assignment that throws away what earlier lines built; a check that runs before the values it checks exist; text built for one format placed into another; escaping done twice; a failure that leaves state half-changed; input used without validation; a call to a database or service inside a loop. The notes file lists the lines that already have a scan row: the same defect needs no second finding there, and a block that restates one is added to that row instead of counted twice. Your findings are numbered `R-01`, `R-02` and so on, in the order of the blocks.
4. **Fill the rest of the notes:** one line per requirement of the intent document under "Coverage of the intent" (`<requirement> | <what was found: the IDs or the count, or none found>`); if the user asked what each defect does to an outcome, the "Effect" part (the outcome after `column:`, one line per kind of finding); the lines you read; the questions for the owner; what was not checked. The verdict of the report is written by the script from the tables. In the "Effect" part say only what the text proves: where the effect depends on how the platform treats the defect, start the sentence with "If"; a defect in a value that nothing uses has no effect, and the notes say where each value goes.
5. **Gate. Run** the same command again. It writes the report from the scan and your notes and must end with `Gate: passed`. If it lists something to correct or still to do, correct the notes and run again. In your reply give the verdict and the counts as the command printed them.

---

## D. Fix

1. **Run** `python3 scripts/run.py fix <code> --out <folder> --log <change log> --register <review report>` (leave `--register` out when there is no review report). It writes the copy with every correction that has one possible form, the change log, and the notes file, which lists the findings of the review that are still open.
2. **Read the notes file and the change log.** For each High finding the script did not correct, decide: correct it, or leave it to the owner. Correct it when the right form is clear from the code and the intent: a block `### line N` with `after:` the corrected line (or `remove: yes`), `kind:`, and `why:` with a worked example (one input, what the line produced before, what it produces now). Read everything that touches the same value first: every place it is set, converted, escaped, defaulted and read. Leave it when the owner has to choose (which of two values is meant, what a placeholder should be, how conditions are grouped, whether a failure should stop the work): one line under "Left for the owner" with the question. The notes file already holds such a line for each of these findings; where it still ends with "What should the code do there?", nobody has looked yet: read the code at that line, then correct it or write what the owner has to choose between. The gate does not pass while one is left as the script wrote it. When the request covers more than one body of code, do all of this for each one. Never put in a value that the code and the intent do not show to be the right one, such as another variable, an empty text or a default: that hides the defect. If you have to ask whether your new line is right, it is the owner's decision; a block with both `after:` and `owner:` is listed as a proposal and not applied. A correction whose new line adds a scan hit is refused. When a correction closes a finding that sits on another line, name the finding in the block with `for:`. Use only functions, operators and syntax the code already uses; the gate lists anything new, and what is new needs a test. Findings about unused code, repeated code and performance are not corrected here; they belong to task E.
3. **Say what a correction switches on, where it reaches further than the defect.** The change log already says what each correction of the script changes. Where a corrected line makes something else happen (a branch that never ran now runs and stores, sends or returns something), write a block for its line with `effect:` and, if the owner must confirm it, `owner:` with the question.
4. **Gate. Run** the same command again until it ends with `Gate: passed`. Write "fixed" for a finding only after the gate; never say the code is ready on the strength of having made the changes.

---

## E. Change existing code: optimize, clean up, restructure, split, rename or migrate

The code works today. The task is to improve it without changing what it does, and the script makes the change from your plan, so that no line is re-typed, lost or mistyped.

1. **Run** `python3 scripts/run.py edit <code> --out <folder> --report <report> --map <map file>` (`--map` when the user asked for a traceability map, or for a split). It writes the plan file with the facts to start from: repeated calls, calls inside loops, the logging calls, commented-out code, unused names, duplicate branches, and the names that are not camelCase with a mechanical form for each. Work from those facts: to remove commented-out code, read the lines the facts list, and write them as one `### lines ...` block with `remove: yes`; searching the file again for comments costs turns and finds nothing more.
2. **Tie each sentence of the requirement to lines** before you plan anything, with those facts. A sentence you cannot tie to lines is a question for the owner, not something to guess. What the requirement asks for is to be done: it is the owner's decision already. In the plan file, under "Coverage of the requirement", write one line for each thing it asks of this task: `done:` with the blocks that do it, `in part:`, or `not done:` with what in the files prevents it (the data is not in the workspace, two things it asks for cannot both hold, the change would alter what the code does). Waiting for an approval is not a reason, and the gate refuses it. When the request covers more than one body of code, plan and run each one in full.
3. **Write the plan,** in the plan file:
   - a **rule** (`### rule <name>`, `match:` a regular expression, `with:` the replacement) for a change that applies to every line of a kind, such as a prefix on every logging call;
   - a **correction** (`### line N` or `### lines A-B`, `after:` the new lines or `remove: yes`) for a merged call or query, a removed block of commented-out code, a merged branch; one block with a list, `### lines 12, 40, 51-53` and `remove: yes`, takes out many separate lines with one `why:`;
   - **renames** (`old -> new`; `accept the proposals` takes every mechanical camelCase form, then your own lines for the names that should say what the value is for);
   - a **copy** (`### copy <model> as <new>`, `lines:` the block of the model, `replace:` one `old -> new` per line for the other spellings of the model's name) for a new item that must be like an existing one, such as a device added to a dashboard: the script copies the model's block, and every other line that names the model, right after itself, with only those replacements. Write one block for each new item, and no block, exception or insertion of your own for the other lines that name the model: the script copies them. So read only the model's block to find its lines and the spellings of its name; the rest of the page does not need reading, and functions that are not in the workspace do not either. Where a style value of the model (a margin, a width) differs between the items made like it, it usually fits the length of their names: the gate gives the value that the items with a name as long as the new one use, to put under `replace:` (`margin-left:72px -> margin-left:50px`); only where no item's name is as long does it show all the values and leave the choice to you (`replace:` or `keep:`). Take as the model an item whose names are its own (not shared with other items); the copy is refused while it still holds the model's name in any letter case, or uses a name the code already has;
   - for a split, **files** (`### path/file.ext`, `lines:` the ranges of the earlier code in the order wanted, `prepend:`/`append:` for the few new lines that join the parts, `why:`). When the earlier code is several files, `lines:` starts with the name of the file the ranges are in (`lines: rules.js: 1-57, 3100-3338`, or `lines: rules.js: all` for the whole file). A file the requirement asks for that holds no earlier line has no `lines:`; its content goes under `prepend:`. Every earlier line must land in a file or be removed by a correction; the script lists the ones that do not.
   A split keeps four things, and the gate refuses a plan that does not. **Whole blocks:** the line that opens a block and the line that closes it are in the same file; a file with half a block is broken, and no explanation settles that. **The moment each line runs:** the line that reads or calls the next file stands where the lines it replaces stood. Put it between two earlier lines with an insertion (`### after line N` with `insert:`); new lines under `append:` come after everything else in the file, which is too late when the file also holds lines from the end of the code. A step that every case reaches (the start, the end, what is sent or returned) stays where every case reaches it, not inside the part for one case. **Every file:** give the folder as the code when the earlier version is several files, so that each one is carried; and every file of the result is named by another file of the result, or the explanations say what reads it. **The call that hands over:** use the call the code already uses to run another part, if it has one; a call the earlier version never made needs a test, and its explanation says so.
   Each block has `why:`: the sentence of the requirement that asks for it, and what stays the same. For a merged query, say why the rows, grouping, distinct values, counts and order are the same. Rules for the plan: keep how the code talks to other systems (the same kind of call, the same data source and names); use only functions, operators and syntax the code already uses; do not reword any output text; before removing anything as unused, find every place it is read, and keep what another component may read; when code moves, keep the order in which things run, and keep a rule that applies to every part where every part reaches it; do not rename anything another component reads by name. Every choice the requirement does not make for you is a question for the owner. A requirement that can only be met in part is met in part, with the reason and the question. When the code hands over to another component that shares its variables, remove only what is evidently dead and ask the owner about the rest.
4. **Gate. Run** the same command again. It applies the plan, writes the copy, the report and the map, and lists every difference between the two versions: a call gone, new or made more often, an operator or keyword new to the code, a string gone or new, a scan hit that is new. A removal accounts by itself for what the removed lines held, a rule for the strings it rewrote on the lines it changed, and a copy for the strings and calls of its model lines. Every other difference is either corrected in the plan or explained, in the `why:` of its block or under "Explanations", with the sentence of the requirement that asks for it, named the way the gate shows it (a call by its name in backticks or its count line `name 3 -> 1`, an operator in backticks, a string by its text). Only what you write counts: the lines the report quotes do not explain themselves. A new scan hit is something the plan broke, or an earlier hit that moved with its line: correct the plan, or say which earlier hit it is by its file and line. When a restructuring rests on one call (for example the call that hands over from one part to the next), say so in the explanations, with what needs a test on the platform. Run again until it ends with `Gate: passed`.

---

## A. Review a change against its baseline

The baseline is the version the change started from, the changed version is the latest one, the intent is the requirement or brief, and the author's claims are the reports written on the way. Find them in the workspace; ask only if you cannot.

1. **Run** `python3 scripts/run.py change <baseline> <changed> --out <review>`, where `<review>` is the file the user asked for. It compares the two versions, writes the review report and the notes file, and stops at `Gate: not passed yet`: that is expected.
2. **Read the notes file.** Under "Differences" it lists every difference the comparison found: a call gone, new or made more often, an operator or keyword new to the code, a string gone or new, a scan hit that is new, a file left with half a block. Judge each one: `no behaviour change` (a rename, a comment, moved code that runs under the same conditions), `intended` (name the requirement or the defect it serves) or `unintended`. Look at the lines before you answer. When the intent says behaviour must stay the same, every unintended difference is a finding. A file that cannot be loaded on its own is unintended whatever the task was.
3. **Read each changed file in full against the baseline,** then answer every line under "Checks performed" with what you found and where you looked. The comparison does not see everything: a step that every case used to reach and that now sits in the part for one case, lines that run at another moment than before, a value no longer set on some path. Write each defect as a block under "Findings" (file and line, severity, a few words of the line, what is wrong, whether the change introduced it, quoting the baseline). A finding is a defect you can show from the code in the workspace and that could be corrected there. What depends on a file, a configuration or a system that is not in the workspace (whether a script elsewhere reads a new name, whether a filter or a table exists on the server) is not a finding: it is a question for the owner. If reading finds none, say so.
4. **Check the author's claims and the intent.** Open the author's reports and notes, which are next to the review: the notes list what they say was done, and their questions for the owner are what the check "no question was acted on anyway" is about. For each claim listed: for each, `holds` or `does not hold`, with the evidence from the files. Under "Coverage of the intent", one line for each requirement the change covers: done, partly done or not done, with one line of evidence; "all" or "every" is done only when a count shows none left.
5. **Gate. Run** the same command again until it ends with `Gate: passed`. The verdict of the report starts with the counts, which the script writes; add one or two sentences on whether the later version is fit to replace the earlier one. What only the owner can settle goes under "Questions for the owner". Give the command the earlier code itself as `<baseline>` (the file, when its folder also holds documents or data), and the folder of the later version as `<changed>`. Do not fix anything.

---

## C. Diagnose a failure

Do not change code while diagnosing.

1. **Run** `python3 scripts/run.py diagnose <code> --out <report>`. It writes the notes file next to the report.
2. **Write** in the notes: the symptom in one or two sentences, in the words of the person who reported it; under "Look for", one per line, the names, values and texts the symptom involves (an id, a field, a device, a message); the evidence that exists besides the code (error text, logs, the input that triggers it, a recent change), quoted with its source, and what is missing.
3. **Run again.** The report lists every line of the code that names what you look for, and the scan hits on those lines. A name that is nowhere in the code comes from outside it (the data, another file, the platform). A scan hit on the path is a cause to consider, not yet the cause.
4. **Write the causes**, most likely first, one block each: `### cause line N`, `quote:` words that are on that line, `how:` how the line produces the symptom, following the value or the flow from the input to what is seen, and `status:` `shown: <evidence>`, `ruled out: <evidence>` or `open: <the test that decides it>`. Name a cause as shown only when the evidence shows it; if two remain, say which test separates them. A fix goes under "Fix proposed", for the owner: nothing is changed by this task. List other defects you noticed apart; they are not the answer.
5. **Gate.** Run again until it ends with `Gate: passed`: one cause is shown, or every cause that is not ruled out names the test that decides it, and each quote is on its line.

---

## Severity and IDs
- **High**: wrong output, lost data, a rule that no longer applies where it should, a security exposure, a file that cannot be loaded on its own (half a block, half a string), a step every case used to reach that only some cases reach now.
- **Medium**: may fail when run, or leaves a requirement partly done.
- **Low**: unused code, a wrong or unsupported statement in a report, naming, tidiness.

The scripts number their rows `S-` (scan), `C-` (corrections of the script), `E-` (changes of a plan); your findings from reading are `R-`, your corrections `H-`, the findings of a review of a change `V-`. Write in plain words for an engineer who maintains the code and has not followed the work.

## When you finish
Give the user the verdict, the counts as the command printed them, the `Gate:` line as printed, and what was not checked, in a few lines for each report. Do not copy the findings, tables or questions into the reply: the report holds them; name the report instead. A gate that passed means the work of the task is complete and accounted for; it does not mean the code is right. Say what the code still needs, such as a test where it runs. After a review or a diagnosis, change nothing until the user says which findings to fix.
