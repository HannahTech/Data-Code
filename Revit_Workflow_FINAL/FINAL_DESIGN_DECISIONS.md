# Final Design Decisions

Compared with the earlier draft package, this final package changes several things for safety and long-term reuse:

1. **The original shared parameter TXT is the GUID authority.**
   The master CSV no longer contains generated GUIDs.

2. **Preview mode is built into Steps 1–3.**
   You can see planned adds, repairs, removals and GUID conflicts before changing Revit.

3. **Automatic data backups are created before mutations.**
   Family and project TD values are written to CSV before stale parameters are removed or bindings are migrated.

4. **Wrong-GUID migration is explicit, not automatic.**
   Same-name/different-GUID conflicts are reported by default. Set `MigrateWrongGUID=True` only after confirming the desired migration.

5. **Cleanup is limited to `TD_` parameters/bindings.**
   Other Revit/client parameters are not deleted.

6. **Furniture Appendix matching blocks duplicate TD_Type_ID values.**
   The script does not guess when the lookup key is ambiguous.

7. **Step 4 uses timestamped export folders.**
   Historical exports are preserved instead of overwritten.

8. **Step 4 de-duplicates type records in the long export.**
   A used Revit type is exported once rather than once per placed instance.

9. **Step 4 can optionally export all model categories.**
   The normal mode stays focused on categories in the parameter master; full-model mode is available when needed.
