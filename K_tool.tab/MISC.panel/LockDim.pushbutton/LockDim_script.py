# -*- coding: utf-8 -*-
"""Lock selected dimensions so they act as constraints."""

__title__ = "Lock\nDimension"
__author__ = "Khoa Le"
__doc__ = "Lock selected dimensions (all segments) so they act as constraints. " \
          "Shift+Click to unlock instead."

from Autodesk.Revit import Exceptions
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import revit, DB, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc

LOCK = not EXEC_PARAMS.config_mode  # Shift+Click unlocks
ACTION = "Lock" if LOCK else "Unlock"


class DimensionFilter(ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, DB.Dimension) and not isinstance(e, DB.SpotDimension)

    def AllowReference(self, ref, point):
        return False


def get_dimensions():
    # Use the current selection if it contains dimensions
    selected = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    dims = [e for e in selected if DimensionFilter().AllowElement(e)]
    if dims:
        return dims

    with forms.WarningBar(title="Select dimensions to {} (Finish when done)".format(ACTION.lower())):
        try:
            refs = uidoc.Selection.PickObjects(ObjectType.Element, DimensionFilter(), "Select dimensions")
        except Exceptions.OperationCanceledException:
            script.exit()
    return [doc.GetElement(r) for r in refs]


def set_lock(dim):
    """Lock/unlock a dimension. Returns (changed, failed) segment counts."""
    changed, failed = 0, 0
    # Multi-segment dimensions must be locked per segment
    targets = list(dim.Segments) if dim.NumberOfSegments > 1 else [dim]
    for t in targets:
        try:
            if t.IsLocked != LOCK:
                t.IsLocked = LOCK
                changed += 1
        except Exception:
            failed += 1
    return changed, failed


dims = get_dimensions()
if not dims:
    forms.alert("No dimensions selected.", exitscript=True)

total_changed, total_failed, failed_ids = 0, 0, []
with revit.Transaction("{} Dimensions".format(ACTION), doc=doc):
    for d in dims:
        c, f = set_lock(d)
        total_changed += c
        total_failed += f
        if f:
            failed_ids.append(d.Id)

msg = "{}ed {} dimension segment(s) on {} dimension(s).".format(ACTION, total_changed, len(dims))
if total_failed:
    msg += "\n\n{} segment(s) could not be {}ed (e.g. references not lockable, " \
           "or locking would over-constrain the model). Those dimensions are now selected.".format(
               total_failed, ACTION.lower())
    revit.get_selection().set_to(failed_ids)
forms.alert(msg, title="{} Dimension".format(ACTION))
