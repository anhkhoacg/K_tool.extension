__title__ = 'Set Workset Visibility'
__author__ = 'Khoa le'
__doc__ = """Set Workset Visibility
    Author: Khoa.Le @Haskoning"""

import os

import clr

# Revit API
clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import FilteredWorksetCollector, WorksetKind, Transaction, WorksetVisibility

# WPF/XAML
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('System.Xaml')
clr.AddReference('System.Xml')

from System.IO import StringReader
from System.Windows.Markup import XamlReader
import System

# try to get Revit document (pyrevit preferred, fallback to RevitServices)
doc = None
revit = None
forms = None
try:
    from pyrevit import revit as _revit, forms as _forms

    revit = _revit
    forms = _forms
    doc = revit.doc
except Exception:
    try:
        clr.AddReference('RevitServices')
        from RevitServices.Persistence import DocumentManager

        doc = DocumentManager.Instance.CurrentDBDocument
    except Exception:
        doc = None

# locate UI.xaml next to this script
script_dir = os.path.dirname(__file__)
xaml_path = os.path.join(script_dir, "UI.xaml")


# load XAML UI
def load_window(xaml_file):
    with open(xaml_file, 'r') as f:
        xaml_text = f.read()
    sr = StringReader(xaml_text)
    xr = System.Xml.XmlReader.Create(sr)
    win = XamlReader.Load(xr)
    return win


# collect user-created worksets
def collect_user_worksets(document):
    if document is None:
        return []
    coll = FilteredWorksetCollector(document).OfKind(WorksetKind.UserWorkset)
    items = [(ws.Name, ws) for ws in coll]
    items.sort(key=lambda x: x[0].lower())
    return items


# simple message (TaskDialog preferred)
def show_message(title, message):
    try:
        clr.AddReference('RevitAPIUI')
        from Autodesk.Revit.UI import TaskDialog
        TaskDialog.Show(title, message)
        return
    except Exception:
        pass
    try:
        if forms:
            forms.alert(message, title=title)
            return
    except Exception:
        pass
    print(title, message)


# Main UI flow
try:
    window = load_window(xaml_path)

    # find controls
    txtFilter = window.FindName("txtFilter")
    btnClear = window.FindName("btnClear")
    lb = window.FindName("lbWorksets")
    btnHide = window.FindName("btnHide")
    btnShow = window.FindName("btnShow")
    btnCancel = window.FindName("btnCancel")

    # prepare items and state
    all_items = collect_user_worksets(doc)  # list of (name, workset)
    checked_state = {}  # wid int -> bool

    from System.Windows.Controls import StackPanel, CheckBox, TextBlock, ListBoxItem
    from System.Windows import Thickness, VerticalAlignment


    def refresh_list(filter_text=""):
        try:
            lb.UnselectAll()
        except Exception:
            pass
        lb.Items.Clear()
        ft = (filter_text or "").strip().lower()
        if not all_items:
            info = ListBoxItem()
            info.Content = "No user-created worksets found or no Revit document available."
            info.IsEnabled = False
            lb.Items.Add(info)
            # disable actions if no doc
            try:
                btnHide.IsEnabled = False
                btnShow.IsEnabled = False
            except Exception:
                pass
            return

        # enable actions
        try:
            btnHide.IsEnabled = True
            btnShow.IsEnabled = True
        except Exception:
            pass

        # build filtered list and sort it (case-insensitive)
        if ft:
            filtered = [(name, ws) for (name, ws) in all_items if ft in name.lower()]
        else:
            filtered = list(all_items)
        filtered.sort(key=lambda x: x[0].lower())

        for name, ws in filtered:
            item = ListBoxItem()
            panel = StackPanel()
            panel.Orientation = System.Windows.Controls.Orientation.Horizontal

            cb = CheckBox()
            try:
                wid = int(ws.Id.IntegerValue)
            except Exception:
                wid = None

            # initialize checkbox from checked_state (persist selection across filters)
            cb.IsChecked = bool(checked_state.get(wid, False))
            cb.Margin = Thickness(0, 0, 6, 0)
            txt = TextBlock()
            txt.Text = name
            txt.VerticalAlignment = VerticalAlignment.Center

            # handlers to update checked_state
            if wid is not None:
                def make_handlers(wid_val):
                    def on_checked(s, e):
                        checked_state[wid_val] = True

                    def on_unchecked(s, e):
                        checked_state[wid_val] = False

                    return on_checked, on_unchecked

                on_c, on_u = make_handlers(wid)
                cb.Checked += on_c
                cb.Unchecked += on_u

            panel.Children.Add(cb)
            panel.Children.Add(txt)
            item.Content = panel
            item.Tag = ws
            lb.Items.Add(item)


    def get_checked_worksets():
        res = []
        # prefer checked_state to determine selection
        for _, ws in all_items:
            try:
                wid = int(ws.Id.IntegerValue)
                if checked_state.get(wid, False):
                    res.append(ws)
            except Exception:
                continue
        return res


    def set_visibility(selected_ws, visibility_value):
        if not selected_ws:
            show_message("Worksets", "No worksets selected.")
            return
        if doc is None:
            show_message("Worksets", "No Revit document available.")
            return
        tr = None
        try:
            try:
                target_view = revit.active_view
            except Exception:
                target_view = doc.ActiveView
            tr = Transaction(doc, "Set workset visibility")
            tr.Start()
            try:
                for ws in selected_ws:
                    target_view.SetWorksetVisibility(ws.Id, visibility_value)
                tr.Commit()
                show_message("Worksets", "Visibility updated for selected worksets in the active view.")
            except Exception:
                if tr.IsActive:
                    tr.RollBack()
                raise
        except Exception as ex:
            show_message("Error", "Failed to update workset visibility: {}".format(str(ex)))


    # event handlers
    def on_filter_changed(sender, args):
        txt = ""
        try:
            txt = sender.Text if hasattr(sender, "Text") else ""
        except Exception:
            txt = ""
        refresh_list(txt)


    def on_clear(sender, args):
        try:
            if txtFilter is not None:
                txtFilter.Text = ""
        except Exception:
            pass
        refresh_list("")


    def on_cancel(sender, args):
        close_dialog(False)


    def close_dialog(dialog_result=None):
        if window is None:
            return
        if dialog_result is not None:
            try:
                # If shown modally, DialogResult closes the dialog deterministically.
                window.DialogResult = dialog_result
                return
            except Exception:
                pass
        try:
            window.Close()
        except Exception:
            pass


    def on_hide(sender, args):
        sel = get_checked_worksets()
        set_visibility(sel, WorksetVisibility.Hidden)
        close_dialog(True)


    def on_show(sender, args):
        sel = get_checked_worksets()
        set_visibility(sel, WorksetVisibility.Visible)
        close_dialog(True)


    # wire events (some hosts accept +=)
    try:
        if txtFilter is not None:
            txtFilter.TextChanged += on_filter_changed
    except Exception:
        pass
    try:
        btnClear.Click += on_clear
    except Exception:
        pass
    try:
        btnCancel.Click += on_cancel
    except Exception:
        pass
    try:
        btnHide.Click += on_hide
    except Exception:
        pass
    try:
        btnShow.Click += on_show
    except Exception:
        pass

    # initial populate and show
    refresh_list("")
    try:
        window.Owner = None
        window.ShowDialog()
    except Exception:
        try:
            window.Show()
        except Exception:
            pass

except Exception:
    import traceback

    print("Failed to load UI or run script:")
    traceback.print_exc()
    raise
