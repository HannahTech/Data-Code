# -*- coding: utf-8 -*-
__title__ = "Import CSV to\nShared Params"
__doc__ = "Creates a Shared Parameter TXT file from CSV with GUIDs and binds them into the Project."

import os
import csv
import uuid
import clr

from pyrevit import forms, script

clr.AddReference("RevitServices")
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

clr.AddReference("RevitAPI")
from Autodesk.Revit.DB import (
    BuiltInCategory,
    CategorySet,
    InstanceBinding,
    ExternalDefinitionCreationOptions,
    SpecTypeId
)

doc = __revit__.ActiveUIDocument.Document
app = __revit__.Application

# ----------------------------------------------------
# 1. SELECT CSV & SET TARGET SHARED PARAMETER TXT PATH
# ----------------------------------------------------
csv_path = forms.pick_file(file_ext="csv", title="Select Parameters CSV File")
if not csv_path:
    script.exit()

# Set output Shared Parameter TXT path (same folder as CSV or custom)
txt_path = os.path.splitext(csv_path)[0] + "_SharedParameters.txt"

# Map string data types from CSV to Revit SpecTypeIds (Revit 2021+)
TYPE_MAP = {
    "Text": SpecTypeId.String.Text,
    "Integer": SpecTypeId.Int.Integer,
    "Number": SpecTypeId.Number.Real,
    "Length": SpecTypeId.Length,
    "YesNo": SpecTypeId.Boolean.YesNo,
    "URL": SpecTypeId.Url
}

# Map category string names to BuiltInCategory enums
CAT_MAP = {
    "OST_Furniture": BuiltInCategory.OST_Furniture,
    "OST_ProjectInformation": BuiltInCategory.OST_ProjectInformation,
    "OST_Rooms": BuiltInCategory.OST_Rooms,
    "OST_Spaces": BuiltInCategory.OST_Spaces
}

# ----------------------------------------------------
# 2. ENSURE SHARED PARAMETER FILE EXISTS & SET IN REVIT
# ----------------------------------------------------
if not os.path.exists(txt_path):
    with open(txt_path, "w") as f:
        f.write("# This is a Revit shared parameter file created via pyRevit.\n")
        f.write("*META	VERSION	MINVERSION\n")
        f.write("META	2.0	2.0\n")
        f.write("*GROUP	ID	NAME\n")
        f.write("*PARAM	GUID	NAME	DATATYPE	DATACAT	GROUP	VISIBLE	DESCRIPTION	USERMODIFIABLE	HIDEWHENNOVALUE\n")

# Assign this text file to active Revit Application
app.SharedParametersFilename = txt_path
def_file = app.OpenSharedParameterFile()

if not def_file:
    forms.alert("Failed to open or initialize Shared Parameter File.", exitscript=True)

# ----------------------------------------------------
# 3. READ CSV & PROCESS PARAMETERS
# ----------------------------------------------------
params_by_cat = {}  # { (ParamName, GroupName, SpecType): [Categories...] }

with open(csv_path, "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        p_name = row["ParameterName"].strip()
        p_group = row["Group"].strip()
        p_cat_str = row["Category"].strip()
        p_type_str = row.get("Type", "Text").strip()

        spec_type = TYPE_MAP.get(p_type_str, SpecTypeId.String.Text)
        cat_enum = CAT_MAP.get(p_cat_str)

        if not cat_enum:
            continue

        key = (p_name, p_group, spec_type)
        if key not in params_by_cat:
            params_by_cat[key] = []
        params_by_cat[key].append(cat_enum)

# ----------------------------------------------------
# 4. CREATE DEFINITIONS (WITH GUIDs) & BIND TO PROJECT
# ----------------------------------------------------
TransactionManager.Instance.EnsureInTransaction(doc)

try:
    binding_map = doc.ParameterBindings
    created_count = 0

    for (p_name, p_group, spec_type), cat_enums in params_by_cat.items():
        # Get or Create Parameter Group in TXT file
        group = def_file.Groups.get_Item(p_group)
        if not group:
            group = def_file.Groups.Create(p_group)

        # Get or Create External Definition (Revit handles GUID creation automatically)
        definition = group.Definitions.get_Item(p_name)
        if not definition:
            opt = ExternalDefinitionCreationOptions(p_name, spec_type)
            # You can explicitly set a custom GUID if needed: opt.GUID = System.Guid(...)
            definition = group.Definitions.Create(opt)

        # Build CategorySet for Project Parameter binding
        cat_set = CategorySet()
        for c_enum in cat_enums:
            cat = doc.Settings.Categories.get_Item(c_enum)
            if cat:
                cat_set.Insert(cat)

        # Bind as Instance Shared Parameter
        binding = InstanceBinding(cat_set)

        if binding_map.Contains(definition):
            binding_map.ReBinding(definition, binding)
        else:
            binding_map.Insert(definition, binding)

        created_count += 1

    TransactionManager.Instance.TransactionTaskDone()

    forms.alert(
        "Done!\n\n"
        "- Processed: {} parameters\n"
        "- Saved to TXT: {}\n"
        "- Bound to Project Parameters for assigned categories.".format(created_count, txt_path),
        title="Success"
    )

except Exception as err:
    TransactionManager.Instance.TransactionTaskDone()
    forms.alert("Error creating shared parameters:\n{}".format(err))

