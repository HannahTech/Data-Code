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


# STEP 2 — FILL FAMILY TYPE DATA FROM FURNITURE APPENDIX
# IN[0] = TD_Master_Parameters.csv
# IN[1] = Furniture Appendix .xlsx / .xlsm / .csv
# IN[2] = Run
# IN[3] = PreviewOnly (recommended True first)
# IN[4] = OverwriteExistingMappedValues

import zipfile
import xml.etree.ElementTree as ET
import posixpath

MASTER_CSV = text(IN[0]) if len(IN) > 0 else ""
APPENDIX_PATH = text(IN[1]) if len(IN) > 1 else ""
RUN = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
PREVIEW = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else True
OVERWRITE_EXISTING = bool(IN[4]) if len(IN) > 4 and IN[4] is not None else True

log = []

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

def find_family_parameter(fm, name):
    target = text(name).lower()
    for p in family_parameters(fm):
        try:
            if text(p.Definition.Name).lower() == target:
                return p
        except:
            pass
    return None

def family_raw_value(ft, p):
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

def family_display_value(ft, p):
    pair = family_raw_value(ft, p)
    if pair is None:
        return ""
    kind, value = pair
    if kind == "String":
        return text(value)
    if kind == "Integer":
        try:
            formatted = ft.AsValueString(p)
            if text(formatted):
                return text(formatted)
        except:
            pass
        return str(value)
    if kind == "Double":
        try:
            formatted = ft.AsValueString(p)
            if text(formatted):
                return text(formatted)
        except:
            pass
        return repr(value)
    if kind == "ElementId":
        return str(eid_value(value))
    return ""

def set_family_display_value(fm, p, value):
    s = text(value)
    if s == "":
        return False
    try:
        if p.StorageType == StorageType.String:
            fm.Set(p, s)
            return True
        if p.StorageType == StorageType.Integer:
            k = norm(s)
            if k in ("true","yes","y"):
                fm.Set(p, 1); return True
            if k in ("false","no","n"):
                fm.Set(p, 0); return True
            fm.Set(p, int(float(s.replace(",",""))))
            return True
        if p.StorageType == StorageType.Double:
            # Let Revit parse display-unit strings first (e.g. "10 SF", "1.5 m²").
            try:
                fm.SetValueString(p, s)
                return True
            except:
                pass

            # Fallback for a plain numeric value: interpret it in current document display units.
            val = float(s.replace(",",""))
            try:
                spec = p.Definition.GetDataType()
                fmt = doc.GetUnits().GetFormatOptions(spec)
                val = UnitUtils.ConvertToInternalUnits(val, fmt.GetUnitTypeId())
            except:
                pass
            fm.Set(p, val)
            return True
    except:
        return False
    return False

def backup_family_type_values(fm, master_path):
    out_dir = os.path.join(backup_root(master_path), "Families")
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)
    path = os.path.join(
        out_dir,
        "{}__{}__BeforeAppendixFill.csv".format(safe_filename(doc.Title), timestamp())
    )
    rows = []
    old = fm.CurrentType
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
            pair = family_raw_value(ft, p)
            if pair is None:
                continue
            kind, raw = pair
            try:
                guid = str(p.GUID)
            except:
                guid = ""
            rows.append([
                text(doc.Title), ft.Name, name, guid,
                "Instance" if bool(p.IsInstance) else "Type",
                kind, "" if raw is None else str(raw)
            ])
    try:
        fm.CurrentType = old
    except:
        pass
    write_csv(
        path,
        ["Family","FamilyType","Parameter","GUID","Binding","StorageType","RawValue"],
        rows
    )
    return path

# ---- Minimal XLSX/XLSM reader: no third-party Python package required inside Dynamo ----

def xlsx_column_index(cell_ref):
    letters = ""
    for ch in text(cell_ref):
        if ch.isalpha():
            letters += ch
        else:
            break
    n = 0
    for ch in letters.upper():
        n = (n * 26) + (ord(ch) - 64)
    return n - 1

def xlsx_tables(path):
    if path.lower().endswith(".xls"):
        raise Exception("Legacy .xls is not supported. Save the Furniture Appendix as .xlsx.")
    z = zipfile.ZipFile(path, "r")

    ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_pkg = "http://schemas.openxmlformats.org/package/2006/relationships"

    shared_strings = []
    if "xl/sharedStrings.xml" in z.namelist():
        ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in ss_root.findall("{%s}si" % ns_main):
            parts = []
            for t in si.iter("{%s}t" % ns_main):
                parts.append(t.text or "")
            shared_strings.append("".join(parts))

    workbook_root = ET.fromstring(z.read("xl/workbook.xml"))
    rels_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    relationships = {}
    for rel in rels_root.findall("{%s}Relationship" % ns_pkg):
        relationships[rel.attrib.get("Id")] = rel.attrib.get("Target")

    result = []
    sheets_node = workbook_root.find("{%s}sheets" % ns_main)
    if sheets_node is None:
        z.close()
        return result

    for sh in sheets_node:
        sheet_name = sh.attrib.get("name", "")
        rid = sh.attrib.get("{%s}id" % ns_rel)
        target = relationships.get(rid)
        if not target:
            continue
        if target.startswith("/"):
            sheet_path = target.lstrip("/")
        else:
            sheet_path = posixpath.normpath(posixpath.join("xl", target))

        if sheet_path not in z.namelist():
            continue

        sh_root = ET.fromstring(z.read(sheet_path))
        sheet_rows = []

        for row_node in sh_root.findall(".//{%s}row" % ns_main):
            cells = {}
            max_idx = -1

            for c in row_node.findall("{%s}c" % ns_main):
                idx = xlsx_column_index(c.attrib.get("r", "A1"))
                max_idx = max(max_idx, idx)
                typ = c.attrib.get("t", "")
                value = ""

                if typ == "inlineStr":
                    is_node = c.find("{%s}is" % ns_main)
                    if is_node is not None:
                        value = "".join((t.text or "") for t in is_node.iter("{%s}t" % ns_main))
                else:
                    v = c.find("{%s}v" % ns_main)
                    raw = "" if v is None or v.text is None else v.text
                    if typ == "s" and raw != "":
                        try:
                            value = shared_strings[int(raw)]
                        except:
                            value = raw
                    elif typ == "b":
                        value = "TRUE" if raw == "1" else "FALSE"
                    else:
                        value = raw

                cells[idx] = value

            if max_idx >= 0:
                values = [""] * (max_idx + 1)
                for i, v in cells.items():
                    values[i] = v
                sheet_rows.append(values)

        result.append((sheet_name, sheet_rows))

    z.close()
    return result

def csv_tables(path):
    try:
        f = open(path, "r", encoding="utf-8-sig", errors="ignore", newline="")
    except:
        f = open(path, "r")
    with f:
        return [("CSV", [row for row in csv.reader(f)])]

def appendix_tables(path):
    if not path or not os.path.exists(path):
        raise Exception("Furniture Appendix file not found: {}".format(path))
    low = path.lower()
    if low.endswith(".csv"):
        return csv_tables(path)
    if low.endswith(".xlsx") or low.endswith(".xlsm"):
        return xlsx_tables(path)
    if low.endswith(".xls"):
        raise Exception("Save the legacy .xls Furniture Appendix as .xlsx first.")
    raise Exception("Furniture Appendix must be .xlsx, .xlsm, or .csv.")

def find_header_row(rows):
    key = norm("TD_Type_ID")
    # Search early rows because some sheets can have title rows above the real table.
    for i, row in enumerate(rows[:80]):
        if any(norm(v) == key for v in row):
            return i
    return None

def build_appendix_index(path):
    records = {}
    duplicates = {}
    sheets_used = 0

    for sheet_name, sheet_rows in appendix_tables(path):
        header_index = find_header_row(sheet_rows)
        if header_index is None:
            log.append("SKIP SHEET | {} | no TD_Type_ID header found".format(sheet_name))
            continue

        headers = sheet_rows[header_index]
        hmap = {}
        for i, h in enumerate(headers):
            if text(h):
                hmap[norm(h)] = i

        type_col = hmap.get(norm("TD_Type_ID"))
        if type_col is None:
            continue

        sheets_used += 1
        for row_index in range(header_index + 1, len(sheet_rows)):
            row = sheet_rows[row_index]
            if type_col >= len(row):
                continue
            type_id = text(row[type_col])
            if not type_id:
                continue

            key = norm(type_id)
            record = {
                "__type_id__": type_id,
                "__sheet__": sheet_name,
                "__excel_row__": row_index + 1,
            }
            for hk, ci in hmap.items():
                record[hk] = text(row[ci]) if ci < len(row) else ""

            if key in records:
                duplicates.setdefault(key, [records[key]])
                duplicates[key].append(record)
            else:
                records[key] = record

    return records, duplicates, sheets_used

def first_source_value(record, priority):
    for alias in [x.strip() for x in text(priority).split("|") if x.strip()]:
        k = norm(alias)
        if k in record and text(record[k]) != "":
            return text(record[k]), alias
    return "", ""

if not RUN:
    OUT = ["READY | Step 2 | Set Run=True. Use PreviewOnly=True first."]
elif not doc.IsFamilyDocument:
    OUT = ["FAILED | Step 2 must run in an open Revit FAMILY."]
else:
    tx_open = False
    try:
        master = [
            r for r in read_csv_dict(MASTER_CSV)
            if norm(r.get("Scope")) == "familytype"
        ]
        appendix_index, duplicate_index, sheets_used = build_appendix_index(APPENDIX_PATH)

        fm = doc.FamilyManager
        type_id_param = find_family_parameter(fm, "TD_Type_ID")
        if type_id_param is None:
            raise Exception("TD_Type_ID is missing. Run Step 1 first.")

        plans = []
        matched = 0
        blank_type_id = 0
        not_found = 0
        ambiguous = 0
        missing_parameter = 0

        old_current = fm.CurrentType

        for ft in family_types(fm):
            try:
                fm.CurrentType = ft
            except:
                pass

            type_id = family_display_value(ft, type_id_param)
            if not type_id:
                blank_type_id += 1
                log.append("SKIP TYPE | '{}' | TD_Type_ID is blank".format(ft.Name))
                continue

            key = norm(type_id)
            if key in duplicate_index:
                ambiguous += 1
                refs = [
                    "{} row {}".format(x.get("__sheet__"), x.get("__excel_row__"))
                    for x in duplicate_index[key]
                ]
                log.append(
                    "AMBIGUOUS TYPE ID | '{}' | {} | {}".format(
                        ft.Name, type_id, "; ".join(refs)
                    )
                )
                continue

            record = appendix_index.get(key)
            if record is None:
                not_found += 1
                log.append("NOT FOUND | '{}' | TD_Type_ID='{}'".format(ft.Name, type_id))
                continue

            matched += 1

            for r in master:
                name = text(r.get("Parameter"))
                if name == "TD_Type_ID":
                    continue
                if not truthy(r.get("PopulateFromAppendix")):
                    continue

                p = find_family_parameter(fm, name)
                if p is None:
                    missing_parameter += 1
                    log.append("MISSING FAMILY PARAMETER | '{}' | {}".format(ft.Name, name))
                    continue

                source_value, source_header = first_source_value(
                    record, r.get("AppendixHeaderPriority")
                )
                if source_value == "":
                    continue

                current_value = family_display_value(ft, p)
                if current_value != "" and not OVERWRITE_EXISTING:
                    continue

                if current_value == source_value:
                    continue

                plans.append({
                    "type_name": ft.Name,
                    "type_id": type_id,
                    "parameter": name,
                    "old": current_value,
                    "new": source_value,
                    "source_header": source_header,
                    "source_sheet": record.get("__sheet__"),
                    "source_row": record.get("__excel_row__"),
                })

        try:
            fm.CurrentType = old_current
        except:
            pass

        if PREVIEW:
            log.append("PREVIEW ONLY — no family values changed.")
        else:
            backup_path = backup_family_type_values(fm, MASTER_CSV)
            log.append("BACKUP | {}".format(backup_path))

            TransactionManager.Instance.EnsureInTransaction(doc)
            tx_open = True

            types_by_name = dict((ft.Name, ft) for ft in family_types(fm))
            updated = 0
            failed = 0

            for plan in plans:
                ft = types_by_name.get(plan["type_name"])
                p = find_family_parameter(fm, plan["parameter"])
                if ft is None or p is None:
                    failed += 1
                    continue
                try:
                    fm.CurrentType = ft
                    if set_family_display_value(fm, p, plan["new"]):
                        updated += 1
                    else:
                        failed += 1
                        log.append(
                            "FAIL SET | '{}' | {} | value='{}'".format(
                                plan["type_name"], plan["parameter"], plan["new"]
                            )
                        )
                except Exception as ex:
                    failed += 1
                    log.append(
                        "FAIL SET | '{}' | {} | {}".format(
                            plan["type_name"], plan["parameter"], ex
                        )
                    )

            try:
                fm.CurrentType = old_current
            except:
                pass

            TransactionManager.Instance.TransactionTaskDone()
            tx_open = False
            log.append("APPLY RESULT | Updated={} | Failed={}".format(updated, failed))

        for plan in plans:
            log.append(
                "UPDATE | Type='{}' | TD_Type_ID='{}' | {} | '{}' -> '{}' | source={}!row {} [{}]".format(
                    plan["type_name"], plan["type_id"], plan["parameter"],
                    plan["old"], plan["new"], plan["source_sheet"],
                    plan["source_row"], plan["source_header"]
                )
            )

        log.insert(0,
            "SUMMARY | Family={} | SheetsUsed={} | AppendixIDs={} | FamilyTypes={} | "
            "Matched={} | BlankTypeID={} | NotFound={} | Ambiguous={} | "
            "MissingParams={} | PlannedUpdates={} | Preview={}".format(
                doc.Title, sheets_used, len(appendix_index), len(family_types(fm)),
                matched, blank_type_id, not_found, ambiguous,
                missing_parameter, len(plans), PREVIEW
            )
        )

    except Exception as ex:
        if tx_open:
            try:
                TransactionManager.Instance.ForceCloseTransaction()
            except:
                pass
        log.insert(0, "FAILED | {}".format(ex))

    OUT = log
