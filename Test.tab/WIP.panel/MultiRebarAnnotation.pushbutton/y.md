# Task update: MultiRebarAnnotation 

## Task
Using the Revit API (Python/pyRevit), create a script that automatically places a Multi-Rebar Annotation for every rebar set visible in the active view.   

## Requirements:
- Get the active document and active view.
- Collect all Rebar elements visible in the active view.
- Using MultiReferenceAnnotation method to create Multi-Rebar Annotation for each rebar set.
- Ensure proper error handling for cases where MultiReferenceAnnotation cannot be applied.
- Wrap all modifications in a Transaction.
- Output results in the pyRevit output window.

Using rebar set direction to determine the orientation of the annotation.