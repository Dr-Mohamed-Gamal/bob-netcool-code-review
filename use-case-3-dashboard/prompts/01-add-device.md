# Prompt 1 · Add the device — a copy, under names of its own

Part of [Use Case 3 — Add a Device to a Dashboard, and Debug It](../README.md).

## The prompt

```text
Add the device <NEW DEVICE>, with DeviceType '<NEW DEVICE>', modelled on the <MODEL> device, to a copy of inputs/<page>.html under refactored/step-1-device-added: the same tiles, filters and selection, under names of its own.
Write reports/add-device.md.
Do not change inputs.
```

## What it does, and why

| | |
|---|---|
| **Why this step** | Make the change the operator asked for: a new device with exactly the same tiles, filters and selection as an existing one, under names of its own |
| **Reads** | The page; the plan file shows the model device's row lines and every other line that names the model |
| **The skill** | Copy the model's block right after itself with only the replacements Bob lists, copy each other line that names the model (the select lists) right after itself the same way, and account for every string and call the copy repeats |
| **Bob decides** | The model, the new names, the lines of the model's block, the replacements, and any style value that depends on the label (the value used by rows whose label is as long as the new one) |
| **The gate refuses** | A copy that still holds any name of the model; a new name the page already uses; a block that is not whole; a second block for the same model; a style value that does not fit the new label |
| **Writes** | The changed copy (step 1) and a report of the copy |
| **Why these words** | "In a copy … under refactored/…" keeps the original as the baseline; "Do not change inputs" protects it; "under names of its own" rules out sharing the model's filters |

## What if the new device is not exactly like the model?

The copy repeats the model's lines and changes only the names Bob lists. So the new device gets the model's tiles, filters and selection, and nothing else.

- **A value that depends on the label**, such as the margin that lines the tiles up after the label, is taken from the rows whose label has the same number of characters as the new one, and the report names those rows. If no row has a label of that length, the model's value stays and the report asks the owner.
- **Anything the model does not have**, such as another tile or another condition in the filter, cannot come from a copy. Bob writes it as a question for the owner; nothing is invented.
- **The gate refuses** a copy that still holds any name of the model, a new name the page already uses, or a block that is not whole.

**The limits.** The copy is checked as text. The page's own scripts, which fetch the counts and build the device filter, were not sent, so whether they pick up the new device cannot be checked here; the report asks the owner. Nothing was opened on the live system.
