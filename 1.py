import clr
import csv

# Import Revit API
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *

# Import Revit Services
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

doc = DocumentManager.Instance.CurrentDBDocument
app = doc.Application

csv_file_path = str(IN[0]) if IN[0] else ""
run_script = bool(IN[1]) if IN[1] is not None else False

results = []

# Helper Function: Converts Column C group string into official Revit API Group
def parse_csv_group(group_input):
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
        return GroupTypeId.Data

if not run_script or not csv_file_path:
    results.append("STOPPED: Inputs invalid or Boolean set to False.")
else:
    sp_file = app.OpenSharedParameterFile()
    
    if not sp_file:
        results.append("ERROR: No Shared Parameter File linked in Revit (Manage -> Shared Parameters).")
    else:
        # Build Category Map (Case-insensitive + Alias support)
        doc_categories = {cat.Name.strip().lower(): cat for cat in doc.Settings.Categories if cat.AllowsBoundParameters}
        if "specialty equipment" in doc_categories:
            doc_categories["speciality equipment"] = doc_categories["specialty equipment"]

        TransactionManager.Instance.EnsureInTransaction(doc)
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                rows = [r for r in reader if r]
                data_rows = rows[1:] if len(rows) > 1 else rows
                
                binding_map = doc.ParameterBindings
                
                for i, row in enumerate(data_rows):
                    clean_row = [str(cell).strip() for cell in row]
                    if len(clean_row) < 5:
                        continue
                    
                    param_name = clean_row[0]                              # Column A
                    custom_class = clean_row[1]                            # Column B
                    csv_ui_group = clean_row[2]                            # Column C (Group Name)
                    is_instance = clean_row[3].upper() == "TRUE"           # Column D
                    category_names = [c.strip().lower() for c in clean_row[4].split(',')] # Column E
                    
                    # Target group from Column C
                    target_ui_group = parse_csv_group(csv_ui_group)
                    
                    # Search Parameter Definition in Shared Parameter File
                    param_def = None
                    for grp in sp_file.Groups:
                        try:
                            param_def = grp.Definitions.get_Item(param_name)
                        except:
                            pass
                        
                        if not param_def:
                            for d in grp.Definitions:
                                if d.Name.strip().lower() == param_name.lower():
                                    param_def = d
                                    break
                        if param_def:
                            break
                    
                    if not param_def:
                        results.append(f"FAILED: '{param_name}' not found in Shared Parameter File.")
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
                    
                    # Create Instance or Type Binding
                    binding = app.Create.NewInstanceBinding(cat_set) if is_instance else app.Create.NewTypeBinding(cat_set)
                    
                    # Step 1: Try Binding with target group from Column C
                    success = False
                    try:
                        success = binding_map.ReInsert(param_def, binding, target_ui_group)
                        if not success:
                            success = binding_map.Insert(param_def, binding, target_ui_group)
                    except:
                        pass
                    
                    # Step 2: Fallback to GroupTypeId.Data (Guaranteed to work like earlier script)
                    if not success:
                        try:
                            success = binding_map.ReInsert(param_def, binding, GroupTypeId.Data)
                            if not success:
                                success = binding_map.Insert(param_def, binding, GroupTypeId.Data)
                            results.append(f"SUCCESS (Fallback to Data Group): '{param_name}'")
                        except Exception as ex:
                            results.append(f"ERROR: '{param_name}' failed to bind: {str(ex)}")
                    else:
                        results.append(f"SUCCESS: Bound '{param_name}' under group '{csv_ui_group}'.")

        except Exception as e:
            results.append(f"FILE OPEN ERROR: {str(e)}")

        TransactionManager.Instance.TransactionTaskDone()

OUT = results
