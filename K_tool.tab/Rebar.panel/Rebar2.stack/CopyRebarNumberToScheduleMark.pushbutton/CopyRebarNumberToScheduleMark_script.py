import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit import DB
from pyrevit import forms


def copy_rebar_number_to_schedule_mark():
    """Copy Rebar Number parameter values to Schedule Mark parameter for all bars in view."""
    doc = __revit__.ActiveUIDocument.Document
    uidoc = __revit__.ActiveUIDocument

    # Collect all rebar in current view
    collector = DB.FilteredElementCollector(doc, doc.ActiveView.Id)
    rebars = collector.OfCategory(DB.BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElements()

    if not rebars:
        forms.alert("No rebar elements found in current view.", title="No Rebar")
        return

    # CORRECT parameter definition - using REBARNUMBER
    rebar_num_param = DB.BuiltInParameter.REBAR_NUMBER
    schedule_mark_param = DB.BuiltInParameter.REBAR_ELEM_SCHEDULE_MARK

    # Verify parameters exist
    sample_rebar = rebars[0]
    if not sample_rebar.get_Parameter(rebar_num_param):
        forms.alert("Rebar Number parameter not found on rebar elements.",
                    title="Parameter Error")
        return

    if not sample_rebar.get_Parameter(schedule_mark_param):
        forms.alert("Schedule Mark parameter not found on rebar elements.",
                    title="Parameter Error")
        return

    # Start transaction
    t = DB.Transaction(doc, "Copy Rebar Number to Schedule Mark")
    t.Start()

    try:
        count = 0
        for rebar in rebars:
            # Get Rebar Number value
            rebar_num = rebar.get_Parameter(rebar_num_param).AsString()

            if rebar_num:
                # Set Schedule Mark value
                rebar.get_Parameter(schedule_mark_param).Set(rebar_num)
                count += 1

        t.Commit()
        forms.alert("Successfully updated {} rebar elements.".format(count),
                    title="Operation Complete")
    except Exception as e:
        t.RollBack()
        forms.alert("Error: {}".format(str(e)), title="Operation Failed")


if __name__ == "__main__":
    copy_rebar_number_to_schedule_mark()
