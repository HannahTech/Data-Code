# -*- coding: utf-8 -*-
# TD Revit Workflow — Dynamo CPython3 — Revit 2026+
import clr
import csv
import os
import re
import System
from datetime import datetime

clr.AddReference("RevitAPI")
clr.AddReference("RevitServices")

from Autodesk.Revit.DB import *
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

doc = DocumentManager.Instance.CurrentDBDocument
app = doc.Application

def text(v):
    return "" if v is None else str(v).strip()

def norm(v):
    return re.sub(r"[^a-zA-Z0-9]", "", text(v)).lower()

def truthy(v):
    return norm(v) in ("true","yes","y","1")

def eid_value(eid):
    try:
        return eid.Value
    except:
        try:
            return eid.IntegerValue
        except:
            return -1

def safe_filename(value):
    s = re.sub(r'[<>:"/\\|?*]+', "_", text(value))
    s = re.sub(r"\s+", "_", s).strip("._")
    return s or "RevitDocument"

def backup_root(master_csv):
    folder = os.path.dirname(os.path.abspath(master_csv))
    path = os.path.join(folder, "TD_Backups")
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def read_csv_dict(path):
    if not path or not os.path.exists(path):
        raise Exception("CSV not found: {}".format(path))
    try:
        f = open(path, "r", encoding="utf-8-sig", errors="ignore", newline="")
    except:
        f = open(path, "r")
    with f:
        return list(csv.DictReader(f))

def write_csv(path, headers, data):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(data)

def group_type_id(name):
    k = norm(name)
    mapping = {
        "identitydata": GroupTypeId.IdentityData,
        "modelproperties": GroupTypeId.AdskModelProperties,
        "general": GroupTypeId.General,
        "data": GroupTypeId.Data,
        "dimensions": GroupTypeId.Dimensions,
        "geometry": GroupTypeId.Dimensions,
        "materials": GroupTypeId.Materials,
        "materialsandfinishes": GroupTypeId.Materials,
        "materialsfinishes": GroupTypeId.Materials,
        "constraints": GroupTypeId.Constraints,
        "graphics": GroupTypeId.Graphics,
        "ifc": GroupTypeId.Ifc,
        "ifcparameters": GroupTypeId.Ifc,
        "phasing": GroupTypeId.Phasing,
        "text": GroupTypeId.Text,
    }
    return mapping.get(k)

def open_shared_parameter_file(path):
    if not path or not os.path.exists(path):
        raise Exception("Shared parameter TXT not found: {}".format(path))
    old = app.SharedParametersFilename
    app.SharedParametersFilename = path
    sf = app.OpenSharedParameterFile()
    if sf is None:
        app.SharedParametersFilename = old
        raise Exception("Revit could not open the selected shared parameter file.")
    return sf, old

def find_external_definition(sf, name):
    target = text(name).lower()
    for group in sf.Groups:
        for d in group.Definitions:
            if text(d.Name).lower() == target:
                return d
    return None

def split_categories(value):
    return [x.strip() for x in text(value).split(",") if x.strip()]

def raw_parameter_value(p):
    if p is None:
        return None
    try:
        st = p.StorageType
        if st == StorageType.String:
            v = p.AsString()
            return ("String", v) if text(v) != "" else None
        if st == StorageType.Integer:
            if not p.HasValue:
                return None
            return ("Integer", p.AsInteger())
        if st == StorageType.Double:
            if not p.HasValue:
                return None
            return ("Double", p.AsDouble())
        if st == StorageType.ElementId:
            if not p.HasValue:
                return None
            return ("ElementId", p.AsElementId())
    except:
        pass
    return None

def display_parameter_value(p):
    if p is None:
        return ""
    try:
        if p.StorageType == StorageType.String:
            return text(p.AsString())
        s = p.AsValueString()
        if text(s):
            return text(s)
        if p.StorageType == StorageType.Integer:
            return str(p.AsInteger())
        if p.StorageType == StorageType.Double:
            return repr(p.AsDouble())
        if p.StorageType == StorageType.ElementId:
            eid = p.AsElementId()
            ref = doc.GetElement(eid)
            if ref is not None:
                return "{} [{}]".format(text(ref.Name), eid_value(eid))
            return str(eid_value(eid))
    except:
        pass
    return ""

def set_raw_parameter_value(p, pair):
    if p is None or pair is None:
        return False
    try:
        if p.IsReadOnly:
            return False
    except:
        pass
    kind, value = pair
    try:
        if kind == "String":
            p.Set(value if value is not None else "")
        elif kind == "Integer":
            p.Set(int(value))
        elif kind == "Double":
            p.Set(float(value))
        elif kind == "ElementId":
            p.Set(value)
        else:
            return False
        return True
    except:
        return False

def is_blank_element_parameter(p):
    if p is None:
        return True
    try:
        if p.StorageType == StorageType.String:
            return text(p.AsString()) == ""
        return not bool(p.HasValue)
    except:
        return True

def set_display_value(p, value):
    """Set a simple CSV/Excel value. Numbers are interpreted in current document display units."""
    if p is None:
        return False
    try:
        if p.IsReadOnly:
            return False
    except:
        pass
    s = text(value)
    if s == "":
        return False
    try:
        if p.StorageType == StorageType.String:
            p.Set(s)
            return True
        if p.StorageType == StorageType.Integer:
            k = norm(s)
            if k in ("true","yes","y"):
                p.Set(1); return True
            if k in ("false","no","n"):
                p.Set(0); return True
            p.Set(int(float(s.replace(",",""))))
            return True
        if p.StorageType == StorageType.Double:
            val = float(s.replace(",",""))
            try:
                spec = p.Definition.GetDataType()
                fmt = doc.GetUnits().GetFormatOptions(spec)
                val = UnitUtils.ConvertToInternalUnits(val, fmt.GetUnitTypeId())
            except:
                pass
            p.Set(val)
            return True
    except:
        return False
    return False


# STEP 4 — EXPORT PROJECT + FAMILY/TYPE + PARAMETER DATA
# IN[0] = TD_Master_Parameters.csv
# IN[1] = Output folder
# IN[2] = Run
# IN[3] = IncludeEmptyParameters
# IN[4] = WriteLongFormExport
# IN[5] = ExportAllModelCategories
#
# Default/recommended IN[5] = False:
#   exports every element in the categories governed by the master CSV.
# IN[5] = True:
#   exports all non-view-specific model-category instances in the project.

MASTER_CSV = text(IN[0]) if len(IN) > 0 else ""
OUTPUT_FOLDER = text(IN[1]) if len(IN) > 1 else ""
RUN = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
INCLUDE_EMPTY = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else False
WRITE_LONG = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True
EXPORT_ALL_MODEL = bool(IN[5]) if len(IN) > 5 and IN[5] is not None else False

log = []

BIC_MAP = {
    "furniture": BuiltInCategory.OST_Furniture,
    "furnituresystems": BuiltInCategory.OST_FurnitureSystems,
    "casework": BuiltInCategory.OST_Casework,
    "specialtyequipment": BuiltInCategory.OST_SpecialityEquipment,
    "specialityequipment": BuiltInCategory.OST_SpecialityEquipment,
    "mechanicalequipment": BuiltInCategory.OST_MechanicalEquipment,
    "electricalequipment": BuiltInCategory.OST_ElectricalEquipment,
    "plumbingfixtures": BuiltInCategory.OST_PlumbingFixtures,
    "lightingfixtures": BuiltInCategory.OST_LightingFixtures,
    "rooms": BuiltInCategory.OST_Rooms,
    "spaces": BuiltInCategory.OST_MEPSpaces,
}

def category_from_name(name):
    k = norm(name)
    bic = BIC_MAP.get(k)
    if bic is not None:
        try:
            return Category.GetCategory(doc, bic)
        except:
            pass
    try:
        for c in doc.Settings.Categories:
            if norm(c.Name) == k:
                return c
    except:
        pass
    return None

def master_export_categories(master_rows):
    result = []
    seen = set()
    for row in master_rows:
        if not truthy(row.get("Export")):
            continue
        if norm(row.get("Scope")) == "projectinformation":
            continue
        for name in split_categories(row.get("Categories")):
            if norm(name) == "projectinformation":
                continue
            key = norm(name)
            if key and key not in seen:
                seen.add(key)
                result.append(name)
    return result

def collect_managed_instances(category_names):
    found = {}
    for name in category_names:
        c = category_from_name(name)
        if c is None:
            log.append("CATEGORY NOT FOUND | {}".format(name))
            continue
        try:
            collector = (
                FilteredElementCollector(doc)
                .WherePasses(ElementCategoryFilter(c.Id))
                .WhereElementIsNotElementType()
            )
            for e in collector:
                try:
                    if e.ViewSpecific:
                        continue
                except:
                    pass
                found[e.UniqueId] = e
        except:
            pass
    return list(found.values())

def collect_all_model_instances():
    found = {}
    collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    for e in collector:
        try:
            if e.ViewSpecific:
                continue
        except:
            pass

        try:
            cat = e.Category
            if cat is None or cat.CategoryType != CategoryType.Model:
                continue
        except:
            continue

        try:
            found[e.UniqueId] = e
        except:
            pass

    return list(found.values())

def element_family_type(e):
    family_name = ""
    type_name = ""
    et = None
    tid = ElementId.InvalidElementId

    try:
        tid = e.GetTypeId()
    except:
        pass

    try:
        if tid is not None and tid != ElementId.InvalidElementId:
            et = doc.GetElement(tid)
    except:
        et = None

    if et is not None:
        try:
            type_name = text(et.Name)
        except:
            pass
        try:
            if isinstance(et, FamilySymbol):
                family_name = text(et.Family.Name)
            elif hasattr(et, "FamilyName"):
                family_name = text(et.FamilyName)
        except:
            pass

    if not family_name:
        try:
            family_name = text(e.Name)
        except:
            pass

    return family_name, type_name, et, tid

def element_level(e):
    try:
        lid = e.LevelId
        if lid is not None and lid != ElementId.InvalidElementId:
            level = doc.GetElement(lid)
            if level is not None:
                return text(level.Name)
    except:
        pass

    # Rooms/Spaces and some hosted assets expose a Level parameter rather than LevelId.
    try:
        p = e.get_Parameter(BuiltInParameter.LEVEL_PARAM)
        if p:
            return display_parameter_value(p)
    except:
        pass
    return ""

def shared_parameter_guid(p):
    try:
        return str(p.GUID)
    except:
        return ""

def storage_type_name(p):
    try:
        return str(p.StorageType)
    except:
        return ""

def parameter_id_text(p):
    try:
        return str(eid_value(p.Id))
    except:
        return ""

def owner_parameters(owner):
    try:
        return list(owner.Parameters)
    except:
        return []

def parameter_map(owner, source_prefix):
    result = {}
    if owner is None:
        return result

    for p in owner_parameters(owner):
        try:
            name = text(p.Definition.Name)
        except:
            continue

        value = display_parameter_value(p)
        if not INCLUDE_EMPTY and value == "":
            continue

        if name.startswith("TD_"):
            key = name
        else:
            key = source_prefix + name

        if key in result:
            # Same-name parameters can exist (e.g. wrong GUID duplicates).
            n = 2
            base = key
            while "{} [{}]".format(base, n) in result:
                n += 1
            key = "{} [{}]".format(base, n)

        result[key] = value

    return result

def merge_parameter_map(target, source, conflict_prefix):
    for k, v in source.items():
        if k not in target:
            target[k] = v
            continue

        if target[k] == v:
            continue

        new_key = conflict_prefix + k
        if new_key in target:
            n = 2
            base = new_key
            while "{} [{}]".format(base, n) in target:
                n += 1
            new_key = "{} [{}]".format(base, n)
        target[new_key] = v

def append_long_rows(
    output_rows, owner, owner_kind, source,
    category="", family_name="", type_name=""
):
    if owner is None:
        return

    for p in owner_parameters(owner):
        try:
            parameter_name = text(p.Definition.Name)
        except:
            continue

        display = display_parameter_value(p)
        if not INCLUDE_EMPTY and display == "":
            continue

        pair = raw_parameter_value(p)
        raw = ""
        if pair is not None:
            raw = "" if pair[1] is None else str(pair[1])

        try:
            read_only = bool(p.IsReadOnly)
        except:
            read_only = False

        output_rows.append([
            text(doc.Title),
            owner_kind,
            str(eid_value(owner.Id)),
            text(owner.UniqueId),
            category,
            family_name,
            type_name,
            source,
            parameter_name,
            display,
            raw,
            storage_type_name(p),
            "TRUE" if shared_parameter_guid(p) else "FALSE",
            shared_parameter_guid(p),
            parameter_id_text(p),
            "TRUE" if read_only else "FALSE",
        ])

if not RUN:
    OUT = ["READY | Step 4 | Choose an output folder and set Run=True."]
elif doc.IsFamilyDocument:
    OUT = ["FAILED | Step 4 must run in a Revit PROJECT."]
else:
    try:
        if not OUTPUT_FOLDER:
            raise Exception("Output folder is blank.")
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)

        master = read_csv_dict(MASTER_CSV)
        managed_categories = master_export_categories(master)

        run_folder = os.path.join(
            OUTPUT_FOLDER,
            "TD_Export_{}_{}".format(safe_filename(doc.Title), timestamp())
        )
        os.makedirs(run_folder)

        if EXPORT_ALL_MODEL:
            instances = collect_all_model_instances()
            export_scope = "All model-category instances"
        else:
            instances = collect_managed_instances(managed_categories)
            export_scope = "Master CSV managed categories"

        fixed_headers = [
            "Document","ElementId","UniqueId","Category",
            "Family","Type","TypeId","Level"
        ]

        wide_dicts = []
        used_types = {}
        long_rows = []

        for e in instances:
            try:
                category_name = text(e.Category.Name)
            except:
                category_name = ""

            family_name, type_name, et, tid = element_family_type(e)

            row = {
                "Document": text(doc.Title),
                "ElementId": str(eid_value(e.Id)),
                "UniqueId": text(e.UniqueId),
                "Category": category_name,
                "Family": family_name,
                "Type": type_name,
                "TypeId": "" if tid is None else str(eid_value(tid)),
                "Level": element_level(e),
            }

            instance_map = parameter_map(e, "I::")
            type_map = parameter_map(et, "T::") if et is not None else {}

            merge_parameter_map(row, instance_map, "I::")
            merge_parameter_map(row, type_map, "T::")

            wide_dicts.append(row)

            if et is not None:
                used_types[str(eid_value(et.Id))] = (
                    et, family_name, type_name, category_name
                )

            if WRITE_LONG:
                append_long_rows(
                    long_rows, e, "ElementInstance", "Instance",
                    category_name, family_name, type_name
                )

        # Add each used TYPE to the long export only once.
        if WRITE_LONG:
            for type_id, (et, family_name, type_name, category_name) in used_types.items():
                append_long_rows(
                    long_rows, et, "ElementType", "Type",
                    category_name, family_name, type_name
                )

        # Wide instance export: stable core fields + TD fields + built-in/custom fields.
        dynamic_columns = set()
        for row in wide_dicts:
            for k in row.keys():
                if k not in fixed_headers:
                    dynamic_columns.add(k)

        td_columns = sorted(
            [k for k in dynamic_columns if k.startswith("TD_")],
            key=str.lower
        )
        other_columns = sorted(
            [k for k in dynamic_columns if not k.startswith("TD_")],
            key=str.lower
        )
        wide_headers = fixed_headers + td_columns + other_columns
        wide_rows = [[row.get(h, "") for h in wide_headers] for row in wide_dicts]

        wide_path = os.path.join(run_folder, "01_TD_Project_Asset_Export_Wide.csv")
        write_csv(wide_path, wide_headers, wide_rows)

        # One row per used Revit type.
        type_fixed = ["Document","TypeId","Category","Family","Type"]
        type_dicts = []

        for type_id, (et, family_name, type_name, category_name) in used_types.items():
            row = {
                "Document": text(doc.Title),
                "TypeId": type_id,
                "Category": category_name,
                "Family": family_name,
                "Type": type_name,
            }
            merge_parameter_map(row, parameter_map(et, "T::"), "T::")
            type_dicts.append(row)

        type_dynamic = set()
        for row in type_dicts:
            for k in row.keys():
                if k not in type_fixed:
                    type_dynamic.add(k)

        type_td = sorted(
            [k for k in type_dynamic if k.startswith("TD_")],
            key=str.lower
        )
        type_other = sorted(
            [k for k in type_dynamic if not k.startswith("TD_")],
            key=str.lower
        )
        type_headers = type_fixed + type_td + type_other
        type_rows = [[row.get(h, "") for h in type_headers] for row in type_dicts]

        type_path = os.path.join(run_folder, "02_TD_Family_Type_Export.csv")
        write_csv(type_path, type_headers, type_rows)

        # Project Information: TD names plain, Revit/default names prefixed P::.
        pi = doc.ProjectInformation
        pi_map = parameter_map(pi, "P::")
        pi_td = sorted([k for k in pi_map if k.startswith("TD_")], key=str.lower)
        pi_other = sorted([k for k in pi_map if not k.startswith("TD_")], key=str.lower)
        pi_headers = ["Document","ElementId","UniqueId"] + pi_td + pi_other
        pi_row = (
            [text(doc.Title), str(eid_value(pi.Id)), text(pi.UniqueId)]
            + [pi_map.get(h, "") for h in pi_td + pi_other]
        )

        project_info_path = os.path.join(run_folder, "03_TD_Project_Information.csv")
        write_csv(project_info_path, pi_headers, [pi_row])

        if WRITE_LONG:
            append_long_rows(
                long_rows, pi, "ProjectInformation", "Project",
                "Project Information", "", ""
            )

        long_path = ""
        if WRITE_LONG:
            long_headers = [
                "Document","OwnerKind","OwnerElementId","OwnerUniqueId",
                "Category","Family","Type","ParameterSource","ParameterName",
                "DisplayValue","RawValue","StorageType","IsShared",
                "SharedGUID","ParameterId","ReadOnly"
            ]
            long_path = os.path.join(run_folder, "04_TD_All_Parameters_Long.csv")
            write_csv(long_path, long_headers, long_rows)

        summary_path = os.path.join(run_folder, "00_TD_Export_Summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("TD PROJECT EXPORT\n")
            f.write("=================\n")
            f.write("Document: {}\n".format(doc.Title))
            f.write("Export run: {}\n".format(timestamp()))
            f.write("Scope: {}\n".format(export_scope))
            f.write("Managed categories from master: {}\n".format(", ".join(managed_categories)))
            f.write("Instances exported: {}\n".format(len(instances)))
            f.write("Used types exported: {}\n".format(len(used_types)))
            f.write("Project Information rows: 1\n")
            f.write("Long parameter rows: {}\n".format(len(long_rows) if WRITE_LONG else 0))
            f.write("Include empty parameters: {}\n".format(INCLUDE_EMPTY))
            f.write("All model categories: {}\n".format(EXPORT_ALL_MODEL))
            f.write("\nFILES\n")
            f.write("01_TD_Project_Asset_Export_Wide.csv\n")
            f.write("02_TD_Family_Type_Export.csv\n")
            f.write("03_TD_Project_Information.csv\n")
            if WRITE_LONG:
                f.write("04_TD_All_Parameters_Long.csv\n")

        OUT = [
            "SUMMARY | Scope={} | Instances={} | UsedTypes={} | LongRows={}".format(
                export_scope, len(instances), len(used_types),
                len(long_rows) if WRITE_LONG else 0
            ),
            "EXPORT FOLDER | {}".format(run_folder),
            wide_path,
            type_path,
            project_info_path,
            long_path,
            summary_path,
        ]

    except Exception as ex:
        OUT = ["FAILED | {}".format(ex)]
