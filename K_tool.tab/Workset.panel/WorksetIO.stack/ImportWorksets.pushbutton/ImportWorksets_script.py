# -*- coding: utf-8 -*-
__title__ = "Import Worksets"
__author__ = "Khoa Le"
__doc__ = "Create worksets from a text file exported with 'Export Worksets'"

import codecs

from pyrevit import revit, DB, forms, script

doc = revit.doc

FALSE_VALUES = ("false", "no", "0", "hidden")


def parse_line(line):
    """Return (name, visible) from '<Name>[<TAB><Visible>]', or None to skip."""
    line = line.strip().lstrip(u"﻿")
    if not line or line.startswith("#"):
        return None
    parts = line.split("\t")
    name = parts[0].strip()
    if not name:
        return None
    visible = True
    if len(parts) > 1 and parts[1].strip().lower() in FALSE_VALUES:
        visible = False
    return name, visible


# Prompt user to pick the TXT file
pathFile = forms.pick_file(files_filter='Text File (*.txt)|*.txt')
if not pathFile:
    script.exit()

# Read worksets from the file (plain one-name-per-line files also work)
try:
    with codecs.open(pathFile, 'r', encoding='utf-8-sig') as f:
        rows = [parse_line(line) for line in f]
except Exception as e:
    forms.alert("Could not read TXT file.\n\n{}".format(e), title="Script cancelled")
    script.exit()

fileWorksets = {}
for row in rows:
    if row and row[0] not in fileWorksets:
        fileWorksets[row[0]] = row[1]

if not fileWorksets:
    forms.alert("No workset names found in TXT file.", title="Script cancelled")
    script.exit()

# Only offer worksets whose names are not already used in the model
newNames = sorted([n for n in fileWorksets if DB.WorksetTable.IsWorksetNameUnique(doc, n)],
                  key=lambda n: n.lower())
existingCount = len(fileWorksets) - len(newNames)

if not newNames:
    forms.alert("All {} worksets in the file already exist in this model.".format(existingCount),
                title="Nothing to import", warn_icon=False)
    script.exit()

items = [forms.TemplateListItem(n, checked=True) for n in newNames]
selected = forms.SelectFromList.show(items, title='Select worksets to create',
                                     width=500, height=800, multiselect=True,
                                     button_name='Create')
if not selected:
    script.exit()

created, failed = [], []
visSettings = DB.WorksetDefaultVisibilitySettings.GetWorksetDefaultVisibilitySettings(doc)

with revit.Transaction('K_tool: Import worksets'):
    for n in selected:
        try:
            ws = DB.Workset.Create(doc, n)
            if not fileWorksets[n]:
                visSettings.SetWorksetVisibility(ws.Id, False)
            created.append(n)
        except Exception as e:
            failed.append(u"{} ({})".format(n, e))

msg = "{} new worksets created.".format(len(created))
if existingCount:
    msg += "\n{} worksets already existed and were skipped.".format(existingCount)
if failed:
    msg += "\n\nFailed to create:\n" + "\n".join(failed)
forms.alert(msg, title='Script complete.', warn_icon=bool(failed))
