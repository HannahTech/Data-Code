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
csv_file_path = IN[0]
run_script = IN[1]

results = []

# Define parameter group safely across Revit versions (Revit 2024+ vs older)
try:
    param_group = GroupTypeId.Data
except AttributeError:
    try:
        param_group = BuiltInParameterGroup.PG_DATA
    except NameError:
        param_group = BuiltInParameterGroup.INVALID

if run_script and csv_file_path:
    # 1. Access Shared Parameter File linked in Revit
    sp_file = app.OpenSharedParameterFile()
    
    if not sp_file:
        results.append("ERROR: No Shared Parameter File linked in Revit (Manage -> Shared Parameters).")
    else:
        # 2. Build Category Lookup Map (Case-insensitive)
        doc_categories = {}
        for cat in doc.Settings.Categories:
            doc_categories[cat.Name.strip().lower()] = cat

        # 3. Read CSV File
        TransactionManager.Instance.EnsureInTransaction(doc)
        
        with open(csv_file_path, 'r', encoding='utf-8-sig') as file:
            reader = csv.reader(file)
            header = next(reader, None)  # Skip header row
            
            for row in reader:
                if not row or len(row) < 4:
                    continue
                
                param_name = row[0].strip()
                group_name = row[1].strip()
                is_instance = row[2].strip().upper() == "TRUE"
                category_names = [c.strip().lower() for c in row[3].split(',')]
                
                # Find parameter definition in SP File
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
                    results.append(f"FAILED: Parameter '{param_name}' not found in Shared Parameter File.")
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
                
                # Map to Revit UI Group
                try:
                    doc.ParameterBindings.Insert(param_def, binding, param_group)
                    results.append(f"SUCCESS: Bound '{param_name}' to {len(bound_cats)} categories.")
                except Exception:
                    # If already bound, update binding
                    doc.ParameterBindings.ReInsert(param_def, binding, param_group)
                    results.append(f"UPDATED: '{param_name}' binding updated.")

        TransactionManager.Instance.TransactionTaskDone()

OUT = results
