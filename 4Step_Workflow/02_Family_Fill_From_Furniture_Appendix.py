
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

import zipfile
import xml.etree.ElementTree as ET
import posixpath

MASTER_CSV = text(IN[0]) if len(IN) > 0 else ""
APPENDIX_PATH = text(IN[1]) if len(IN) > 1 else ""
RUN = bool(IN[2]) if len(IN) > 2 and IN[2] is not None else False
OVERWRITE_EXISTING = bool(IN[3]) if len(IN) > 3 and IN[3] is not None else True

log = []

def col_index(cell_ref):
    letters = ""
    for ch in cell_ref:
        if ch.isalpha():
            letters += ch
        else:
            break
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1

def xlsx_sheets(path):
    if path.lower().endswith(".xls"):
        raise Exception("Legacy .xls is not supported by the no-dependency reader. Save the appendix as .xlsx.")
    z = zipfile.ZipFile(path, "r")
    ns_main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ns_rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ns_pkg = "http://schemas.openxmlformats.org/package/2006/relationships"

    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root_ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root_ss.findall("{%s}si" % ns_main):
            pieces = []
            for t in si.iter("{%s}t" % ns_main):
                pieces.append(t.text or "")
            shared.append("".join(pieces))

    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels_root = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rels = {}
    for rel in rels_root.findall("{%s}Relationship" % ns_pkg):
        rels[rel.attrib["Id"]] = rel.attrib["Target"]

    out = []
    for sh in wb.find("{%s}sheets" % ns_main):
        name = sh.attrib.get("name","")
        rid = sh.attrib.get("{%s}id" % ns_rel)
        target = rels.get(rid)
        if not target:
            continue
        if target.startswith("/"):
            sheet_path = target.lstrip("/")
        else:
            sheet_path = posixpath.normpath(posixpath.join("xl", target))
        root_sh = ET.fromstring(z.read(sheet_path))
        rows = []
        for row in root_sh.findall(".//{%s}row" % ns_main):
            cells = {}
            max_i = -1
            for c in row.findall("{%s}c" % ns_main):
                ref = c.attrib.get("r","A1")
                idx = col_index(ref)
                max_i = max(max_i, idx)
                typ = c.attrib.get("t","")
                value = ""
                if typ == "inlineStr":
                    isel = c.find("{%s}is" % ns_main)
                    if isel is not None:
                        value = "".join((t.text or "") for t in isel.iter("{%s}t" % ns_main))
                else:
                    v = c.find("{%s}v" % ns_main)
                    raw = "" if v is None or v.text is None else v.text
                    if typ == "s" and raw != "":
                        try:
                            value = shared[int(raw)]
                        except:
                            value = raw
                    elif typ == "b":
                        value = "TRUE" if raw == "1" else "FALSE"
                    else:
                        value = raw
                cells[idx] = value
            if max_i >= 0:
                vals = [""] * (max_i + 1)
                for i,v in cells.items():
                    vals[i] = v
                rows.append(vals)
        out.append((name, rows))
    z.close()
    return out

def csv_sheet(path):
    try:
        f = open(path, "r", encoding="utf-8-sig", errors="ignore", newline="")
    except:
        f = open(path, "r")
    with f:
        return [("CSV", [row for row in csv.reader(f)])]

def appendix_tables(path):
    if not path or not os.path.exists(path):
        raise Exception("Furniture appendix file not found: {}".format(path))
    if path.lower().endswith(".csv"):
        return csv_sheet(path)
    if path.lower().endswith((".xlsx",".xlsm")):
        return xlsx_sheets(path)
    if path.lower().endswith(".xls"):
        raise Exception("Save legacy .xls as .xlsx first.")
    raise Exception("Appendix must be .xlsx, .xlsm, or .csv.")

def find_header_row(rows):
    key = norm("TD_Type_ID")
    for i, row in enumerate(rows[:60]):
        if any(norm(v) == key for v in row):
            return i
    return None

def build_appendix_index(path):
    index = {}
    duplicates = set()
    header_catalog = {}
    for sheet_name, rows in appendix_tables(path):
        hi = find_header_row(rows)
        if hi is None:
            log.append("SKIP SHEET {} | no TD_Type_ID header found".format(sheet_name))
            continue
        headers = rows[hi]
        hmap = {}
        for i,h in enumerate(headers):
            if text(h):
                hmap[norm(h)] = i
        type_col = hmap.get(norm("TD_Type_ID"))
        header_catalog[sheet_name] = hmap
        for ri in range(hi + 1, len(rows)):
            row = rows[ri]
            if type_col is None or type_col >= len(row):
                continue
            type_id = text(row[type_col])
            if not type_id:
                continue
            key = norm(type_id)
            record = {"__sheet__":sheet_name, "__row__":ri+1}
            for hk, ci in hmap.items():
                record[hk] = text(row[ci]) if ci < len(row) else ""
            if key in index:
                duplicates.add(key)
            else:
                index[key] = record
    return index, duplicates

def family_types(fm):
    out = []
    it = fm.Types.ForwardIterator()
    it.Reset()
    while it.MoveNext():
        out.append(it.Current)
    return out

def find_family_parameter(fm, name):
    n = text(name).lower()
    for p in fm.Parameters:
        try:
            if text(p.Definition.Name).lower() == n:
                return p
        except:
            pass
    return None

def family_value(ft, p):
    try:
        st = p.StorageType
        if st == StorageType.String:
            return text(ft.AsString(p))
        if st == StorageType.Integer:
            return str(ft.AsInteger(p))
        if st == StorageType.Double:
            return str(ft.AsDouble(p))
        if st == StorageType.ElementId:
            return str(ft.AsElementId(p).Value)
    except:
        pass
    return ""

def set_family_value(fm, p, value):
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
                fm.Set(p,1); return True
            if k in ("false","no","n"):
                fm.Set(p,0); return True
            fm.Set(p, int(float(s.replace(",",""))))
            return True
        if p.StorageType == StorageType.Double:
            v = float(s.replace(",",""))
            try:
                spec = p.Definition.GetDataType()
                fmt = doc.GetUnits().GetFormatOptions(spec)
                v = UnitUtils.ConvertToInternalUnits(v, fmt.GetUnitTypeId())
            except:
                pass
            fm.Set(p, v)
            return True
    except:
        return False
    return False

def first_source_value(record, priority):
    for alias in [x.strip() for x in text(priority).split("|") if x.strip()]:
        k = norm(alias)
        if k in record and text(record[k]) != "":
            return text(record[k]), alias
    return "", ""

if not RUN:
    OUT = ["READY | Step 2 Family Fill | Select furniture appendix .xlsx and set Run=True."]
elif not doc.IsFamilyDocument:
    OUT = ["FAILED | Step 2 must run in an open Revit family (.rfa)."]
else:
    tx_open = False
    try:
        master_rows = [r for r in read_csv_dict(MASTER_CSV) if norm(r.get("Scope")) == "familytype"]
        index, duplicates = build_appendix_index(APPENDIX_PATH)
        fm = doc.FamilyManager
        types = family_types(fm)
        type_id_param = find_family_parameter(fm, "TD_Type_ID")
        if type_id_param is None:
            raise Exception("TD_Type_ID is missing. Run Step 1 first.")

        TransactionManager.Instance.EnsureInTransaction(doc)
        tx_open = True

        matched = no_type_id = not_found = filled = kept = failed = 0
        old_current = fm.CurrentType

        for ft in types:
            try:
                fm.CurrentType = ft
            except:
                pass
            type_id = family_value(ft, type_id_param)
            if not type_id:
                no_type_id += 1
                log.append("TYPE '{}' | SKIP | TD_Type_ID is blank".format(ft.Name))
                continue
            key = norm(type_id)
            if key in duplicates:
                failed += 1
                log.append("TYPE '{}' | FAIL | duplicate TD_Type_ID '{}' exists in appendix".format(ft.Name, type_id))
                continue
            record = index.get(key)
            if record is None:
                not_found += 1
                log.append("TYPE '{}' | NOT FOUND | TD_Type_ID='{}'".format(ft.Name, type_id))
                continue

            matched += 1
            type_changes = 0
            for r in master_rows:
                name = text(r.get("Parameter"))
                if name == "TD_Type_ID" or not truthy(r.get("PopulateFromAppendix")):
                    continue
                p = find_family_parameter(fm, name)
                if p is None:
                    failed += 1
                    log.append("TYPE '{}' | MISSING PARAM | {}".format(ft.Name, name))
                    continue
                source_value, source_header = first_source_value(record, r.get("AppendixHeaderPriority"))
                if source_value == "":
                    continue
                current = family_value(ft, p)
                if current != "" and not OVERWRITE_EXISTING:
                    kept += 1
                    continue
                if set_family_value(fm, p, source_value):
                    filled += 1
                    type_changes += 1
                else:
                    failed += 1
                    log.append("TYPE '{}' | FAIL SET {} from '{}' value='{}'".format(
                        ft.Name, name, source_header, source_value))
            log.append("TYPE '{}' | MATCH {} | sheet='{}' row={} | fields updated={}".format(
                ft.Name, type_id, record.get("__sheet__"), record.get("__row__"), type_changes))

        try:
            fm.CurrentType = old_current
        except:
            pass

        TransactionManager.Instance.TransactionTaskDone()
        tx_open = False
        log.insert(0,
            "SUMMARY | FamilyTypes={} | Matched={} | BlankTypeID={} | NotFound={} | "
            "ValuesFilled={} | ExistingKept={} | Failed={}".format(
                len(types), matched, no_type_id, not_found, filled, kept, failed))
    except Exception as ex:
        if tx_open:
            try:
                TransactionManager.Instance.ForceCloseTransaction()
            except:
                pass
        log.insert(0, "FAILED | {}".format(ex))
    OUT = log
