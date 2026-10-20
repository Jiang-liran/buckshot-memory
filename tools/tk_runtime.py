"""Locate Tcl data explicitly included by the portable-Python build fallback."""
import os
from pathlib import Path
import sys

bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
for key, folder in (("TCL_LIBRARY", "_tcl_data"), ("TK_LIBRARY", "_tk_data")):
    if (bundle / folder).is_dir():
        os.environ[key] = str(bundle / folder)
