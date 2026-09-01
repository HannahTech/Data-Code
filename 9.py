import sys
import clr
import re
import os

# Import Revit API
clr.AddReference("RevitAPI")
clr.AddReference("RevitServices")
import Autodesk
from Autodesk.Revit.DB import *
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

doc = DocumentManager.Instance.CurrentDBDocument
app = doc.Application

# Input handling
csv_path = str(IN[0]) if len(IN) > 0 and IN[0] else ""
shared_txt_path = str(IN[1]) if len(IN) > 1 and IN[1] else ""
run_script = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
add_all_parameters = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else False
remove_obsolete = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True
force_repair = bool(IN[5]) if len(IN) > 5 and IN[5] is not None else False

results = []

def to_text(value):
    if value is None:
        return ""
    return str(value).strip()

def is_blank(value):
    return value is None or str(value).strip() == ""

def clean_name(value):
    if value is None:
        return ""
    value = str(value).strip()
    value = value.replace("\\", "_")
    value = re.sub(r"[^a-zA-Z0-9_]", "", value)
    return value.strip()

def normalize(value):
    if value is None:
        return ""
    value = str(value).strip()
    value = value.replace("\\", "_")
    return re.sub(r"[^a-zA-Z0-9_]", "", value).lower()

def parse_boolean(value):
    return normalize(value) in ["true", "yes", "y", "1"]

def safe_int(value):
    try:
        return int(float(str(value).strip()))
    except:
        return None

def safe_float(value):
    try:
        return float(str(value).strip())
    except:
        return None

def split_joined_values(value):
    if is_blank(value):
        return []
    raw = str(value).strip()
    if re.search(r"\s+-\s+", raw):
        parts = re.split(r"\s+-\s+", raw)
    else:
        parts = [raw]
    output = []
    for part in parts:
        part = str(part).strip()
        if part:
            output.append(part)
    return output

def deduplicate_joined_value(value):
    output = []
    seen = set()
    for part in split_joined_values(value):
        key = part.lower()
        if key not in seen:
            seen.add(key)
            output.append(part)
    return " - ".join(output)

def merge_unique_values(old_value, new_value):
    combined = []
    if not is_blank(old_value):
        combined.extend(split_joined_values(old_value))
    if not is_blank(new_value):
        combined.extend(split_joined_values(new_value))
    output = []
    seen = set()
    for part in combined:
        key = part.lower()
        if key not in seen:
            seen.add(key)
            output.append(part)
    return " - ".join(output)

def read_csv(path):
    rows = []
    try:
        try:
            file_object = open(path, "r", encoding="utf-8-sig", errors="ignore")
        except:
            file_object = open(path, "r")
        with file_object:
            import csv
            reader = csv.reader(file_object)
            for row in reader:
                if row:
                    rows.append(row)
    except Exception as ex:
        results.append("FAILED: Could not read CSV: {}".format(str(ex)))
        return [], {}
    if not rows:
        return [], {}
    headers = rows[0]
    header_lookup = {}
    for index, heading in enumerate(headers):
        header_lookup[normalize(heading)] = index
    return rows[1:], header_lookup

def get_cell(row, header_lookup, headings, fallback=None):
    for heading in headings:
        key = normalize(heading)
        if key in header_lookup:
            index = header_lookup[key]
            if index < len(row):
                return to_text(row[index])
    if fallback is not None and fallback < len(row):
        return to_text(row[fallback])
    return ""

def split_categories(value):
    if is_blank(value):
        return []
    output = []
    for category in str(value).split(","):
        category = category.strip()
        if category:
            output.append(category)
    return output

def get_optional_csv_value(row, header_lookup):
    return get_cell(
        row,
        header_lookup,
        ["Value", "Default Value", "Default_Value", "Family Value", "Family_Value", "Type Value", "Type_Value"],
        None
    )

def get_family_category():
    try:
        return doc.OwnerFamily.FamilyCategory.Name
    except:
        return ""

def category_matches(csv_categories, family_category):
    if add_all_parameters:
        return True
    family_key = normalize(family_category)
    csv_keys = [normalize(x) for x in csv_categories]
    if family_key in csv_keys:
        return True
    category_aliases = {
        "furniture": ["furniture", "furnituresystems"],
        "furnituresystems": ["furniture", "furnituresystems"],
        "mechanicalequipment": ["mechanicalequipment"],
        "electricalequipment": ["electricalequipment"],
        "plumbingfixtures": ["plumbingfixtures"],
        "specialtyequipment": ["specialtyequipment", "specialityequipment"],
        "specialityequipment": ["specialtyequipment", "specialityequipment"],
        "casework": ["casework"],
        "lightingfixtures": ["lightingfixtures"]
    }
    acceptable = category_aliases.get(family_key, [family_key])
    for key in csv_keys:
        if key in acceptable:
            return True
    return False

def get_group_id(group_name):
    key = normalize(group_name)

    # Standard GroupTypeId mapping for Revit 2022+ / 2026+
    try:
        if key in ["identitydata", "identity", "td_asset_identification", "td_assetidentification"]:
            return GroupTypeId.IdentityData
        elif key in ["modelproperties", "adskmodelproperties"]:
            return GroupTypeId.AdskModelProperties
        elif key == "general":
            return GroupTypeId.General
        elif key in ["data", "td_space_information"]:
            return GroupTypeId.Data
        elif key in ["dimensions", "geometry", "td_physical_characteristics"]:
            return GroupTypeId.Dimensions
        elif key == "constraints":
            return GroupTypeId.Constraints
        elif key == "graphics":
            return GroupTypeId.Graphics
        elif key in ["materialsfinishes", "materialsandfinishes", "materials"]:
            return GroupTypeId.Materials
        elif key == "ifc":
            return GroupTypeId.Ifc
        elif key == "phasing":
            return GroupTypeId.Phasing
        elif key == "text":
            return GroupTypeId.Text
        else:
            return GroupTypeId.Data
    except:
        pass

    # Legacy Fallback
    try:
        bip_name = "PG_DATA"
        if key in ["identitydata", "identity", "td_asset_identification", "td_assetidentification"]:
            bip_name = "PG_IDENTITY_DATA"
        elif key in ["modelproperties", "adskmodelproperties"]:
            bip_name = "PG_ADSK_MODEL_PROPERTIES"
        elif key == "general":
            bip_name = "PG_GENERAL"
        elif key in ["dimensions", "geometry"]:
            bip_name = "PG_GEOMETRY"
        elif key == "constraints":
            bip_name = "PG_CONSTRAINTS"
        elif key == "graphics":
            bip_name = "PG_GRAPHICS"
        elif key in ["materialsfinishes", "materialsandfinishes", "materials"]:
            bip_name = "PG_MATERIALS"

        bipg_enum = System.Enum.Parse(Autodesk.Revit.DB.BuiltInParameterGroup, bip_name)
        try:
            return ParameterUtils.GetParameterGroupTypeId(bipg_enum)
        except:
            return bipg_enum
    except:
        return None
        
def existing_group_id(family_parameter):
    try:
        return family_parameter.Definition.GetGroupTypeId()
    except:
        try:
            return family_parameter.Definition.ParameterGroup
        except:
            return None

def same_group(group_a, group_b):
    if group_a is None or group_b is None:
        return False
    try:
        return group_a == group_b
    except:
        return str(group_a) == str(group_b)

def open_shared_file(path):
    if is_blank(path) or not os.path.exists(path):
        return None
    try:
        app.SharedParametersFilename = path
        return app.OpenSharedParameterFile()
    except:
        return None

def find_definition(shared_file, parameter_name):
    if shared_file is None or not parameter_name:
        return None
    target_clean = parameter_name.strip().lower()
    try:
        for group in shared_file.Groups:
            for definition in group.Definitions:
                if definition.Name.strip().lower() == target_clean:
                    return definition
    except:
        pass
    return None

def definition_guid(definition):
    try:
        return str(definition.GUID).lower()
    except:
        return ""

def ensure_family_type(family_manager):
    try:
        if family_manager.CurrentType:
            return True
    except:
        pass
    try:
        iterator = family_manager.Types.ForwardIterator()
        iterator.Reset()
        if iterator.MoveNext():
            family_manager.CurrentType = iterator.Current
            return True
    except:
        pass
    try:
        family_manager.NewType("Default")
        return True
    except:
        return False

def get_family_types(family_manager):
    output = []
    try:
        iterator = family_manager.Types.ForwardIterator()
        iterator.Reset()
        while iterator.MoveNext():
            output.append(iterator.Current)
    except:
        pass
    return output

def find_family_parameter(family_manager, parameter_name):
    target = clean_name(parameter_name)
    try:
        for parameter in family_manager.Parameters:
            try:
                if clean_name(parameter.Definition.Name) == target:
                    return parameter
            except:
                pass
    except:
        pass
    return None

def parameter_name(parameter):
    try:
        return clean_name(parameter.Definition.Name)
    except:
        return ""

def parameter_guid(parameter):
    try:
        return str(parameter.GUID).lower()
    except:
        return ""

def parameter_is_instance(parameter):
    try:
        return bool(parameter.IsInstance)
    except:
        return None

def get_td_parameters(family_manager):
    output = []
    try:
        for parameter in family_manager.Parameters:
            if parameter_name(parameter).startswith("TD_"):
                output.append(parameter)
    except:
        pass
    return output

def read_value(family_type, parameter):
    try:
        storage = parameter.StorageType
        if storage == StorageType.String:
            return family_type.AsString(parameter)
        if storage == StorageType.Integer:
            return family_type.AsInteger(parameter)
        if storage == StorageType.Double:
            return family_type.AsDouble(parameter)
        if storage == StorageType.ElementId:
            return family_type.AsElementId(parameter)
    except:
        return None
    return None

def backup_values(family_manager, parameter):
    backup = {}
    for family_type in get_family_types(family_manager):
        try:
            backup[family_type.Name] = read_value(family_type, parameter)
        except:
            pass
    return backup

def set_current_type_value(family_manager, parameter, value):
    if parameter is None or value is None:
        return False
    try:
        storage = parameter.StorageType
        if storage == StorageType.String:
            family_manager.Set(parameter, deduplicate_joined_value(value))
            return True
        if storage == StorageType.Integer:
            value_key = normalize(value)
            if value_key in ["true", "yes", "y"]:
                family_manager.Set(parameter, 1)
                return True
            if value_key in ["false", "no", "n"]:
                family_manager.Set(parameter, 0)
                return True
            integer_value = safe_int(value)
            if integer_value is not None:
                family_manager.Set(parameter, integer_value)
                return True
        if storage == StorageType.Double:
            double_value = safe_float(value)
            if double_value is not None:
                family_manager.Set(parameter, double_value)
                return True
        if storage == StorageType.ElementId:
            if isinstance(value, ElementId):
                family_manager.Set(parameter, value)
                return True
    except:
        return False
    return False

def restore_values(family_manager, parameter, backup):
    restored = 0
    failed = 0
    types_by_name = {}
    for family_type in get_family_types(family_manager):
        types_by_name[family_type.Name] = family_type
    for type_name, old_value in backup.items():
        if old_value is None:
            continue
        if type_name not in types_by_name:
            failed += 1
            continue
        try:
            family_manager.CurrentType = types_by_name[type_name]
            current_value = read_value(types_by_name[type_name], parameter)
            final_value = old_value
            if parameter.StorageType == StorageType.String:
                final_value = merge_unique_values(old_value, current_value)
            if set_current_type_value(family_manager, parameter, final_value):
                restored += 1
            else:
                failed += 1
        except:
            failed += 1
    return restored, failed

def clean_existing_duplicates(family_manager, parameter):
    cleaned = 0
    failed = 0
    try:
        if parameter.StorageType != StorageType.String:
            return cleaned, failed
    except:
        return cleaned, failed
    for family_type in get_family_types(family_manager):
        try:
            family_manager.CurrentType = family_type
            old_value = read_value(family_type, parameter)
            if is_blank(old_value):
                continue
            new_value = deduplicate_joined_value(old_value)
            if str(new_value) != str(old_value):
                if set_current_type_value(family_manager, parameter, new_value):
                    cleaned += 1
                else:
                    failed += 1
        except:
            failed += 1
    return cleaned, failed

def apply_csv_value_without_data_loss(family_manager, parameter, csv_value):
    applied = 0
    preserved = 0
    failed = 0
    if is_blank(csv_value):
        return applied, preserved, failed
    for family_type in get_family_types(family_manager):
        try:
            family_manager.CurrentType = family_type
            existing_value = read_value(family_type, parameter)
            if parameter.StorageType == StorageType.String:
                final_value = merge_unique_values(existing_value, csv_value)
                if set_current_type_value(family_manager, parameter, final_value):
                    applied += 1
                else:
                    failed += 1
            else:
                if existing_value is not None:
                    preserved += 1
                    continue
                if set_current_type_value(family_manager, parameter, csv_value):
                    applied += 1
                else:
                    failed += 1
        except:
            failed += 1
    return applied, preserved, failed

def add_parameter(family_manager, definition, ui_group, is_instance):
    group_id = get_group_id(ui_group)
    if group_id is None:
        return None, "Could not resolve Revit UI group '{}'.".format(ui_group)
    try:
        parameter = family_manager.AddParameter(definition, group_id, is_instance)
        return parameter, ""
    except Exception as ex:
        return None, "Could not add '{}' as {} under '{}'. Error: {}".format(
            definition.Name,
            "Instance" if is_instance else "Type",
            ui_group,
            str(ex)
        )

def repair_reasons(existing, definition, target_group, target_is_instance):
    reasons = []
    old_guid = parameter_guid(existing)
    new_guid = definition_guid(definition)
    if old_guid and new_guid and old_guid != new_guid:
        reasons.append("wrong GUID")
    old_instance = parameter_is_instance(existing)
    if old_instance is not None and old_instance != target_is_instance:
        reasons.append("wrong Instance/Type binding")
    old_group = existing_group_id(existing)
    if old_group is not None and not same_group(old_group, target_group):
        reasons.append("wrong UI group")
    return reasons

def synchronize_parameter(family_manager, definition, parameter_name_value, ui_group, target_is_instance):
    existing = find_family_parameter(family_manager, parameter_name_value)
    target_group = get_group_id(ui_group)
    
    if target_group is None:
        return None, "FAILED ADD: Could not resolve UI group '{}'".format(ui_group), 0, 0

    if existing is None:
        parameter, error = add_parameter(family_manager, definition, ui_group, target_is_instance)
        if parameter is None:
            return None, "FAILED ADD: " + error, 0, 0
        status = "ADDED INSTANCE" if target_is_instance else "ADDED TYPE"
        return parameter, status, 0, 0

    reasons = repair_reasons(existing, definition, target_group, target_is_instance)
    if not reasons:
        return existing, "EXISTING CORRECT", 0, 0

    if not force_repair:
        return existing, "REPAIR NEEDED: " + ", ".join(reasons), 0, 0

    backup = backup_values(family_manager, existing)
    try:
        repaired_parameter = family_manager.ReplaceParameter(
            existing,
            definition,
            target_group,
            target_is_instance
        )
        restored, restore_failed = restore_values(family_manager, repaired_parameter, backup)
        return repaired_parameter, "REPAIRED: " + ", ".join(reasons), restored, restore_failed
    except:
        pass

    try:
        family_manager.RemoveParameter(existing)
    except Exception as ex:
        return existing, "FAILED REMOVE: " + str(ex), 0, 0

    repaired_parameter, error = add_parameter(family_manager, definition, ui_group, target_is_instance)
    if repaired_parameter is None:
        return None, "FAILED RE-ADD: " + error, 0, 0

    restored, restore_failed = restore_values(family_manager, repaired_parameter, backup)
    return repaired_parameter, "REMOVED AND RE-ADDED: " + ", ".join(reasons), restored, restore_failed

# Main Execution Flow
if not run_script:
    results.append("SKIPPED: Run Boolean is False.")
elif not doc.IsFamilyDocument:
    results.append("FAILED: Open the .rfa family and run Dynamo from the Family Editor.")
elif is_blank(csv_path) or not os.path.exists(csv_path):
    results.append("FAILED: CSV file does not exist.")
elif is_blank(shared_txt_path) or not os.path.exists(shared_txt_path):
    results.append("FAILED: Shared parameter TXT does not exist.")
else:
    transaction_started = False
    try:
        family_manager = doc.FamilyManager
        family_category = get_family_category()
        shared_file = open_shared_file(shared_txt_path)
        csv_rows, header_lookup = read_csv(csv_path)

        if shared_file is None:
            results.append("FAILED: Could not open shared parameter TXT.")
        elif not csv_rows:
            results.append("FAILED: CSV has no data rows.")
        else:
            expected = {}
            skipped_by_category = 0
            for row_index, row in enumerate(csv_rows):
                row_number = row_index + 2
                name = clean_name(get_cell(row, header_lookup, ["Parameter", "Parameter Name", "Parameter_Name"], 0))
                if not name:
                    continue
                ui_group = get_cell(row, header_lookup, ["RevitUIGroup"], 1)
                is_instance = parse_boolean(get_cell(row, header_lookup, ["Is Instance", "Is_Instance", "Instance"], 2))
                categories_text = get_cell(row, header_lookup, ["Categories", "Category"], 3)
                categories = split_categories(categories_text)

                if not category_matches(categories, family_category):
                    skipped_by_category += 1
                    continue

                expected[name] = {
                    "row": row_number,
                    "group": ui_group,
                    "instance": is_instance,
                    "value": get_optional_csv_value(row, header_lookup)
                }

            results.append("FAMILY: {}".format(doc.Title))
            results.append("CATEGORY: {}".format(family_category))
            results.append("EXPECTED TD PARAMETERS: {}".format(len(expected)))

            if not expected:
                results.append("STOPPED SAFELY: No CSV rows match category '{}'.".format(family_category))
            else:
                TransactionManager.Instance.EnsureInTransaction(doc)
                transaction_started = True

                if not ensure_family_type(family_manager):
                    raise Exception("The family has no usable family type.")

                added = 0
                existing_correct = 0
                repaired = 0
                repair_needed = 0
                removed = 0
                failed = 0
                missing_definition = 0
                restored = 0
                restore_failed = 0
                duplicates_cleaned = 0
                duplicate_clean_failed = 0
                csv_values_merged = 0
                old_values_preserved = 0
                csv_value_failed = 0

                if remove_obsolete:
                    for existing_parameter in list(get_td_parameters(family_manager)):
                        name = parameter_name(existing_parameter)
                        if name not in expected:
                            try:
                                family_manager.RemoveParameter(existing_parameter)
                                removed += 1
                                results.append("REMOVED OBSOLETE: " + name)
                            except Exception as ex:
                                failed += 1
                                results.append("FAILED REMOVE '{}': {}".format(name, str(ex)))

                for name in sorted(expected.keys()):
                    info = expected[name]
                    definition = find_definition(shared_file, name)
                    if definition is None:
                        missing_definition += 1
                        results.append("FAILED ROW {}: '{}' not found in shared parameter TXT.".format(info["row"], name))
                        continue

                    parameter, status, restored_count, restore_failed_count = synchronize_parameter(
                        family_manager,
                        definition,
                        name,
                        info["group"],
                        info["instance"]
                    )

                    restored += restored_count
                    restore_failed += restore_failed_count

                    if status.startswith("ADDED"):
                        added += 1
                    elif status == "EXISTING CORRECT":
                        existing_correct += 1
                    elif status.startswith("REPAIRED") or status.startswith("REMOVED AND RE-ADDED"):
                        repaired += 1
                    elif status.startswith("REPAIR NEEDED"):
                        repair_needed += 1
                    elif status.startswith("FAILED"):
                        failed += 1

                    kind = "Instance" if info["instance"] else "Type"
                    results.append("ROW {}: '{}' ({}) | Group '{}' | {}".format(info["row"], name, kind, info["group"], status))

                    if parameter is None:
                        continue

                    cleaned, clean_failed = clean_existing_duplicates(family_manager, parameter)
                    duplicates_cleaned += cleaned
                    duplicate_clean_failed += clean_failed

                    merged, preserved, value_failed = apply_csv_value_without_data_loss(family_manager, parameter, info["value"])
                    csv_values_merged += merged
                    old_values_preserved += preserved
                    csv_value_failed += value_failed

                doc.Regenerate()
                TransactionManager.Instance.TransactionTaskDone()
                transaction_started = False

                results.append("--------- SUMMARY ---------")
                results.append("Added parameters: {}".format(added))
                results.append("Existing correct: {}".format(existing_correct))
                results.append("Repaired parameters: {}".format(repaired))
                results.append("Repair needed with force_repair=False: {}".format(repair_needed))
                results.append("Removed obsolete TD_: {}".format(removed))
                results.append("Missing TXT definitions: {}".format(missing_definition))
                results.append("Failed operations: {}".format(failed))
                results.append("Values restored: {}".format(restored))
                results.append("Value restore failures: {}".format(restore_failed))
                results.append("Duplicate values cleaned: {}".format(duplicates_cleaned))
                results.append("Duplicate cleaning failures: {}".format(duplicate_clean_failed))
                results.append("CSV values merged: {}".format(csv_values_merged))
                results.append("Existing values preserved: {}".format(old_values_preserved))
                results.append("CSV value failures: {}".format(csv_value_failed))

    except Exception as ex:
        if transaction_started:
            try:
                TransactionManager.Instance.TransactionTaskDone()
            except:
                pass
        results.append("FATAL SCRIPT ERROR: " + str(ex))

OUT = results
