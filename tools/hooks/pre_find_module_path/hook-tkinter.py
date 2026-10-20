"""Keep tkinter when Tcl data is explicitly supplied by our build script.

PyInstaller's discovery subprocess can reject a usable portable Tcl runtime.
The build fallback provides the matching Python runtime's data and DLLs.
"""


def pre_find_module_path(hook_api):
    pass
