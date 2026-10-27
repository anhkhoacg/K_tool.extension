# -*- coding: utf-8 -*-
__title__ = 'Filter By Type Name'
__author__ = 'Khoa le'
__doc__ = """Select one element, then create/apply a view filter that hides every other
            element of the same category whose Type Name is different from the
            selected element's type name.

            Filter name pattern: "<Category>_<TypeName>_not equal"
            Author: Khoa.Le @Haskoning"""

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import (
    BuiltInParameter,
    ElementId,
    FilteredElementCollector,
    ParameterFilterElement,
    ParameterFilterRuleFactory,
    ElementParameterFilter,
    Transaction,
)
from Autodesk.Revit.UI.Selection import ObjectType
from System.Collections.Generic import List

from pyrevit import revit, forms

doc = revit.doc
uidoc = revit.uidoc


def create_not_equals_rule(param_id, value):
    """Handle the Revit-version differences in CreateNotEqualsRule's signature."""
    try:
        return ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, value)
    except TypeError:
        return ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, value, False)


try:
    ref = uidoc.Selection.PickObject(ObjectType.Element, "Select one element")
except Exception:
    forms.alert("No element selected. Script cancelled.", exitscript=True)

elem = doc.GetElement(ref)
if elem is None:
    forms.alert("Could not resolve the selected element.", exitscript=True)

category = elem.Category
if category is None:
    forms.alert("Selected element has no category.", exitscript=True)

elem_type = doc.GetElement(elem.GetTypeId())
if elem_type is None:
    forms.alert("Could not find a type for the selected element.", exitscript=True)

type_name = elem_type.get_Parameter(BuiltInParameter.ALL_MODEL_TYPE_NAME).AsString() or elem_type.Name

filter_name = "{}_{}_not equal".format(category.Name, type_name)

param_id = ElementId(BuiltInParameter.ALL_MODEL_TYPE_NAME)
rule = create_not_equals_rule(param_id, type_name)
elem_filter = ElementParameterFilter(rule)
categories = List[ElementId]([category.Id])

t = Transaction(doc, "Create and apply type name filter")
t.Start()
try:
    existing = next((f for f in FilteredElementCollector(doc).OfClass(ParameterFilterElement)
                      if f.Name == filter_name), None)
    if existing is not None:
        existing.SetCategories(categories)
        existing.SetElementFilter(elem_filter)
        filter_elem = existing
    else:
        filter_elem = ParameterFilterElement.Create(doc, filter_name, categories, elem_filter)

    view = doc.ActiveView
    if filter_elem.Id not in view.GetFilters():
        view.AddFilter(filter_elem.Id)
    view.SetFilterVisibility(filter_elem.Id, False)

    t.Commit()
except Exception:
    t.RollBack()
    raise

#forms.alert("Filter '{}' applied and hidden in the current view.".format(filter_name), title="Done")
