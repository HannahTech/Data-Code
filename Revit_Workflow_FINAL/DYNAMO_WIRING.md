# Dynamo Wiring — FINAL

Use a Dynamo **Python Script** node set to **CPython3**.

Paste one `.py` script into one Python node. Add/remove node inputs with the `+` / `-` controls so the input count matches below.

---

## 01 — Family Sync

Script:
`01_Family_Sync_Type_Parameters.py`

Inputs:
- `IN[0]` File Path — `TD_Master_Parameters.csv`
- `IN[1]` File Path — your ORIGINAL TD shared parameter `.txt`
- `IN[2]` Boolean — Run
- `IN[3]` Boolean — PreviewOnly
- `IN[4]` Boolean — RemoveStaleTDParameters
- `IN[5]` Boolean — MigrateWrongGUID

First run:
`True / True / True / False`

Apply normal synchronization:
`True / False / True / False`

Only after confirming GUID conflicts:
`MigrateWrongGUID=True`

---

## Manual step

Enter/import `TD_Type_ID` in every Revit family type.

Do this after Step 1 and before Step 2.

---

## 02 — Fill From Furniture Appendix

Script:
`02_Family_Fill_From_Furniture_Appendix.py`

Inputs:
- `IN[0]` File Path — `TD_Master_Parameters.csv`
- `IN[1]` File Path — real Furniture Appendix `.xlsx`, `.xlsm`, or `.csv`
- `IN[2]` Boolean — Run
- `IN[3]` Boolean — PreviewOnly
- `IN[4]` Boolean — OverwriteExistingMappedValues

First run:
`True / True / True`

Apply:
`True / False / True`

If you want the appendix to fill only blank family values:
`OverwriteExistingMappedValues=False`

---

## 03 — Project Sync

Script:
`03_Project_Sync_Instance_ProjectInfo.py`

Inputs:
- `IN[0]` File Path — `TD_Master_Parameters.csv`
- `IN[1]` File Path — your ORIGINAL TD shared parameter `.txt`
- `IN[2]` Boolean — Run
- `IN[3]` Boolean — PreviewOnly
- `IN[4]` Boolean — RemoveStaleTDProjectBindings
- `IN[5]` Boolean — MigrateWrongGUID
- `IN[6]` Boolean — ApplyDefaultsToBlankValues

First run:
`True / True / True / False / True`

Normal apply:
`True / False / True / False / True`

Only after confirming GUID conflicts:
`MigrateWrongGUID=True`

---

## 04 — Project Export

Script:
`04_Project_Export_All_Data.py`

Inputs:
- `IN[0]` File Path — `TD_Master_Parameters.csv`
- `IN[1]` Directory Path — parent export folder
- `IN[2]` Boolean — Run
- `IN[3]` Boolean — IncludeEmptyParameters
- `IN[4]` Boolean — WriteLongFormExport
- `IN[5]` Boolean — ExportAllModelCategories

Recommended:
`True / False / True / False`

For a much larger full-model export:
`ExportAllModelCategories=True`

---

# Recommended complete sequence

1. Open RFA.
2. Step 1 in Preview mode.
3. Step 1 Apply.
4. Manually set/import `TD_Type_ID`.
5. Step 2 in Preview mode.
6. Step 2 Apply.
7. Check Family Types and save the RFA.
8. Open RVT.
9. Step 3 in Preview mode.
10. Step 3 Apply.
11. Fill missing building/instance values manually.
12. Load the prepared furniture families.
13. Step 4 export.
