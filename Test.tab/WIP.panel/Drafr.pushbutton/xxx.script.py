__title__ = "Multi Rebar Annotation"
__doc__ = (
    """Bulk create MultiRebar Annotation of all rebar on active view.
    -----------------------------------------------
    1. Select the Multi rebar annotation type.
    2. Select direction: Horizontal or Vertical.
    Rebars are grouped by Rebar Number; one annotation per group.
    """)
__author__ = "khoa.le at Haskoning.com"

import re
from collections import defaultdict
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

doc = revit.doc
uidoc = revit.uidoc
view = revit.active_view
active_view_id = view.Id

output = script.get_output()
output.close_others()

output.print_md("# Multi-Rebar Annotation - Auto Placement")
output.print_md("**Active View:** `{}`".format(view.Name))

if view is None:
    raise Exception("No active view found.")

# 1. Collect all Rebar elements visible in the active view
rebar_list = list(
    DB.FilteredElementCollector(doc, view.Id)
    .OfClass(DB.Structure.Rebar)
    .WhereElementIsNotElementType()
)

output.print_md("**Total Rebars Found:** {}".format(len(rebar_list)))

if not rebar_list:
    raise Exception("There are no rebars in the view!")

# 2. Group rebars by Rebar Number
groups = defaultdict(list)
for rebar in rebar_list:
    try:
        param = rebar.LookupParameter("Rebar Number")
        key = param.AsString() if param and param.AsString() else str(rebar.Id.IntegerValue)
    except Exception:
        key = str(rebar.Id.IntegerValue)
    groups[key].append(rebar)

output.print_md("**Rebar Groups (by Rebar Number):** {}".format(len(groups)))

# 3. Find and select a MultiReferenceAnnotationType
mra_types = sorted(
    list(
        DB.FilteredElementCollector(doc)
        .OfClass(DB.MultiReferenceAnnotationType)
        .WhereElementIsElementType()
    ),
    key=lambda t: (t.Name.lower(), int(t.Id.IntegerValue))
)
if not mra_types:
    raise Exception("No MultiReferenceAnnotationType found in the document.")

def _safe_name(el):
    try:
        return el.Name
    except Exception:
        pass
    try:
        p = el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p:
            val = p.AsString()
            if val:
                return val
    except Exception:
        pass
    try:
        return "TypeId:{}".format(int(el.Id.IntegerValue))
    except Exception:
        return "<unnamed>"

choices = ["{0} (Id:{1})".format(_safe_name(t), int(t.Id.IntegerValue)) for t in mra_types]
sel = forms.SelectFromList.show(choices, title="Select MultiReferenceAnnotationType", width=500)
if not sel:
    raise SystemExit

sel_str = sel if isinstance(sel, str) else (sel[0] if len(sel) else None)
selected_type = None
if sel_str:
    m = re.search(r"Id:(-?\d+)", sel_str)
    if m:
        sel_id = int(m.group(1))
        selected_type = next((t for t in mra_types if int(t.Id.IntegerValue) == sel_id), None)

if selected_type is None:
    raise Exception("Selected MultiReferenceAnnotationType not found.")

output.print_md("**Using Annotation Type:** `{}` (id: {})".format(
    _safe_name(selected_type), selected_type.Id.IntegerValue))

# 4. Get annotation position from UIView zoom corners
ui_view = None
for uv in uidoc.GetOpenUIViews():
    if uv.ViewId.IntegerValue == active_view_id.IntegerValue:
        ui_view = uv
        break

if ui_view:
    p1, p2 = ui_view.GetZoomCorners()
    center_VIEW = (p1 + p2) * 0.5
else:
    output.print_md("_Warning: No UIView found. Using origin as fallback._")
    center_VIEW = DB.XYZ(0, 0, 0)

# 5. Select annotation direction
ops_out = forms.CommandSwitchWindow.show(['Horizontal', 'Vertical'], message='Select Annotation Direction')
if not ops_out:
    raise SystemExit

if ops_out == 'Horizontal':
    lineDirection = view.RightDirection
else:
    lineDirection = view.UpDirection

try:
    lineDirection = lineDirection.Normalize()
except Exception:
    pass

# 6. Create annotations inside a Transaction
created = 0
skipped = 0

with revit.Transaction("Create_RebarGroup_Annotations"):
    dimension_spacing = 4.0 * float(view.Scale) / 308.4
    distribute_direction = view.ViewDirection.CrossProduct(lineDirection)
    try:
        distribute_direction = distribute_direction.Normalize()
    except Exception:
        distribute_direction = view.UpDirection

    for i, (rebar_number, rebar_group) in enumerate(groups.items()):
        rebar_ids = List[DB.ElementId]([r.Id for r in rebar_group])
        if not rebar_ids:
            skipped += 1
            continue

        offset = distribute_direction * (i * dimension_spacing)
        options = DB.MultiReferenceAnnotationOptions(selected_type)
        options.TagHasLeader = True
        options.TagHeadPosition = center_VIEW + offset
        options.DimensionLineOrigin = center_VIEW + offset
        options.DimensionLineDirection = lineDirection
        options.DimensionPlaneNormal = view.ViewDirection
        options.SetElementsToDimension(rebar_ids)

        try:
            DB.MultiReferenceAnnotation.Create(doc, view.Id, options)
            output.print_md("  + Group **{}** - {} rebar(s) annotated.".format(rebar_number, len(rebar_group)))
            created += 1
        except Exception as e:
            output.print_md("  - Group **{}** - failed: `{}`. Skipped.".format(rebar_number, e))
            skipped += 1

# 7. Summary
output.print_md("---")
output.print_md("**Done.** Annotations created: **{}** | Skipped: **{}**".format(created, skipped))