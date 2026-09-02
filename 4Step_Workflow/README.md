# TD Revit 4-Step Parameter/Data Workflow

This package implements the workflow in four separate Dynamo CPython3 scripts.

## Step 1 — Family parameter synchronization
Open an RFA family and run `01_Family_Sync_Type_Parameters.py`.

It reads `TD_Master_Parameters.csv` and:
- keeps only the TD parameters whose Scope is `FamilyType` and whose category applies to the open family;
- adds missing shared TYPE parameters;
- repairs wrong shared GUID, Type/Instance binding, and Revit UI group;
- preserves existing family-type values during repair;
- removes stale `TD_` family parameters that are no longer FamilyType rows in the CSV.

After Step 1, manually enter/import `TD_Type_ID` for each family type.

## Step 2 — Fill family TYPE data from Furniture Appendix
Run `02_Family_Fill_From_Furniture_Appendix.py`.

It:
- reads the Furniture Appendix `.xlsx`, `.xlsm`, or `.csv`;
- searches every worksheet for a header row containing `TD_Type_ID`;
- matches each Revit family type using the manually entered `TD_Type_ID`;
- fills only the FamilyType parameters marked `PopulateFromAppendix=TRUE`;
- prefers `TD_Description [Standard]` / `TD_Description (Standard)` over the non-standard description;
- maps appendix `TD_Colour` to Revit `TD_Color`;
- never writes project-instance fields such as `TD_Serial_Number`.

Save and close the family after checking Step 2.

## Step 3 — Project parameter synchronization
Open the RVT project and run `03_Project_Sync_Instance_ProjectInfo.py`.

It:
- adds/repairs all `ProjectInstance` shared parameters as Instance bindings;
- adds/repairs all `ProjectInformation` building parameters on Project Information;
- corrects category sets, UI groups, bindings and GUIDs;
- backs up and restores existing values during repair;
- if an incorrect old parameter was Type-bound but the master says Instance, it propagates the old type value to each matching instance during migration;
- removes stale `TD_` project parameter bindings not listed as ProjectInstance/ProjectInformation;
- fills CSV default values only where the target parameter is blank.

Then fill any remaining project values manually and load the prepared furniture families.

## Step 4 — Export all project/family data
Run `04_Project_Export_All_Data.py`.

It exports:
- `01_TD_Project_Asset_Export_Wide.csv` — one row per project element, with instance + type data. TD parameters keep plain names; other parameters are prefixed `I::` or `T::`.
- `02_TD_Family_Type_Export.csv` — one row per used Revit type.
- `03_TD_Project_Information.csv` — built-in and TD project/building data.
- `04_TD_All_Parameters_Long.csv` — normalized long-form export of every non-empty instance/type/project parameter, including built-in/default Revit parameters.
- `00_TD_Export_Summary.txt`.

## Important
The GUIDs in `TD_Shared_Parameters.txt` and `TD_Master_Parameters.csv` are the same GUIDs from the previous TD package. Do not regenerate them after deployment.

The actual Furniture Appendix workbook was not available as a file in the chat; only its screenshot was available. Step 2 is therefore intentionally header-driven and works directly with the real appendix when you select its `.xlsx` file.
