"""Create Dimension Lines between Grids."""

__title__ = 'Dimension\nGrids'
__doc__ = 'Create dimension lines between selected grid lines in the current view.'
__author__ = 'Khoa Le (at) Haskoning', 'Copilot'
__tooltip__ = 'Select grid lines to automatically create dimensions between them and overall line.'

from Autodesk.Revit import Exceptions
from Autodesk.Revit.UI.Selection import ISelectionFilter
from pyrevit import revit, DB, forms
from pyrevit.compat import get_elementid_value_func

# set the active Revit application and document
app = __revit__.Application
doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument
active_view = doc.ActiveView

get_elementid_value = get_elementid_value_func()


# Selection Filter
class CustomISelectionFilter(ISelectionFilter):
    def __init__(self, cat):
        self.cat = cat

    def AllowElement(self, e):
        if get_elementid_value(e.Category.Id) == int(self.cat):
            return True
        else:
            return False

    @staticmethod
    def AllowReference(ref, point):
        return True


active_view = revit.active_view  # the current active view
is_plan = True  # Separate condition if the view is a Plan View or Elevetaion/Section

if doc.GetElement(active_view.GetTypeId()).FamilyName == 'Floor Plan':
    is_plan = True
else:
    is_plan = False

with forms.WarningBar(title="Pick Parallel grid lines"):
    try:
        grids = uidoc.Selection.PickElementsByRectangle(CustomISelectionFilter(DB.BuiltInCategory.OST_Grids),
                                                        "Select Grids")
    except Exceptions.OperationCanceledException:
        forms.alert("Cancelled", ok=True, exitscript=True)

# Terminate early if no grids were selected
if not grids:
    forms.alert("No grids selected.", ok=True, exitscript=True)

# Filter out curved grids and store grid data
grid_data = []
direction = None
for gr in grids:
    if gr.IsCurved:
        continue
    crv = gr.Curve
    p = crv.GetEndPoint(0)
    q = crv.GetEndPoint(1)
    v = p - q
    up = DB.XYZ.BasisZ
    direction = up.CrossProduct(v)
    grid_data.append((gr, direction, p, q))

if len(grid_data) < 2:
    forms.alert("At least 2 straight grids required.", ok=True, exitscript=True)

# Create first reference array with all grids
all_ref_array = DB.ReferenceArray()
for gr, _, _, _ in grid_data:
    ref = DB.Reference.ParseFromStableRepresentation(doc, gr.UniqueId)
    all_ref_array.Append(ref)

# Find the 2 furthest grid lines
max_distance = 0
furthest_pair = (grid_data[0], grid_data[1])

for i in range(len(grid_data)):
    for j in range(i + 1, len(grid_data)):
        gr1, dir1, p1, q1 = grid_data[i]
        gr2, dir2, p2, q2 = grid_data[j]

        # Calculate distance between the two grid lines
        # Use the distance from midpoint of grid1 to midpoint of grid2
        mid1 = (p1 + q1) * 0.5
        mid2 = (p2 + q2) * 0.5
        distance = mid1.DistanceTo(mid2)

        if distance > max_distance:
            max_distance = distance
            furthest_pair = (grid_data[i], grid_data[j])

# Create second reference array with only the 2 furthest grid lines
furthest_ref_array = DB.ReferenceArray()
for grid_item in furthest_pair:
    gr, _, _, _ = grid_item
    ref = DB.Reference.ParseFromStableRepresentation(doc, gr.UniqueId)
    furthest_ref_array.Append(ref)

# Condion: Elevation/Section
if not is_plan:
    with revit.Transaction("Dim Grids Sketch Plane", doc=doc):
        origin = active_view.Origin
        direction = active_view.ViewDirection

        plane = DB.Plane.CreateByNormalAndOrigin(direction, origin)
        sp = DB.SketchPlane.Create(doc, plane)

        active_view.SketchPlane = sp
        doc.Regenerate

# Pick the placement point
with forms.WarningBar(title="Pick Point"):
    try:
        pick_point = revit.uidoc.Selection.PickPoint()
    except Exceptions.OperationCanceledException:
        forms.alert("Cancelled", ok=True, exitscript=True)

# Create the first dim line
if is_plan:
    line1 = DB.Line.CreateBound(pick_point, pick_point + direction * 100)
else:
    line1 = DB.Line.CreateBound(pick_point, pick_point + DB.XYZ.BasisX * 100)

# Create the second dim line offset above the first
offset_distance = 15  # Offset distance in feet for the second dimension
if is_plan:
    offset_point = pick_point + direction * 100 + direction.Normalize() * offset_distance
    line2 = DB.Line.CreateBound(offset_point, offset_point + direction * 100)
else:
    offset_point = pick_point + DB.XYZ.BasisX * 100 + DB.XYZ.BasisY * offset_distance
    line2 = DB.Line.CreateBound(offset_point, offset_point + DB.XYZ.BasisX * 100)

# Create both dimensions
with revit.Transaction("Dim Grids", doc=revit.doc):
    revit.doc.Create.NewDimension(active_view, line1, all_ref_array)
    revit.doc.Create.NewDimension(active_view, line2, furthest_ref_array)
