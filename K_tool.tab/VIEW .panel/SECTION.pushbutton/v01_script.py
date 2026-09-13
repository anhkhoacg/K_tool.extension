# -*- coding: utf-8 -*-
"""
Prompt for one or more elements and create Cross Section,
Elevation Section and Plan (section-based) views for each,
named after the element's Type Mark.
"""

from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import revit, DB, forms, script


doc = revit.doc
uidoc = revit.uidoc
output = script.get_output()


# ============================================================
# SETTINGS
# ============================================================

# Margin around each element, in millimetres
MARGIN_MM = 500.0

# Minimum section-box size (width/height/depth), in millimetres
MIN_BOX_SIZE_MM = 500.0

# Used if both Type Mark and Type Name are empty
FALLBACK_PREFIX = "ELEMENT"

# Suffixes appended to the Type Mark for each view
CROSS_SUFFIX_1 = " - Cross Section 1"
CROSS_SUFFIX_2 = " - Cross Section 2"
ELEVATION_SUFFIX = " - Elevation Section"
PLAN_SUFFIX = " - Plan"


# ============================================================
# UNIT HELPERS
# ============================================================

def mm_to_internal(value_mm):
    """Convert millimetres to Revit internal feet."""

    try:
        return DB.UnitUtils.ConvertToInternalUnits(
            value_mm,
            DB.UnitTypeId.Millimeters
        )
    except AttributeError:
        # Revit 2020 or earlier
        return DB.UnitUtils.ConvertToInternalUnits(
            value_mm,
            DB.DisplayUnitType.DUT_MILLIMETERS
        )


def element_id_value(element_id):
    """Return an ElementId as an integer, across API versions."""

    if hasattr(element_id, "Value"):
        return element_id.Value

    return element_id.IntegerValue


MARGIN = mm_to_internal(MARGIN_MM)
MIN_BOX_SIZE = mm_to_internal(MIN_BOX_SIZE_MM)


# ============================================================
# VIEW NAME HELPERS
# ============================================================

def get_existing_view_names():
    """Collect existing project view names once."""

    names = set()

    views = (
        DB.FilteredElementCollector(doc)
        .OfClass(DB.View)
        .WhereElementIsNotElementType()
    )

    for view in views:
        try:
            names.add(view.Name)
        except Exception:
            pass

    return names


def clean_view_name(value):
    """Remove characters that Revit does not allow in view names."""

    if not value:
        return ""

    result = value.strip()

    prohibited_characters = [
        "\\", ":", "{", "}", "[", "]",
        "|", ";", "<", ">", "?", "`", "~"
    ]

    for character in prohibited_characters:
        result = result.replace(character, "-")

    if len(result) > 230:
        result = result[:230]

    return result.strip()


def get_unique_view_name(base_name, existing_names):
    """Return a unique Revit view name."""

    base_name = clean_view_name(base_name)

    if not base_name:
        base_name = "SECTION"

    if base_name not in existing_names:
        existing_names.add(base_name)
        return base_name

    index = 1

    while True:

        candidate = "{}_{:02d}".format(base_name, index)

        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate

        index += 1


def get_type_mark(element):
    """
    Get the element Type Mark.

    Naming fallback order:
    1. Type Mark
    2. Type Name
    3. Element ID
    """

    element_type = None

    try:
        type_id = element.GetTypeId()

        if type_id and type_id != DB.ElementId.InvalidElementId:
            element_type = doc.GetElement(type_id)

    except Exception:
        element_type = None

    if element_type:

        try:
            parameter = element_type.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_TYPE_MARK
            )

            if parameter:
                value = parameter.AsString()

                if value and value.strip():
                    return value.strip()

        except Exception:
            pass

        try:
            parameter = element_type.get_Parameter(
                DB.BuiltInParameter.SYMBOL_NAME_PARAM
            )

            if parameter:
                value = parameter.AsString()

                if value and value.strip():
                    return value.strip()

        except Exception:
            pass

        try:
            if element_type.Name:
                return element_type.Name
        except Exception:
            pass

    return "{}_{}".format(
        FALLBACK_PREFIX,
        element_id_value(element.Id)
    )


# ============================================================
# ORIENTATION HELPERS
# ============================================================

def normalize_or_none(vector):
    """Return a normalized XYZ, or None if the vector is degenerate."""

    try:
        if vector.GetLength() < 0.001:
            return None
        return vector.Normalize()
    except Exception:
        return None


def get_forward_direction(element):
    """
    Determine the element's own "length" direction.

    Fallback order:
    1. LocationCurve direction (walls, beams, pipes, ...)
    2. FacingOrientation (family instances)
    3. Global X axis
    """

    location = getattr(element, "Location", None)

    if isinstance(location, DB.LocationCurve):
        curve = location.Curve
        direction = normalize_or_none(
            curve.GetEndPoint(0) - curve.GetEndPoint(1)
        )
        if direction:
            return direction

    try:
        facing = element.FacingOrientation
        direction = normalize_or_none(facing)
        if direction:
            return direction
    except Exception:
        pass

    return DB.XYZ.BasisX


def make_right_handed_axes(view_dir, up_hint):
    """
    Build a right-handed (right, up, view_dir) axis set from a view
    direction and an approximate "up" hint, so that
    right x up == view_dir.
    """

    right = normalize_or_none(
        up_hint.CrossProduct(view_dir)
    ) or DB.XYZ.BasisX

    up = view_dir.CrossProduct(right)

    return right, up, view_dir


def build_view_axes(forward):
    """
    Build right-handed axis sets for the two center cross sections,
    the elevation and the plan view, based on the element's forward
    direction.

    Each entry is (right, up, view_direction), where view_direction
    is the section box BasisZ (points toward the viewer). Cross
    Section 1 and Cross Section 2 are parallel cuts through the
    element's center, viewed from opposite ends.
    """

    global_up = DB.XYZ.BasisZ

    # Guard against a forward vector that is (near) vertical
    if abs(forward.DotProduct(global_up)) > 0.999:
        forward = DB.XYZ.BasisX

    horizontal_forward = normalize_or_none(
        DB.XYZ(forward.X, forward.Y, 0)
    ) or DB.XYZ.BasisX

    side_direction = normalize_or_none(
        global_up.CrossProduct(horizontal_forward)
    ) or DB.XYZ.BasisY

    # Cross Section 1: cut plane normal is the element's length axis,
    # its trace in the plan view runs along side_direction
    #cross1_axes = make_right_handed_axes(horizontal_forward, global_up)

    # Cross Section 2: parallel to Cross Section 1 (same cut-plane
    # orientation), viewed from the opposite end, still through the
    # element's center
    cross2_axes = make_right_handed_axes(
        horizontal_forward.Negate(),
        global_up
    )

    # Elevation section: viewed from the opposite (back) face, so
    # the element's length still runs left-to-right
    elevation_axes = make_right_handed_axes(
        side_direction.Negate(),
        global_up
    )

    # Plan view: looking straight down, "up" in the view follows
    # the element's forward direction
    plan_axes = make_right_handed_axes(
        global_up.Negate(),
        horizontal_forward
    )

    return {
       # "cross1": cross1_axes,
        "cross2": cross2_axes,
        "elevation": elevation_axes,
        "plan": plan_axes,
    }


# ============================================================
# SECTION BOX HELPERS
# ============================================================

def get_world_bounding_box(element):
    """Return the element's model-space bounding box, if any."""

    try:
        return element.get_BoundingBox(None)
    except Exception:
        return None


def get_bbox_corners(bbox):
    """Return the 8 corners of a world-aligned bounding box."""

    corners = []

    for x in (bbox.Min.X, bbox.Max.X):
        for y in (bbox.Min.Y, bbox.Max.Y):
            for z in (bbox.Min.Z, bbox.Max.Z):
                corners.append(DB.XYZ(x, y, z))

    return corners


def enlarge_axis(minimum, maximum, margin, minimum_size):
    """Apply margin and guarantee a minimum dimension."""

    minimum -= margin
    maximum += margin

    current_size = maximum - minimum

    if current_size < minimum_size:
        missing_size = minimum_size - current_size
        half_missing = missing_size / 2.0
        minimum -= half_missing
        maximum += half_missing

    return minimum, maximum


def build_section_box(element, world_bbox, axes):
    """
    Build a BoundingBoxXYZ oriented along the given (right, up,
    view_direction) axes, sized to fit the element with margin.
    """

    right, up, view_dir = axes

    center = (world_bbox.Min + world_bbox.Max) / 2.0

    transform = DB.Transform.Identity
    transform.Origin = center
    transform.BasisX = right
    transform.BasisY = up
    transform.BasisZ = view_dir

    inverse = transform.Inverse

    local_min = None
    local_max = None

    for corner in get_bbox_corners(world_bbox):
        local_point = inverse.OfPoint(corner)

        if local_min is None:
            local_min = local_point
            local_max = local_point
            continue

        local_min = DB.XYZ(
            min(local_min.X, local_point.X),
            min(local_min.Y, local_point.Y),
            min(local_min.Z, local_point.Z)
        )
        local_max = DB.XYZ(
            max(local_max.X, local_point.X),
            max(local_max.Y, local_point.Y),
            max(local_max.Z, local_point.Z)
        )

    min_x, max_x = enlarge_axis(local_min.X, local_max.X, MARGIN, MIN_BOX_SIZE)
    min_y, max_y = enlarge_axis(local_min.Y, local_max.Y, MARGIN, MIN_BOX_SIZE)

    # Keep some visual depth in front of and behind the element
    min_z, max_z = enlarge_axis(local_min.Z, local_max.Z, MARGIN, MIN_BOX_SIZE)

    section_box = DB.BoundingBoxXYZ()
    section_box.Transform = transform
    section_box.Min = DB.XYZ(min_x, min_y, min_z)
    section_box.Max = DB.XYZ(max_x, max_y, max_z)

    return section_box


def get_section_view_family_type():
    """Return the first ViewFamilyType belonging to the Section family."""

    collector = DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)

    for view_family_type in collector:
        if view_family_type.ViewFamily == DB.ViewFamily.Section:
            return view_family_type

    return None


# ============================================================
# SELECTION
# ============================================================

selected_ids = uidoc.Selection.GetElementIds()

if selected_ids:
    elements = [doc.GetElement(eid) for eid in selected_ids]
else:
    try:
        references = uidoc.Selection.PickObjects(
            ObjectType.Element,
            "Select one or more elements, then click Finish"
        )
    except Exception:
        script.exit()

    elements = [doc.GetElement(ref) for ref in references]

elements = [element for element in elements if element is not None]

if not elements:
    forms.alert("No elements were selected.", exitscript=True)


section_view_family_type = get_section_view_family_type()

if section_view_family_type is None:
    forms.alert(
        "No Section ViewFamilyType was found in the current project.",
        exitscript=True
    )


# ============================================================
# CREATE VIEWS
# ============================================================

existing_view_names = get_existing_view_names()

created_views = []
failed_elements = []


with revit.Transaction("Create sections from selected elements"):

    for element in elements:

        world_bbox = get_world_bounding_box(element)

        if world_bbox is None:
            failed_elements.append((element, "No bounding box available"))
            continue

        type_mark = get_type_mark(element)
        forward = get_forward_direction(element)
        axes_by_kind = build_view_axes(forward)

        view_specs = [
           # ("cross1", CROSS_SUFFIX_1),
            ("cross2", CROSS_SUFFIX_2),
            ("elevation", ELEVATION_SUFFIX),
            ("plan", PLAN_SUFFIX),
        ]

        for kind, suffix in view_specs:

            sub_transaction = DB.SubTransaction(doc)

            try:
                sub_transaction.Start()

                section_box = build_section_box(
                    element,
                    world_bbox,
                    axes_by_kind[kind]
                )

                new_view = DB.ViewSection.CreateSection(
                    doc,
                    section_view_family_type.Id,
                    section_box
                )

                unique_view_name = get_unique_view_name(
                    "{}{}".format(type_mark, suffix),
                    existing_view_names
                )

                new_view.Name = unique_view_name

                sub_transaction.Commit()

                created_views.append((element, new_view, unique_view_name))

            except Exception as error:

                if sub_transaction.GetStatus() == DB.TransactionStatus.Started:
                    sub_transaction.RollBack()

                failed_elements.append((
                    element,
                    "{}: {}".format(kind, error)
                ))


# ============================================================
# REPORT
# ============================================================

output.print_md("# Sections created from selection")
output.print_md("**Selected elements:** {}".format(len(elements)))
output.print_md("**Views created:** {}".format(len(created_views)))
output.print_md("**Failed:** {}".format(len(failed_elements)))


if created_views:

    table_data = []

    for element, view, view_name in created_views:
        table_data.append([
            output.linkify(element.Id),
            get_type_mark(element),
            view_name,
            output.linkify(view.Id)
        ])

    output.print_table(
        table_data=table_data,
        columns=["Source element", "Type Mark", "View name", "View"],
        title="Created views"
    )


if failed_elements:

    failure_data = []

    for element, error_message in failed_elements:
        failure_data.append([
            output.linkify(element.Id),
            error_message
        ])

    output.print_table(
        table_data=failure_data,
        columns=["Element", "Failure reason"],
        title="Failed elements"
    )


forms.alert(
    "{} views created.\n{} failures.".format(
        len(created_views),
        len(failed_elements)
    ),
    title="Create Sections from Selection",
    warn_icon=False
)
