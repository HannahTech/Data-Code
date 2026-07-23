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

# Ensure path input is a clean string
csv_file_path = str(IN[0]) if IN[0] else ""
run_script = bool(IN[1]) if IN[1] is not None else False

results = []

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
        try:
            return getattr(BuiltInParameterGroup, f"PG_{target_attr.upper()}")
        except AttributeError:
            return BuiltInParameterGroup.PG_DATA

if not run_script:
    results.append("STOPPED: IN[1] (Boolean) is set to False.")
elif not csv_file_path or csv_file_path == "":
    results.append("STOPPED: IN[0] (File Path) is empty or null.")
else:
    results.append(f"Reading File: {csv_file_path}")
    
    sp_file = app.OpenSharedParameterFile()
    if not sp_file:
        results.append("ERROR: No Shared Parameter File linked in Revit (Manage -> Shared Parameters).")
    else:
        doc_categories = {cat.Name.strip().lower(): cat for cat in doc.Settings.Categories}
        if "specialty equipment" in doc_categories:
            doc_categories["speciality equipment"] = doc_categories["specialty equipment"]

        TransactionManager.Instance.EnsureInTransaction(doc)
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig') as file:
                reader = csv.reader(file)
                rows = [r for r in reader if r] # Filter empty lines
                
                results.append(f"Total rows found in CSV: {len(rows)}")
                
                # Skip header if present
                data_rows = rows[1:] if len(rows) > 1 else rows
                
                for i, row in enumerate(data_rows):
                    # Clean up row items
                    clean_row = [str(cell).strip() for cell in row]
                    
                    if len(clean_row) < 5:
                        results.append(f"Row {i+1} Skipped: Expected 5 columns, found {len(clean_row)}. Content: {clean_row}")
                        continue
                    
                    param_name = clean_row[0]
                    custom_class = clean_row[1]
                    csv_ui_group = clean_row[2]
                    is_instance = clean_row[3].upper() == "TRUE"
                    category_names = [c.strip().lower() for c in clean_row[4].split(',')]
                    
                    target_ui_group = parse_csv_group(csv_ui_group)
                    
                    # Search Parameter Definition
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
                        results.append(f"FAILED: '{param_name}' not in Shared Parameter File.")
                        continue
                    
                    # Category Binding
                    cat_set = app.Create.NewCategorySet()
                    bound_cats = []
                    for c_name in category_names:
                        if c_name in doc_categories:
                            cat_set.Insert(doc_categories[c_name])
                            bound_cats.append(doc_categories[c_name].Name)
                        else:
                            results.append(f"WARNING: Category '{c_name}' not recognized.")
                    
                    if cat_set.IsEmpty:
                        results.append(f"SKIPPED: '{param_name}' (No valid categories found).")
                        continue
                    
                    binding = app.Create.NewInstanceBinding(cat_set) if is_instance else app.Create.NewTypeBinding(cat_set)
                    
                    try:
                        doc.ParameterBindings.ReInsert(param_def, binding, target_ui_group)
                        results.append(f"SUCCESS: Bound '{param_name}' under '{csv_ui_group}'.")
                    except Exception:
                        try:
                            doc.ParameterBindings.Insert(param_def, binding, target_ui_group)
                            results.append(f"SUCCESS: Bound '{param_name}'.")
                        except Exception as ex:
                            results.append(f"ERROR: {str(ex)}")

        except Exception as e:
            results.append(f"FILE OPEN ERROR: {str(e)}")

        TransactionManager.Instance.TransactionTaskDone()

OUT = results
