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
| **The scripts** | Copy the model's block right after itself with only the replacements Bob lists, copy each other line that names the model (the select lists) right after itself the same way, and account for every string and call the copy repeats |
| **Bob decides** | The model, the new names, the lines of the model's block, the replacements, and any style value that depends on the label (the value used by rows whose label is as long as the new one) |
| **The gate refuses** | A copy that still holds any name of the model; a new name the page already uses; a block that is not whole; a second block for the same model; a style value that does not fit the new label |
| **Writes** | The changed copy (step 1) and a report of the copy |
| **Why these words** | "In a copy … under refactored/…" keeps the original as the baseline; "Do not change inputs" protects it; "under names of its own" rules out sharing the model's filters |
