
## Task
Using the Revit API (Python/pyRevit), create a script that automatically places a Multi-Rebar Annotation for every rebar set visible in the active view.

## Requirements:
- Get the active document and active view.
- Collect all Rebar elements visible in the active view.
- Group rebars by Rebar Number.
- Find a valid MultiRebarAnnotationType in the document.
- Determine an appropriate annotation position based on the rebar group's bounding box center.
- Create a MultiRebarAnnotation for each group.
- Ignore groups that cannot be annotated.
- Wrap all modifications in a Transaction.
- Print detailed logging to the pyRevit output window.
- Follow Revit API best practices and include error handling.
## Using :
-   MultiReferenceAnnotation