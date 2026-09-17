__title__ = 'Filter Views\nby Type Name'
__author__ = 'Khoa le'
__doc__ = """Pick one element, read its Type Name, then create a filter on the
Views category that selects any View/SectionView whose "View Name" does NOT
contain that Type Name. The filter is added to the active view and hidden.

    Author: Khoa.Le @Haskoning"""

import clr
import re

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, ParameterFilterElement,
    ParameterFilterRuleFactory, ElementParameterFilter, FilterRule, Transaction,
    FilteredElementCollector,
)
from Autodesk.Revit.UI.Selection import ObjectType
from System.Collections.Generic import List

from pyrevit import revit, forms

doc = revit.doc
uidoc = revit.uidoc

# Revit filter names cannot contain these characters
INVALID_NAME_CHARS = r'[\\:{}\[\]|;<>?`~]'


def sanitize_name(name):
    return re.sub(INVALID_NAME_CHARS, '_', name)


def get_type_name(element):
    type_id = element.GetTypeId()
    if type_id is None or type_id == ElementId.InvalidElementId:
        return None
    type_elem = doc.GetElement(type_id)
    if type_elem is None:
        return None
    return type_elem.Name


try:
    ref = uidoc.Selection.PickObject(ObjectType.Element, "Select an element")
except Exception:
    forms.alert("No element selected. Operation cancelled.", title="Filter Views by Type Name")
    raise SystemExit

selected_elem = doc.GetElement(ref)
type_name = get_type_name(selected_elem)

if not type_name:
    forms.alert("Could not determine Type Name of the selected element.", title="Filter Views by Type Name")
    raise SystemExit

active_view_name = doc.ActiveView.Name
filter_name = sanitize_name("SectionView_{}_{}_not Contains".format(active_view_name, type_name))

views_category_id = ElementId(BuiltInCategory.OST_Views)
categories = List[ElementId]([views_category_id])

view_name_param_id = ElementId(BuiltInParameter.VIEW_NAME)
rule = ParameterFilterRuleFactory.CreateNotContainsRule(view_name_param_id, type_name)
elem_filter = ElementParameterFilter(List[FilterRule]([rule]))

# reuse an existing filter with the same name instead of creating a duplicate
existing_filters = FilteredElementCollector(doc).OfClass(ParameterFilterElement)
filter_elem = next((f for f in existing_filters if f.Name == filter_name), None)

t = Transaction(doc, "Create/Apply View Name Filter")
try:
    t.Start()
    if filter_elem is None:
        filter_elem = ParameterFilterElement.Create(doc, filter_name, categories, elem_filter)

    active_view = doc.ActiveView
    if filter_elem.Id not in active_view.GetFilters():
        active_view.AddFilter(filter_elem.Id)
    active_view.SetFilterVisibility(filter_elem.Id, False)
    t.Commit()
except Exception:
    if t.HasStarted():
        t.RollBack()
    raise

forms.alert(
    "Filter '{}' applied to view '{}' and set to hidden.".format(filter_name, active_view_name),
    title="Filter Views by Type Name",
)
