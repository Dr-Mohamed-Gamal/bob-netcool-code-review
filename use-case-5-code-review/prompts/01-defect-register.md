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
| **Bob decides** | Whether each hit is a real defect, with a reason the workspace shows; what reading adds that the scan cannot see; for each finding its effect, the fix and how sure it is; the questions only the operator can answer |
| **The gate refuses** | A hit left undecided; a finding whose quoted words are not on the line it cites; a "not a defect" without the evidence that settles it |
| **Writes** | A defect register per input, with the notes file that holds Bob's judgements |
| **Why these words** | "The effect on the ticket / on the event" makes the register speak the operator's language; "Do not change" keeps the step read-only |
