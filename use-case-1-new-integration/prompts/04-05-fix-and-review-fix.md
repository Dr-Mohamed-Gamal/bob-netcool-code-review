# Prompt 4 · Fix and 5 · Review the fix — only when the review finds something

Part of [Use Case 1 — New Integration: from MIBs to Probe Rules](../README.md).

## The prompt

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

## What it does, and why

A finding marked "fix" is corrected where the rules come from — the decision in the notes of the catalogue or of the generation — and the rules are generated again, then reviewed again. In the runs below the review found nothing, so these two prompts were not needed.
