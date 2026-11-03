# -*- coding: utf-8 -*-
__title__ = 'Grid 3D to 2D'
__author__ = 'Khoa Le (at) Haskoning', 'Copilot'
__doc__ = 'Convert selected Revit Grids from 3D (Model) to 2D (ViewSpecific) in the active view.'

"""
Convert selected Revit Grids from 3D (Model) to 2D (ViewSpecific) in the active view.
Works in pyRevit environment.
"""

from Autodesk.Revit.DB import Grid, DatumEnds, DatumExtentType, Transaction
from Autodesk.Revit.Exceptions import InvalidOperationException

# pyRevit built-in variables
doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
active_view = doc.ActiveView

try:
    # Get all selected grids
    sel_ids = list(uidoc.Selection.GetElementIds())
    grids = [doc.GetElement(eid) for eid in sel_ids]
    grids = [g for g in grids if isinstance(g, Grid)]

    if not grids:
        print("No Grid selected. Please select one or more grids and run again.")
    else:
        t = Transaction(doc, "Convert Selected Grids to 2D in View")
        t.Start()

        success = 0
        failed = []

        for grid in grids:
            try:
                grid.SetDatumExtentType(DatumEnds.End0, active_view, DatumExtentType.ViewSpecific)
                grid.SetDatumExtentType(DatumEnds.End1, active_view, DatumExtentType.ViewSpecific)
                success += 1
            except Exception:
                failed.append(grid.Name)

        t.Commit()

        print("✅ Converted {}/{} selected grid(s) to 2D in view '{}'.".format(success, len(grids), active_view.Name))
        if failed:
            print("⚠ Failed grids: {}".format(", ".join(failed)))

except InvalidOperationException:
    print("⚠ Operation cancelled by user.")
except Exception as e:
    print("❌ Error: {}".format(e))
