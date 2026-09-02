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
            try:
                p.SetValueString(s)
                return True
            except:
                pass
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


# STEP 3 — PROJECT INSTANCE + PROJECT INFORMATION PARAMETER SYNC
# IN[0] = TD_Master_Parameters.csv
# IN[1] = ORIGINAL TD shared parameter TXT
# IN[2] = Run
# IN[3] = PreviewOnly (recommended True first)
# IN[4] = RemoveStaleTDProjectBindings
# IN[5] = MigrateWrongGUID
# IN[6] = ApplyDefaultsToBlankValues

MASTER_CSV = text(IN[0]) if len(IN) > 0 else ""
SHARED_TXT = text(IN[1]) if len(IN) > 1 else ""
RUN = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
PREVIEW = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else True
REMOVE_STALE = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True
MIGRATE_WRONG_GUID = bool(IN[5]) if len(IN) > 5 and IN[5] is not None else False
APPLY_DEFAULTS = bool(IN[6]) if len(IN) > 6 and IN[6] is not None else True

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
    "projectinformation": BuiltInCategory.OST_ProjectInformation,
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

def desired_category_names(row):
    if norm(row.get("Scope")) == "projectinformation":
        return ["Project Information"]
    return split_categories(row.get("Categories"))

def make_category_set(category_names):
    category_set = app.Create.NewCategorySet()
    ids = set()
    resolved_names = []
    for name in category_names:
        c = category_from_name(name)
        if c is None:
            log.append("CATEGORY NOT FOUND | {}".format(name))
            continue
        try:
            if not c.AllowsBoundParameters:
                log.append("CATEGORY DOES NOT ALLOW BOUND PARAMETERS | {}".format(name))
                continue
        except:
            pass
        category_set.Insert(c)
        ids.add(str(eid_value(c.Id)))
        resolved_names.append(c.Name)
    return category_set, ids, resolved_names

def binding_category_info(binding):
    ids = set()
    names = []
    try:
        for c in binding.Categories:
            ids.add(str(eid_value(c.Id)))
            names.append(c.Name)
    except:
        pass
    return ids, names

def definition_guid(definition):
    # BindingMap keys are normally InternalDefinition objects.
    # For shared parameters, the corresponding element is a SharedParameterElement.
    try:
        pe = doc.GetElement(definition.Id)
        if isinstance(pe, SharedParameterElement):
            return str(pe.GuidValue).lower()
    except:
        pass
    return ""

def binding_snapshot():
    result = []
    it = doc.ParameterBindings.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        d = it.Key
        b = it.Current
        try:
            result.append({
                "definition": d,
                "binding": b,
                "name": text(d.Name),
                "guid": definition_guid(d),
            })
        except:
            pass
    return result

def is_instance_binding(binding):
    return isinstance(binding, InstanceBinding)

def binding_kind(binding):
    if isinstance(binding, InstanceBinding):
        return "Instance"
    if isinstance(binding, TypeBinding):
        return "Type"
    return type(binding).__name__

def collect_instances(category_names):
    found = {}

    for name in category_names:
        if norm(name) == "projectinformation":
            try:
                pi = doc.ProjectInformation
                found[pi.UniqueId] = pi
            except:
                pass
            continue

        c = category_from_name(name)
        if c is None:
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

def collect_types(category_names):
    # Used for the external backup: include loaded types even when they currently
    # have no placed instance.
    found = {}
    for name in category_names:
        if norm(name) == "projectinformation":
            continue
        c = category_from_name(name)
        if c is None:
            continue
        try:
            collector = (
                FilteredElementCollector(doc)
                .WherePasses(ElementCategoryFilter(c.Id))
                .WhereElementIsElementType()
            )
            for t in collector:
                found[t.UniqueId] = t
        except:
            pass
    return list(found.values())

def parameter_by_definition(owner, definition):
    if owner is None:
        return None
    try:
        return owner.get_Parameter(definition)
    except:
        pass
    try:
        for p in owner.GetParameters(definition.Name):
            try:
                if p.Id == definition.Id:
                    return p
            except:
                pass
    except:
        pass
    return None

def parameter_by_guid(owner, guid_value):
    if owner is None:
        return None
    try:
        return owner.get_Parameter(guid_value)
    except:
        return None

def capture_values_for_target(definition, binding, target_categories):
    """
    Return owner UniqueId -> raw value.
    If the old binding is TYPE but the target is INSTANCE, copy the type value
    to each placed instance of the desired categories.
    """
    data = {}

    if isinstance(binding, TypeBinding):
        for e in collect_instances(target_categories):
            try:
                tid = e.GetTypeId()
                if tid is None or tid == ElementId.InvalidElementId:
                    continue
                et = doc.GetElement(tid)
                p = parameter_by_definition(et, definition) if et else None
                pair = raw_parameter_value(p)
                if pair is not None:
                    data[e.UniqueId] = pair
            except:
                pass
    else:
        for e in collect_instances(target_categories):
            p = parameter_by_definition(e, definition)
            pair = raw_parameter_value(p)
            if pair is not None:
                data[e.UniqueId] = pair

    return data

def restore_value_maps(guid_value, value_maps, only_if_blank=True):
    restored = 0
    conflicts_kept = 0

    for value_map in value_maps:
        for uid, pair in value_map.items():
            try:
                owner = doc.GetElement(uid)
            except:
                owner = None

            if owner is None:
                # ProjectInformation is still retrievable by UniqueId in supported versions,
                # but keep a fallback just in case.
                try:
                    if doc.ProjectInformation.UniqueId == uid:
                        owner = doc.ProjectInformation
                except:
                    pass

            if owner is None:
                continue

            p = parameter_by_guid(owner, guid_value)
            if p is None:
                continue

            if only_if_blank and not is_blank_element_parameter(p):
                conflicts_kept += 1
                continue

            if set_raw_parameter_value(p, pair):
                restored += 1

    return restored, conflicts_kept

def backup_all_project_td_values(master_path):
    out_dir = os.path.join(backup_root(master_path), "Projects")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    path = os.path.join(
        out_dir,
        "{}__{}__ProjectTDBindingBackup.csv".format(safe_filename(doc.Title), timestamp())
    )

    rows = []

    for item in binding_snapshot():
        name = item["name"]
        if not name.startswith("TD_"):
            continue

        d = item["definition"]
        b = item["binding"]
        _, category_names = binding_category_info(b)

        owners = collect_instances(category_names) if isinstance(b, InstanceBinding) else collect_types(category_names)

        for owner in owners:
            p = parameter_by_definition(owner, d)
            pair = raw_parameter_value(p)
            if pair is None:
                continue

            kind, raw = pair
            try:
                cat_name = owner.Category.Name
            except:
                cat_name = "Project Information" if owner.Id == doc.ProjectInformation.Id else ""

            rows.append([
                text(doc.Title),
                binding_kind(b),
                ", ".join(category_names),
                name,
                item["guid"],
                "Type" if isinstance(b, TypeBinding) else "Instance",
                str(eid_value(owner.Id)),
                text(owner.UniqueId),
                cat_name,
                kind,
                "" if raw is None else str(raw),
            ])

    write_csv(
        path,
        [
            "Project","BindingKind","BindingCategories","Parameter","GUID","ValueOwner",
            "OwnerElementId","OwnerUniqueId","OwnerCategory","StorageType","RawValue"
        ],
        rows
    )
    return path

def insert_expected_binding(ext_definition, row):
    category_set, ids, resolved = make_category_set(desired_category_names(row))
    if not ids:
        return False, "No valid target categories."

    gid = group_type_id(row.get("RevitUIGroup"))
    if gid is None:
        return False, "Unsupported Revit UI group '{}'".format(row.get("RevitUIGroup"))

    binding = app.Create.NewInstanceBinding(category_set)
    try:
        ok = doc.ParameterBindings.Insert(ext_definition, binding, gid)
        return bool(ok), "" if ok else "BindingMap.Insert returned False."
    except Exception as ex:
        return False, str(ex)

def repair_same_guid(definition, old_binding, ext_definition, row):
    target_categories = desired_category_names(row)
    old_values = capture_values_for_target(definition, old_binding, target_categories)

    category_set, ids, resolved = make_category_set(target_categories)
    if not ids:
        return False, 0, 0, "No valid target categories."

    gid = group_type_id(row.get("RevitUIGroup"))
    if gid is None:
        return False, 0, 0, "Unsupported Revit UI group."

    new_binding = app.Create.NewInstanceBinding(category_set)

    sub = SubTransaction(doc)
    sub.Start()
    try:
        ok = doc.ParameterBindings.ReInsert(definition, new_binding, gid)
        if not ok:
            raise Exception("BindingMap.ReInsert returned False.")

        restored, kept = restore_value_maps(
            ext_definition.GUID, [old_values], only_if_blank=True
        )
        sub.Commit()
        return True, restored, kept, ""
    except Exception as ex:
        try:
            sub.RollBack()
        except:
            pass
        return False, 0, 0, str(ex)

def migrate_wrong_guid_entries(wrong_entries, ext_definition, row, desired_exists=False):
    target_categories = desired_category_names(row)
    value_maps = []

    for item in wrong_entries:
        value_maps.append(
            capture_values_for_target(item["definition"], item["binding"], target_categories)
        )

    sub = SubTransaction(doc)
    sub.Start()
    try:
        for item in wrong_entries:
            if not doc.ParameterBindings.Remove(item["definition"]):
                raise Exception(
                    "Could not remove wrong-GUID binding '{}'.".format(item["name"])
                )

        if not desired_exists:
            ok, err = insert_expected_binding(ext_definition, row)
            if not ok:
                raise Exception(err)

        restored, kept = restore_value_maps(
            ext_definition.GUID, value_maps, only_if_blank=True
        )
        sub.Commit()
        return True, restored, kept, ""
    except Exception as ex:
        try:
            sub.RollBack()
        except:
            pass
        return False, 0, 0, str(ex)

def apply_default_to_row(ext_definition, row):
    default = text(row.get("DefaultValue"))
    if default == "":
        return 0

    count = 0
    for owner in collect_instances(desired_category_names(row)):
        p = parameter_by_guid(owner, ext_definition.GUID)
        if p is not None and is_blank_element_parameter(p):
            if set_display_value(p, default):
                count += 1
    return count

if not RUN:
    OUT = ["READY | Step 3 | Set Run=True. Use PreviewOnly=True first."]
elif doc.IsFamilyDocument:
    OUT = ["FAILED | Step 3 must run in a Revit PROJECT."]
else:
    old_shared = None
    tx_open = False

    try:
        master = read_csv_dict(MASTER_CSV)
        expected_rows = [
            r for r in master
            if norm(r.get("Scope")) in ("projectinstance", "projectinformation")
        ]
        expected_names = set(text(r.get("Parameter")).lower() for r in expected_rows)

        sf, old_shared = open_shared_parameter_file(SHARED_TXT)
        snapshot = binding_snapshot()

        plans = []
        failures = 0
        ext_by_name = {}

        for row in expected_rows:
            name = text(row.get("Parameter"))
            ext = find_external_definition(sf, name)
            if ext is None:
                failures += 1
                plans.append(("FAIL", name, "Missing from selected shared parameter TXT"))
                continue

            ext_by_name[name.lower()] = ext
            desired_guid = str(ext.GUID).lower()
            target_set, target_ids, resolved_names = make_category_set(desired_category_names(row))
            gid = group_type_id(row.get("RevitUIGroup"))

            if not target_ids:
                failures += 1
                plans.append(("FAIL", name, "No valid target categories"))
                continue
            if gid is None:
                failures += 1
                plans.append(("FAIL", name, "Unsupported UI group"))
                continue

            same_name = [
                item for item in snapshot
                if item["name"].lower() == name.lower()
            ]
            correct = [
                item for item in same_name
                if item["guid"] == desired_guid
            ]
            wrong = [
                item for item in same_name
                if item["guid"] != desired_guid
            ]

            if not correct:
                if wrong:
                    if MIGRATE_WRONG_GUID:
                        plans.append((
                            "MIGRATE_GUID", name,
                            "{} wrong same-name binding(s) -> GUID {}".format(
                                len(wrong), desired_guid
                            )
                        ))
                    else:
                        failures += 1
                        plans.append((
                            "GUID_CONFLICT", name,
                            "No correct GUID binding. Selected shared TXT GUID={}. Set MigrateWrongGUID=True to migrate.".format(
                                desired_guid
                            )
                        ))
                else:
                    plans.append(("ADD", name, "INSTANCE | {}".format(", ".join(resolved_names))))
                continue

            # There should normally be only one correct binding.
            c = correct[0]
            current_ids, current_names = binding_category_info(c["binding"])
            binding_ok = is_instance_binding(c["binding"])
            categories_ok = current_ids == target_ids
            try:
                group_ok = c["definition"].GetGroupTypeId() == gid
            except:
                group_ok = False

            if not (binding_ok and categories_ok and group_ok):
                plans.append((
                    "REPAIR", name,
                    "Binding={} | Categories={} | Group={}".format(
                        "OK" if binding_ok else "Type→Instance",
                        "OK" if categories_ok else "{}→{}".format(
                            ", ".join(current_names), ", ".join(resolved_names)
                        ),
                        "OK" if group_ok else "Move to {}".format(row.get("RevitUIGroup"))
                    )
                ))
            else:
                plans.append(("OK", name, "Binding/GUID/categories/group match"))

            if wrong:
                if MIGRATE_WRONG_GUID:
                    plans.append((
                        "MERGE_DUPLICATE_GUIDS", name,
                        "{} additional wrong-GUID same-name binding(s)".format(len(wrong))
                    ))
                else:
                    failures += 1
                    plans.append((
                        "GUID_CONFLICT", name,
                        "{} additional wrong-GUID same-name binding(s) left untouched".format(len(wrong))
                    ))

        stale = [
            item for item in snapshot
            if item["name"].startswith("TD_")
            and item["name"].lower() not in expected_names
        ]
        if REMOVE_STALE:
            for item in stale:
                plans.append(("REMOVE_STALE", item["name"], "Not ProjectInstance/ProjectInformation in master CSV"))

        if PREVIEW:
            log.append("PREVIEW ONLY — no Revit changes made.")
        else:
            backup_path = backup_all_project_td_values(MASTER_CSV)
            log.append("BACKUP | {}".format(backup_path))

            TransactionManager.Instance.EnsureInTransaction(doc)
            tx_open = True

            added = repaired = migrated = merged = removed = defaults = restored_total = kept_conflicts = 0

            # Re-snapshot as operations progress.
            for row in expected_rows:
                name = text(row.get("Parameter"))
                ext = find_external_definition(sf, name)
                if ext is None:
                    continue

                desired_guid = str(ext.GUID).lower()
                current_snapshot = binding_snapshot()
                same_name = [
                    item for item in current_snapshot
                    if item["name"].lower() == name.lower()
                ]
                correct = [item for item in same_name if item["guid"] == desired_guid]
                wrong = [item for item in same_name if item["guid"] != desired_guid]

                if not correct:
                    if wrong:
                        if not MIGRATE_WRONG_GUID:
                            continue
                        ok, restored, kept, err = migrate_wrong_guid_entries(
                            wrong, ext, row, desired_exists=False
                        )
                        if ok:
                            migrated += 1
                            restored_total += restored
                            kept_conflicts += kept
                        else:
                            failures += 1
                            log.append("FAIL GUID MIGRATION {} | {}".format(name, err))
                            continue
                    else:
                        ok, err = insert_expected_binding(ext, row)
                        if ok:
                            added += 1
                        else:
                            failures += 1
                            log.append("FAIL ADD {} | {}".format(name, err))
                            continue
                else:
                    c = correct[0]
                    target_set, target_ids, resolved_names = make_category_set(desired_category_names(row))
                    current_ids, current_names = binding_category_info(c["binding"])
                    gid = group_type_id(row.get("RevitUIGroup"))
                    binding_ok = is_instance_binding(c["binding"])
                    categories_ok = current_ids == target_ids
                    try:
                        group_ok = c["definition"].GetGroupTypeId() == gid
                    except:
                        group_ok = False

                    if not (binding_ok and categories_ok and group_ok):
                        ok, restored, kept, err = repair_same_guid(
                            c["definition"], c["binding"], ext, row
                        )
                        if ok:
                            repaired += 1
                            restored_total += restored
                            kept_conflicts += kept
                        else:
                            failures += 1
                            log.append("FAIL REPAIR {} | {}".format(name, err))
                            continue

                    # Refresh and merge/remove any wrong-GUID duplicates after desired binding is secure.
                    current_snapshot = binding_snapshot()
                    same_name = [
                        item for item in current_snapshot
                        if item["name"].lower() == name.lower()
                    ]
                    wrong = [item for item in same_name if item["guid"] != desired_guid]

                    if wrong and MIGRATE_WRONG_GUID:
                        ok, restored, kept, err = migrate_wrong_guid_entries(
                            wrong, ext, row, desired_exists=True
                        )
                        if ok:
                            merged += len(wrong)
                            restored_total += restored
                            kept_conflicts += kept
                        else:
                            failures += 1
                            log.append("FAIL MERGE DUPLICATE {} | {}".format(name, err))

                if APPLY_DEFAULTS:
                    defaults += apply_default_to_row(ext, row)

            if REMOVE_STALE:
                for item in [
                    x for x in binding_snapshot()
                    if x["name"].startswith("TD_")
                    and x["name"].lower() not in expected_names
                ]:
                    try:
                        if doc.ParameterBindings.Remove(item["definition"]):
                            removed += 1
                        else:
                            failures += 1
                            log.append("FAIL REMOVE STALE {} | BindingMap.Remove returned False".format(item["name"]))
                    except Exception as ex:
                        failures += 1
                        log.append("FAIL REMOVE STALE {} | {}".format(item["name"], ex))

            TransactionManager.Instance.TransactionTaskDone()
            tx_open = False

            log.append(
                "APPLY RESULT | Added={} | Repaired={} | GUIDMigrated={} | DuplicateBindingsMerged={} | "
                "StaleRemoved={} | ValuesRestored={} | ExistingConflictsKept={} | DefaultsFilled={}".format(
                    added, repaired, migrated, merged, removed,
                    restored_total, kept_conflicts, defaults
                )
            )

        for kind, name, detail in plans:
            if kind != "OK":
                log.append("{} | {} | {}".format(kind, name, detail))

        counts = {}
        for kind, name, detail in plans:
            counts[kind] = counts.get(kind, 0) + 1

        log.insert(0,
            "SUMMARY | Project={} | Expected={} | Preview={} | Failures/Conflicts={} | {}".format(
                doc.Title, len(expected_rows), PREVIEW, failures,
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
