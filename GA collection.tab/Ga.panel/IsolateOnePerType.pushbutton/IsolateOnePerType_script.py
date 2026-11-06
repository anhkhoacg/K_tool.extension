# -*- coding: utf-8 -*-
"""Temporarily isolate one element of each type in the active view."""

__title__ = "Isolate One\nPer Type"
__author__ = "Khoa Le"
__doc__ = "Temporarily isolate one element of each type in the active view. " \
          "Pre-select to limit to those types. Shift+Click to also select them."

from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script, EXEC_PARAMS

doc = revit.doc
uidoc = revit.uidoc
view = doc.ActiveView

SELECT_RESULT = EXEC_PARAMS.config_mode  # Shift+Click -> also select isolated elements


def eid(element_id):
    """Integer id that works on Revit 2024+ (Value) and older (IntegerValue)."""
    return getattr(element_id, "Value", None) or element_id.IntegerValue


def is_candidate(el):
    """Model elements that have a type (skips annotations, views, sketches...)."""
    if el is None or el.Category is None:
        return False
    if el.Category.CategoryType != DB.CategoryType.Model:
        return False
    if el.ViewSpecific:
        return False
    return el.GetTypeId() != DB.ElementId.InvalidElementId


def type_label(type_id):
    t = doc.GetElement(type_id)
    if t is None:
        return "-", "-"
    family = getattr(t, "FamilyName", "") or "-"
    name = DB.Element.Name.GetValue(t)
    return family, name


# ---------------------------------------------------------------- checks
if not view.CanUseTemporaryVisibilityModes():
    forms.alert("The active view does not support temporary hide/isolate.", exitscript=True)

view_elements = [e for e in DB.FilteredElementCollector(doc, view.Id)
                 .WhereElementIsNotElementType()
                 if is_candidate(e)]

# Limit to the types of pre-selected elements, if any
selected = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
wanted_types = set(eid(e.GetTypeId()) for e in selected if is_candidate(e))
if wanted_types:
    view_elements = [e for e in view_elements if eid(e.GetTypeId()) in wanted_types]

if not view_elements:
    forms.alert("No typed model elements found in the active view.", exitscript=True)

# ---------------------------------------------------------------- group by type
by_type = {}   # type id int -> [elements]
for e in view_elements:
    by_type.setdefault(eid(e.GetTypeId()), []).append(e)

# Prefer a pre-selected element as the representative, else lowest id
selected_ids = set(eid(e.Id) for e in selected if e is not None)
keep = []
rows = []
for tid, elems in by_type.items():
    elems.sort(key=lambda x: (eid(x.Id) not in selected_ids, eid(x.Id)))
    rep = elems[0]
    keep.append(rep.Id)
    family, name = type_label(rep.GetTypeId())
    rows.append((rep.Category.Name, family, name, len(elems), rep.Id))

ids = List[DB.ElementId](keep)
with revit.Transaction("Isolate One Element Per Type", doc=doc):
    view.IsolateElementsTemporary(ids)

if SELECT_RESULT:
    revit.get_selection().set_to(keep)

# ---------------------------------------------------------------- report
#output = script.get_output()
#rows.sort(key=lambda r: (r[0], r[1], r[2]))
#output.print_md("### Isolated {} element(s), one per type, in view **{}**".format(len(keep), view.Name))
#output.print_table(
#    [[c, f, n, cnt, output.linkify(i)] for c, f, n, cnt, i in rows],
#    columns=["Category", "Family", "Type", "Count in view", "Isolated element"])
