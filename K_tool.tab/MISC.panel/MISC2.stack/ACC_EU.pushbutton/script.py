# -*- coding: utf-8 -*-
__title__ = 'Open in Autodesk Docs'
__author__ = 'Khoa le'
__doc__ = """This script will open the current Revit project in Autodesk Docs in your default web browser.
            Author: Khoa.Le @Haskoning"""

# .NET imports
import clr

clr.AddReference('RevitAPI')
from Autodesk.Revit.DB import Document
from Autodesk.Revit.UI import TaskDialog
import webbrowser

# Get the current Revit document and version
doc = __revit__.ActiveUIDocument.Document

# Check if the document is a cloud model
if not doc.IsModelInCloud:
    TaskDialog.Show("Error", "This document is not a cloud model.\nPlease save your project to Autodesk Docs first.")
else:
    try:
        # Get project ID
        project_id = Document.GetProjectId(doc).ToString()

        # Clean up the project ID by removing any 'b.' or 'b\'' prefix
        if project_id.startswith('b.') or project_id.startswith('b\''):
            project_id = project_id[2:]  # Remove 'b.' or 'b\'' prefix
        project_id = project_id.strip('\'"')  # Remove any remaining quotes

        # Construct the Autodesk Docs URL (using Python 2.7 string formatting)
        docs_url = "https://acc.autodesk.eu/docs/files/projects/{0}/files".format(project_id)

        # Open the URL in the default web browser
        webbrowser.open(docs_url)

        # Show success message
        TaskDialog.Show(
            "Success",
            "Opening project in Autodesk Docs...\n{0}".format(project_id)
        )

    except Exception as e:
        error_msg = "Failed to open Autodesk Docs:\n{0}".format(str(e))
        TaskDialog.Show("Error", error_msg)
