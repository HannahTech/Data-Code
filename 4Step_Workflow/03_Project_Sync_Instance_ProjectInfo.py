
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
SHARED_TXT = text(IN[1]) if len(IN) > 1 else ""
RUN = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
REMOVE_STALE = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else True
REPAIR_BINDINGS = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True
APPLY_DEFAULTS = bool(IN[5]) if len(IN) > 5 and IN[5] is not None else True

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
    "projectinformation": BuiltInCategory.OST_ProjectInformation,
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

def make_category_set(names):
    cs = app.Create.NewCategorySet()
    ids = set()
    for name in names:
        c = category_from_name(name)
        if c is None:
            log.append("CATEGORY NOT FOUND | {}".format(name))
            continue
        try:
            if not c.AllowsBoundParameters:
                log.append("CATEGORY CANNOT BIND PARAMETERS | {}".format(name))
                continue
        except:
            pass
        cs.Insert(c)
        ids.add(str(c.Id.Value))
    return cs, ids

def binding_categories(binding):
    ids = set()
    names = []
    try:
        for c in binding.Categories:
            ids.add(str(c.Id.Value))
            names.append(c.Name)
    except:
        pass
    return ids, names

def definition_guid(defn):
    try:
        pe = doc.GetElement(defn.Id)
        if isinstance(pe, SharedParameterElement):
            return str(pe.GuidValue).lower()
    except:
        pass
    return ""

def binding_snapshot():
    items = []
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        d = it.Key
        b = it.Current
        try:
            items.append((d,b,text(d.Name),definition_guid(d)))
        except:
            pass
    return items

def parameter_by_definition(element, definition):
    try:
        return element.get_Parameter(definition)
    except:
        pass
    try:
        did = definition.Id
        for p in element.GetParameters(definition.Name):
            try:
                if p.Id == did:
                    return p
            except:
                pass
    except:
        pass
    return None

def raw_value(p):
    if p is None:
        return None
    try:
        if not p.HasValue and p.StorageType != StorageType.String:
            return None
    except:
        pass
    try:
        if p.StorageType == StorageType.String:
            v = p.AsString()
            return ("String", v) if text(v) != "" else None
        if p.StorageType == StorageType.Integer:
            return ("Integer", p.AsInteger())
        if p.StorageType == StorageType.Double:
            return ("Double", p.AsDouble())
        if p.StorageType == StorageType.ElementId:
            return ("ElementId", p.AsElementId())
    except:
        pass
    return None

def set_raw(p, pair):
    if p is None or pair is None or p.IsReadOnly:
        return False
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

def elements_of_categories(categories, element_types=False):
    found = {}
    for c in categories:
        cat = category_from_name(c)
        if cat is None:
            continue
        try:
            fec = FilteredElementCollector(doc).WherePasses(ElementCategoryFilter(cat.Id))
            fec = fec.WhereElementIsElementType() if element_types else fec.WhereElementIsNotElementType()
            for e in fec:
                found[e.UniqueId] = e
        except:
            pass
    return list(found.values())

def backup_binding_values(definition, binding, target_categories):
    data = {}
    # If an old parameter was Type-bound but should become Instance-bound,
    # copy each type value to each instance of that type.
    if isinstance(binding, TypeBinding):
        for e in elements_of_categories(target_categories, False):
            try:
                t = doc.GetElement(e.GetTypeId())
                p = parameter_by_definition(t, definition) if t else None
                pair = raw_value(p)
                if pair is not None:
                    data[e.UniqueId] = pair
            except:
                pass
    else:
        _, old_cat_names = binding_categories(binding)
        for e in elements_of_categories(old_cat_names, False):
            p = parameter_by_definition(e, definition)
            pair = raw_value(p)
            if pair is not None:
                data[e.UniqueId] = pair
    return data

def restore_to_guid(guid_text, data):
    g = safe_guid(guid_text)
    if g is None:
        return 0
    restored = 0
    for uid, pair in data.items():
        try:
            e = doc.GetElement(uid)
            if e is None:
                continue
            p = e.get_Parameter(g)
            if set_raw(p, pair):
                restored += 1
        except:
            pass
    return restored

def categories_from_row(r):
    if norm(r.get("Scope")) == "projectinformation":
        return ["Project Information"]
    return split_categories(r.get("Categories"))

def bind_new(ext_def, r):
    cats = categories_from_row(r)
    cs, ids = make_category_set(cats)
    if len(ids) == 0:
        return False, "No valid categories."
    binding = app.Create.NewInstanceBinding(cs)
    gid = group_type_id(r.get("RevitUIGroup"))
    if gid is None:
        return False, "Unsupported UI group '{}'".format(r.get("RevitUIGroup"))
    ok = doc.ParameterBindings.Insert(ext_def, binding, gid)
    return bool(ok), "" if ok else "BindingMap.Insert returned False."

def repair_existing(definition, binding, r):
    cats = categories_from_row(r)
    backup = backup_binding_values(definition, binding, cats)
    cs, desired_ids = make_category_set(cats)
    if len(desired_ids) == 0:
        return False, 0, "No valid categories."
    gid = group_type_id(r.get("RevitUIGroup"))
    if gid is None:
        return False, 0, "Unsupported UI group."
    new_binding = app.Create.NewInstanceBinding(cs)

    sub = SubTransaction(doc)
    sub.Start()
    try:
        ok = doc.ParameterBindings.ReInsert(definition, new_binding, gid)
        if not ok:
            raise Exception("BindingMap.ReInsert returned False.")
        restored = restore_to_guid(r.get("GUID"), backup)
        sub.Commit()
        return True, restored, ""
    except Exception as ex:
        try:
            sub.RollBack()
        except:
            pass
        return False, 0, str(ex)

def replace_wrong_definition(old_def, old_binding, ext_def, r):
    cats = categories_from_row(r)
    backup = backup_binding_values(old_def, old_binding, cats)
    sub = SubTransaction(doc)
    sub.Start()
    try:
        if not doc.ParameterBindings.Remove(old_def):
            raise Exception("Could not remove old binding.")
        ok, err = bind_new(ext_def, r)
        if not ok:
            raise Exception(err)
        restored = restore_to_guid(r.get("GUID"), backup)
        sub.Commit()
        return True, restored, ""
    except Exception as ex:
        try:
            sub.RollBack()
        except:
            pass
        return False, 0, str(ex)

def apply_default(r):
    default = text(r.get("DefaultValue"))
    if default == "":
        return 0
    g = safe_guid(r.get("GUID"))
    if g is None:
        return 0
    count = 0
    for e in elements_of_categories(categories_from_row(r), False):
        try:
            p = e.get_Parameter(g)
            if p is not None and is_blank_parameter(p):
                if set_element_parameter(p, default):
                    count += 1
        except:
            pass
    return count

if not RUN:
    OUT = ["READY | Step 3 Project Sync | Set Run=True."]
elif doc.IsFamilyDocument:
    OUT = ["FAILED | Step 3 must run in a Revit PROJECT, not a family."]
else:
    old_shared = None
    tx_open = False
    try:
        all_rows = read_csv_dict(MASTER_CSV)
        expected_rows = [r for r in all_rows if norm(r.get("Scope")) in ("projectinstance","projectinformation")]
        expected_names = set(text(r.get("Parameter")).lower() for r in expected_rows)
        sf, old_shared = open_shared_parameter_file(SHARED_TXT)

        TransactionManager.Instance.EnsureInTransaction(doc)
        tx_open = True

        added = repaired = kept = removed = failed = restored_total = defaults = 0

        for r in expected_rows:
            name = text(r.get("Parameter"))
            desired_guid = text(r.get("GUID")).lower()
            ext = find_external_definition(sf, name)
            if ext is None:
                failed += 1
                log.append("FAIL {} | not found in shared parameter TXT".format(name))
                continue

            snap = binding_snapshot()
            same_name = [(d,b,n,g) for d,b,n,g in snap if n.lower() == name.lower()]
            correct = None
            for item in same_name:
                if item[3] == desired_guid:
                    correct = item
                    break

            desired_cats = categories_from_row(r)
            _, desired_ids = make_category_set(desired_cats)
            gid = group_type_id(r.get("RevitUIGroup"))

            if correct is not None:
                d,b,n,g = correct
                current_ids, _ = binding_categories(b)
                binding_ok = isinstance(b, InstanceBinding)
                try:
                    group_ok = d.GetGroupTypeId() == gid
                except:
                    group_ok = False
                cats_ok = current_ids == desired_ids

                if binding_ok and group_ok and cats_ok:
                    kept += 1
                elif REPAIR_BINDINGS:
                    ok, restored, err = repair_existing(d,b,r)
                    if ok:
                        repaired += 1
                        restored_total += restored
                        log.append("REPAIR {} | binding/group/categories | restored={}".format(name,restored))
                    else:
                        failed += 1
                        log.append("FAIL REPAIR {} | {}".format(name,err))
                        continue
                else:
                    failed += 1
                    log.append("NEEDS REPAIR {} | binding={} group={} categories={}".format(
                        name, binding_ok, group_ok, cats_ok))
                    continue

                # Remove duplicate same-name wrong-GUID bindings after the correct one is secured.
                if REPAIR_BINDINGS:
                    for od,ob,on,og in same_name:
                        if od.Id == d.Id:
                            continue
                        try:
                            if doc.ParameterBindings.Remove(od):
                                log.append("REMOVE DUPLICATE WRONG GUID {} | {}".format(name,og or "non-shared"))
                        except:
                            pass

            elif same_name:
                od,ob,on,og = same_name[0]
                if REPAIR_BINDINGS:
                    ok, restored, err = replace_wrong_definition(od,ob,ext,r)
                    if ok:
                        repaired += 1
                        restored_total += restored
                        log.append("REPLACE WRONG GUID {} | old={} new={} | restored={}".format(
                            name, og or "non-shared", desired_guid, restored))
                        # Remove additional duplicates if any.
                        for od2,ob2,on2,og2 in same_name[1:]:
                            try:
                                doc.ParameterBindings.Remove(od2)
                            except:
                                pass
                    else:
                        failed += 1
                        log.append("FAIL REPLACE {} | {}".format(name,err))
                        continue
                else:
                    failed += 1
                    log.append("NEEDS REPAIR {} | wrong GUID/non-shared".format(name))
                    continue

            else:
                ok, err = bind_new(ext,r)
                if ok:
                    added += 1
                    log.append("ADD {} | INSTANCE | {}".format(name,", ".join(desired_cats)))
                else:
                    failed += 1
                    log.append("FAIL ADD {} | {}".format(name,err))
                    continue

            if APPLY_DEFAULTS:
                defaults += apply_default(r)

        if REMOVE_STALE:
            for d,b,n,g in binding_snapshot():
                if not n.startswith("TD_"):
                    continue
                if n.lower() in expected_names:
                    continue
                try:
                    if doc.ParameterBindings.Remove(d):
                        removed += 1
                        log.append("REMOVE STALE PROJECT PARAMETER {}".format(n))
                except Exception as ex:
                    failed += 1
                    log.append("FAIL REMOVE {} | {}".format(n,ex))

        TransactionManager.Instance.TransactionTaskDone()
        tx_open = False
        log.insert(0,
            "SUMMARY | Expected={} | Added={} | Repaired={} | Kept={} | Removed={} | "
            "ValuesRestored={} | DefaultsFilled={} | Failed={}".format(
                len(expected_rows), added, repaired, kept, removed, restored_total, defaults, failed))
    except Exception as ex:
        if tx_open:
            try:
                TransactionManager.Instance.ForceCloseTransaction()
            except:
                pass
        log.insert(0, "FAILED | {}".format(ex))
    finally:
        if old_shared is not None:
            try:
                app.SharedParametersFilename = old_shared
            except:
                pass
    OUT = log
