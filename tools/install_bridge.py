"""Build a local single-player bridge copy from a supported, user-owned game.

No game files are downloaded or distributed. The original is never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCHED_NAME = "Buckshot Roulette Memory.exe"
GAME_SHA256 = "df2f8a31bd469438a1a29f831945ccea7b26963ab735f73b32936792207b1663"
SCRIPT_HASHES = {
    "ShellSpawner.gd": "3831575fdfcbd30cea2158d2ca40ad88293f4771eec297f8356b2b491bf78f3c",
    "ShellExamine.gd": "4e75c5933489501db656c6f8d90d2afff7ee759f75fd3dcb971db47d4a5ee74f",
    "BurnerPhone.gd": "f3130a1a0a31621fb22b8fa49ca229742ae4d0009abc875a6f21ef952561fb8b",
}
STARTUP = "func _ready():\n\tpass\n\n\nfunc _process(delta):\n\tpass\n"


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def replace_once(source: str, anchor: str, replacement: str) -> str:
    if source.count(anchor) != 1:
        raise ValueError(f"Unsupported script structure: expected one {anchor!r}")
    return source.replace(anchor, replacement, 1)


def patch_script(name: str, source: str, fragment: str) -> str:
    source = source.replace("\r\n", "\n")
    if "MemoryMarkKnown(" in source or "MEMORY_STATE_PATH" in source:
        raise ValueError("This script is already patched; use the original game.")
    if name == "ShellSpawner.gd":
        source = replace_once(source, STARTUP, fragment.rstrip() + "\n")
        for anchor in ("\troundManager.LoadShells()", "\tlocationIndex = 0"):
            source = replace_once(source, anchor, "\tMemoryResetKnown()\n" + anchor)
    elif name == "ShellExamine.gd":
        anchor = "\tvar shellState = shellSpawner.sequenceArray[0]"
        source = replace_once(source, anchor, anchor + "\n\tshellSpawner.MemoryMarkKnown(0)")
    elif name == "BurnerPhone.gd":
        anchor = "\t\tif(randindex == 8 or randindex == 7): randindex -= 1"
        source = replace_once(source, anchor, anchor + "\n\t\tsh.MemoryMarkKnown(randindex)")
    else:
        raise ValueError(f"Unexpected script: {name}")
    return source


def run_gdre(gdre: Path, arguments: list[str], cwd: Path) -> None:
    result = subprocess.run(
        [str(gdre), "--headless", *arguments], cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", timeout=300,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise RuntimeError("GDRE failed:\n" + result.stdout[-3000:])
    # Some GDRE errors return zero. Callers must verify all output artifacts.


def extract(gdre: Path, game: Path, destination: Path, cwd: Path) -> None:
    run_gdre(gdre, [
        f"--extract={game}", f"--output={destination}",
        *[f"--include=res://scripts/{name}" for name in SCRIPT_HASHES],
    ], cwd)
    for name in SCRIPT_HASHES:
        if not (destination / "scripts" / name).is_file():
            raise RuntimeError(f"GDRE did not extract {name}; no installation performed.")


def validate_game(game: Path) -> None:
    if not game.is_file() or game.suffix.lower() != ".exe":
        raise ValueError("Select the original Buckshot Roulette.exe.")
    if sha256(game) != GAME_SHA256:
        raise ValueError(
            "Unsupported game build. This release supports the tested Windows "
            "v2.2.0.6 executable only (see README SHA-256). No files were changed."
        )


def validate_output(game: Path, output: Path) -> None:
    if output == game or output.name.lower() == game.name.lower():
        raise ValueError("The bridge must have a different filename from the original game.")
    if output.suffix.lower() != ".exe":
        raise ValueError("The output filename must end in .exe.")
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an existing file: {output}")
    if not output.parent.is_dir():
        raise ValueError("The output directory must already exist.")


def install(game: Path, gdre: Path, output: Path) -> None:
    game, gdre, output = game.resolve(), gdre.resolve(), output.resolve()
    validate_output(game, output)
    if not gdre.is_file():
        raise FileNotFoundError("Select gdre_tools.exe from the official GDRE Tools release.")
    print("Checking the original game (read-only)...", flush=True)
    validate_game(game)
    fragment = (ROOT / "bridge" / "memory_bridge.gd.inc").read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="buckshot-memory-") as temporary:
        temp = Path(temporary)
        extracted, patches, verified = temp / "original", temp / "patches", temp / "verified"
        print("Extracting three scripts into a temporary directory...", flush=True)
        extract(gdre, game, extracted, temp)
        patches.mkdir()
        for name, expected in SCRIPT_HASHES.items():
            original = extracted / "scripts" / name
            if sha256(original) != expected:
                raise ValueError(f"Unsupported script content: {name}")
            patched = patch_script(name, original.read_text(encoding="utf-8"), fragment)
            (patches / name).write_text(patched, encoding="utf-8", newline="\n")
        generated = temp / PATCHED_NAME
        print("Building a separate executable; the Steam original is unchanged...", flush=True)
        run_gdre(gdre, [
            f"--pck-patch={game}", f"--output={generated}", f"--embed={game}",
            *[f"--patch-file={patches / name}=res://scripts/{name}" for name in SCRIPT_HASHES],
        ], temp)
        if not generated.is_file():
            raise RuntimeError("GDRE did not create the bridge executable.")
        with generated.open("rb") as binary:
            if binary.read(2) != b"MZ":
                raise RuntimeError("Invalid Windows executable header.")
            binary.seek(-4, os.SEEK_END)
            if binary.read() != b"GDPC":
                raise RuntimeError("Embedded game pack is missing.")
        print("Re-extracting and verifying the generated bridge...", flush=True)
        extract(gdre, generated, verified, temp)
        for name in SCRIPT_HASHES:
            if sha256(verified / "scripts" / name) != sha256(patches / name):
                raise RuntimeError(f"Generated script verification failed: {name}")
        # Exclusive creation prevents overwriting files added during the build.
        # On failure, only our own newly-created, partial output is removed.
        created = False
        try:
            with output.open("xb") as destination:
                created = True
                with generated.open("rb") as source:
                    shutil.copyfileobj(source, destination, 1024 * 1024)
        except BaseException:
            if created:
                output.unlink(missing_ok=True)
            raise
    print(f"Bridge ready: {output}\nOriginal game preserved. Start the helper to play single-player.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path, help="Original Buckshot Roulette.exe")
    parser.add_argument("--gdre", type=Path, help="Official GDRE Tools 2.6.0 gdre_tools.exe")
    parser.add_argument("--output", type=Path, help=f"Defaults to {PATCHED_NAME} beside the original")
    parser.add_argument("--check-only", action="store_true", help="Check game compatibility without writing")
    args = parser.parse_args()
    try:
        if args.check_only:
            validate_game(args.game)
            print("Supported game build; no files changed.")
        else:
            if args.gdre is None:
                parser.error("--gdre is required unless --check-only is used")
            install(args.game, args.gdre, args.output or args.game.parent / PATCHED_NAME)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Installation stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
