__doc__ = "Make all bars obscured in view."
__title__ = "Obscure Bars"
__author__ = "Khoa LE"
__helpurl__ = ""



import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')
from Autodesk.Revit.DB import *
from Autodesk.Revit.DB.Structure import *

doc = __revit__.ActiveUIDocument.Document
view = doc.ActiveView

# Collect rebar elements visible in current view
rebar_list = list(FilteredElementCollector(doc, view.Id).OfClass(Rebar))


t = Transaction(doc, "ObscuredBars")
t.Start()
for rebar in rebar_list:
    rebar.SetUnobscuredInView(view, False)
t.Commit()
