"""
clean_demo.py
=============
Removes all generated files and compiled executables from the demo directory
so that run_demo.py can start from a completely fresh state.

Run this between demonstrations or if a run fails partway through.
"""

import os
import sys
import glob

DEMO_DIR = os.path.dirname(os.path.abspath(__file__))

# Files that are generated or compiled during the demo
GENERATED = [
    # Generated header (the build artifact)
    "generated_config.h",

    # Compiled executables — Linux / macOS
    "generate_config",
    "consumer",
    "independent1",
    "independent2",
    "independent3",

    # Compiled executables — Windows
    "generate_config.exe",
    "consumer.exe",
    "independent1.exe",
    "independent2.exe",
    "independent3.exe",

    # Object files (if any)
    "*.o",
]


def clean():
    removed = []
    errors  = []

    for pattern in GENERATED:
        matches = glob.glob(os.path.join(DEMO_DIR, pattern))
        for path in matches:
            try:
                os.remove(path)
                removed.append(os.path.basename(path))
            except OSError as exc:
                errors.append(f"  Could not remove {path}: {exc}")

    print()
    print("=" * 60)
    print("  CLEAN")
    print("=" * 60)

    if removed:
        print(f"\n  Removed {len(removed)} file(s):")
        for name in removed:
            print(f"    - {name}")
    else:
        print("\n  Nothing to remove -- directory is already clean.")

    if errors:
        print("\n  Errors:")
        for e in errors:
            print(e)
        sys.exit(1)

    print()
    print("  Demo directory is clean. Ready for a fresh run.")
    print()


if __name__ == "__main__":
    clean()
