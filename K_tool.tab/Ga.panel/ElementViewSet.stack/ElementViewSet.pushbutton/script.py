# -*- coding: utf-8 -*-
"""
Element View Set

For each selected element, create a set of views centred on the
element's centroid:
    - an isometric 3D view cropped by a section box,
    - a floor plan cut through the centroid,
    - a long section and a cross section through the centroid.

In every created view, everything except the element is hidden and a
filter hides the markers of views whose name does not contain the
element's type name. Views are named <TypeName>_<KIND>
(e.g. W310x39_SEC1), with a _01, _02... suffix if the name is taken.

Compatible with IronPython 2.7 and CPython 3 (pyRevit), Revit 2024+.
"""

from System.Collections.Generic import List
from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import revit, DB, forms, script


doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()


# ============================================================
# SETTINGS
# ============================================================

# Default offset around each element, in millimetres
DEFAULT_OFFSET_MM = 1000.0

# Smallest offset accepted, in millimetres
MIN_OFFSET_MM = 50.0

# True  -> each view shows all selected elements
# False -> each view shows only its own element
ISOLATE_ALL_SELECTED = False

# Browser organization parameters (set only if they exist on views)
VIEW_GROUP_PARAM = "View Group"
VIEW_GROUP_VALUE = "ELEMENT CHECK"
VIEW_SUBGROUP_PARAM = "View Sub Group"   # set to the type name

# Prefix of the "hide unrelated view markers" filter
MARKER_FILTER_PREFIX = "VIEWS_ViewName_NOT CONTAINS_"

# View-marker categories controlled by that filter
MARKER_CATEGORIES = [
    DB.BuiltInCategory.OST_Sections,
    DB.BuiltInCategory.OST_Viewers,
]

# After the run: open the first N created views, close all others
OPEN_VIEW_LIMIT = 4
CLOSE_OTHER_VIEWS = True

# View kinds: key -> (label, name suffix)
VIEW_KINDS = [
    ("3D", "3D view (section box)", "3D"),
    ("PLAN", "Floor plan (cut at centroid)", "PLAN"),
    ("SEC1", "Section 1 - along element", "SEC1"),
    ("SEC2", "Section 2 - across element", "SEC2"),
]

PROHIBITED_NAME_CHARS = [
    "\\", ":", "{", "}", "[", "]", "|", ";", "<", ">", "?", "`", "~"
]


# ============================================================
# GENERAL HELPERS
# ============================================================

def mm_to_internal(value_mm):
    """Convert millimetres to Revit internal feet."""
    return DB.UnitUtils.ConvertToInternalUnits(
        value_mm, DB.UnitTypeId.Millimeters
    )


def id_value(element_id):
    """ElementId -> int, across API versions."""
    if hasattr(element_id, "Value"):
        return element_id.Value
    return element_id.IntegerValue


def to_id_list(ids):
    return List[DB.ElementId](list(ids))


def normalize_or_none(vector):
    try:
        if vector is None or vector.GetLength() < 1e-6:
            return None
        return vector.Normalize()
    except Exception:
        return None


def clean_name(value):
    """Replace characters Revit forbids in view / filter names."""
    if not value:
        return ""
    result = value.strip()
    for character in PROHIBITED_NAME_CHARS:
        result = result.replace(character, "-")
    return result[:200].strip()


def get_existing_view_names():
    names = set()
    for view in DB.FilteredElementCollector(doc).OfClass(DB.View):
        try:
            names.add(view.Name)
        except Exception:
            pass
    return names


def unique_name(base_name, existing_names):
    base_name = clean_name(base_name) or "VIEW"
    candidate = base_name
    index = 1
    while candidate in existing_names:
        candidate = "{}_{:02d}".format(base_name, index)
        index += 1
    existing_names.add(candidate)
    return candidate


def get_view_family_type(view_family):
    for vft in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if vft.ViewFamily == view_family:
            return vft
    return None


# ============================================================
# SELECTION INPUT
# ============================================================

def get_selected_elements():
    ids = list(uidoc.Selection.GetElementIds())
    if ids:
        elements = [doc.GetElement(eid) for eid in ids]
    else:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element,
                "Select one or more elements, then click Finish"
            )
        except Exception:
            script.exit()
        elements = [doc.GetElement(ref) for ref in refs]
    return [el for el in elements if el is not None]


def skip_reason(element):
    """Return why an element can't be used, or None if it is fine."""
    if isinstance(element, DB.ElementType):
        return "Element type, not an instance"
    if element.OwnerViewId != DB.ElementId.InvalidElementId:
        return "View-specific element"
    if element.get_BoundingBox(None) is None:
        return "No geometry / bounding box"
    return None


def get_related_ids(element):
    """The element plus its group members and nested sub-components."""
    ids = set([element.Id])
    if isinstance(element, DB.Group):
        ids.update(element.GetMemberIds())
    if isinstance(element, DB.FamilyInstance):
        try:
            ids.update(element.GetSubComponentIds())
        except Exception:
            pass
    if isinstance(element, DB.AssemblyInstance):
        ids.update(element.GetMemberIds())
    return ids


def get_type_name(element):
    """Type name of the element; fallback to the category name."""
    try:
        element_type = doc.GetElement(element.GetTypeId())
    except Exception:
        element_type = None

    if element_type is not None:
        for bip in (DB.BuiltInParameter.SYMBOL_NAME_PARAM,
                    DB.BuiltInParameter.ALL_MODEL_TYPE_NAME):
            try:
                param = element_type.get_Parameter(bip)
                if param and param.AsString() and param.AsString().strip():
                    return param.AsString().strip()
            except Exception:
                pass
        try:
            name = DB.Element.Name.GetValue(element_type)
        except Exception:
            name = getattr(element_type, "Name", None)
        if name:
            return name

    if element.Category is not None:
        return element.Category.Name
    return "ELEMENT"


# ============================================================
# CENTROID CALCULATION
# ============================================================

def collect_solids(geometry, solids):
    if geometry is None:
        return
    for geom_obj in geometry:
        if isinstance(geom_obj, DB.Solid):
            if geom_obj.Volume > 1e-9:
                solids.append(geom_obj)
        elif isinstance(geom_obj, DB.GeometryInstance):
            collect_solids(geom_obj.GetInstanceGeometry(), solids)


def get_centroid(element, bbox):
    """Volume-weighted centroid of the solids; fallback bbox centre."""
    options = DB.Options()
    options.ComputeReferences = False
    options.DetailLevel = DB.ViewDetailLevel.Fine

    solids = []
    try:
        collect_solids(element.get_Geometry(options), solids)
    except Exception:
        solids = []

    total_volume = 0.0
    weighted = DB.XYZ.Zero
    for solid in solids:
        try:
            centroid = solid.ComputeCentroid()
        except Exception:
            continue
        weighted = weighted.Add(centroid.Multiply(solid.Volume))
        total_volume += solid.Volume

    if total_volume > 1e-9:
        return weighted.Divide(total_volume), True

    return bbox.Min.Add(bbox.Max).Multiply(0.5), False


def bbox_corners(bbox):
    corners = []
    for x in (bbox.Min.X, bbox.Max.X):
        for y in (bbox.Min.Y, bbox.Max.Y):
            for z in (bbox.Min.Z, bbox.Max.Z):
                corners.append(DB.XYZ(x, y, z))
    return corners


def local_extents(bbox, transform):
    """Min/max of the world bbox corners in a transform's local space."""
    inverse = transform.Inverse
    points = [inverse.OfPoint(c) for c in bbox_corners(bbox)]
    lo = DB.XYZ(min(p.X for p in points),
                min(p.Y for p in points),
                min(p.Z for p in points))
    hi = DB.XYZ(max(p.X for p in points),
                max(p.Y for p in points),
                max(p.Z for p in points))
    return lo, hi


# ============================================================
# ORIENTATION
# ============================================================

def get_long_axis(element, bbox):
    """Horizontal direction of the element's long axis."""
    candidates = []

    location = getattr(element, "Location", None)
    if isinstance(location, DB.LocationCurve):
        curve = location.Curve
        candidates.append(curve.GetEndPoint(1).Subtract(curve.GetEndPoint(0)))

    try:
        candidates.append(element.HandOrientation)
    except Exception:
        pass

    for vector in candidates:
        horizontal = normalize_or_none(DB.XYZ(vector.X, vector.Y, 0))
        if horizontal is not None:
            return horizontal

    size = bbox.Max.Subtract(bbox.Min)
    return DB.XYZ.BasisX if size.X >= size.Y else DB.XYZ.BasisY


# ============================================================
# VIEW CREATION
# ============================================================

def create_3d_view(vft_3d, bbox, offset):
    view = DB.View3D.CreateIsometric(doc, vft_3d.Id)
    box = DB.BoundingBoxXYZ()
    box.Min = bbox.Min.Subtract(DB.XYZ(offset, offset, offset))
    box.Max = bbox.Max.Add(DB.XYZ(offset, offset, offset))
    view.IsSectionBoxActive = True
    view.SetSectionBox(box)
    return view


def get_levels():
    levels = list(DB.FilteredElementCollector(doc).OfClass(DB.Level))
    return sorted(levels, key=lambda lvl: lvl.ProjectElevation)


def pick_level(element, centroid_z, levels):
    """Element's own level if it is below the centroid, else nearest below."""
    tolerance = 1e-4
    level_ids = [element.LevelId]
    for bip_name in ("FAMILY_LEVEL_PARAM",
                     "INSTANCE_REFERENCE_LEVEL_PARAM",
                     "SCHEDULE_LEVEL_PARAM",
                     "WALL_BASE_CONSTRAINT",
                     "LEVEL_PARAM"):
        bip = getattr(DB.BuiltInParameter, bip_name, None)
        if bip is None:
            continue
        try:
            param = element.get_Parameter(bip)
            if param and param.StorageType == DB.StorageType.ElementId:
                level_ids.append(param.AsElementId())
        except Exception:
            pass

    for level_id in level_ids:
        level = doc.GetElement(level_id) if level_id else None
        if isinstance(level, DB.Level) and \
                level.ProjectElevation <= centroid_z + tolerance:
            return level

    below = [l for l in levels if l.ProjectElevation <= centroid_z + tolerance]
    if below:
        return below[-1]
    return levels[0] if levels else None


def create_plan_view(vft_plan, level, bbox, centroid, offset):
    view = DB.ViewPlan.Create(doc, vft_plan.Id, level.Id)
    view.ViewTemplateId = DB.ElementId.InvalidElementId

    # --- View range: cut plane through the centroid ---
    level_z = level.ProjectElevation
    cut = centroid.Z - level_z
    top = max(bbox.Max.Z - level_z + offset, cut + 0.1)
    bottom = min(bbox.Min.Z - level_z - offset, cut - 0.1)

    view_range = view.GetViewRange()
    for plane in (DB.PlanViewPlane.TopClipPlane,
                  DB.PlanViewPlane.BottomClipPlane,
                  DB.PlanViewPlane.ViewDepthPlane):
        try:
            view_range.SetLevelId(plane, level.Id)
        except Exception:
            pass
    view_range.SetOffset(DB.PlanViewPlane.TopClipPlane, top)
    view_range.SetOffset(DB.PlanViewPlane.CutPlane, cut)
    view_range.SetOffset(DB.PlanViewPlane.BottomClipPlane, bottom)
    view_range.SetOffset(DB.PlanViewPlane.ViewDepthPlane, bottom)
    view.SetViewRange(view_range)

    # --- Crop box: element bbox in XY + offset ---
    crop = view.CropBox
    lo, hi = local_extents(bbox, crop.Transform)
    new_crop = DB.BoundingBoxXYZ()
    new_crop.Transform = crop.Transform
    new_crop.Min = DB.XYZ(lo.X - offset, lo.Y - offset, crop.Min.Z)
    new_crop.Max = DB.XYZ(hi.X + offset, hi.Y + offset, crop.Max.Z)
    view.CropBoxActive = True
    view.CropBox = new_crop
    return view


def create_section_view(vft_section, bbox, centroid, direction, offset):
    """
    Section whose transform origin is the centroid.
    BasisX = direction, BasisY = Z up, BasisZ = BasisX x BasisY
    (BasisZ points toward the viewer; cut plane at local Z = 0).
    """
    basis_x = direction
    basis_y = DB.XYZ.BasisZ
    basis_z = basis_x.CrossProduct(basis_y)

    transform = DB.Transform.Identity
    transform.Origin = centroid
    transform.BasisX = basis_x
    transform.BasisY = basis_y
    transform.BasisZ = basis_z

    lo, hi = local_extents(bbox, transform)

    box = DB.BoundingBoxXYZ()
    box.Transform = transform
    box.Min = DB.XYZ(lo.X - offset, lo.Y - offset, min(lo.Z, 0.0) - offset)
    box.Max = DB.XYZ(hi.X + offset, hi.Y + offset, 0.0)

    view = DB.ViewSection.CreateSection(doc, vft_section.Id, box)
    view.ViewTemplateId = DB.ElementId.InvalidElementId
    align_section_to_point(view, centroid)
    return view


def cut_plane_distance(view, point):
    """Signed distance from the section's cut plane to a point."""
    return point.Subtract(view.Origin).DotProduct(view.ViewDirection)


def find_section_marker(view):
    for marker in (DB.FilteredElementCollector(doc)
                   .OfCategory(DB.BuiltInCategory.OST_Viewers)
                   .WhereElementIsNotElementType()):
        param = marker.get_Parameter(DB.BuiltInParameter.VIEW_NAME)
        if param and param.AsString() == view.Name:
            return marker
    return None


def align_section_to_point(view, point):
    """
    Move the section along its view direction so its cut plane passes
    exactly through `point`. A section's cut plane contains view.Origin
    and is normal to view.ViewDirection, so this measures where Revit
    actually put it, whatever it did with the section box Z range.
    """
    doc.Regenerate()
    distance = cut_plane_distance(view, point)
    if abs(distance) < 1e-6:
        return

    move = view.ViewDirection.Multiply(distance)
    try:
        DB.ElementTransformUtils.MoveElement(doc, view.Id, move)
    except Exception:
        marker = find_section_marker(view)
        if marker is None:
            raise Exception("Could not move section onto the centroid")
        DB.ElementTransformUtils.MoveElement(doc, marker.Id, move)
    doc.Regenerate()


# ============================================================
# ISOLATION FILTERS
# ============================================================

def create_not_contains_rule(param_id, value):
    try:
        return DB.ParameterFilterRuleFactory.CreateNotContainsRule(
            param_id, value)
    except TypeError:
        return DB.ParameterFilterRuleFactory.CreateNotContainsRule(
            param_id, value, False)


def get_filterable_marker_category_ids():
    filterable = set(
        id_value(cid)
        for cid in DB.ParameterFilterUtilities.GetAllFilterableCategories()
    )
    result = []
    for bic in MARKER_CATEGORIES:
        cid = DB.ElementId(bic)
        if id_value(cid) in filterable:
            result.append(cid)
    return result


_marker_filter_cache = {}


def get_marker_filter(type_name, category_ids):
    """Reuse or create VIEWS_ViewName_NOT CONTAINS_<TypeName>. None if impossible."""
    if type_name in _marker_filter_cache:
        return _marker_filter_cache[type_name]

    filter_name = clean_name(MARKER_FILTER_PREFIX + type_name)
    found = None
    for pfe in DB.FilteredElementCollector(doc).OfClass(
            DB.ParameterFilterElement):
        if pfe.Name == filter_name:
            found = pfe
            break

    if found is None and category_ids:
        try:
            rule = create_not_contains_rule(
                DB.ElementId(DB.BuiltInParameter.VIEW_NAME), type_name)
            found = DB.ParameterFilterElement.Create(
                doc, filter_name, to_id_list(category_ids),
                DB.ElementParameterFilter(rule))
        except Exception:
            found = None

    _marker_filter_cache[type_name] = found
    return found


def hide_unrelated_markers_manually(view, type_name):
    """Fallback: hide markers whose view name lacks the type name."""
    to_hide = []
    for bic in MARKER_CATEGORIES:
        markers = (DB.FilteredElementCollector(doc, view.Id)
                   .OfCategory(bic)
                   .WhereElementIsNotElementType())
        for marker in markers:
            param = marker.get_Parameter(DB.BuiltInParameter.VIEW_NAME)
            name = param.AsString() if param else None
            if name and type_name not in name and marker.CanBeHidden(view):
                to_hide.append(marker.Id)
    if to_hide:
        view.HideElements(to_id_list(to_hide))


def isolate_in_view(view, keep_ids):
    """Hide every element in the view except keep_ids and view markers."""
    keep = set(id_value(i) for i in keep_ids)
    marker_cats = set(id_value(DB.ElementId(b)) for b in MARKER_CATEGORIES)

    to_hide = []
    collector = (DB.FilteredElementCollector(doc, view.Id)
                 .WhereElementIsNotElementType())
    for el in collector:
        if id_value(el.Id) in keep:
            continue
        if el.Category is not None and \
                id_value(el.Category.Id) in marker_cats:
            continue
        try:
            if el.CanBeHidden(view):
                to_hide.append(el.Id)
        except Exception:
            pass

    if to_hide:
        view.HideElements(to_id_list(to_hide))
    return len(to_hide)


def apply_marker_filter(view, type_name, marker_category_ids):
    pfe = get_marker_filter(type_name, marker_category_ids)
    if pfe is not None:
        try:
            if pfe.Id not in view.GetFilters():
                view.AddFilter(pfe.Id)
            view.SetFilterVisibility(pfe.Id, False)
            return "filter"
        except Exception:
            pass
    hide_unrelated_markers_manually(view, type_name)
    return "hidden"


# ============================================================
# VIEW ORGANIZATION
# ============================================================

def set_text_param(view, param_name, value):
    param = view.LookupParameter(param_name)
    if param is None or param.IsReadOnly or \
            param.StorageType != DB.StorageType.String:
        return False
    param.Set(value)
    return True


# ============================================================
# MAIN
# ============================================================

elements = get_selected_elements()
if not elements:
    forms.alert("No elements were selected.", exitscript=True)

# --- Options ---
kind_by_label = dict((label, key) for key, label, _s in VIEW_KINDS)
kind_items = [
    forms.TemplateListItem(label, checked=True)
    for _k, label, _s in VIEW_KINDS
]
chosen = forms.SelectFromList.show(
    kind_items,
    title="Element View Set - views to create",
    multiselect=True,
    button_name="Next",
)
if not chosen:
    script.exit()
chosen_kinds = set(kind_by_label[label] for label in chosen)

offset_text = forms.ask_for_string(
    default=str(int(DEFAULT_OFFSET_MM)),
    prompt="Offset around each element (mm):",
    title="Element View Set",
)
if offset_text is None:
    script.exit()
try:
    offset_mm = max(float(offset_text), MIN_OFFSET_MM)
except ValueError:
    forms.alert("Invalid offset: {}".format(offset_text), exitscript=True)
OFFSET = mm_to_internal(offset_mm)

# --- View family types ---
vft_3d = get_view_family_type(DB.ViewFamily.ThreeDimensional)
vft_plan = (get_view_family_type(DB.ViewFamily.FloorPlan)
            or get_view_family_type(DB.ViewFamily.StructuralPlan))
vft_section = get_view_family_type(DB.ViewFamily.Section)

missing = []
if "3D" in chosen_kinds and vft_3d is None:
    missing.append("3D")
if "PLAN" in chosen_kinds and vft_plan is None:
    missing.append("Floor/Structural plan")
if chosen_kinds & set(["SEC1", "SEC2"]) and vft_section is None:
    missing.append("Section")
if missing:
    forms.alert("No view family type found for: {}".format(", ".join(missing)),
                exitscript=True)

# --- Prepare element data ---
targets = []
skipped = []
for el in elements:
    reason = skip_reason(el)
    if reason:
        skipped.append((el, reason))
    else:
        targets.append(el)

if not targets:
    forms.alert("None of the selected elements can be used.", exitscript=True)

all_selected_ids = set()
for el in targets:
    all_selected_ids.update(get_related_ids(el))

levels = get_levels()
existing_names = get_existing_view_names()
suffix_by_kind = dict((k, s) for k, _l, s in VIEW_KINDS)

created = []    # dicts: element, type_name, kind, view, centroid_from_solid
failures = []   # (element, message)
browser_param_missing = False

with revit.Transaction("Create element view sets"):

    marker_category_ids = get_filterable_marker_category_ids()

    # ---------- Pass 1: create views ----------
    for el in targets:
        bbox = el.get_BoundingBox(None)
        centroid, from_solid = get_centroid(el, bbox)
        type_name = clean_name(get_type_name(el)) or "ELEMENT"
        long_axis = get_long_axis(el, bbox)
        cross_axis = DB.XYZ.BasisZ.CrossProduct(long_axis)

        for kind, _label, _suffix in VIEW_KINDS:
            if kind not in chosen_kinds:
                continue

            sub = DB.SubTransaction(doc)
            try:
                sub.Start()

                if kind == "3D":
                    view = create_3d_view(vft_3d, bbox, OFFSET)
                elif kind == "PLAN":
                    level = pick_level(el, centroid.Z, levels)
                    if level is None:
                        raise Exception("No level found in the project")
                    view = create_plan_view(
                        vft_plan, level, bbox, centroid, OFFSET)
                elif kind == "SEC1":
                    view = create_section_view(
                        vft_section, bbox, centroid, long_axis, OFFSET)
                else:
                    view = create_section_view(
                        vft_section, bbox, centroid, cross_axis, OFFSET)

                try:
                    view.ViewTemplateId = DB.ElementId.InvalidElementId
                except Exception:
                    pass

                view.Name = unique_name(
                    "{}_{}".format(type_name, suffix_by_kind[kind]),
                    existing_names)

                ok_group = set_text_param(view, VIEW_GROUP_PARAM,
                                          VIEW_GROUP_VALUE)
                set_text_param(view, VIEW_SUBGROUP_PARAM, type_name)
                if not ok_group:
                    browser_param_missing = True

                sub.Commit()
                created.append({
                    "element": el,
                    "type_name": type_name,
                    "kind": kind,
                    "view": view,
                    "from_solid": from_solid,
                    "cut_mm": (
                        round(DB.UnitUtils.ConvertFromInternalUnits(
                            abs(cut_plane_distance(view, centroid)),
                            DB.UnitTypeId.Millimeters), 1)
                        if kind in ("SEC1", "SEC2") else "-"),
                })
            except Exception as error:
                if sub.GetStatus() == DB.TransactionStatus.Started:
                    sub.RollBack()
                failures.append((el, "{}: {}".format(kind, error)))

    doc.Regenerate()

    # ---------- Pass 2: isolation + marker filters ----------
    # Done after every view exists, so markers of all new views are known.
    for item in created:
        view = item["view"]
        el = item["element"]
        keep_ids = all_selected_ids if ISOLATE_ALL_SELECTED \
            else get_related_ids(el)

        sub = DB.SubTransaction(doc)
        try:
            sub.Start()
            item["hidden"] = isolate_in_view(view, keep_ids)
            item["markers"] = apply_marker_filter(
                view, item["type_name"], marker_category_ids)
            sub.Commit()
        except Exception as error:
            if sub.GetStatus() == DB.TransactionStatus.Started:
                sub.RollBack()
            item["hidden"] = "-"
            item["markers"] = "failed"
            failures.append((el, "isolate {}: {}".format(item["kind"], error)))


# ============================================================
# OPEN VIEWS (outside the transaction)
# ============================================================

opened_ids = set()
for item in created[:OPEN_VIEW_LIMIT]:
    try:
        uidoc.ActiveView = item["view"]
        opened_ids.add(id_value(item["view"].Id))
    except Exception:
        pass

if CLOSE_OTHER_VIEWS and opened_ids:
    for ui_view in list(uidoc.GetOpenUIViews()):
        if id_value(ui_view.ViewId) not in opened_ids:
            try:
                ui_view.Close()
            except Exception:
                pass


# ============================================================
# REPORT
# ============================================================

output.print_md("# Element View Set")
output.print_md(
    "**Elements:** {} used, {} skipped &nbsp;|&nbsp; **Views created:** {} "
    "&nbsp;|&nbsp; **Failures:** {} &nbsp;|&nbsp; **Offset:** {} mm".format(
        len(targets), len(skipped), len(created), len(failures),
        int(offset_mm)))

if created:
    rows = []
    for item in created:
        rows.append([
            output.linkify(item["element"].Id),
            item["type_name"],
            item["kind"],
            output.linkify(item["view"].Id, item["view"].Name),
            "solid" if item["from_solid"] else "bbox",
            item["cut_mm"],
            item.get("hidden", "-"),
            item.get("markers", "-"),
        ])
    output.print_table(
        table_data=rows,
        columns=["Element", "Type name", "Kind", "View", "Centroid",
                 "Cut to centroid (mm)", "Hidden elems", "Markers"],
        title="Created views")

if skipped:
    output.print_table(
        table_data=[[output.linkify(e.Id), r] for e, r in skipped],
        columns=["Element", "Reason"],
        title="Skipped elements")

if failures:
    output.print_table(
        table_data=[[output.linkify(e.Id), m] for e, m in failures],
        columns=["Element", "Error"],
        title="Failures")

if browser_param_missing:
    output.print_md(
        "> **Note:** views have no writable text parameter `{}`. Add it as a "
        "project parameter (category Views) and group the Project Browser by "
        "it to collect these views together.".format(VIEW_GROUP_PARAM))
