# -*- coding: utf-8 -*-
__title__ = "Delete Worksets"
__author__ = "Khoa Le"
__doc__ = "Delete selected worksets, deleting their elements or moving them to another workset"

from pyrevit import revit, DB, forms, script

doc = revit.doc

OPT_MOVE = "Move elements to another workset"
OPT_DELETE = "Delete elements"

# DeleteWorkset API is only available from Revit 2022
if not hasattr(DB, "DeleteWorksetSettings"):
    forms.alert("Deleting worksets requires Revit 2022 or newer.", title="Script cancelled")
    script.exit()


def count_elements(workset):
    return DB.FilteredElementCollector(doc) \
        .WherePasses(DB.ElementWorksetFilter(workset.Id, False)) \
        .GetElementCount()


# Collect all user worksets, sorted by name
worksets = DB.FilteredWorksetCollector(doc).OfKind(DB.WorksetKind.UserWorkset).ToWorksets()
worksets = sorted(worksets, key=lambda w: w.Name.lower())

if len(worksets) < 2:
    forms.alert("The model must keep at least one user workset.", title="Script cancelled")
    script.exit()

# Show element counts in the list so the user knows what will be affected
labels = {}
for w in worksets:
    labels[u"{}  ({} elements)".format(w.Name, count_elements(w))] = w

selectedLabels = forms.SelectFromList.show(sorted(labels, key=lambda l: l.lower()),
                                           title='Select worksets to delete',
                                           width=500, height=800, multiselect=True,
                                           button_name='Next')
if not selectedLabels:
    script.exit()

toDelete = [labels[l] for l in selectedLabels]
deleteIds = set(w.Id.IntegerValue for w in toDelete)
remaining = [w for w in worksets if w.Id.IntegerValue not in deleteIds]

if not remaining:
    forms.alert("You cannot delete all user worksets. Keep at least one.", title="Script cancelled")
    script.exit()

# Ask what to do with the elements on the deleted worksets
option = forms.CommandSwitchWindow.show([OPT_MOVE, OPT_DELETE],
                                        message='What to do with elements on the selected worksets?')
if not option:
    script.exit()

if option == OPT_MOVE:
    targetName = forms.SelectFromList.show([w.Name for w in remaining],
                                           title='Move elements to workset',
                                           width=500, height=600, multiselect=False,
                                           button_name='Select')
    if not targetName:
        script.exit()
    target = [w for w in remaining if w.Name == targetName][0]
    settings = DB.DeleteWorksetSettings(DB.DeleteWorksetOption.MoveElementsToWorkset, target.Id)
    action = u"move their elements to '{}'".format(target.Name)
else:
    settings = DB.DeleteWorksetSettings(DB.DeleteWorksetOption.DeleteAllElements, DB.WorksetId.InvalidWorksetId)
    action = u"PERMANENTLY DELETE all their elements"

# Final confirmation
names = u"\n".join(u"  - " + w.Name for w in toDelete)
if not forms.alert(u"Delete {} worksets and {}?\n\n{}".format(len(toDelete), action, names),
                   title="Confirm delete", yes=True, no=True):
    script.exit()

deleted, failed = [], []
with revit.Transaction('K_tool: Delete worksets'):
    for w in toDelete:
        name = w.Name
        try:
            if not DB.WorksetTable.CanDeleteWorkset(doc, w.Id, settings):
                failed.append(u"{} (cannot be deleted - active, or elements/workset owned by others?)".format(name))
                continue
            DB.WorksetTable.DeleteWorkset(doc, w.Id, settings)
            deleted.append(name)
        except Exception as e:
            failed.append(u"{} ({})".format(name, e))

msg = u"{} worksets deleted.".format(len(deleted))
if failed:
    msg += u"\n\nNot deleted:\n" + u"\n".join(failed)
forms.alert(msg, title='Script complete.', warn_icon=bool(failed))
