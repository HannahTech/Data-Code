
import clr
import csv
import os
import re
import System

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

def read_csv_dict(path):
    if not path or not os.path.exists(path):
        raise Exception("CSV not found: {}".format(path))
    try:
        f = open(path, "r", encoding="utf-8-sig", errors="ignore", newline="")
    except:
        f = open(path, "r")
    with f:
        return list(csv.DictReader(f))

def group_type_id(name):
    k = norm(name)
    m = {
        "identitydata": GroupTypeId.IdentityData,
        "modelproperties": GroupTypeId.AdskModelProperties,
        "general": GroupTypeId.General,
        "data": GroupTypeId.Data,
        "dimensions": GroupTypeId.Dimensions,
        "materialsandfinishes": GroupTypeId.Materials,
        "materialsfinishes": GroupTypeId.Materials,
        "materials": GroupTypeId.Materials,
        "constraints": GroupTypeId.Constraints,
        "graphics": GroupTypeId.Graphics,
        "ifcparameters": GroupTypeId.Ifc,
        "ifc": GroupTypeId.Ifc,
        "phasing": GroupTypeId.Phasing,
        "text": GroupTypeId.Text,
    }
    return m.get(k)

def open_shared_parameter_file(path):
    if not path or not os.path.exists(path):
        raise Exception("Shared parameter TXT not found: {}".format(path))
    old = app.SharedParametersFilename
    app.SharedParametersFilename = path
    sf = app.OpenSharedParameterFile()
    if sf is None:
        app.SharedParametersFilename = old
        raise Exception("Revit could not open the shared parameter file.")
    return sf, old

def find_external_definition(sf, name):
    n = text(name).lower()
    for g in sf.Groups:
        for d in g.Definitions:
            if text(d.Name).lower() == n:
                return d
    return None

def split_categories(value):
    return [x.strip() for x in text(value).split(",") if x.strip()]

def safe_guid(value):
    try:
        return System.Guid(text(value))
    except:
        return None

def is_blank_parameter(p):
    if p is None:
        return True
    try:
        if p.StorageType == StorageType.String:
            return text(p.AsString()) == ""
        return not bool(p.HasValue)
    except:
        return True

def set_element_parameter(p, value):
    if p is None or p.IsReadOnly:
        return False
    s = text(value)
    if s == "":
        return False
    try:
        st = p.StorageType
        if st == StorageType.String:
            p.Set(s)
            return True
        if st == StorageType.Integer:
            k = norm(s)
            if k in ("true","yes","y"):
                p.Set(1); return True
            if k in ("false","no","n"):
                p.Set(0); return True
            p.Set(int(float(s)))
            return True
        if st == StorageType.Double:
            # Numeric CSV values are interpreted in current Revit document display units.
            val = float(s.replace(",",""))
            try:
                spec = p.Definition.GetDataType()
                fmt = doc.GetUnits().GetFormatOptions(spec)
                unit_id = fmt.GetUnitTypeId()
                val = UnitUtils.ConvertToInternalUnits(val, unit_id)
            except:
                pass
            p.Set(val)
            return True
    except:
        return False
    return False

MASTER_CSV = text(IN[0]) if len(IN) > 0 else ""
OUTPUT_FOLDER = text(IN[1]) if len(IN) > 1 else ""
RUN = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
INCLUDE_EMPTY = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else False
WRITE_LONG = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True

log = []

BIC = {
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
    if k in BIC:
        try:
            return Category.GetCategory(doc, BIC[k])
        except:
            pass
    try:
        for c in doc.Settings.Categories:
            if norm(c.Name) == k:
                return c
    except:
        pass
    return None

def get_export_categories(rows):
    names = []
    seen = set()
    for r in rows:
        if norm(r.get("Scope")) == "projectinformation":
            continue
        for c in split_categories(r.get("Categories")):
            k = norm(c)
            if k == "projectinformation" or k in seen:
                continue
            seen.add(k)
            names.append(c)
    return names

def collect_instances(category_names):
    out = {}
    for cname in category_names:
        c = category_from_name(cname)
        if c is None:
            log.append("CATEGORY NOT FOUND | {}".format(cname))
            continue
        try:
            fec = FilteredElementCollector(doc).WherePasses(ElementCategoryFilter(c.Id)).WhereElementIsNotElementType()
            for e in fec:
                if e.ViewSpecific:
                    continue
                out[e.UniqueId] = e
        except:
            pass
    return list(out.values())

def display_value(p):
    if p is None:
        return ""
    try:
        if p.StorageType == StorageType.String:
            return text(p.AsString())
        s = p.AsValueString()
        if text(s) != "":
            return text(s)
        if p.StorageType == StorageType.Integer:
            return str(p.AsInteger())
        if p.StorageType == StorageType.Double:
            return str(p.AsDouble())
        if p.StorageType == StorageType.ElementId:
            eid = p.AsElementId()
            if eid is None:
                return ""
            try:
                ref = doc.GetElement(eid)
                if ref is not None:
                    return "{} [{}]".format(text(ref.Name), eid.Value)
            except:
                pass
            return str(eid.Value)
    except:
        pass
    return ""

def raw_text(p):
    try:
        if p.StorageType == StorageType.String:
            return text(p.AsString())
        if p.StorageType == StorageType.Integer:
            return str(p.AsInteger())
        if p.StorageType == StorageType.Double:
            return repr(p.AsDouble())
        if p.StorageType == StorageType.ElementId:
            return str(p.AsElementId().Value)
    except:
        pass
    return ""

def shared_guid(p):
    try:
        return str(p.GUID)
    except:
        return ""

def storage_name(p):
    try:
        return str(p.StorageType)
    except:
        return ""

def element_family_type(e):
    family = ""
    typ = ""
    et = None
    try:
        tid = e.GetTypeId()
        if tid and tid != ElementId.InvalidElementId:
            et = doc.GetElement(tid)
    except:
        pass
    if et is not None:
        try:
            typ = text(et.Name)
        except:
            pass
        try:
            if isinstance(et, FamilySymbol):
                family = text(et.Family.Name)
        except:
            pass
    if not family:
        try:
            family = text(e.Name)
        except:
            pass
    return family, typ, et

def level_name(e):
    try:
        lid = e.LevelId
        if lid and lid != ElementId.InvalidElementId:
            lev = doc.GetElement(lid)
            if lev:
                return text(lev.Name)
    except:
        pass
    return ""

def parameters_to_dict(owner, source_prefix):
    result = {}
    if owner is None:
        return result
    try:
        params = list(owner.Parameters)
    except:
        params = []
    for p in params:
        try:
            name = text(p.Definition.Name)
        except:
            continue
        val = display_value(p)
        if not INCLUDE_EMPTY and val == "":
            continue
        key = name if name.startswith("TD_") else source_prefix + name
        if key in result and result[key] != val:
            # Avoid hiding duplicate-name parameters.
            n = 2
            base = key
            while "{} [{}]".format(base,n) in result:
                n += 1
            key = "{} [{}]".format(base,n)
        result[key] = val
    return result

def append_long(rows, owner, owner_kind, source, family="", typ="", category=""):
    if owner is None:
        return
    try:
        params = list(owner.Parameters)
    except:
        params = []
    for p in params:
        try:
            name = text(p.Definition.Name)
        except:
            continue
        val = display_value(p)
        if not INCLUDE_EMPTY and val == "":
            continue
        rows.append([
            text(doc.Title), owner_kind, str(owner.Id.Value), text(owner.UniqueId), category,
            family, typ, source, name, val, raw_text(p), storage_name(p),
            "TRUE" if shared_guid(p) else "FALSE", shared_guid(p),
            str(p.Id.Value) if p.Id else "", "TRUE" if p.IsReadOnly else "FALSE"
        ])

def write_csv(path, headers, rows):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)

if not RUN:
    OUT = ["READY | Step 4 Export | Choose output folder and set Run=True."]
elif doc.IsFamilyDocument:
    OUT = ["FAILED | Step 4 must run in a Revit PROJECT."]
else:
    try:
        if not OUTPUT_FOLDER:
            raise Exception("Output folder is blank.")
        if not os.path.exists(OUTPUT_FOLDER):
            os.makedirs(OUTPUT_FOLDER)

        master_rows = read_csv_dict(MASTER_CSV)
        export_categories = get_export_categories(master_rows)
        instances = collect_instances(export_categories)

        fixed_headers = [
            "Document","ElementId","UniqueId","Category","Family","Type","TypeId","Level"
        ]
        wide_rows_dict = []
        long_rows = []
        used_types = {}

        for e in instances:
            category = ""
            try:
                category = text(e.Category.Name)
            except:
                pass
            family, typ, et = element_family_type(e)
            type_id = ""
            try:
                type_id = str(e.GetTypeId().Value)
            except:
                pass

            row = {
                "Document": text(doc.Title),
                "ElementId": str(e.Id.Value),
                "UniqueId": text(e.UniqueId),
                "Category": category,
                "Family": family,
                "Type": typ,
                "TypeId": type_id,
                "Level": level_name(e),
            }
            row.update(parameters_to_dict(e, "I::"))
            if et is not None:
                row.update(parameters_to_dict(et, "T::"))
                used_types[str(et.Id.Value)] = (et, family, typ, category)

            wide_rows_dict.append(row)
            if WRITE_LONG:
                append_long(long_rows, e, "ElementInstance", "Instance", family, typ, category)
                if et is not None:
                    append_long(long_rows, et, "ElementType", "Type", family, typ, category)

        # Wide union, fixed columns first, TD_ columns next, then built-in/custom instance/type columns.
        dynamic = set()
        for r in wide_rows_dict:
            dynamic.update(k for k in r.keys() if k not in fixed_headers)
        td_cols = sorted([k for k in dynamic if k.startswith("TD_")], key=str.lower)
        other_cols = sorted([k for k in dynamic if not k.startswith("TD_")], key=str.lower)
        wide_headers = fixed_headers + td_cols + other_cols
        wide_rows = [[r.get(h,"") for h in wide_headers] for r in wide_rows_dict]

        wide_path = os.path.join(OUTPUT_FOLDER, "01_TD_Project_Asset_Export_Wide.csv")
        write_csv(wide_path, wide_headers, wide_rows)

        # One row per used type, with all type parameters that have data.
        type_dicts = []
        for tid,(et,family,typ,category) in used_types.items():
            r = {
                "Document": text(doc.Title),
                "TypeId": tid,
                "Category": category,
                "Family": family,
                "Type": typ,
            }
            r.update(parameters_to_dict(et, "T::"))
            type_dicts.append(r)
        type_fixed = ["Document","TypeId","Category","Family","Type"]
        type_dynamic = set()
        for r in type_dicts:
            type_dynamic.update(k for k in r.keys() if k not in type_fixed)
        type_headers = type_fixed + sorted(type_dynamic, key=str.lower)
        type_rows = [[r.get(h,"") for h in type_headers] for r in type_dicts]
        type_path = os.path.join(OUTPUT_FOLDER, "02_TD_Family_Type_Export.csv")
        write_csv(type_path, type_headers, type_rows)

        # Project Information: built-in + TD building parameters.
        pi = doc.ProjectInformation
        pi_dict = parameters_to_dict(pi, "P::")
        pi_headers = ["Document","ElementId","UniqueId"] + sorted(pi_dict.keys(), key=str.lower)
        pi_row = [text(doc.Title), str(pi.Id.Value), text(pi.UniqueId)] + [pi_dict.get(h,"") for h in pi_headers[3:]]
        pi_path = os.path.join(OUTPUT_FOLDER, "03_TD_Project_Information.csv")
        write_csv(pi_path, pi_headers, [pi_row])
        if WRITE_LONG:
            append_long(long_rows, pi, "ProjectInformation", "Project", "", "", "Project Information")

        long_path = ""
        if WRITE_LONG:
            long_headers = [
                "Document","OwnerKind","OwnerElementId","OwnerUniqueId","Category","Family","Type",
                "ParameterSource","ParameterName","Value","RawValue","StorageType","IsShared",
                "SharedGUID","ParameterId","ReadOnly"
            ]
            long_path = os.path.join(OUTPUT_FOLDER, "04_TD_All_Parameters_Long.csv")
            write_csv(long_path, long_headers, long_rows)

        summary_path = os.path.join(OUTPUT_FOLDER, "00_TD_Export_Summary.txt")
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("TD PROJECT EXPORT\n")
            f.write("=================\n")
            f.write("Document: {}\n".format(doc.Title))
            f.write("Exported categories: {}\n".format(", ".join(export_categories)))
            f.write("Instances exported: {}\n".format(len(instances)))
            f.write("Used types exported: {}\n".format(len(used_types)))
            f.write("Long parameter rows: {}\n".format(len(long_rows)))
            f.write("\nFiles:\n{}\n{}\n{}\n{}\n".format(wide_path,type_path,pi_path,long_path))

        OUT = [
            "SUMMARY | Instances={} | UsedTypes={} | LongRows={}".format(
                len(instances), len(used_types), len(long_rows)),
            summary_path, wide_path, type_path, pi_path, long_path
        ]
    except Exception as ex:
        OUT = ["FAILED | {}".format(ex)]
