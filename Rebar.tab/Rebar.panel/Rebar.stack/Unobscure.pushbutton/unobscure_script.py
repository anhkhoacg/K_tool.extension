__doc__ = "Make all bars Unobscured in view."
__title__ = "UNObscure Bars"
__author__ = "Khoa LE"



import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import *

doc = __revit__.ActiveUIDocument.Document
view = doc.ActiveView

# Collect rebar elements visible in current view
rebar_collector = list(FilteredElementCollector(doc, view.Id).OfClass(Rebar))

t = Transaction(doc, "ObscuredBars")
t.Start()
for rebar in rebar_collector:
    rebar.SetUnobscuredInView(view, True)
t.Commit()
