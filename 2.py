import clr
import csv
import re
import os

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

def sanitize_param_name(val):
    if not val:
        return ""
    return re.sub(r'[^a-zA-Z0-9_]', '', str(val))

def sanitize_text(val):
    if not val:
        return ""
    cleaned = re.sub(r'[^a-zA-Z0-9_\s]', '', str(val))
    return cleaned.strip()

def parse_csv_group(group_input):
    g_str = sanitize_param_name(group_input).lower().replace("pg", "").replace("and", "")
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
    results.append("FAILED: Inputs invalid or Boolean set to False.")
else:
    TransactionManager.Instance.EnsureInTransaction(doc)
    
    # =========================================================================
    # STEP 1: COMPLETE DELETION OF ALL SHARED PARAMETERS IN REVIT DOCUMENT
    # =========================================================================
    try:
        # A. Unbind all Parameter Bindings
        binding_map = doc.ParameterBindings
        iterator = binding_map.ForwardIterator()
        defs_to_remove = []
        while iterator.MoveNext():
            if iterator.Key:
                defs_to_remove.append(iterator.Key)
        
        for param_def in defs_to_remove:
            try:
                binding_map.Remove(param_def)
            except:
                pass

        # B. Collect & Force Delete All SharedParameterElements from Doc Database
        sp_elements = FilteredElementCollector(doc).OfClass(SharedParameterElement).ToElements()
        deleted_count = 0
        for sp_elem in sp_elements:
            try:
                doc.Delete(sp_elem.Id)
                deleted_count += 1
            except:
                pass
                
        results.append(f"STEP 1 COMPLETE: Force-deleted {deleted_count} shared parameters from model database.")
    except Exception as purge_ex:
        results.append(f"STEP 1 WARNING: Could not purge - {str(purge_ex)}")

    # =========================================================================
    # STEP 2: OPEN OR AUTO-CREATE SHARED PARAMETER FILE (.TXT)
    # =========================================================================
    sp_file = app.OpenSharedParameterFile()
    
    if not sp_file:
        auto_txt_path = os.path.join(os.path.dirname(csv_file_path), "Auto_SharedParameters.txt")
        if not os.path.exists(auto_txt_path):
            with open(auto_txt_path, 'w') as f:
                f.write("# This is a Revit shared parameter file created automatically by Dynamo Python.\n*META\tVERSION\t2.1\n*GROUP\tID\tNAME\n*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\tUSERMODIFIABLE\tHIDEWHENNOVALUE\n")
        
        app.SharedParametersFilename = auto_txt_path
        sp_file = app.OpenSharedParameterFile()

    if not sp_file:
        results.append("FAILED: Could not open or create Shared Parameter File.")
    else:
        # Build Category Lookup Map
        doc_categories = {}
        for cat in doc.Settings.Categories:
            try:
                cat_id_val = cat.Id.Value if hasattr(cat.Id, 'Value') else cat.Id.IntegerValue
                if cat.AllowsBoundParameters or cat_id_val == int(BuiltInCategory.OST_ProjectInformation):
                    doc_categories[sanitize_text(cat.Name).lower()] = cat
            except:
                pass

        # =========================================================================
        # STEP 3: RE-CREATE GROUPS & BIND CLEANED PARAMETERS FROM CSV
        # =========================================================================
        try:
            with open(csv_file_path, 'r', encoding='utf-8-sig', errors='ignore') as file:
                reader = csv.reader(file)
                rows = [r for r in reader if r]
                data_rows = rows[1:] if len(rows) > 1 else rows
                
                binding_map = doc.ParameterBindings
                
                for i, row in enumerate(data_rows):
                    if len(row) < 5 or not row[0]:
                        continue
                    
                    param_name = sanitize_param_name(row[0])               # Column A
                    internal_group_name = sanitize_param_name(row[1])      # Column B
                    csv_ui_group = sanitize_text(row[2])                   # Column C
                    is_instance = str(row[3]).strip().upper() == "TRUE"    # Column D
                    category_names = [sanitize_text(c).lower() for c in str(row[4]).split(',')] # Column E
                    
                    if not param_name:
                        continue
                        
                    target_ui_group = parse_csv_group(csv_ui_group)
                    
                    # Get/Create Group in .txt file using Column B
                    txt_group = None
                    for existing_grp in sp_file.Groups:
                        if sanitize_param_name(existing_grp.Name).lower() == internal_group_name.lower():
                            txt_group = existing_grp
                            break
                    
                    if not txt_group:
                        txt_group = sp_file.Groups.Create(internal_group_name)
                    
                    # Get/Create Parameter Definition in .txt File
                    param_def = txt_group.Definitions.get_Item(param_name)
                    if not param_def:
                        try:
                            opt = ExternalDefinitionCreationOptions(param_name, SpecTypeId.String.Text)
                            param_def = txt_group.Definitions.Create(opt)
                        except:
                            try:
                                opt = ExternalDefinitionCreationOptions(param_name, ParameterType.Text)
                                param_def = txt_group.Definitions.Create(opt)
                            except Exception as ex:
                                results.append(f"FAILED: '{param_name}' - {str(ex)}")
                                continue
                    
                    # Build Category Set
                    cat_set = app.Create.NewCategorySet()
                    for c_name in category_names:
                        if c_name in doc_categories:
                            cat_set.Insert(doc_categories[c_name])
                    
                    if cat_set.IsEmpty:
                        results.append(f"FAILED: '{param_name}' (No matching categories in Revit)")
                        continue
                    
                    binding = app.Create.NewInstanceBinding(cat_set) if is_instance else app.Create.NewTypeBinding(cat_set)
                    
                    # Bind Parameter to Revit Project
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
                            results.append(f"SUCCESS: '{param_name}'")
                        except Exception as ex:
                            results.append(f"FAILED: '{param_name}' - {str(ex)}")
                    else:
                        results.append(f"SUCCESS: '{param_name}'")

        except Exception as e:
            results.append(f"FAILED: File error - {str(e)}")

    TransactionManager.Instance.TransactionTaskDone()

OUT = results
