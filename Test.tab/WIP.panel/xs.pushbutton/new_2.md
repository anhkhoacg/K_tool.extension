
## Using the Revit API and pyRevit, create a script that:

1. Prompts the user to select one or more Revit elements.
2. Prompts the user to pick a spline curve (ModelCurve, DetailCurve, or another curve-based element).
3. Prompts the user to specify the distance to create along the spline.
4. Creates copies of the selected elements and places them along the spline path.
5. Aligns the copied elements to the tangent direction of the spline at each placement point, similar to Revit's native Array tool
6. Preserves the original element parameters and host relationships where possible.
7. Uses a Revit Transaction for all modifications.
8. Includes error handling for:
   - No element selected
   - Invalid curve selection
   - Unsupported element types
   - Failed copy operations
9. Add comments explaining each major step.

## Target environment:
- Revit API
- Python for pyRevit
- Compatible with Revit 2022+

Provide the complete working script.
