# -*- coding: utf-8 -*-
"""Place model lines (3D cross) at the centroid of selected elements."""

__title__ = "Centroid"
__author__ = "Khoa Le"
__doc__ = "Place a 3D cross of model lines at the centroid of each selected element. " \
          "Shift+Click to place a single marker at the combined centroid."

from Autodesk.Revit import Exceptions
from Autodesk.Revit.UI.Selection import ObjectType
from pyrevit import revit, DB, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc

COMBINED = EXEC_PARAMS.config_mode   # Shift+Click -> one marker for all elements
MARKER_SIZE_MM = 500.0               # full length of each arm of the cross
HALF = MARKER_SIZE_MM / 304.8 / 2.0  # half length in feet (internal units)
MIN_VOLUME = 1e-9


def iter_solids(geom):
    """Yield all solids with volume from a GeometryElement (recurses into instances)."""
    if geom is None:
        return
    for g in geom:
        if isinstance(g, DB.Solid):
            if g.Volume > MIN_VOLUME:
                yield g
        elif isinstance(g, DB.GeometryInstance):
            # GetInstanceGeometry is already transformed to model coordinates
            for s in iter_solids(g.GetInstanceGeometry()):
                yield s


def element_centroid(el):
    """Return (XYZ centroid, volume). Volume is 0 when bbox fallback was used."""
    opts = DB.Options()
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    opts.IncludeNonVisibleObjects = False

    total_v = 0.0
    acc = DB.XYZ.Zero
    try:
        for s in iter_solids(el.get_Geometry(opts)):
            v = s.Volume
            acc = acc + s.ComputeCentroid().Multiply(v)
            total_v += v
    except Exception:
        total_v = 0.0

    if total_v > MIN_VOLUME:
        return acc.Divide(total_v), total_v

    # Fallback: bounding-box centre
    bb = el.get_BoundingBox(None)
    if bb is None:
        return None, 0.0
    return (bb.Min + bb.Max).Multiply(0.5), 0.0


def get_elements():
    selected = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    if selected:
        return selected
    with forms.WarningBar(title="Select elements (Finish when done)"):
        try:
            refs = uidoc.Selection.PickObjects(ObjectType.Element, "Select elements")
        except Exceptions.OperationCanceledException:
            script.exit()
    return [doc.GetElement(r) for r in refs]


def make_line(p, direction, normal):
    """Create a model line through p along direction on a plane with given normal."""
    a = p - direction.Multiply(HALF)
    b = p + direction.Multiply(HALF)
    plane = DB.Plane.CreateByNormalAndOrigin(normal, p)
    sp = DB.SketchPlane.Create(doc, plane)
    return doc.Create.NewModelCurve(DB.Line.CreateBound(a, b), sp)


def place_marker(p):
    """3D cross: X and Y arms on a horizontal plane, Z arm on a vertical plane."""
    return [
        make_line(p, DB.XYZ.BasisX, DB.XYZ.BasisZ),
        make_line(p, DB.XYZ.BasisY, DB.XYZ.BasisZ),
        make_line(p, DB.XYZ.BasisZ, DB.XYZ.BasisX),
    ]


# ---------------------------------------------------------------- main
elements = get_elements()
if not elements:
    forms.alert("No elements selected.", exitscript=True)

results = []   # (element, centroid, volume)
skipped = []
for el in elements:
    c, v = element_centroid(el)
    if c is None:
        skipped.append(el)
    else:
        results.append((el, c, v))

if not results:
    forms.alert("Could not compute a centroid for any selected element.", exitscript=True)

if COMBINED:
    # Volume-weighted if every element has a solid, otherwise plain average
    if all(v > MIN_VOLUME for _, _, v in results):
        tot = sum(v for _, _, v in results)
        acc = DB.XYZ.Zero
        for _, c, v in results:
            acc = acc + c.Multiply(v)
        points = [acc.Divide(tot)]
    else:
        acc = DB.XYZ.Zero
        for _, c, _ in results:
            acc = acc + c
        points = [acc.Divide(len(results))]
else:
    points = [c for _, c, _ in results]

new_ids = []
with revit.Transaction("Place Centroid Markers", doc=doc):
    for p in points:
        for mc in place_marker(p):
            new_ids.append(mc.Id)

# Report
# output = script.get_output()
# to_mm = lambda x: x * 304.8
# output.print_md("### Centroid markers")
# if COMBINED:
#     p = points[0]
#     output.print_md("Combined centroid of **{}** element(s): ({:.1f}, {:.1f}, {:.1f}) mm".format(
#         len(results), to_mm(p.X), to_mm(p.Y), to_mm(p.Z)))
# else:
#     rows = []
#     for el, c, v in results:
#         rows.append([output.linkify(el.Id), el.Category.Name if el.Category else "-",
#                      "{:.1f}".format(to_mm(c.X)), "{:.1f}".format(to_mm(c.Y)),
#                      "{:.1f}".format(to_mm(c.Z)),
#                      "Solid" if v > MIN_VOLUME else "BBox"])
#     output.print_table(rows, columns=["Element", "Category", "X (mm)", "Y (mm)", "Z (mm)", "Method"])
# if skipped:
#     output.print_md("**Skipped (no geometry):** {}".format(
#         ", ".join(output.linkify(e.Id) for e in skipped)))
#
# revit.get_selection().set_to(new_ids)
