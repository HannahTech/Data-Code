
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
REPAIR = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True

log = []

def family_category_name():
    try:
        return doc.OwnerFamily.FamilyCategory.Name
    except:
        return ""

def category_matches(csv_categories, family_category):
    if not csv_categories:
        return True
    fk = norm(family_category)
    aliases = {
        "furniture": ("furniture","furnituresystems"),
        "furnituresystems": ("furniture","furnituresystems"),
        "specialtyequipment": ("specialtyequipment","specialityequipment"),
        "specialityequipment": ("specialtyequipment","specialityequipment"),
    }
    accepted = aliases.get(fk, (fk,))
    return any(norm(c) in accepted for c in csv_categories)

def family_types(fm):
    items = []
    try:
        it = fm.Types.ForwardIterator()
        it.Reset()
        while it.MoveNext():
            items.append(it.Current)
    except:
        pass
    return items

def ensure_type(fm):
    try:
        if fm.CurrentType is not None:
            return True
    except:
        pass
    ts = family_types(fm)
    if ts:
        try:
            fm.CurrentType = ts[0]
            return True
        except:
            pass
    try:
        fm.NewType("Default")
        return True
    except:
        return False

def find_family_parameter(fm, name):
    n = text(name).lower()
    for p in fm.Parameters:
        try:
            if text(p.Definition.Name).lower() == n:
                return p
        except:
            pass
    return None

def family_parameter_guid(p):
    try:
        return str(p.GUID).lower()
    except:
        return ""

def raw_family_value(ft, p):
    try:
        st = p.StorageType
        if st == StorageType.String:
            return ("String", ft.AsString(p))
        if st == StorageType.Integer:
            return ("Integer", ft.AsInteger(p))
        if st == StorageType.Double:
            return ("Double", ft.AsDouble(p))
        if st == StorageType.ElementId:
            return ("ElementId", ft.AsElementId(p))
    except:
        pass
    return (None, None)

def backup_family_values(fm, p):
    out = {}
    for ft in family_types(fm):
        out[ft.Name] = raw_family_value(ft, p)
    return out

def restore_family_values(fm, p, values):
    restored = 0
    types_by_name = dict((ft.Name, ft) for ft in family_types(fm))
    old_current = fm.CurrentType
    for tname, pair in values.items():
        if tname not in types_by_name:
            continue
        kind, value = pair
        if kind is None or value is None:
            continue
        try:
            fm.CurrentType = types_by_name[tname]
            if kind == "String":
                fm.Set(p, value)
            elif kind == "Integer":
                fm.Set(p, int(value))
            elif kind == "Double":
                fm.Set(p, float(value))
            elif kind == "ElementId":
                fm.Set(p, value)
            restored += 1
        except:
            pass
    try:
        fm.CurrentType = old_current
    except:
        pass
    return restored

def set_family_default(fm, p, value):
    s = text(value)
    if s == "":
        return 0
    old_current = fm.CurrentType
    count = 0
    for ft in family_types(fm):
        try:
            fm.CurrentType = ft
            # Only populate empty values.
            kind, old = raw_family_value(ft, p)
            empty = (old is None) or (kind == "String" and text(old) == "")
            if not empty:
                continue
            if p.StorageType == StorageType.String:
                fm.Set(p, s); count += 1
            elif p.StorageType == StorageType.Integer:
                k = norm(s)
                if k in ("true","yes","y"):
                    fm.Set(p,1); count += 1
                elif k in ("false","no","n"):
                    fm.Set(p,0); count += 1
                else:
                    fm.Set(p,int(float(s))); count += 1
            elif p.StorageType == StorageType.Double:
                val = float(s.replace(",",""))
                try:
                    spec = p.Definition.GetDataType()
                    fmt = doc.GetUnits().GetFormatOptions(spec)
                    val = UnitUtils.ConvertToInternalUnits(val, fmt.GetUnitTypeId())
                except:
                    pass
                fm.Set(p,val); count += 1
        except:
            pass
    try:
        fm.CurrentType = old_current
    except:
        pass
    return count

def repair_family_parameter(fm, p, ext_def, desired_group):
    backup = backup_family_values(fm, p)
    desired_guid = str(ext_def.GUID).lower()
    existing_guid = family_parameter_guid(p)
    wrong_guid = (existing_guid != desired_guid)
    wrong_instance = False
    try:
        wrong_instance = bool(p.IsInstance)
    except:
        pass
    wrong_group = True
    try:
        wrong_group = p.Definition.GetGroupTypeId() != desired_group
    except:
        pass

    # Same shared parameter: make it Type and/or move group without deleting it.
    if not wrong_guid:
        try:
            if wrong_instance:
                fm.MakeType(p)
            try:
                if p.Definition.GetGroupTypeId() != desired_group:
                    p.Definition.SetGroupTypeId(desired_group)
            except:
                # If direct group change fails, ReplaceParameter is the safe API route.
                p = fm.ReplaceParameter(p, ext_def, desired_group, False)
            restore_family_values(fm, p, backup)
            return p, "repaired in place"
        except Exception as ex:
            return None, "in-place repair failed: {}".format(ex)

    # Wrong GUID or non-shared parameter: ReplaceParameter preserves formulas/labels when possible.
    replace_error = None
    sub = SubTransaction(doc)
    sub.Start()
    try:
        newp = fm.ReplaceParameter(p, ext_def, desired_group, False)
        restore_family_values(fm, newp, backup)
        sub.Commit()
        return newp, "replaced with correct shared GUID"
    except Exception as ex:
        replace_error = ex
        try:
            sub.RollBack()
        except:
            pass

    # Some Revit versions/family states may reject shared->shared ReplaceParameter.
    # Safe fallback: remove/add inside a SubTransaction so failure rolls back completely.
    formula = None
    try:
        formula = p.Formula
    except:
        pass
    sub2 = SubTransaction(doc)
    sub2.Start()
    try:
        fm.RemoveParameter(p)
        newp = fm.AddParameter(ext_def, desired_group, False)
        if formula:
            try:
                fm.SetFormula(newp, formula)
            except:
                pass
        restore_family_values(fm, newp, backup)
        sub2.Commit()
        return newp, "remove/add fallback to correct shared GUID"
    except Exception as ex2:
        try:
            sub2.RollBack()
        except:
            pass
        return None, "ReplaceParameter failed: {}; fallback failed: {}".format(replace_error, ex2)

if not RUN:
    OUT = ["READY | Step 1 Family Sync | Set Run=True."]
elif not doc.IsFamilyDocument:
    OUT = ["FAILED | Step 1 must run in an open Revit family (.rfa)."]
else:
    old_shared = None
    tx_open = False
    try:
        rows = read_csv_dict(MASTER_CSV)
        sf, old_shared = open_shared_parameter_file(SHARED_TXT)
        fm = doc.FamilyManager
        if not ensure_type(fm):
            raise Exception("Family has no usable type.")
        fam_cat = family_category_name()

        expected = {}
        for r in rows:
            if norm(r.get("Scope")) != "familytype":
                continue
            cats = split_categories(r.get("Categories"))
            if not category_matches(cats, fam_cat):
                continue
            expected[text(r.get("Parameter")).lower()] = r

        TransactionManager.Instance.EnsureInTransaction(doc)
        tx_open = True

        added = repaired = kept = removed = failed = defaults = 0

        for key, r in expected.items():
            name = text(r.get("Parameter"))
            gid = group_type_id(r.get("RevitUIGroup"))
            ext = find_external_definition(sf, name)
            if gid is None:
                failed += 1
                log.append("FAIL {} | unsupported UI group '{}'".format(name, r.get("RevitUIGroup")))
                continue
            if ext is None:
                failed += 1
                log.append("FAIL {} | not found in shared parameter TXT".format(name))
                continue

            p = find_family_parameter(fm, name)
            if p is None:
                try:
                    if fm.IsUserAssignableParameterGroup(gid) is False:
                        raise Exception("UI group is not assignable in this family.")
                except AttributeError:
                    pass
                try:
                    p = fm.AddParameter(ext, gid, False)  # TYPE
                    added += 1
                    log.append("ADD {} | TYPE | {}".format(name, r.get("RevitUIGroup")))
                except Exception as ex:
                    failed += 1
                    log.append("FAIL ADD {} | {}".format(name, ex))
                    continue
            else:
                desired_guid = str(ext.GUID).lower()
                current_guid = family_parameter_guid(p)
                wrong_guid = current_guid != desired_guid
                try:
                    wrong_instance = bool(p.IsInstance)
                except:
                    wrong_instance = False
                try:
                    wrong_group = p.Definition.GetGroupTypeId() != gid
                except:
                    wrong_group = True

                if wrong_guid or wrong_instance or wrong_group:
                    if REPAIR:
                        p2, msg = repair_family_parameter(fm, p, ext, gid)
                        if p2 is None:
                            failed += 1
                            log.append("FAIL REPAIR {} | {}".format(name, msg))
                            continue
                        p = p2
                        repaired += 1
                        log.append("REPAIR {} | {}".format(name, msg))
                    else:
                        failed += 1
                        log.append("NEEDS REPAIR {} | GUID={}, Instance={}, Group={}".format(
                            name, wrong_guid, wrong_instance, wrong_group))
                        continue
                else:
                    kept += 1

            defaults += set_family_default(fm, p, r.get("DefaultValue"))

        if REMOVE_STALE:
            for p in list(fm.Parameters):
                try:
                    name = text(p.Definition.Name)
                except:
                    continue
                if not name.startswith("TD_"):
                    continue
                if name.lower() in expected:
                    continue
                try:
                    fm.RemoveParameter(p)
                    removed += 1
                    log.append("REMOVE STALE {}".format(name))
                except Exception as ex:
                    failed += 1
                    log.append("FAIL REMOVE {} | {}".format(name, ex))

        TransactionManager.Instance.TransactionTaskDone()
        tx_open = False
        log.insert(0,
            "SUMMARY | Category={} | Expected={} | Added={} | Repaired={} | Kept={} | "
            "Removed={} | DefaultsFilled={} | Failed={}".format(
                fam_cat, len(expected), added, repaired, kept, removed, defaults, failed
            )
        )
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
