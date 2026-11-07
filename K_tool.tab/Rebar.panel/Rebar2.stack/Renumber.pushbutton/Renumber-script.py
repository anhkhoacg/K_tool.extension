
# -*- coding: utf-8 -*-
# pyRevit script: renumber rebar in partition

# Analysis:
# Purpose: UI to renumber rebars by partition using Revit's numbering schema.
# Observations / potential issues:
# - "Rebar" number matching and partition lookups rely on parameter names; consider handling case-insensitive parameter names or built-in fallbacks (already partly addressed).
# - Name comparisons and numeric parsing assume integers; code alerts when values are non-numeric but could be more tolerant.
# - get_rebar_numbers_in_partition and other functions create new FilteredElementCollector calls repeatedly; consider caching if performance becomes an issue.
# - The script creates InputForm twice (get_user_inputs unused & main loop creates InputForm directly). Consider consolidating to a single flow to avoid duplication.
# - Silent exception handling hides specific API failures (ChangeNumber). Consider logging failed element ids or exception messages for debugging.
# - Category checks use Category.Id.IntegerValue vs int(BuiltInCategory.OST_Rebar) — this works but using ElementId(int(...)) comparisons or utility helpers may be clearer.
# Suggested minimal improvements (not applied here to avoid behavior changes):
#  - Make numeric checks robust (handle leading zeros, whitespace).
#  - Make "Partition" and "Number" lookup case-insensitive, and prefer BuiltInParameter lookups when possible.
#  - Log or collect failed operations to present to the user after the transaction.

from Autodesk.Revit.DB import *
from pyrevit import forms
from pyrevit import revit, DB
from pyrevit import script
from pyrevit.forms import ProgressBar

doc = __revit__.ActiveUIDocument.Document
uidoc = __revit__.ActiveUIDocument


def get_param_value(element, param_name):
    """Helper function to get parameter value"""
    param = element.LookupParameter(param_name)
    if not param:
        # Try to get parameter by built-in parameter
        if param_name == "Partition":
            param = element.get_Parameter(BuiltInParameter.NUMBER_PARTITION_PARAM)
        elif param_name == "Number":
            param = element.get_Parameter(BuiltInParameter.REBAR_NUMBER)

    if param:
        if param.StorageType == StorageType.String:
            return param.AsString()
        elif param.StorageType == StorageType.Integer:
            return str(param.AsInteger())
        elif param.StorageType == StorageType.Double:
            return str(param.AsDouble())
    return None


def get_all_rebar_partitions():
    """Get all unique rebar partitions in the model using parameter name"""
    all_rebars = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElements()
    partitions = set()

    # Debug information
    if not all_rebars:
        forms.alert("No rebars found in the model!")
        return []

    for rebar in all_rebars:
        partition = get_param_value(rebar, "Partition")
        if partition:
            partitions.add(partition)

    # Debug information
    if not partitions:
        forms.alert("No partitions found in the rebars. Check parameter names.")

    return sorted(list(partitions))


def get_rebar_number_digits():
    """
    Try to obtain the rebar-number digit count from the NumberingSchema.
    If the API does not expose a digits property, infer from existing rebar numbers
    by using the maximum numeric string length found (fallback).
    Returns an integer >= 0 (0 means 'no fixed padding').
    """
    # Try schema attribute heuristics first
    try:
        schema = NumberingSchema.GetNumberingSchema(
            doc,
            NumberingSchemaTypes.StructuralNumberingSchemas.Rebar
        )
        # common possible attribute names (best-effort)
        for attr in ('Digits', 'NumberDigits', 'NumberOfDigits', 'DigitCount'):
            val = getattr(schema, attr, None)
            if isinstance(val, int) and val >= 0:
                return val
    except Exception:
        pass

    # Fallback: infer from existing rebar numbers (max string length of numeric-looking values)
    try:
        all_rebars = FilteredElementCollector(doc).OfCategory(
            BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElements()
        max_len = 0
        for rebar in all_rebars:
            num = get_param_value(rebar, "Number")
            if not num:
                continue
            s = str(num).strip()
            # consider strings that contain digits (e.g. "08", "8"); count full length to preserve leading zeros
            if any(ch.isdigit() for ch in s):
                max_len = max(max_len, len(s))
        return max_len if max_len > 0 else 0
    except Exception:
        return 0


def get_rebar_numbers_in_partition(partition):
    """Get all rebar numbers in a specific partition"""
    all_rebars = FilteredElementCollector(doc).OfCategory(
        BuiltInCategory.OST_Rebar).WhereElementIsNotElementType().ToElements()
    rebar_data = []

    # Debug information
    if not all_rebars:
        forms.alert("No rebars found while getting numbers!")
        return []

    # determine padding digits for display
    digits = get_rebar_number_digits()

    for rebar in all_rebars:
        current_partition = get_param_value(rebar, "Partition")
        if current_partition == partition:
            number = get_param_value(rebar, "Number")
            if number:
                num_str = str(number).strip()
                # try to parse integer value; for non-numeric keep original string and skip int
                try:
                    num_int = int(num_str)
                    padded = str(num_int).zfill(digits) if digits and digits > 0 else str(num_int)
                except Exception:
                    num_int = None
                    padded = num_str
                # Store raw, int (or None), padded display and element info
                rebar_data.append({
                    'number': num_str,
                    'int': num_int,
                    'padded': padded,
                    'id': rebar.Id.IntegerValue,
                    'rebar': rebar
                })

    # Debug information
    if not rebar_data:
        forms.alert("No rebar numbers found in partition: " + partition)

    # Sort by integer when possible, otherwise by string
    sorted_data = sorted(rebar_data,
                         key=lambda x: (x['int'] is None, x['int'] if x['int'] is not None else x['number']))
    return sorted_data


def get_selected_rebar():
    """Get the currently selected rebar element if any"""
    selection = list(uidoc.Selection.GetElementIds())
    if len(selection) == 1:
        element = doc.GetElement(selection[0])
        if element and element.Category and element.Category.Id.IntegerValue == int(BuiltInCategory.OST_Rebar):
            return element
    return None


class InputForm(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(self, 'input_form.xaml')

        # Set up event handlers
        self.ok_button.Click += self.save_values
        self.cancel_button.Click += self.window_close
        self.Select_partition.SelectionChanged += self.on_partition_changed

        # Add Apply button handler
        self.apply_button.Click += self.apply_values

        # Store rebar data
        self.rebar_data = []
        self.finish_requested = False

        # Get all partitions
        self.partitions = get_all_rebar_partitions()
        if not self.partitions:
            forms.alert("No rebar partitions found in the model.", exitscript=True)

        # Set up partition dropdown
        self.Select_partition.ItemsSource = self.partitions

        # Check for selected rebar
        selected_rebar = get_selected_rebar()
        if selected_rebar:
            # Set default partition from selection
            partition = get_param_value(selected_rebar, "Partition")
            if partition in self.partitions:
                self.Select_partition.SelectedItem = partition

            # Store default rebar number from selection (apply after items are populated)
            current_number = get_param_value(selected_rebar, "Number")
            if current_number:
                self.default_current_number = str(current_number)
        else:
            # No selection, set first partition
            self.Select_partition.SelectedIndex = 0

        # Initialize rebar numbers for selected partition
        self.update_rebar_numbers()

        # If a rebar was selected when the form opened, apply that number selection now
        if hasattr(self, 'default_current_number') and self.rebar_data:
            # Determine digits/padded form from the data set
            # Build list of padded strings from data
            unique_padded = []
            for d in self.rebar_data:
                if d['padded'] not in unique_padded:
                    unique_padded.append(d['padded'])

            # Normalize default_current_number by integer if possible, else compare raw string
            try:
                default_int = int(str(self.default_current_number).strip())
                # format with detected padding if present in data
                # find digits from data (all padded entries with numeric ints will have same length)
                digits = len(next((p for p in unique_padded if p.isdigit()), str(default_int)))
                default_padded = str(default_int).zfill(digits) if digits and digits > 0 else str(default_int)
            except Exception:
                default_padded = str(self.default_current_number)

            if default_padded in unique_padded:
                self.Select_rebar_number.SelectedItem = default_padded

        # Set up default value for new rebar number
        self.New_Rebar_number.Text = "0"

    def on_partition_changed(self, sender, e):
        self.update_rebar_numbers()

    def update_rebar_numbers(self):
        selected_partition = self.Select_partition.SelectedItem
        if selected_partition:
            # Get rebar data for the selected partition
            self.rebar_data = get_rebar_numbers_in_partition(selected_partition)

            # Update the dropdown with unique numbers (numerically sorted / padded)
            if self.rebar_data:
                unique_padded = []
                unique_others = []
                for d in self.rebar_data:
                    if d['int'] is not None:
                        if d['padded'] not in unique_padded:
                            unique_padded.append(d['padded'])
                    else:
                        if d['number'] not in unique_others:
                            unique_others.append(d['number'])

                # numeric (padded) are already in numeric order from sorted_data
                numbers_list = unique_padded[:]
                if unique_others:
                    numbers_list.extend(sorted(unique_others))

                self.Select_rebar_number.ItemsSource = numbers_list
                self.Select_rebar_number.SelectedIndex = 0

    def save_values(self, sender, e):
        # Get values from input form
        self.current_number = self.Select_rebar_number.SelectedItem  # Changed from .Text to .SelectedItem
        self.new_number = self.New_Rebar_number.Text
        self.selected_partition = self.Select_partition.SelectedItem

        # Silent finish on blank new number
        if not str(self.new_number).strip():
            self.finish_requested = True
            self.DialogResult = True
            self.Close()
            return

        # Find selected rebar data: match by integer when possible, else by padded/raw string
        selected_rebar_data = None
        try:
            sel_int = int(str(self.current_number).strip())
        except Exception:
            sel_int = None

        if sel_int is not None:
            selected_rebar_data = next(
                (data for data in self.rebar_data if data['int'] == sel_int),
                None
            )
        else:
            # fallback to matching padded or raw string
            selected_rebar_data = next(
                (data for data in self.rebar_data if
                 data['padded'] == str(self.current_number) or data['number'] == str(self.current_number)),
                None
            )

        self.selected_rebar_data = selected_rebar_data

        # Validate new rebar number is an integer
        try:
            int(self.new_number)
            if self.selected_rebar_data:  # Make sure we have valid rebar data
                self.DialogResult = True
                self.Close()
            else:
                forms.alert("Please select a valid rebar number.", exitscript=False)
        except ValueError:
            forms.alert("New rebar number must be an integer.", exitscript=False)

    def apply_values(self, sender, e):
        """
        Validate inputs, call renumber_rebar immediately, refresh the rebar numbers list without closing the dialog.
        """
        # Read values from form controls
        current_number = self.Select_rebar_number.SelectedItem
        # fixed control name (was New_Rebar_Number) -> use New_Rebar_number
        new_number = self.New_Rebar_number.Text
        selected_partition = self.Select_partition.SelectedItem

        # Validate new number is integer
        try:
            new_int = int(new_number)
        except ValueError:
            forms.alert("New rebar number must be an integer.", exitscript=False)
            return

        if current_number is None:
            forms.alert("Please select a rebar number.", exitscript=False)
            return

        # Determine selected current as integer when possible
        try:
            current_int = int(str(current_number).strip())
        except Exception:
            current_int = None

        # Find a matching rebar entry; prefer integer match
        if current_int is not None:
            selected_rebar_data = next(
                (data for data in self.rebar_data if data['int'] == current_int),
                None
            )
        else:
            selected_rebar_data = next(
                (data for data in self.rebar_data if
                 data['padded'] == str(current_number) or data['number'] == str(current_number)),
                None
            )

        if not selected_rebar_data:
            forms.alert("Please select a valid rebar number.", exitscript=False)
            return

        # Call renumber function
        success, message = renumber_rebar(doc, selected_partition,
                                          current_int if current_int is not None else selected_rebar_data.get('number'),
                                          new_int)

        if success:
            # Silent on success — refresh the number list to reflect changes
            self.update_rebar_numbers()
            self.New_Rebar_number.Text = ""

            # Try to select the new number if present (use padded display)
            digits = get_rebar_number_digits()
            new_str = str(new_int).zfill(digits) if digits and digits > 0 else str(new_int)
            items = list(self.Select_rebar_number.ItemsSource) if self.Select_rebar_number.ItemsSource else []
            if new_str in items:
                self.Select_rebar_number.SelectedItem = new_str
        else:
            # Show generic warning instead of exception message
            forms.alert("Rebar number is existed. Please select another new rebar number.", exitscript=False)

    def window_close(self, sender, e):
        self.DialogResult = False
        self.Close()

def get_user_inputs():
    # Create and show the form
    input_form = InputForm()
    result = input_form.show_dialog()

    # If user cancelled
    if not result:
        # Silent exit on cancel/close
        script.exit()

    # Validate number inputs
    try:
        current_num = int(input_form.current_number)
        new_num = int(input_form.new_number)
    except ValueError:
        forms.alert("Please enter valid numbers for current and new rebar numbers.", exitscript=True)

    return {
        'partition': input_form.selected_partition,
        'current_number': current_num,
        'new_number': new_num
    }


def renumber_rebar(doc, partition_name, num, new_num):
    """
    Attempt to renumber rebar using the Revit numbering schema API.
    This will:
      - Get the Rebar numbering schema
      - Start a Transaction
      - Call schema.ChangeNumber(partition_name, num, new_num)
      - Commit on success or RollBack on failure
    Returns (success: bool, message: str)
    """
    try:
        schema = NumberingSchema.GetNumberingSchema(
            doc,
            NumberingSchemaTypes.StructuralNumberingSchemas.Rebar
        )
    except Exception as e:
        return False, "Failed to obtain Rebar numbering schema: {}".format(e)

    # Ensure we run the change inside a transaction
    try:
        t = Transaction(doc, "Renumber Rebar")
        t.Start()
        try:
            # ChangeNumber expects the partition name and numeric values
            schema.ChangeNumber(partition_name, int(num), int(new_num))
            t.Commit()
            return True, "Renumbered {} -> {} in partition '{}'".format(num, new_num, partition_name)
        except Exception as ex_change:
            try:
                if t.GetStatus() == TransactionStatus.Started:
                    t.RollBack()
            except Exception:
                pass
            return False, "ChangeNumber failed: {}".format(ex_change)
    except Exception as ex_tx:
        return False, "Transaction error: {}".format(ex_tx)


# Main execution - show form, validate and attempt renumber inside a retry loop.
# If renumber fails, prompt user to select another new rebar number (re-open form).
try:
    while True:
        input_form = InputForm()
        result = input_form.show_dialog()

        # If user cancelled, exit silently
        if not result:
            script.exit()

        # If user pressed OK with blank new number, finish silently
        if getattr(input_form, 'finish_requested', False):
            break

        # Validate number inputs
        try:
            current_num = int(input_form.current_number)
            new_num = int(input_form.new_number)
        except Exception:
            forms.alert("Please enter valid integers for current and new rebar numbers.", exitscript=False)
            # Re-open the form to let user correct values
            continue

        # Attempt renumber
        success, message = renumber_rebar(
            doc,
            input_form.selected_partition,
            current_num,
            new_num
        )

        if success:
            # Silent on success — exit loop and finish
            break
        else:
            # Ask user to select another new rebar number and re-open the form
            forms.alert(" Rebar Number is exist. Please select another new rebar number.", exitscript=False)
            # Loop will re-open the dialog

except Exception as e:
    forms.alert("An unexpected error occurred: {}".format(str(e)), exitscript=True)
