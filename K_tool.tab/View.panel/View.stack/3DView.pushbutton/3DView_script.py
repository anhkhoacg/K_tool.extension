# -*- coding: utf-8 -*-

from Autodesk.Revit.UI.Selection import ObjectType

from pyrevit import revit, DB, forms, script


doc = revit.doc
uidoc = revit.uidoc
active_view = doc.ActiveView
output = script.get_output()


# ============================================================
# SETTINGS
# ============================================================

# Margin around each element, in millimetres
MARGIN_MM = 1000.0

# Minimum section-box size, in millimetres.
# Prevents an empty box for very thin or point-based elements.
MIN_BOX_SIZE_MM = 1000.0

# Used if both Type Mark and Type Name are empty
FALLBACK_PREFIX = "ELEMENT"

# Optional prefix.
# Set to "" if the view name must start directly with Type Mark.
VIEW_PREFIX = ""

# Exclude elements located inside model groups
INCLUDE_GROUPED_ELEMENTS = False

# Set to True to skip Revit links
EXCLUDE_REVIT_LINKS = True

# Set to True to skip imported CAD instances
EXCLUDE_IMPORTS = True


# ============================================================
# UNIT AND ELEMENT-ID HELPERS
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
    """
    Return an ElementId as an integer.

    Revit 2025/2026 commonly supports IntegerValue.
    Newer APIs may expose Value.
    """

    if hasattr(element_id, "Value"):
        return element_id.Value

    return element_id.IntegerValue


MARGIN = mm_to_internal(MARGIN_MM)
MIN_BOX_SIZE = mm_to_internal(MIN_BOX_SIZE_MM)


# ============================================================
# VIEW HELPERS
# ============================================================

def get_3d_view_family_type():
    """Return the first non-template 3D ViewFamilyType."""

    collector = DB.FilteredElementCollector(doc).OfClass(
        DB.ViewFamilyType
    )

    for view_family_type in collector:
        if view_family_type.ViewFamily == DB.ViewFamily.ThreeDimensional:
            return view_family_type

    return None


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
        "\\",
        ":",
        "{",
        "}",
        "[",
        "]",
        "|",
        ";",
        "<",
        ">",
        "?",
        "`",
        "~"
    ]

    for character in prohibited_characters:
        result = result.replace(character, "-")

    # Avoid excessive name length.
    # Leave space for duplicate suffixes.
    if len(result) > 230:
        result = result[:230]

    return result.strip()


def get_unique_view_name(base_name, existing_names):
    """Return a unique Revit view name."""

    base_name = clean_view_name(base_name)

    if not base_name:
        base_name = "3D VIEW"

    if base_name not in existing_names:
        existing_names.add(base_name)
        return base_name

    index = 1

    while True:

        candidate = "{}_{:02d}".format(
            base_name,
            index
        )

        if candidate not in existing_names:
            existing_names.add(candidate)
            return candidate

        index += 1


# ============================================================
# ELEMENT NAME HELPERS
# ============================================================

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

        if (
            type_id
            and type_id != DB.ElementId.InvalidElementId
        ):
            element_type = doc.GetElement(type_id)

    except Exception:
        element_type = None

    if element_type:

        # Type Mark
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

        # Type Name
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

        # ElementType.Name fallback
        try:
            if element_type.Name:
                return element_type.Name
        except Exception:
            pass

    return "{}_{}".format(
        FALLBACK_PREFIX,
        element_id_value(element.Id)
    )


def get_view_name_for_element(element):
    """Build the base view name for an element."""

    type_mark = get_type_mark(element)

    if VIEW_PREFIX:
        return "{}{}".format(
            VIEW_PREFIX,
            type_mark
        )

    return type_mark


# ============================================================
# ELEMENT FILTERING
# ============================================================

def is_valid_model_element(element):
    """Determine whether the element should receive a 3D view."""

    if element is None:
        return False

    if isinstance(element, DB.ElementType):
        return False

    if isinstance(element, DB.View):
        return False

    try:
        if element.ViewSpecific:
            return False
    except Exception:
        pass

    category = element.Category

    if category is None:
        return False

    # Only process model categories
    try:
        if category.CategoryType != DB.CategoryType.Model:
            return False
    except Exception:
        return False

    # Skip scope boxes
    try:
        if category.Id == DB.ElementId(
            DB.BuiltInCategory.OST_VolumeOfInterest
        ):
            return False
    except Exception:
        pass

    # Skip cameras
    try:
        if category.Id == DB.ElementId(
            DB.BuiltInCategory.OST_Cameras
        ):
            return False
    except Exception:
        pass

    # Skip Revit links if configured
    if EXCLUDE_REVIT_LINKS:
        try:
            if isinstance(element, DB.RevitLinkInstance):
                return False
        except Exception:
            pass

    # Skip imported CAD if configured
    if EXCLUDE_IMPORTS:
        try:
            if isinstance(element, DB.ImportInstance):
                return False
        except Exception:
            pass

    # Optionally skip grouped elements
    if not INCLUDE_GROUPED_ELEMENTS:
        try:
            if element.GroupId != DB.ElementId.InvalidElementId:
                return False
        except Exception:
            pass

    return True


# ============================================================
# BOUNDING BOX HELPERS
# ============================================================

def enlarge_axis(minimum, maximum, margin, minimum_size):
    """
    Apply margin and guarantee a minimum dimension.

    Returns:
        enlarged minimum, enlarged maximum
    """

    minimum -= margin
    maximum += margin

    current_size = maximum - minimum

    if current_size < minimum_size:

        missing_size = minimum_size - current_size
        half_missing = missing_size / 2.0

        minimum -= half_missing
        maximum += half_missing

    return minimum, maximum


def create_section_box(element):
    """
    Create an axis-aligned BoundingBoxXYZ around the element.

    The active-view bounding box is used first because the request
    applies to elements visible in that view.

    If Revit cannot return a view-specific box, the model bounding
    box is used as a fallback.
    """

    bbox = None

    try:
        bbox = element.get_BoundingBox(active_view)
    except Exception:
        bbox = None

    if bbox is None:
        try:
            bbox = element.get_BoundingBox(None)
        except Exception:
            bbox = None

    if bbox is None:
        return None

    min_x, max_x = enlarge_axis(
        bbox.Min.X,
        bbox.Max.X,
        MARGIN,
        MIN_BOX_SIZE
    )

    min_y, max_y = enlarge_axis(
        bbox.Min.Y,
        bbox.Max.Y,
        MARGIN,
        MIN_BOX_SIZE
    )

    min_z, max_z = enlarge_axis(
        bbox.Min.Z,
        bbox.Max.Z,
        MARGIN,
        MIN_BOX_SIZE
    )

    section_box = DB.BoundingBoxXYZ()

    # Element bounding boxes are normally returned in model
    # coordinates. Use an identity transform for the new box.
    section_box.Transform = DB.Transform.Identity

    section_box.Min = DB.XYZ(
        min_x,
        min_y,
        min_z
    )

    section_box.Max = DB.XYZ(
        max_x,
        max_y,
        max_z
    )

    return section_box


# ============================================================
# VALIDATION
# ============================================================

if active_view is None:
    forms.alert(
        "No active view was found.",
        exitscript=True
    )


invalid_view_types = [
    DB.ViewType.Schedule,
    DB.ViewType.DrawingSheet,
    DB.ViewType.Report,
    DB.ViewType.Internal,
    DB.ViewType.ProjectBrowser,
    DB.ViewType.SystemBrowser
]

if active_view.ViewType in invalid_view_types:
    forms.alert(
        "Open a graphical model view before running this tool.",
        exitscript=True
    )


view_family_type = get_3d_view_family_type()

if view_family_type is None:
    forms.alert(
        "No Three Dimensional ViewFamilyType was found "
        "in the current project.",
        exitscript=True
    )


# ============================================================
# SELECT ELEMENTS
# ============================================================

selected_ids = uidoc.Selection.GetElementIds()

if selected_ids:
    selected_elements = [doc.GetElement(eid) for eid in selected_ids]
else:
    try:
        references = uidoc.Selection.PickObjects(
            ObjectType.Element,
            "Select one or more elements, then click Finish"
        )
    except Exception:
        script.exit()

    selected_elements = [doc.GetElement(ref) for ref in references]

selected_elements = [
    element for element in selected_elements if element is not None
]

if not selected_elements:
    forms.alert("No elements were selected.", exitscript=True)


elements_to_process = []

for element in selected_elements:

    if not is_valid_model_element(element):
        continue

    section_box = create_section_box(element)

    if section_box is None:
        continue

    elements_to_process.append(
        (
            element,
            section_box
        )
    )


if not elements_to_process:
    forms.alert(
        "No eligible model elements with bounding boxes "
        "were found in the selection.",
        exitscript=True
    )


# ============================================================
# WARNING FOR LARGE BATCHES
# ============================================================

element_count = len(elements_to_process)

if element_count > 500:

    proceed = forms.alert(
        "{} eligible elements were found.\n\n"
        "This will create one 3D view per element and may add "
        "a very large number of views to the project.\n\n"
        "Continue?".format(element_count),
        yes=True,
        no=True,
        warn_icon=True
    )

    if not proceed:
        script.exit()


# ============================================================
# CREATE 3D VIEWS
# ============================================================

existing_view_names = get_existing_view_names()

created_views = []
failed_elements = []


with revit.Transaction(
    "Create element 3D views with section boxes"
):

    for element, section_box in elements_to_process:

        sub_transaction = DB.SubTransaction(doc)

        try:
            sub_transaction.Start()

            # Create an isometric 3D view
            new_view = DB.View3D.CreateIsometric(
                doc,
                view_family_type.Id
            )

            # Activate and apply the section box
            new_view.IsSectionBoxActive = True
            new_view.SetSectionBox(section_box)

            # Create a unique name from Type Mark
            base_view_name = get_view_name_for_element(
                element
            )

            unique_view_name = get_unique_view_name(
                base_view_name,
                existing_view_names
            )

            new_view.Name = unique_view_name

            sub_transaction.Commit()

            created_views.append(
                (
                    element,
                    new_view,
                    unique_view_name
                )
            )

        except Exception as error:

            if sub_transaction.GetStatus() == DB.TransactionStatus.Started:
                sub_transaction.RollBack()

            failed_elements.append(
                (
                    element,
                    str(error)
                )
            )


# ============================================================
# REPORT
# ============================================================

output.print_md(
    "# Element 3D views"
)

output.print_md(
    "**Source view:** {}".format(
        active_view.Name
    )
)

output.print_md(
    "**Eligible elements:** {}".format(
        len(elements_to_process)
    )
)

output.print_md(
    "**3D views created:** {}".format(
        len(created_views)
    )
)

output.print_md(
    "**Failed:** {}".format(
        len(failed_elements)
    )
)


if created_views:

    table_data = []

    for element, view_3d, view_name in created_views:

        category_name = "No category"

        try:
            if element.Category:
                category_name = element.Category.Name
        except Exception:
            pass

        table_data.append([
            output.linkify(element.Id),
            category_name,
            get_type_mark(element),
            view_name,
            output.linkify(view_3d.Id)
        ])

    output.print_table(
        table_data=table_data,
        columns=[
            "Source element",
            "Category",
            "Type Mark",
            "3D view name",
            "3D view"
        ],
        title="Created views"
    )


if failed_elements:

    failure_data = []

    for element, error_message in failed_elements:

        category_name = "No category"

        try:
            if element.Category:
                category_name = element.Category.Name
        except Exception:
            pass

        failure_data.append([
            output.linkify(element.Id),
            category_name,
            error_message
        ])

    output.print_table(
        table_data=failure_data,
        columns=[
            "Element",
            "Category",
            "Failure reason"
        ],
        title="Failed elements"
    )


forms.alert(
    "{} 3D views created.\n"
    "{} elements failed.".format(
        len(created_views),
        len(failed_elements)
    ),
    title="Create Element 3D Views",
    warn_icon=False
)