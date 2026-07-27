# -*- coding: utf-8 -*-
__title__ = "Workset to Txt"
__author__ = ""
__doc__ = """Export all user-defined worksets to a txt file.
Workset names are sorted by name and written in one column."""

import os
from datetime import datetime

import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import FilteredWorksetCollector, WorksetKind
from Autodesk.Revit.UI import TaskDialog


def get_document():
    try:
        revit_app = globals().get('__revit__', None)
        if revit_app and revit_app.ActiveUIDocument:
            return revit_app.ActiveUIDocument.Document
        return None
    except Exception:
        return None


def get_sorted_user_workset_names(document):
    worksets = FilteredWorksetCollector(document).OfKind(WorksetKind.UserWorkset)
    names = [ws.Name for ws in worksets]
    names.sort(key=lambda n: n.lower())
    return names


def pick_export_path(default_name):
    try:
        from pyrevit import forms

        path = forms.save_file(
            file_ext='txt',
            default_name=default_name,
            title='Export User Worksets'
        )
        if path:
            return path
    except Exception:
        pass

    try:
        clr.AddReference('System.Windows.Forms')
        from System.Windows.Forms import SaveFileDialog, DialogResult

        dialog = SaveFileDialog()
        dialog.Filter = 'Text files (*.txt)|*.txt|All files (*.*)|*.*'
        dialog.FileName = default_name
        dialog.Title = 'Export User Worksets'
        if dialog.ShowDialog() == DialogResult.OK:
            return dialog.FileName
    except Exception:
        pass

    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    return os.path.join(desktop, default_name)


def export_worksets_to_txt(file_path, workset_names):
    folder = os.path.dirname(file_path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder)

    with open(file_path, 'w') as f:
        for name in workset_names:
            f.write(name + '\n')


def main():
    doc = get_document()
    if doc is None:
        TaskDialog.Show('Workset to Txt', 'No active Revit document found.')
        return

    workset_names = get_sorted_user_workset_names(doc)
    if not workset_names:
        TaskDialog.Show('Workset to Txt', 'No user-defined worksets found in this model.')
        return

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    default_name = 'UserWorksets_{0}.txt'.format(timestamp)
    export_path = pick_export_path(default_name)

    if not export_path:
        TaskDialog.Show('Workset to Txt', 'Export was cancelled.')
        return

    try:
        export_worksets_to_txt(export_path, workset_names)
        TaskDialog.Show(
            'Workset to Txt',
            'Exported {0} worksets to:\n{1}'.format(len(workset_names), export_path)
        )
    except Exception as ex:
        TaskDialog.Show('Workset to Txt', 'Failed to export worksets:\n{0}'.format(str(ex)))


if __name__ == '__main__':
    main()