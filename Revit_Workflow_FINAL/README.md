# TD Revit Parameter / Data Workflow — FINAL

This is the final recommended architecture for your repeated Revit family + project workflow.

## Core design

There is one **master parameter classification**:
- `FamilyType` — stable information stored in RFA family TYPE parameters.
- `ProjectInstance` — placed-element information stored as project INSTANCE parameters.
- `ProjectInformation` — building/project information bound to Revit Project Information.

`TD_Master_Parameters.csv` is the classification/mapping authority.

Your **original TD shared-parameter TXT** is the GUID authority. Do not replace it with newly generated GUIDs.

## Why the shared TXT is not regenerated here

A shared parameter GUID is the parameter's identity in Revit. Your screenshots show that you already have an established TD shared-parameter file. Re-creating it with new GUIDs would produce same-name parameters with different identities and can split your data.

Therefore the final scripts always read the GUID from the shared TXT you select at runtime. The master CSV deliberately has no competing GUID column.

Use your existing original file for Steps 1 and 3. If you want it physically inside this ZIP, copy your original file into this folder as `TD_Shared_Parameters.txt`.

---

# Recommended run order

## Step 1 — Synchronize a family

Open an RFA and run `01_Family_Sync_Type_Parameters.py`.

It:
- reads only `FamilyType` rows applicable to the open family category;
- adds missing shared TYPE parameters;
- changes an existing same-GUID parameter from Instance to Type when required;
- moves it to the correct Revit UI group;
- can migrate a same-name wrong-GUID parameter to the GUID in your original shared TXT;
- preserves all family-type values during repair;
- removes stale `TD_` parameters that should not be in that family;
- automatically writes a TD-value backup CSV before any apply-mode mutation.

**Best first run**
- Run = True
- PreviewOnly = True
- RemoveStale = True
- MigrateWrongGUID = False

Review OUT. If you have confirmed same-name/wrong-GUID parameters that should be migrated, then use `MigrateWrongGUID=True`.

After Step 1, manually enter/import `TD_Type_ID` for every family type.

## Step 2 — Fill family type data from Furniture Appendix

Run `02_Family_Fill_From_Furniture_Appendix.py`.

It:
- reads the real Furniture Appendix `.xlsx`, `.xlsm`, or `.csv`;
- searches every worksheet for the row containing the `TD_Type_ID` header;
- looks up each Revit family type using its manually entered `TD_Type_ID`;
- blocks ambiguous duplicate Type IDs instead of guessing;
- populates only FamilyType parameters marked `PopulateFromAppendix=TRUE`;
- never overwrites `TD_Type_ID`;
- prefers standardized description columns;
- maps `TD_Colour` in the appendix to `TD_Color` in Revit;
- automatically backs up current TD family values before apply mode.

**Best first run**
- Run = True
- PreviewOnly = True
- OverwriteExisting = True

Review the planned changes, then change PreviewOnly to False.

Save and close the family after validation.

## Step 3 — Synchronize the project

Open the RVT project and run `03_Project_Sync_Instance_ProjectInfo.py`.

It:
- creates/repairs all `ProjectInstance` parameters as Instance bindings;
- creates/repairs all `ProjectInformation` building parameters;
- corrects UI group and category bindings;
- uses your original shared TXT GUIDs as identity;
- can migrate old same-name/wrong-GUID bindings when explicitly enabled;
- when converting an old Type-bound parameter to Instance, it copies the old type value to placed instances where possible;
- preserves existing project values through repair;
- keeps existing nonblank values when merging duplicate/wrong-GUID parameters;
- removes only stale `TD_` project bindings not classified as ProjectInstance/ProjectInformation;
- fills master defaults only into blank values;
- automatically creates a TD project-value backup before mutation.

**Best first run**
- Run = True
- PreviewOnly = True
- RemoveStale = True
- MigrateWrongGUID = False
- ApplyDefaults = True

After checking OUT, apply with PreviewOnly=False. Enable MigrateWrongGUID only when the conflicts are understood.

Then fill any remaining project/instance values manually and load the prepared furniture families.

## Step 4 — Export the data

Run `04_Project_Export_All_Data.py`.

Every run creates a timestamped export folder so an older export is not overwritten.

Outputs:
- `00_TD_Export_Summary.txt`
- `01_TD_Project_Asset_Export_Wide.csv`
  - one row per exported element;
  - contains metadata + instance parameters + type parameters;
  - TD parameter names remain plain;
  - other instance parameters use `I::`;
  - other type parameters use `T::`.
- `02_TD_Family_Type_Export.csv`
  - one row per used Revit type with all populated type parameters.
- `03_TD_Project_Information.csv`
  - TD building parameters and standard/default Project Information parameters.
- `04_TD_All_Parameters_Long.csv`
  - normalized database-style export;
  - every populated parameter appears as its own row;
  - contains owner kind, parameter source, display value, raw value, storage type, shared GUID and read-only status.

By default Step 4 exports the categories governed by the master CSV. Set `ExportAllModelCategories=True` if you want all non-view-specific model-category instances in the RVT.

---

# Important behavior for deleted parameters

If a parameter is truly removed from the master, its value cannot remain inside Revit after the parameter itself is deleted. The safe solution used here is:

1. create an automatic backup CSV;
2. then remove the stale parameter/binding.

Backups are written beneath:

`<folder containing TD_Master_Parameters.csv>/TD_Backups/`

with separate `Families` and `Projects` folders.

---

# Furniture Appendix

The code does not hard-code sheet names such as Task Chairs, Sofas, High Stools, Bench, Guest Chairs, Ottoman, etc.

It searches every worksheet and recognizes columns by header aliases. That makes the workflow more reusable when the appendix changes or new furniture sheets are added.

The provided `02_Furniture_Appendix_Column_Map.csv` documents the current mapping.

---

# Files

- `TD_Master_Parameters.xlsx` — human-readable master workbook and workflow dashboard.
- `TD_Master_Parameters.csv` — machine-readable master used by all four scripts.
- `01_Family_Type_Parameters.csv` — FamilyType subset for review.
- `02_Furniture_Appendix_Column_Map.csv` — appendix field mapping.
- `03_Project_Instance_Parameters.csv` — ProjectInstance subset.
- `03_Project_Information_Parameters.csv` — ProjectInformation subset.
- `01_Family_Sync_Type_Parameters.py`
- `02_Family_Fill_From_Furniture_Appendix.py`
- `03_Project_Sync_Instance_ProjectInfo.py`
- `04_Project_Export_All_Data.py`
- `DYNAMO_WIRING.md`
- `API_NOTES.md`
- `00_USE_YOUR_EXISTING_SHARED_PARAMETER_FILE.txt`

## Safety boundary

The cleanup logic only removes parameters whose names begin with `TD_`. It does not delete unrelated company/client/project parameters.
