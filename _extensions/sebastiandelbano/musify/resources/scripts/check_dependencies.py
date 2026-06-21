# =============================================================================
# MUSIFY DEPENDENCY CHECKER
# This script verifies that all required system tools and files are present
# before the Musify extension attempts to render any music.
# =============================================================================

import shutil
import os
import sys

def check_dependencies(abc2svg="abcnode", abc2midi="abc2midi", 
                       fluidsynth="fluidsynth", ffmpeg="ffmpeg", sf2_path=""):
    """
    Checks for required binaries and the SoundFont file.
    Prints an error message and exits with code 1 if anything is missing.
    """
    
    # 1. LIST OF REQUIRED BINARIES
    required_binaries = {
        "abc2svg": abc2svg,
        "abc2midi": abc2midi,
        "fluidsynth": fluidsynth,
        "ffmpeg": ffmpeg
    }

    missing_binaries = []

    for name, path in required_binaries.items():
        if shutil.which(path) is None:
            missing_binaries.append(f"{name} (path: {path})")

    # 2. CHECK FOR SOUNDFONT
    if not sf2_path:
        # Check environment variable first, then fallback to local user path
        sf2_path = os.environ.get("MUSIFY_SF2_PATH") or "~/.local/share/soundfonts/timbresOfHeaven4.00.sf2"
    
    sf2_path = os.path.expandvars(os.path.expanduser(sf2_path))
    sf2_exists = os.path.exists(sf2_path)

    # 3. REPORT ERRORS
    if missing_binaries or not sf2_exists:
        print("\n" + "="*60)
        print("MUSIFY EXTENSION: MISSING DEPENDENCIES")
        print("="*60)
        
        if missing_binaries:
            print(f"\nThe following required tools were not found in your PATH:")
            for b in missing_binaries:
                print(f"  - {b}")
            print("\nPlease install them using your package manager (brew, apt, npm, etc.).")
            if "abc2svg" in [b.split()[0] for b in missing_binaries]:
                print("  Note: abc2svg can be installed via 'npm install -g abc2svg'")

        if not sf2_exists:
            print(f"\nThe required SoundFont file was not found:")
            print(f"  Path: {sf2_path}")
            print("\nPlease download 'Timbres of Heaven 4.00' and place it at this location.")

        print("="*60 + "\n")
        sys.exit(1)

    # Success
    sys.exit(0)

if __name__ == "__main__":
    # If run directly without args, use defaults
    check_dependencies()
