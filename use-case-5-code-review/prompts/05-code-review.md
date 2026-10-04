# Prompt 5 · Code review — the final copy against the original

Part of [Use Case 5 — Code Analysis, Standardization and Optimization](../README.md).

## The prompt

```text
Review impact-policy/refactored/step-3-standardized against impact-policy/inputs/<policy>.ipl, and probe-rules/refactored/step-3-standardized against probe-rules/inputs/<rules>.rules, one after the other.
Write impact-policy/reports/code-review.md and probe-rules/reports/code-review.md.
Do not fix anything.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | An independent check of the final copy against the original: everything that changed, judged, before anyone deploys it |
| **Reads** | The final copy, the original, and every earlier report and notes file |
| **The skill** | Compare the two versions line by line, count the defects before and after, group the differences (corrections, removals, renames, path changes), and check the claims of the earlier reports |
| **Bob decides** | For each difference: no change of behaviour, intended (and by which report), or unintended; what reading adds; the operator's open decisions as questions |
| **The gate refuses** | Any difference left unjudged; a claim of an earlier report that the files do not bear out |
| **Writes** | A review of the whole change per input |
| **Why these words** | "Do not fix anything" keeps the reviewer and the author apart, even when both are Bob |
