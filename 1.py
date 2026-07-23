import clr

# Import Revit API
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *

# Import Revit Services
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

doc = DocumentManager.Instance.CurrentDBDocument
app = doc.Application

# Inputs from Dynamo
raw_data = IN[0]  # Excel Data
run_script = IN[1]

results = []

# Helper Function: Converts Excel Group string (Column C) into Revit API Group
def parse_excel_group(group_input):
    g_str = str(group_input).strip().lower().replace("pg_", "").replace(" ", "").replace("_", "")
    
    group_map = {
        "identitydata": "IdentityData",
        "identity": "IdentityData",
        "constraints": "Constraints",
        "data": "Data",
        "dimensions": "Dimensions",
        "geometry": "Dimensions",
        "ifc": "Ifc",
        "phasing": "Phasing",
        "text": "Text",
        "general": "General",
        "analysisresults": "AnalysisResults",
        "mechanical": "Mechanical",
        "electrical": "Electrical",
        "plumbing": "Plumbing",
        "fireprotection": "FireProtection",
        "graphics": "Graphics",
        "modelproperties": "ModelProperties"
    }
    
    target_attr = group_map.get(g_str, "Data")
    
    try:
        return getattr(GroupTypeId, target_attr)
    except AttributeError:
        try:
            return getattr(BuiltInParameterGroup, f"PG_{target_attr.upper()}")
        except AttributeError:
            return BuiltInParameterGroup.PG_DATA

if run_script and raw_data:
    sp_file = app.OpenSharedParameterFile()
    
    if not sp_file:
        results.append("ERROR: No Shared Parameter File linked in Revit.")
    else:
        doc_categories = {}
        for cat in doc.Settings.Categories:
            doc_categories[cat.Name.strip().lower()] = cat
        
        if "specialty equipment" in doc_categories:
            doc_categories["speciality equipment"] = doc_categories["specialty equipment"]

        TransactionManager.Instance.EnsureInTransaction(doc)
        
        data_rows = raw_data[1:] if len(raw_data) > 1 else []
        
        for row in data_rows:
            if not row or len(row) < 5:
                continue
            
            param_name = str(row[0]).strip()          # Column A (Index 0)
            custom_class = str(row[1]).strip()        # Column B (Index 1 - Kept for reference)
            excel_ui_group = str(row[2]).strip()      # Column C (Index 2 - Revit UI Group)
            is_instance = str(row[3]).strip().upper() == "TRUE" # Column D (Index 3)
            category_names = [c.strip().lower() for c in str(row[4]).split(',')] # Column E (Index 4)
            
            # Parse target group from Column C
            target_ui_group = parse_excel_group(excel_ui_group)
            
            # Search parameter definition
            param_def = None
            for grp in sp_file.Groups:
                try:
                    param_def = grp.Definitions.get_Item(param_name)
                except:
                    pass
                
                if not param_def:
                    for d in grp.Definitions:
                        if d.Name.strip().lower() == param_name.strip().lower():
                            param_def = d
                            break
                if param_def:
                    break
            
            if not param_def:
                results.append(f"FAILED: '{param_name}' not in Shared Parameter File.")
                continue
            
            # Build Target Category Set
            cat_set = app.Create.NewCategorySet()
            bound_cats = []
            
            for c_name in category_names:
                if c_name in doc_categories:
                    cat_set.Insert(doc_categories[c_name])
                    bound_cats.append(doc_categories[c_name].Name)
            
            if cat_set.IsEmpty:
                results.append(f"SKIPPED: '{param_name}' (No valid categories found).")
                continue
            
            if is_instance:
                binding = app.Create.NewInstanceBinding(cat_set)
            else:
                binding = app.Create.NewTypeBinding(cat_set)
            
            try:
                doc.ParameterBindings.ReInsert(param_def, binding, target_ui_group)
                results.append(f"SUCCESS: '{param_name}' bound under '{excel_ui_group}'.")
            except Exception:
                try:
                    doc.ParameterBindings.Insert(param_def, binding, target_ui_group)
                    results.append(f"SUCCESS: '{param_name}' bound.")
                except Exception as ex:
                    results.append(f"ERROR: {str(ex)}")

        TransactionManager.Instance.TransactionTaskDone()

OUT = results
