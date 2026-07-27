"""Excel import helper for pyRevit scripts.

This module keeps the legacy API expected by ByExcel_script.py:

    xcl = xclUtils([], path_to_file)
    data, ok = xcl.xclUtils_import("Sheet1", 2, 0)

The import routine reads from a closed Excel workbook by automating Excel
through COM, which is the most compatible approach in a pyRevit / Windows
environment.
"""

from __future__ import print_function

try:
    import clr  # noqa: F401
    import System
    from System import Activator
    from System.Runtime.InteropServices import Marshal
except Exception:
    System = None
    Activator = None
    Marshal = None


def _safe_text(value):
    if value is None:
        return ""
    try:
        return value.ToString()
    except Exception:
        return str(value)


class xclUtils(object):
    def __init__(self, data, path_file):
        self.data = data or []
        self.path_file = path_file

    def xclUtils_import(self, sheet_name="Sheet1", start_row=1, start_col=0):
        excel_app = None
        workbook = None
        worksheet = None
        rows = []

        if not self.path_file or System is None or Activator is None:
            return rows, False

        try:
            excel_type = System.Type.GetTypeFromProgID("Excel.Application")
            if excel_type is None:
                return rows, False

            excel_app = Activator.CreateInstance(excel_type)
            excel_app.Visible = False
            excel_app.DisplayAlerts = False

            workbook = excel_app.Workbooks.Open(self.path_file, False, True)

            try:
                worksheet = workbook.Worksheets(sheet_name)
            except Exception:
                return rows, False

            used_range = worksheet.UsedRange
            last_row = used_range.Rows.Count
            last_col = used_range.Columns.Count

            if start_row < 1:
                start_row = 1
            if start_col < 0:
                start_col = 0

            for row_index in range(start_row, last_row + 1):
                current_row = []
                has_value = False

                for col_index in range(start_col + 1, last_col + 1):
                    cell_value = worksheet.Cells(row_index, col_index).Value2
                    normalized = _safe_text(cell_value)
                    if normalized != "":
                        has_value = True
                    current_row.append(normalized)

                if has_value:
                    rows.append(current_row)

            return rows, True

        except Exception:
            return rows, False

        finally:
            if workbook is not None:
                try:
                    workbook.Close(False)
                except Exception:
                    pass

            if excel_app is not None:
                try:
                    excel_app.Quit()
                except Exception:
                    pass

            for com_object in (worksheet, workbook, excel_app):
                if Marshal is None or com_object is None:
                    continue
                try:
                    Marshal.FinalReleaseComObject(com_object)
                except Exception:
                    pass