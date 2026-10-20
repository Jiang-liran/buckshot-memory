"""Package only the assistant, never a game executable or game resources."""
from pathlib import Path
import os
import subprocess
import sys


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    if sys.platform != "win32":
        raise SystemExit("Build the Windows executable on Windows with Python 3.12.")
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=root, check=True)
    arguments = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--noupx", "--name", "BuckshotMemory",
        "--distpath", str(root / "dist"), "--workpath", str(root / "build"),
        "--specpath", str(root / "build"),
    ]
    # Some portable Python distributions ship Tcl outside normal hook discovery.
    # Use their own Tcl data, never a machine-specific hardcoded directory.
    tcl = Path(sys.base_prefix) / "tcl"
    if (tcl / "tcl8.6").is_dir() and (tcl / "tk8.6").is_dir():
        arguments += [
            "--add-data", f"{tcl / 'tcl8.6'}{os.pathsep}_tcl_data",
            "--add-data", f"{tcl / 'tk8.6'}{os.pathsep}_tk_data",
            "--runtime-hook", str(root / "tools" / "tk_runtime.py"),
            "--additional-hooks-dir", str(root / "tools" / "hooks"),
            "--hidden-import", "tkinter", "--hidden-import", "_tkinter",
        ]
        for name in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll"):
            binary = Path(sys.base_prefix) / "DLLs" / name
            if binary.is_file():
                arguments += ["--add-binary", f"{binary}{os.pathsep}."]
    arguments.append(str(root / "src" / "buckshot_bridge_ui.py"))
    subprocess.run(arguments, cwd=root, check=True)
    print("Built:", root / "dist" / "BuckshotMemory.exe")


if __name__ == "__main__":
    main()
