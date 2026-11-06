
__title__ = 'Flip Grids'
__doc__ = 'Flip the selected grid bubble in the current view.'
__author__ = 'Khoa Le (at) Haskoning', 'Copilot'
__tooltip__ = 'Select grid lines to cycle between on/off bubble.'

from Autodesk.Revit import Exceptions
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import forms, revit, DB
from pyrevit.compat import get_elementid_value_func


get_elementid_value = get_elementid_value_func()


class GridSelectionFilter(ISelectionFilter):
    def AllowElement(self, element):
        return bool(
            element.Category
            and get_elementid_value(element.Category.Id) == int(DB.BuiltInCategory.OST_Grids)
        )

    @staticmethod
    def AllowReference(reference, point):
        return False

# Set the active Revit application and document
doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView
# Select multiple objects
objects = revit.get_selection()
# filter the grids of the selection
grids = [obj for obj in objects if isinstance(obj, DB.Grid)]

# Check if grids are selected
if not grids:
    with forms.WarningBar(title='Pick Grids'):
        try:
            picked_refs = uidoc.Selection.PickObjects(
                ObjectType.Element, GridSelectionFilter(), 'Select grids'
            )
        except Exceptions.OperationCanceledException:
            forms.alert('Cancelled', ok=True, exitscript=True)
    grids = [doc.GetElement(reference.ElementId) for reference in picked_refs]

if not grids:
    forms.alert('No Grids selected!', ok=True, exitscript=True)
end_0 = []
end_1 = []
# Enumerate through the selected grids
with revit.Transaction('Flip Grids'):
    for grid in grids:
        # Define Ends
        end_0 = grid.IsBubbleVisibleInView(DB.DatumEnds.End0, active_view)
        end_1 = grid.IsBubbleVisibleInView(DB.DatumEnds.End1, active_view)

        # Special rule: if both are visible, show End0
        if end_0 and end_1:
            grid.ShowBubbleInView(DB.DatumEnds.End0, active_view)
            grid.HideBubbleInView(DB.DatumEnds.End1, active_view)
            continue

        if end_0:
            grid.HideBubbleInView(DB.DatumEnds.End0, active_view)
        else:
            grid.ShowBubbleInView(DB.DatumEnds.End0, active_view)

        if end_1:
            grid.HideBubbleInView(DB.DatumEnds.End1, active_view)
        else:
            grid.ShowBubbleInView(DB.DatumEnds.End1, active_view)
