import clr

# Import Revit API
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import *

# Import Revit Services
clr.AddReference('RevitServices')
from RevitServices.Persistence import DocumentManager
from RevitServices.Transactions import TransactionManager

doc = DocumentManager.Instance.CurrentDBDocument
run_purge = bool(IN[0]) if IN[0] is not None else False

results = []

if not run_purge:
    results.append("PURGE SKIPPED: Set input to True to run purge.")
else:
    TransactionManager.Instance.EnsureInTransaction(doc)
    
    try:
        # 1. Unbind all Project/Shared Parameter Bindings
        binding_map = doc.ParameterBindings
        iterator = binding_map.ForwardIterator()
        defs_to_remove = []
        while iterator.MoveNext():
            if iterator.Key:
                defs_to_remove.append(iterator.Key)
        
        for param_def in defs_to_remove:
            try:
                binding_map.Remove(param_def)
            except:
                pass

        # 2. Force-delete all SharedParameterElements from Document DB
        sp_elements = FilteredElementCollector(doc).OfClass(SharedParameterElement).ToElements()
        deleted_count = 0
        for sp_elem in sp_elements:
            try:
                doc.Delete(sp_elem.Id)
                deleted_count += 1
            except:
                pass
                
        results.append(f"SUCCESS: Force-deleted {deleted_count} shared parameters from model database.")
    except Exception as ex:
        results.append(f"PURGE FAILED: {str(ex)}")

    TransactionManager.Instance.TransactionTaskDone()

OUT = results
