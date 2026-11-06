# -*- coding: utf-8 -*-
"""Add Multi-Rebar Annotations to every applicable rebar set in the active view."""

__title__ = "Multi Rebar\nAnnotation"
__author__ = "Khoa Le"
__doc__ = "Add a Multi-Rebar Annotation to each applicable rebar set in the active view " \
          "(or the pre-selected rebars). Shift+Click for a preview without changes."

from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc
view = revit.active_view
output = script.get_output()

PREVIEW_ONLY = EXEC_PARAMS.config_mode  # Shift+Click = dry run

# Placement, in paper millimetres (scaled by the view scale)
DIM_OFFSET_MM = 6.0   # gap between the rebar set and the dimension line
TAG_OFFSET_MM = 6.0   # gap between the dimension line and the tag head

# Distribution must lie in the view plane: |dir . viewDir| below this
IN_PLANE_TOL = 0.01

ANNOTATABLE_VIEWS = (
    DB.ViewType.FloorPlan,
    DB.ViewType.CeilingPlan,
    DB.ViewType.EngineeringPlan,
    DB.ViewType.AreaPlan,
    DB.ViewType.Section,
    DB.ViewType.Elevation,
    DB.ViewType.Detail,
)


# --------------------------------------------------------------------------- helpers
def eid_int(eid):
    """ElementId -> int for both Revit <2024 (IntegerValue) and 2024+ (Value)."""
    try:
        return eid.Value
    except AttributeError:
        return eid.IntegerValue


def type_name(el):
    try:
        return DB.Element.Name.GetValue(el)
    except Exception:
        p = el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        return p.AsString() if p else "Type {}".format(eid_int(el.Id))


def mm_on_paper(mm):
    """Paper millimetres -> model feet at the active view scale."""
    return mm / 304.8 * view.Scale


def project_to_view_plane(pt):
    vd = view.ViewDirection
    return pt - vd.Multiply((pt - view.Origin).DotProduct(vd))


def distribution_direction(rebar):
    """Direction in which the bars of the set are spread, or None."""
    try:
        if rebar.IsRebarShapeDriven():
            path = rebar.GetShapeDrivenAccessor().GetDistributionPath()
            return path.Direction
    except Exception:
        pass
    # Free-form or unknown: compare first and last bar centerlines
    try:
        n = rebar.NumberOfBarPositions
        opt = DB.Structure.MultiplanarOption.IncludeOnlyPlanarCurves
        c0 = rebar.GetCenterlineCurves(False, False, False, opt, 0)[0]
        cn = rebar.GetCenterlineCurves(False, False, False, opt, n - 1)[0]
        delta = cn.GetEndPoint(0) - c0.GetEndPoint(0)
        if delta.GetLength() > 1e-6:
            return delta.Normalize()
    except Exception:
        pass
    return None


def annotated_rebar_ids():
    """Ids of rebars already referenced by a Multi-Rebar Annotation in this view."""
    ids = set()
    mras = DB.FilteredElementCollector(doc, view.Id).OfClass(DB.MultiReferenceAnnotation)
    for mra in mras:
        dim = doc.GetElement(mra.DimensionId)
        if dim is None:
            continue
        for ref in dim.References:
            ids.add(eid_int(ref.ElementId))
    return ids


def placement(rebar, direction):
    """(dimension line origin, tag head position) next to the rebar set, or None."""
    bb = rebar.get_BoundingBox(view)
    if bb is None:
        return None
    vd = view.ViewDirection
    perp = vd.CrossProduct(direction).Normalize()
    # Place annotations above / to the right of the set
    if abs(perp.DotProduct(view.UpDirection)) > 1e-6:
        if perp.DotProduct(view.UpDirection) < 0:
            perp = perp.Negate()
    elif perp.DotProduct(view.RightDirection) < 0:
        perp = perp.Negate()

    center = project_to_view_plane((bb.Min + bb.Max) * 0.5)
    corners = [DB.XYZ(x, y, z)
               for x in (bb.Min.X, bb.Max.X)
               for y in (bb.Min.Y, bb.Max.Y)
               for z in (bb.Min.Z, bb.Max.Z)]
    half_extent = max((project_to_view_plane(c) - center).DotProduct(perp) for c in corners)

    dim_origin = center + perp.Multiply(half_extent + mm_on_paper(DIM_OFFSET_MM))
    tag_head = dim_origin + perp.Multiply(mm_on_paper(TAG_OFFSET_MM))
    return dim_origin, tag_head


# --------------------------------------------------------------------------- checks
if view is None or view.IsTemplate or view.ViewType not in ANNOTATABLE_VIEWS:
    forms.alert("Open a plan, section, elevation or detail view first.\n"
                "Multi-Rebar Annotations cannot be placed in 3D views, sheets or schedules.",
                exitscript=True)

# Scope: pre-selected rebars, otherwise every rebar visible in the view
selected = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
rebars = [e for e in selected if isinstance(e, DB.Structure.Rebar)]
scope = "selected"
if not rebars:
    scope = "in view"
    rebars = list(DB.FilteredElementCollector(doc, view.Id)
                  .OfClass(DB.Structure.Rebar)
                  .WhereElementIsNotElementType())
if not rebars:
    forms.alert("No rebar found in the active view.", exitscript=True)

# Multi-Rebar Annotation types that reference the Structural Rebar category
rebar_cat = eid_int(DB.ElementId(DB.BuiltInCategory.OST_Rebar))
mra_types = []
for t in DB.FilteredElementCollector(doc).OfClass(DB.MultiReferenceAnnotationType):
    try:
        if eid_int(t.ReferenceCategoryId) != rebar_cat:
            continue
    except Exception:
        pass
    mra_types.append(t)
if not mra_types:
    forms.alert("No Multi-Rebar Annotation type found in this model.\n"
                "Create one under Annotate > Tag > Multi-Rebar Annotation type properties.",
                exitscript=True)

# --------------------------------------------------------------------------- classify
already = annotated_rebar_ids()
applicable, skipped = [], []   # applicable: (rebar, direction); skipped: (rebar, reason)
for rb in rebars:
    if eid_int(rb.Id) in already:
        skipped.append((rb, "already annotated"))
        continue
    if rb.NumberOfBarPositions < 2:
        skipped.append((rb, "single bar (needs a set of 2+)"))
        continue
    d = distribution_direction(rb)
    if d is None:
        skipped.append((rb, "distribution direction unknown"))
        continue
    if abs(d.DotProduct(view.ViewDirection)) > IN_PLANE_TOL:
        skipped.append((rb, "distributed out of the view plane"))
        continue
    vd = view.ViewDirection
    applicable.append((rb, (d - vd.Multiply(d.DotProduct(vd))).Normalize()))


def print_report(created, failed):
    output.print_md("## Multi-Rebar Annotation ({} rebar {})".format(len(rebars), scope))
    if PREVIEW_ONLY:
        output.print_md("**Preview only** - nothing was created.")
        rows = [[output.linkify(rb.Id), "would annotate"] for rb, _ in applicable]
    else:
        rows = [[output.linkify(rb.Id), "annotated"] for rb in created]
        rows += [[output.linkify(rb.Id), "failed: {}".format(msg)] for rb, msg in failed]
    rows += [[output.linkify(rb.Id), "skipped: {}".format(why)] for rb, why in skipped]
    output.print_table(rows, columns=["Rebar", "Result"])


if PREVIEW_ONLY:
    print_report([], [])
    script.exit()

if not applicable:
    print_report([], [])
    forms.alert("None of the {} rebar {} can take a Multi-Rebar Annotation.\n"
                "See the output window for reasons.".format(len(rebars), scope),
                exitscript=True)

# --------------------------------------------------------------------------- type choice
by_name = {}
for t in mra_types:
    by_name["{}  [Id {}]".format(type_name(t), eid_int(t.Id))] = t
if len(by_name) == 1:
    mra_type = mra_types[0]
else:
    picked = forms.SelectFromList.show(sorted(by_name.keys()),
                                       title="Multi-Rebar Annotation type",
                                       button_name="Annotate {} set(s)".format(len(applicable)),
                                       width=500)
    if not picked:
        script.exit()
    mra_type = by_name[picked]

# --------------------------------------------------------------------------- create
created, failed = [], []
with revit.Transaction("Multi-Rebar Annotations"):
    for rb, d in applicable:
        pos = placement(rb, d)
        if pos is None:
            failed.append((rb, "no bounding box in view"))
            continue
        dim_origin, tag_head = pos

        sub = DB.SubTransaction(doc)
        sub.Start()
        try:
            opts = DB.MultiReferenceAnnotationOptions(mra_type)
            opts.SetElementsToDimension(List[DB.ElementId]([rb.Id]))
            opts.DimensionPlaneNormal = view.ViewDirection
            opts.DimensionLineDirection = d
            opts.DimensionLineOrigin = dim_origin
            opts.TagHeadPosition = tag_head
            opts.TagHasLeader = True
            DB.MultiReferenceAnnotation.Create(doc, view.Id, opts)
            sub.Commit()
            created.append(rb)
        except Exception as ex:
            sub.RollBack()
            failed.append((rb, str(ex).splitlines()[0] if str(ex) else type(ex).__name__))

if failed or skipped:
    print_report(created, failed)
summary = "{} annotated, {} skipped, {} failed".format(len(created), len(skipped), len(failed))
try:
    forms.toast(summary, title="Multi-Rebar Annotation")
except Exception:
    print(summary)
