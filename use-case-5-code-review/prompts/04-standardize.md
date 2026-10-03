# Prompt 4 · Standardize — names and paths

Part of [Use Case 5 — Code Analysis, Standardization and Optimization](../README.md).

## The prompt

```text
Standardize a copy of each step-2-cleaned, one after the other.
Policy: in a copy of impact-policy/refactored/step-2-cleaned under impact-policy/refactored/step-3-standardized, rename the variables to camelCase as section 3 of the requirement document asks.
Rules: in a copy of probe-rules/refactored/step-2-cleaned under probe-rules/refactored/step-3-standardized, replace the absolute path prefix /opt/IBM/tivoli/netcool/omnibus/etc/probes/rules with $NC_RULES_HOME in every include and table line, as standard 2 of the code standards document asks.
Write impact-policy/reports/standards.md and probe-rules/reports/standards.md.
Do not change the ticket content or the events, or any folder or file name after the path prefix.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Names that say what the data is, and paths that move with the installation: the two standardizations the documents ask for that a script can make reliably |
| **Reads** | The step-2 copy and the document's item on names (policy) or paths (rules) |
| **The scripts** | Propose a camelCase name for every local variable and apply the map; refuse to rename a name another component may read (event fields, names read before they are set, names that may come from outside); for the rules, replace the prefix with one rule on the include and table lines only |
| **Bob decides** | Which proposed names to take, which to adjust, and which to leave for the operator to confirm |
| **The gate refuses** | A rename that merges two names or touches an event field; a path line where anything other than the prefix changed |
| **Writes** | The standardized copy (step 3) and a standards report per input |
| **Why these words** | The exact prefix and "any folder or file name after the path prefix" were added after a run where a looser prompt also changed folder names |
