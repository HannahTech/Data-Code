# Dynamo Wiring

Use one **Python Script** node set to **CPython3** for each step. Paste the matching `.py` file into the node.

## 01 Family Sync
Inputs:
- IN[0] File Path → `TD_Master_Parameters.csv`
- IN[1] File Path → `TD_Shared_Parameters.txt`
- IN[2] Boolean → Run
- IN[3] Boolean → Remove stale TD family parameters
- IN[4] Boolean → Repair wrong GUID / binding / UI group

Recommended production values:
`True, True, True` for IN[2:5] after testing one copy of a family.

## 02 Family Fill From Furniture Appendix
Inputs:
- IN[0] File Path → `TD_Master_Parameters.csv`
- IN[1] File Path → your real Furniture Appendix `.xlsx`
- IN[2] Boolean → Run
- IN[3] Boolean → Overwrite existing mapped family values

Recommended:
- First validation run: Overwrite=False
- Canonical update from appendix: Overwrite=True

The script searches all workbook tabs, so Task Chairs / Sofas / High Stools / Bench / Guest Chairs / Ottoman / etc. do not need separate Dynamo graphs.

## 03 Project Sync
Inputs:
- IN[0] File Path → `TD_Master_Parameters.csv`
- IN[1] File Path → `TD_Shared_Parameters.txt`
- IN[2] Boolean → Run
- IN[3] Boolean → Remove stale TD project bindings
- IN[4] Boolean → Repair bindings/GUID/categories/groups
- IN[5] Boolean → Apply default values to blank parameters

Recommended after testing a copy:
`Run=True, RemoveStale=True, Repair=True, ApplyDefaults=True`

## 04 Project Export
Inputs:
- IN[0] File Path → `TD_Master_Parameters.csv`
- IN[1] Directory Path → export folder
- IN[2] Boolean → Run
- IN[3] Boolean → Include empty parameters
- IN[4] Boolean → Write long-form parameter export

Recommended:
`Run=True, IncludeEmpty=False, WriteLong=True`

## Run order
1. Family → Step 1
2. Manually enter/import TD_Type_ID
3. Family → Step 2
4. Save family
5. Project → Step 3
6. Fill missing project/instance data manually
7. Load prepared families
8. Project → Step 4
