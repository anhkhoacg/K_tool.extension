__title__ = "Show All Rebar"
__author__ = "Khoa Le at Haskoning"
__helpurl__ = ""
__doc__ = """Version = 1.1
Date    = 10.10.2023
_____________________________________________________________________
Description:
Show all rebar bars in current view
_____________________________________________________________________
How-to:
- Click on the button Show All Rebar.
_____________________________________________________________________
"""

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import FilteredElementCollector, BuiltInCategory, Transaction
from Autodesk.Revit.UI import TaskDialog

uidoc = __revit__.ActiveUIDocument
doc = uidoc.Document
view = doc.ActiveView

t = Transaction(doc, "Show All Rebar Bars")
t.Start()

try:
    collector = FilteredElementCollector(doc, view.Id)
    rebars = collector.OfCategory(BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElements()

    for rebar in rebars:
        try:
            bar_count = rebar.NumberOfBarPositions
            for i in range(bar_count):
                rebar.SetBarHiddenStatus(view, i, False)
        except Exception:
            continue

    t.Commit()

except Exception as e:
    t.RollBack()
    TaskDialog.Show("Error", "Failed to process bars in view {}: {}".format(view.Name, str(e)))
