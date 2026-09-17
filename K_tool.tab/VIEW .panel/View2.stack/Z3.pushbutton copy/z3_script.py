__title__ = 'Filter Sections\nby View Name'
__author__ = 'Khoa le'
__doc__ = """Read the active view's name, take its first 8 letters, then create
a filter on the Views category that selects any view whose "View Name" does
NOT contain those first 8 letters. The filter is added to the active view and
set to hidden.

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
from System.Collections.Generic import List

from pyrevit import revit, forms

doc = revit.doc

# Revit filter names cannot contain these characters
INVALID_NAME_CHARS = r'[\\:{}\[\]|;<>?`~]'


def sanitize_name(name):
    return re.sub(INVALID_NAME_CHARS, '_', name)


active_view = doc.ActiveView
active_view_name = active_view.Name
name_prefix = active_view_name[:8]

if not name_prefix:
    forms.alert("Active view has no name to filter on.", title="Filter Sections by View Name")
    raise SystemExit

filter_name = sanitize_name("Sections_View Name_not contains_{}".format(name_prefix))

views_category_id = ElementId(BuiltInCategory.OST_Sections)
categories = List[ElementId]([views_category_id])

view_name_param_id = ElementId(BuiltInParameter.VIEW_NAME)
rule = ParameterFilterRuleFactory.CreateNotContainsRule(view_name_param_id, name_prefix)
elem_filter = ElementParameterFilter(List[FilterRule]([rule]))

# reuse an existing filter with the same name instead of creating a duplicate
# (Revit treats filter names as case-insensitive, so compare that way too)
def find_filter_by_name(name):
    existing_filters = FilteredElementCollector(doc).OfClass(ParameterFilterElement)
    return next((f for f in existing_filters if f.Name.lower() == name.lower()), None)


filter_elem = find_filter_by_name(filter_name)

t = Transaction(doc, "Create/Apply View Name Filter")
try:
    t.Start()
    if filter_elem is None:
        try:
            filter_elem = ParameterFilterElement.Create(doc, filter_name, categories, elem_filter)
        except Exception:
            # name collision missed by the earlier lookup - reuse the existing filter instead
            filter_elem = find_filter_by_name(filter_name)
            if filter_elem is None:
                raise

    if filter_elem.Id not in active_view.GetFilters():
        active_view.AddFilter(filter_elem.Id)
    active_view.SetFilterVisibility(filter_elem.Id, False)
    t.Commit()
except Exception as ex:
    if t.HasStarted():
        t.RollBack()
    print(ex)
    raise

#forms.alert(
#    "Filter '{}' applied to view '{}' and set to hidden.".format(filter_name, active_view_name),
#    title="Filter Sections by View Name",
#)
