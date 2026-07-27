# -*- coding: utf-8 -*-
"""
Array elements along a spline curve in Revit.
Copies selected elements at equal intervals along a picked spline,
aligning each copy to the tangent direction of the curve at that point.
"""

import math
import clr
clr.AddReference('System')
from System.Collections.Generic import List as CsList
from pyrevit import revit, DB, UI
from pyrevit import forms

doc = revit.doc
uidoc = revit.uidoc


# ---------------------------------------------------------------------------
# Helper: get the tangent angle (in XY plane) of a curve at a given parameter
# ---------------------------------------------------------------------------
def get_tangent_angle(curve, param):
    """Return the rotation angle (radians) of the curve tangent at normalized parameter."""
    point = curve.Evaluate(param, True)
    derivative = curve.ComputeDerivatives(param, True)
    tangent = derivative.BasisX  # tangent vector at that point
    return math.atan2(tangent.Y, tangent.X)


# ---------------------------------------------------------------------------
# Helper: build a rotation Transform about Z-axis around an origin point
# ---------------------------------------------------------------------------
def rotation_transform(origin, angle):
    """Create a Transform that rotates by `angle` radians around the Z-axis at `origin`."""
    axis = DB.XYZ.BasisZ
    t = DB.Transform.CreateRotationAtPoint(axis, angle, origin)
    return t


# ---------------------------------------------------------------------------
# STEP 1 – Ask user to select one or more elements
# ---------------------------------------------------------------------------
try:
    selection = uidoc.Selection.PickObjects(
        UI.Selection.ObjectType.Element,
        "Select one or more elements to array along the spline."
    )
    if not selection:
        forms.alert("No elements selected. Script cancelled.", exitscript=True)
except Exception as e:
    forms.alert("Element selection cancelled or failed:\n{}".format(str(e)), exitscript=True)

selected_ids = [ref.ElementId for ref in selection]

# ---------------------------------------------------------------------------
# STEP 2 – Ask user to pick the spline / curve element
# ---------------------------------------------------------------------------
try:
    curve_ref = uidoc.Selection.PickObject(
        UI.Selection.ObjectType.Element,
        "Pick a spline or curve element to array along."
    )
    curve_elem = doc.GetElement(curve_ref.ElementId)
except Exception as e:
    forms.alert("Curve selection cancelled or failed:\n{}".format(str(e)), exitscript=True)

# Extract the geometry curve from the element
geo_curve = None
if isinstance(curve_elem, DB.ModelCurve):
    geo_curve = curve_elem.GeometryCurve
elif isinstance(curve_elem, DB.DetailCurve):
    geo_curve = curve_elem.GeometryCurve
elif hasattr(curve_elem, "GeometryCurve"):
    geo_curve = curve_elem.GeometryCurve
else:
    # Try to get the first curve from geometry
    try:
        geom_opts = DB.Options()
        geom = curve_elem.get_Geometry(geom_opts)
        for geo_obj in geom:
            if isinstance(geo_obj, DB.Curve):
                geo_curve = geo_obj.Tessellate()
                break
    except Exception:
        pass

if geo_curve is None:
    forms.alert(
        "Selected element does not contain a usable curve.\n"
        "Please pick a ModelCurve, DetailCurve, or similar curve element.",
        exitscript=True
    )

# ---------------------------------------------------------------------------
# STEP 3 – Ask user for the spacing distance along the spline
# ---------------------------------------------------------------------------
try:
    dist_input = forms.ask_for_string(
        prompt="Enter the spacing distance between copies (in project units, e.g. feet):",
        title="Array Spacing",
        default="5"
    )
    if dist_input is None:
        forms.alert("No distance entered. Script cancelled.", exitscript=True)
    spacing = float(dist_input)
    if spacing <= 0:
        raise ValueError("Distance must be positive.")
except ValueError as e:
    forms.alert("Invalid distance value:\n{}".format(str(e)), exitscript=True)

# Determine how many copies fit along the curve
curve_length = geo_curve.Length
num_copies = int(math.floor(curve_length / spacing))

if num_copies < 1:
    forms.alert(
        "Spacing ({:.3f}) is larger than the curve length ({:.3f}).\n"
        "No copies can be placed.".format(spacing, curve_length),
        exitscript=True
    )

# ---------------------------------------------------------------------------
# STEP 4 – Compute placement points and tangent angles along the spline
# ---------------------------------------------------------------------------
placement_data = []  # list of (XYZ point, rotation angle in radians)

for i in range(1, num_copies + 1):
    # Normalised parameter along curve (0.0 = start, 1.0 = end)
    norm_param = (i * spacing) / curve_length
    if norm_param > 1.0:
        break
    point = geo_curve.Evaluate(norm_param, True)
    angle = get_tangent_angle(geo_curve, norm_param)
    placement_data.append((point, angle))

# Tangent angle at the origin (start of curve) – used as reference
origin_angle = get_tangent_angle(geo_curve, 0.0)

# ---------------------------------------------------------------------------
# STEP 5 – Get bounding box centre of original selection (used as copy origin)
# ---------------------------------------------------------------------------
def get_elements_centroid(elem_ids):
    """Approximate centroid from bounding boxes of all selected elements."""
    pts = []
    for eid in elem_ids:
        elem = doc.GetElement(eid)
        bb = elem.get_BoundingBox(None)
        if bb:
            pts.append((bb.Min + bb.Max) * 0.5)
    if not pts:
        return DB.XYZ.Zero
    cx = sum(p.X for p in pts) / len(pts)
    cy = sum(p.Y for p in pts) / len(pts)
    cz = sum(p.Z for p in pts) / len(pts)
    return DB.XYZ(cx, cy, cz)

source_centroid = get_elements_centroid(selected_ids)

# ---------------------------------------------------------------------------
# STEP 6 – Copy and place elements in a single Transaction
# ---------------------------------------------------------------------------
with revit.Transaction("Array Elements Along Spline"):
    for point, angle in placement_data:
        # --- 6a. Copy the original elements to the target point ---
        try:
            translation = point - source_centroid
            id_list = CsList[DB.ElementId](selected_ids)
            copied_ids = DB.ElementTransformUtils.CopyElements(
                doc,
                id_list,
                translation
            )
        except Exception as copy_err:
            # Skip placements that fail (unsupported element type, etc.)
            forms.alert(
                "Failed to copy element(s) to point ({:.2f}, {:.2f}, {:.2f}):\n{}".format(
                    point.X, point.Y, point.Z, str(copy_err)
                )
            )
            continue

        # --- 6b. Rotate copied elements to align with the spline tangent ---
        delta_angle = angle - origin_angle  # rotation relative to source orientation
        if abs(delta_angle) > 1e-9:
            try:
                copied_list = CsList[DB.ElementId](copied_ids)
                DB.ElementTransformUtils.RotateElements(
                    doc,
                    copied_list,
                    DB.Line.CreateBound(point, point + DB.XYZ.BasisZ),
                    delta_angle
                )
            except Exception as rot_err:
                # Rotation failure is non-fatal – leave element in place
                print("Warning: could not rotate copy at ({:.2f},{:.2f}):\n{}".format(
                    point.X, point.Y, str(rot_err)
                ))

print("Done. {} cop{} placed along the spline.".format(
    len(placement_data),
    "y" if len(placement_data) == 1 else "ies"
))
