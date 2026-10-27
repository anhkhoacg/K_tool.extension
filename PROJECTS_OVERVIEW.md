# PycharmProjects — Overview & Structure Review

_Reviewed 2026-10-27._

This folder holds three Revit automation projects, all built on [pyRevit](https://github.com/pyrevitlabs/pyRevit):

| Project | What it is | Git | Size | Structure verdict |
|---|---|---|---|---|
| [K_tool.extension](K_tool.extension/) | Personal pyRevit toolbar (worksets, rebar, grids, views) | Yes — `github.com/anhkhoacg/K_tool.extension` | ~30 scripts, 2.8k lines | **Fair** — standard pyRevit layout, but naming drift, WIP code shipped, a few config bugs |

## 1. K_tool.extension

### Purpose
Revit toolbar (`K_tool` tab) for daily workflows: worksets, rebar, grids, views and filters.

### Layout
```
K_tool.extension/
├── extension.json          # pyRevit extension metadata
├── README.md               # EN + VI feature list
├── Installation.md         # VI install guide (CLI / zip / extension manager)
├── LICENSE
├── img/                    # screenshots used by Installation.md
├── Lib/Ktool_xclUtils.py   # Excel COM import helper (currently unused)
├── revit_utils.py          # Reference-resolving helpers (currently unused)
├── K_tool.tab/             # production tab
│   ├── Workset.panel/      # Workset.stack, Workset2.stack
│   ├── Rebar.panel/        # Rebar.stack, Rebar2.stack
│   ├── MISC.panel/         # ACC_EU button, MISC1.stack, MISC2.stack
│   └── VIEW .panel/        # View.stack, View2.stack   (note trailing space)
└── Test.tab/               # check.panel, WIP.panel — experiments
```

### Tool reference

**Workset panel**
| Button | Does |
|---|---|
| Hide Workset | Hides the worksets of the selected elements in the active view |
| Show Active Workset | Makes the current active workset visible in the active view |
| Show All Worksets | Makes every user workset visible in the active view |
| Create Worksets using text file (`ByTxt`) | Creates worksets from a `.txt` file, one name per line, no header. Workshared models only |
| Set Workset Visibility | WPF dialog (`UI.xaml`) to search, select and hide/show worksets |

**Rebar panel**
| Button | Does |
|---|---|
| Obscure Bars | Sets all rebar in the view to obscured (drawn under other elements) |
| UNObscure Bars | Sets all rebar in the view to unobscured (drawn on top) |
| Show All Rebar | Shows every bar of each rebar set in the view |
| Copy Rebar Number → Schedule Mark | Copies `Rebar Number` into `Schedule Mark` for all bars in the view |
| Multi Rebar Annotation | Bulk-places Multi-Rebar annotations; asks for annotation type and horizontal/vertical direction |
| Renumber | Dialog (`input_form.xaml`) to renumber rebar within a partition |

**MISC panel**
| Button | Does |
|---|---|
| Open in Autodesk Docs / Forma | Opens the current cloud model in Autodesk Docs (EU) in the browser |
| Dimension Grids | Pick grids → creates chained dimensions plus an overall dimension |
| Flip Grids | Toggles bubble ends of selected grids |
| Grid 3D to 2D | Switches selected grids to view-specific (2D) extents in the active view |
| Add filter to current view | Searchable list of all model filters; adds the picked ones to the view (set to hidden) |
| change Background | Cycles Revit background colour Black → Gray → White |

**VIEW panel** (not yet in README)
| Button | Does |
|---|---|
| 3D ViewS | Creates a section-boxed 3D view per picked element (1000 mm margin), named by Type Mark / Type Name |
| SectionS | Creates cross section, elevation section and section-based plan per picked element, named by Type Mark |
| Filter By Type Name | Pick one element → filter `<Category>_<TypeName>_not equal` that hides same-category elements of other types |
| Filter View By Type Name | Pick one element → filter that hides section views whose name does not contain its type name |

### Installation
See [Installation.md](Installation.md). Short version:

```bash
pyrevit extend ui K_tool https://github.com/anhkhoacg/K_tool.extension --dest="C:\pyRevitExtensions" --branch=main
```

### Structure findings
What's good: follows pyRevit's `tab/panel/stack/pushbutton` convention, most buttons have icons, light/dark icons in several places, bilingual README, LICENSE file present.

Issues, highest impact first:

1. **Broken bundle metadata**
   - [MISC.panel/ACC_EU.pushbutton/bundle.yaml](K_tool.tab/MISC.panel/ACC_EU.pushbutton/bundle.yaml) contains Python (`__title__ = ...`), not YAML, so pyRevit ignores it. The script's title says "Open in Autodesk Docs", the YAML intends "Open in Forma" — pick one.
   - [MISC.panel/bundle.yaml](K_tool.tab/MISC.panel/bundle.yaml) uses `Layout:` (capital L); pyRevit reads `layout:`, so the ordering is ignored.
   - [K_tool.tab/bundle.yaml](K_tool.tab/bundle.yaml) layout omits the VIEW panel.
2. **`VIEW .panel` has a trailing space** in the folder name — fragile on Windows tooling and in paths. Rename to `View.panel`.
3. **Test/WIP code ships to users.** `Test.tab/` (buttons named `x`, `xs`, `Z`, `Drafr`, with `new_2.md`/`y.md` notes) loads for everyone who installs. Move to a separate branch or a separate dev-only extension.
4. **Duplicate tool**: `MultiRebarAnnotation` exists in both `Rebar2.stack` and `Test.tab/WIP.panel`.
5. **Dead / broken shared code**
   - `revit_utils.py` sits at the repo root (not on pyRevit's `lib` path), is imported nowhere, and uses an f-string — a syntax error under IronPython 2.7.
   - `Lib/Ktool_xclUtils.py` documents itself for `ByExcel_script.py`, which no longer exists.
   - Meanwhile common boilerplate (`doc = __revit__...`, transaction wrappers, rebar collectors) is copy-pasted across ~15 scripts. A small `lib/ktool/` package would remove that.
6. **Revit 2027 readiness**: 6 scripts use `ElementId.IntegerValue`, removed in Revit 2027 (Renumber, MultiRebarAnnotation, 3DView, SECTION, ShowAllWorkset, Workset_Visible). Use `pyrevit.compat.get_elementid_value_func()` as `dimGrid` already does.
7. **Inconsistent naming**
   - Folders: `FlipGrip` (typo), `ShowAllRebar_py`, `addfilter` vs `Workset_Visible` vs `CopyRebarNumberToScheduleMark`.
   - Script files: `script.py`, `v01_script.py`, `Renumber-script.py`, `MultiRebarAnnotation.script.py`, `Isolateworkset_script.py` (for the "Show Active" button). pyRevit accepts any `*script.py`, but one convention (`script.py`) is easier to maintain.
   - Metadata: some buttons use `bundle.yaml`, some `xxx_bundle.yaml`, some only `__title__` in the script, some nothing (SECTION/3DView scripts have no `__doc__`).
8. **Repo hygiene**: `.idea/` and `Thumbs.db` are committed; stray `iconn.png`; `.gitignore` only ignores one folder. Remote is `K_tool.extension` but README/Installation link `anhkhoacg/K_tool`.
9. **Docs drift**: README misses the VIEW panel and the "Create worksets from text" tool; Installation.md is Vietnamese-only and numbered 3 → 2 → 1.

