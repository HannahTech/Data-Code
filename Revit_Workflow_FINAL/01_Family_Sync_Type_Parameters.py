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

# STEP 1 — FAMILY TYPE PARAMETER SYNC
# IN[0] = TD_Master_Parameters.csv
# IN[1] = ORIGINAL TD shared parameter TXT
# IN[2] = Run
# IN[3] = PreviewOnly (recommended True first)
# IN[4] = RemoveStaleTDParameters
# IN[5] = MigrateWrongGUID

MASTER_CSV = text(IN[0]) if len(IN) > 0 else ""
SHARED_TXT = text(IN[1]) if len(IN) > 1 else ""
RUN = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
PREVIEW = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else True
REMOVE_STALE = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True
MIGRATE_WRONG_GUID = bool(IN[5]) if len(IN) > 5 and IN[5] is not None else False

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

def family_parameters(fm):
    try:
        return list(fm.GetParameters())
    except:
        return list(fm.Parameters)

def family_types(fm):
    result = []
    it = fm.Types.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        result.append(it.Current)
    return result

def ensure_type(fm):
    try:
        if fm.CurrentType is not None:
            return True
    except:
        pass
    ts = family_types(fm)
    if ts:
        fm.CurrentType = ts[0]
        return True
    try:
        fm.NewType("Default")
        return True
    except:
        return False

def find_family_parameter(fm, name):
    target = text(name).lower()
    for p in family_parameters(fm):
        try:
            if text(p.Definition.Name).lower() == target:
                return p
        except:
            pass
    return None

def family_parameter_guid(p):
    try:
        return str(p.GUID).lower()
    except:
        return ""

def family_value(ft, p):
    try:
        if p.StorageType == StorageType.String:
            v = ft.AsString(p)
            return ("String", v) if text(v) else None
        if p.StorageType == StorageType.Integer:
            return ("Integer", ft.AsInteger(p))
        if p.StorageType == StorageType.Double:
            return ("Double", ft.AsDouble(p))
        if p.StorageType == StorageType.ElementId:
            return ("ElementId", ft.AsElementId(p))
    except:
        return None
    return None

def backup_all_td_family_values(fm, master_path):
    out_dir = os.path.join(backup_root(master_path), "Families")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(
        out_dir,
        "{}__{}__FamilyTDBackup.csv".format(safe_filename(doc.Title), timestamp())
    )
    rows = []
    original = fm.CurrentType
    for ft in family_types(fm):
        try:
            fm.CurrentType = ft
        except:
            pass
        for p in family_parameters(fm):
            try:
                name = text(p.Definition.Name)
            except:
                continue
            if not name.startswith("TD_"):
                continue
            pair = family_value(ft, p)
            if pair is None:
                continue
            kind, raw = pair
            rows.append([
                text(doc.Title), ft.Name, name, family_parameter_guid(p),
                "Instance" if bool(p.IsInstance) else "Type",
                kind, "" if raw is None else str(raw)
            ])
    try:
        fm.CurrentType = original
    except:
        pass
    write_csv(path,
        ["Family","FamilyType","Parameter","GUID","Binding","StorageType","RawValue"],
        rows
    )
    return path

def backup_one_parameter(fm, p):
    data = {}
    for ft in family_types(fm):
        data[ft.Name] = family_value(ft, p)
    return data

def restore_one_parameter(fm, p, data):
    by_name = dict((ft.Name, ft) for ft in family_types(fm))
    old = fm.CurrentType
    restored = 0
    for tname, pair in data.items():
        if pair is None or tname not in by_name:
            continue
        try:
            fm.CurrentType = by_name[tname]
            kind, value = pair
            if kind == "String":
                fm.Set(p, value if value is not None else "")
            elif kind == "Integer":
                fm.Set(p, int(value))
            elif kind == "Double":
                fm.Set(p, float(value))
            elif kind == "ElementId":
                fm.Set(p, value)
            else:
                continue
            restored += 1
        except:
            pass
    try:
        fm.CurrentType = old
    except:
        pass
    return restored

def current_group(p):
    try:
        return p.Definition.GetGroupTypeId()
    except:
        return None

if not RUN:
    OUT = ["READY | Step 1 | Set Run=True. Use PreviewOnly=True first."]
elif not doc.IsFamilyDocument:
    OUT = ["FAILED | Step 1 must run in an open Revit FAMILY."]
else:
    old_shared = None
    tx_open = False
    try:
        master = read_csv_dict(MASTER_CSV)
        sf, old_shared = open_shared_parameter_file(SHARED_TXT)
        fm = doc.FamilyManager
        if not ensure_type(fm):
            raise Exception("Family has no usable family type.")
        fam_cat = family_category_name()

        expected = {}
        for r in master:
            if norm(r.get("Scope")) != "familytype":
                continue
            if not category_matches(split_categories(r.get("Categories")), fam_cat):
                continue
            expected[text(r.get("Parameter")).lower()] = r

        actions = []
        failures = 0

        for key, r in expected.items():
            name = text(r.get("Parameter"))
            gid = group_type_id(r.get("RevitUIGroup"))
            ext = find_external_definition(sf, name)
            if gid is None:
                failures += 1
                actions.append(("FAIL", name, "Unsupported UI group '{}'".format(r.get("RevitUIGroup"))))
                continue
            if ext is None:
                failures += 1
                actions.append(("FAIL", name, "Missing from selected shared parameter TXT"))
                continue

            p = find_family_parameter(fm, name)
            if p is None:
                actions.append(("ADD", name, "TYPE / {}".format(r.get("RevitUIGroup"))))
                continue

            current_guid = family_parameter_guid(p)
            desired_guid = str(ext.GUID).lower()
            wrong_guid = current_guid != desired_guid
            try:
                wrong_binding = bool(p.IsInstance)
            except:
                wrong_binding = False
            wrong_group = current_group(p) != gid

            if wrong_guid:
                if MIGRATE_WRONG_GUID:
                    actions.append(("REPLACE_GUID", name, "{} -> {}".format(current_guid or "non-shared", desired_guid)))
                else:
                    failures += 1
                    actions.append(("GUID_CONFLICT", name,
                        "Existing={} | SharedTXT={}. No change unless MigrateWrongGUID=True.".format(
                            current_guid or "non-shared", desired_guid)))
                    continue
            if wrong_binding:
                actions.append(("MAKE_TYPE", name, "Instance -> Type"))
            if wrong_group:
                actions.append(("MOVE_GROUP", name, "{}".format(r.get("RevitUIGroup"))))
            if not wrong_guid and not wrong_binding and not wrong_group:
                actions.append(("OK", name, "Already matches"))

        stale = []
        if REMOVE_STALE:
            for p in family_parameters(fm):
                try:
                    n = text(p.Definition.Name)
                except:
                    continue
                if n.startswith("TD_") and n.lower() not in expected:
                    stale.append(p)
                    actions.append(("REMOVE_STALE", n, "Not listed as FamilyType for '{}'".format(fam_cat)))

        if PREVIEW:
            log.append("PREVIEW ONLY — no Revit changes made.")
        else:
            # Back up all current TD values before any mutation.
            backup_path = backup_all_td_family_values(fm, MASTER_CSV)
            log.append("BACKUP | {}".format(backup_path))

            TransactionManager.Instance.EnsureInTransaction(doc)
            tx_open = True

            for key, r in expected.items():
                name = text(r.get("Parameter"))
                gid = group_type_id(r.get("RevitUIGroup"))
                ext = find_external_definition(sf, name)
                if gid is None or ext is None:
                    continue

                p = find_family_parameter(fm, name)
                if p is None:
                    try:
                        try:
                            assignable = fm.IsUserAssignableParameterGroup(gid)
                            if assignable is False:
                                raise Exception("UI group not assignable in this family.")
                        except AttributeError:
                            pass
                        fm.AddParameter(ext, gid, False)
                    except Exception as ex:
                        failures += 1
                        log.append("FAIL ADD {} | {}".format(name, ex))
                    continue

                backup = backup_one_parameter(fm, p)
                current_guid = family_parameter_guid(p)
                desired_guid = str(ext.GUID).lower()

                if current_guid != desired_guid:
                    if not MIGRATE_WRONG_GUID:
                        continue
                    try:
                        p = fm.ReplaceParameter(p, ext, gid, False)
                        restore_one_parameter(fm, p, backup)
                    except Exception as ex:
                        failures += 1
                        log.append("FAIL GUID MIGRATION {} | {}".format(name, ex))
                        continue
                else:
                    try:
                        if bool(p.IsInstance):
                            fm.MakeType(p)
                    except Exception as ex:
                        failures += 1
                        log.append("FAIL MAKE TYPE {} | {}".format(name, ex))
                    try:
                        if p.Definition.GetGroupTypeId() != gid:
                            p.Definition.SetGroupTypeId(gid)
                    except Exception as ex:
                        failures += 1
                        log.append("FAIL MOVE GROUP {} | {}".format(name, ex))
                    restore_one_parameter(fm, p, backup)

            if REMOVE_STALE:
                for p in stale:
                    try:
                        fm.RemoveParameter(p)
                    except Exception as ex:
                        failures += 1
                        try:
                            n = p.Definition.Name
                        except:
                            n = "?"
                        log.append("FAIL REMOVE {} | {}".format(n, ex))

            TransactionManager.Instance.TransactionTaskDone()
            tx_open = False

        counts = {}
        for kind, name, detail in actions:
            counts[kind] = counts.get(kind, 0) + 1
            if kind != "OK":
                log.append("{} | {} | {}".format(kind, name, detail))

        log.insert(0,
            "SUMMARY | Family={} | Category={} | Expected={} | Preview={} | Failures={} | Actions={}".format(
                doc.Title, fam_cat, len(expected), PREVIEW, failures,
                ", ".join("{}={}".format(k,v) for k,v in sorted(counts.items()))
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
