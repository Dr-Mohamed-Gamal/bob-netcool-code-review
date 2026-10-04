# Prompt 3 · Fix — the findings of the review

Part of [Use Case 3 — Add a Device to a Dashboard, and Debug It](../README.md).

## The prompt

```text
Fix the findings of reports/code-review.md in a copy of refactored/step-1-device-added under refactored/step-2-fixed.
Write reports/change-log.md.
Do not decide what is the client's to decide.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Correct what the review found, if anything, in a new copy |
| **Reads** | The review's findings and the step-1 copy |
| **The skill** | Apply the corrections from Bob's notes in a copy and compare it with step 1. With no finding, the fix passes at once and the copy is unchanged |
| **Bob decides** | The correction of each finding, or a question for the owner |
| **The gate refuses** | A finding with neither a correction nor a question |
| **Writes** | The fixed copy (step 2) and a change log |
| **Why these words** | "Do not decide what is the client's to decide" leaves design questions with the owner |
