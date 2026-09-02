# Revit API Notes

The final workflow is designed for Dynamo CPython3 with current Revit APIs.

Key API choices:
- Family shared parameters are added with `FamilyManager.AddParameter`.
- Existing family parameters with the correct shared GUID are moved between Instance/Type with `FamilyManager.MakeType` and are moved to the intended parameter group through the definition group API.
- A family parameter that has the wrong identity can be replaced with the shared definition using `FamilyManager.ReplaceParameter`.
- Project parameter category/binding/group corrections use the project `BindingMap`.
- Project parameters are created as `InstanceBinding` for both placed-element data and Project Information.
- `GroupTypeId.AdskModelProperties` is used for Revit's Model Properties group.

Official Autodesk references:
- FamilyManager class:
  https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/1cc4fe6c-0e9f-7439-0021-32d2e06f4c33.htm
- FamilyManager.ReplaceParameter:
  https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/9ddbd75b-887d-397a-14aa-3e4052a2a2eb.htm
- InternalDefinition.SetGroupTypeId:
  https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/62a8a155-a7a6-e019-8cd8-9a7c9b4cd80a.htm
- BindingMap.ReInsert:
  https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/6dbdd2ef-e286-dc2a-8102-d6fbfef7e973.htm

Important:
No static API reference can guarantee behavior for every third-party family or every legacy parameter configuration. That is why Steps 1–3 include Preview mode and automatic backup before destructive changes.
