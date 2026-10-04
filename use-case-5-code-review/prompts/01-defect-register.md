# Prompt 1 · Defect register — review, no change

Part of [Use Case 5 — Code Analysis, Standardization and Optimization](../README.md).

## The prompt

```text
Review impact-policy/inputs/<policy>.ipl and probe-rules/inputs/<rules>.rules for defects, one after the other, each with the document from the client next to it as the guide.
Write impact-policy/reports/defect-register.md and probe-rules/reports/defect-register.md, with the effect of each defect on the ticket for the policy and on the event for the rules.
Do not change the policy or the rules file.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Before anything changes, list what is wrong and what each defect does to a ticket or an event. The operator sees the size of the problem, and every later step refers back to this list |
| **Reads** | The original policy and rules file, each with its document; the lookup files when a finding depends on them |
| **The scripts** | Scan the code for 37 kinds of defect (a name misspelt, read before it is set or never used; a single `=` where a comparison is meant; an XML entity or tag not closed; brackets that do not balance; branches that repeat each other; code that cannot run), say for each hit where its value goes, and write the notes file with every hit to decide |
| **Bob decides** | Whether each hit is a real defect, with a reason the workspace shows; by reading the whole file once, the defects the scan cannot see (see below); for each finding its effect, the fix and how sure it is; the questions only the operator can answer |
| **The gate refuses** | A hit left undecided; a finding whose quoted words are not on the line it cites; a "not a defect" without the evidence that settles it |
| **Writes** | A defect register per input, with the notes file that holds Bob's judgements |
| **Why these words** | "The effect on the ticket / on the event" makes the register speak the operator's language; "Do not change" keeps the step read-only |

## What if a defect is not one of the 37 kinds?

The 37 kinds are only the first pass. Prompt 1 works in two passes:

1. **The scan (a script)** finds the 37 kinds of defect that readers most often miss. It finds the same things every time.
2. **The reading (Bob).** The skill makes Bob read the whole file once, from the first line to the last, for what a scan cannot see: wrong logic, code that can never run, a value that ends up in the wrong field. Each defect found this way goes into the register under **Findings from reading**, with its line, the quoted code, what it does, its effect on the ticket or the event, the fix, and how sure Bob is. The gate checks that the quoted words are on the line the finding cites.

Kinds of defect that only reading finds, for example:

- a branch that can never run, because of how an if / else chain is built;
- a ticket field built from a variable that nothing sets, so the field is always empty;
- a field set, then always overwritten further down, so the first line does nothing;
- a log line that says an alarm is dropped while the line that drops it is commented out, so the alarm still reaches the event list.

In the clean run, reading added findings of this kind in both files.

**The limits.** Reading is Bob's judgement, as a human reviewer's is. The gate checks that each finding quotes its line, but no script can prove that every defect was found, so a person should read the findings from reading before they go to the operator. Some defects cannot be seen in the code at all, such as a wrong value in a lookup table or a difference from the live system. That is why every register ends with **Not checked**: nothing was run on an Impact server or a probe.
