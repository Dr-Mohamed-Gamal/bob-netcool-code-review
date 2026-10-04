# Prompt 2 · Fix — corrected copy and change log

Part of [Use Case 5 — Code Analysis, Standardization and Optimization](../README.md).

## The prompt

```text
Fix the defects of impact-policy/inputs/<policy>.ipl in a copy under impact-policy/refactored/step-1-fixed and of probe-rules/inputs/<rules>.rules in a copy under probe-rules/refactored/step-1-fixed, one after the other.
Write impact-policy/reports/change-log.md and probe-rules/reports/change-log.md.
Do not decide what is the client's to decide.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Correct what is plainly wrong, in a copy, so the original stays as the baseline and every change is written down |
| **Reads** | The original file and its defect register |
| **The skill** | Make every correction that has only one possible form, apply Bob's corrections, and compare the copy with the original. A correction tagged with the wrong finding is refused; switching commented-out code back on becomes a question, not a fix |
| **Bob decides** | The correction of each finding the code itself settles, and a specific question for each one only the operator can settle (a filter switched off on purpose, an address written into the code) |
| **The gate refuses** | A High finding with neither a correction nor a specific question; a new call, operator or non-ASCII character the original did not have, unless its reason is written; a conditional operator (?) the code does not already use; notes left untouched. A correction that writes more or fewer lines than it replaces is not made: it is listed for the operator as a proposal, with its text |
| **Writes** | The corrected copy (step 1) and a change log per input |
| **Why these words** | "Do not decide what is the client's to decide" turns business choices into questions instead of silent changes |
