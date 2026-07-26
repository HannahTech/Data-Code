import clr
import csv
import re

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

# Clean string function to strip hidden unicode spaces (\xa0) and non-alphanumeric trailing symbols
def clean_string(val):
    if not val:
        return ""
    # Strip non-breaking space \xa0 and standard whitespaces
    cleaned = str(val).replace('\xa0', '').strip()
    # Remove hidden control characters
    cleaned = re.sub(r'[\r\n\t]', '', cleaned)
    return cleaned

# Helper Function: Converts Column C group string into official Revit API Group
def parse_csv_group(group_input):
    g_str = clean_string(group_input).lower().replace("pg_", "").replace(" ", "").replace("_", "").replace("and", "")
    
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
        "modelproperties": "ModelProperties",
        "materialsfinishes": "Materials",
        "materials": "Materials"
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
        # Get or create default group in Shared Parameter File
        sp_group = sp_file.Groups.get_Item("COM_Parameters")
        if not sp_group:
            sp_group = sp_file.Groups.Create("COM_Parameters")

        # Build Category Lookup Map
        doc_categories = {}
        for cat in doc.Settings.Categories:
            try:
                cat_id_val = cat.Id.Value if hasattr(cat.Id, 'Value') else cat.Id.IntegerValue
                if cat.AllowsBoundParameters or cat_id_val == int(BuiltInCategory.OST_ProjectInformation):
                    doc_categories[clean_string(cat.Name).lower()] = cat
            except:
                pass

        TransactionManager.Instance.EnsureInTransaction(doc)
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig', errors='replace') as file:
                reader = csv.reader(file)
                rows = [r for r in reader if r]
                data_rows = rows[1:] if len(rows) > 1 else rows
                
                binding_map = doc.ParameterBindings
                
                for i, row in enumerate(data_rows):
                    # Aggressively clean every cell in the row
                    clean_row = [clean_string(cell) for cell in row]
                    if len(clean_row) < 5 or not clean_row[0]:
                        continue
                    
                    param_name = clean_row[0]                              # Column A
                    custom_class = clean_row[1]                            # Column B
                    csv_ui_group = clean_row[2]                            # Column C
                    is_instance = clean_row[3].upper() == "TRUE"           # Column D
                    category_names = [clean_string(c).lower() for c in clean_row[4].split(',')] # Column E
                    
                    target_ui_group = parse_csv_group(csv_ui_group)
                    
                    # 1. Search for parameter definition in Shared Parameter File (with whitespace protection)
                    param_def = None
                    for grp in sp_file.Groups:
                        try:
                            param_def = grp.Definitions.get_Item(param_name)
                        except:
                            pass
                        
                        if not param_def:
                            for d in grp.Definitions:
                                if clean_string(d.Name).lower() == param_name.lower():
                                    param_def = d
                                    break
                        if param_def:
                            break
                    
                    # 2. Auto-create in Shared Parameter File if missing
                    if not param_def:
                        try:
                            opt = ExternalDefinitionCreationOptions(param_name, SpecTypeId.String.Text)
                            param_def = sp_group.Definitions.Create(opt)
                            results.append(f"CREATED IN SP FILE: '{param_name}'")
                        except:
                            try:
                                opt = ExternalDefinitionCreationOptions(param_name, ParameterType.Text)
                                param_def = sp_group.Definitions.Create(opt)
                                results.append(f"CREATED IN SP FILE: '{param_name}'")
                            except Exception as ex:
                                results.append(f"FAILED TO CREATE: '{param_name}' ({str(ex)})")
                                continue
                    
                    # 3. Build Category Set
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
                    
                    binding = app.Create.NewInstanceBinding(cat_set) if is_instance else app.Create.NewTypeBinding(cat_set)
                    
                    # 4. Bind Parameter
                    success = False
                    try:
                        success = binding_map.ReInsert(param_def, binding, target_ui_group)
                        if not success:
                            success = binding_map.Insert(param_def, binding, target_ui_group)
                    except:
                        pass
                    
                    if not success:
                        try:
                            success = binding_map.ReInsert(param_def, binding, GroupTypeId.Data)
                            if not success:
                                success = binding_map.Insert(param_def, binding, GroupTypeId.Data)
                            results.append(f"SUCCESS (Bound under Data Group): '{param_name}'")
                        except Exception as ex:
                            results.append(f"ERROR: '{param_name}' failed to bind: {str(ex)}")
                    else:
                        results.append(f"SUCCESS: Bound '{param_name}' under '{csv_ui_group}'.")

        except Exception as e:
            results.append(f"FILE OPEN ERROR: {str(e)}")

        TransactionManager.Instance.TransactionTaskDone()

OUT = results
