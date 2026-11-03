# -*- coding: utf-8 -*-
__title__ = "Export Worksets"
__author__ = "Khoa Le"
__doc__ = "Export all user worksets of the current model to a text file"

import codecs

from pyrevit import revit, DB, forms, script

doc = revit.doc

# Collect all user worksets, sorted by name
worksets = DB.FilteredWorksetCollector(doc).OfKind(DB.WorksetKind.UserWorkset).ToWorksets()
worksets = sorted(worksets, key=lambda w: w.Name.lower())

if not worksets:
    forms.alert("No user worksets found in this model.", title="Script cancelled")
    script.exit()

# Ask where to save the file
default_name = "{}_Worksets".format(doc.Title)
pathFile = forms.save_file(file_ext='txt', default_name=default_name)
if not pathFile:
    script.exit()

# One workset per line: <Name><TAB><VisibleInAllViews>
# Lines starting with '#' are comments and are ignored on import
lines = [
    u"# Worksets exported from: {}".format(doc.Title),
    u"# Format: WorksetName<TAB>VisibleInAllViews (True/False)",
]
for w in worksets:
    lines.append(u"{}\t{}".format(w.Name, w.IsVisibleByDefault))

try:
    with codecs.open(pathFile, 'w', encoding='utf-8') as f:
        f.write(u"\n".join(lines) + u"\n")
except Exception as e:
    forms.alert("Could not write TXT file.\n\n{}".format(e), title="Script cancelled")
    script.exit()

forms.alert("{} worksets exported to:\n{}".format(len(worksets), pathFile),
            title="Script complete.", warn_icon=False)
