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

# Inputs from Dynamo
csv_file_path = IN[0]  # File Path node pointing to your .csv
run_script = IN[1]     # Boolean set to True

results = []

# Helper Function: Converts Column C string into official Revit API Group
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
    
    # Revit 2024+ ForgeTypeId vs Legacy BuiltInParameterGroup
    try:
        return getattr(GroupTypeId, target_attr)
    except AttributeError:
        try:
            return getattr(BuiltInParameterGroup, f"PG_{target_attr.upper()}")
        except AttributeError:
            return BuiltInParameterGroup.PG_DATA

if run_script and csv_file_path:
    # 1. Access Shared Parameter File linked in Revit
    sp_file = app.OpenSharedParameterFile()
    
    if not sp_file:
        results.append("ERROR: No Shared Parameter File linked in Revit (Manage -> Shared Parameters).")
    else:
        # 2. Build Category Lookup Map (Case-insensitive + Alias support)
        doc_categories = {}
        for cat in doc.Settings.Categories:
            doc_categories[cat.Name.strip().lower()] = cat
        
        # Alias for Speciality / Specialty typo protection
        if "specialty equipment" in doc_categories:
            doc_categories["speciality equipment"] = doc_categories["specialty equipment"]

        # 3. Read CSV File Directly
        TransactionManager.Instance.EnsureInTransaction(doc)
        
        with open(csv_file_path, 'r', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader, None)  # Skip header row
            
            for row in reader:
                if not row or len(row) < 5:
                    continue
                
                param_name = row[0].strip()                              # Column A
                custom_class = row[1].strip()                            # Column B (Kept for reference)
                csv_ui_group = row[2].strip()                            # Column C (Revit UI Group)
                is_instance = row[3].strip().upper() == "TRUE"           # Column D
                category_names = [c.strip().lower() for c in row[4].split(',')] # Column E
                
                # Parse target group from Column C
                target_ui_group = parse_csv_group(csv_ui_group)
                
                # Search for parameter definition in Shared Parameter File
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
                    results.append(f"FAILED: '{param_name}' not found in Shared Parameter File.")
                    continue
                
                # Build Target Category Set
                cat_set = app.Create.NewCategorySet()
                bound_cats = []
                
                for c_name in category_names:
                    if c_name in doc_categories:
                        cat_set.Insert(doc_categories[c_name])
                        bound_cats.append(doc_categories[c_name].Name)
                    else:
                        results.append(f"WARNING: Category '{c_name}' not recognized in Revit.")
                
                if cat_set.IsEmpty:
                    results.append(f"SKIPPED: '{param_name}' (No valid categories found).")
                    continue
                
                # Create Instance or Type Binding
                if is_instance:
                    binding = app.Create.NewInstanceBinding(cat_set)
                else:
                    binding = app.Create.NewTypeBinding(cat_set)
                
                # Bind / Re-bind Parameter to specified UI Group
                try:
                    doc.ParameterBindings.ReInsert(param_def, binding, target_ui_group)
                    results.append(f"SUCCESS: Bound '{param_name}' under '{csv_ui_group}'.")
                except Exception:
                    try:
                        doc.ParameterBindings.Insert(param_def, binding, target_ui_group)
                        results.append(f"SUCCESS: Bound '{param_name}'.")
                    except Exception as ex:
                        results.append(f"ERROR: {str(ex)}")

        TransactionManager.Instance.TransactionTaskDone()

OUT = results
