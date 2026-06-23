"""
FuzeKeys Version Information

This module contains version information for FuzeKeys following semantic versioning (semver).
"""

__version__ = "1.0.0"
__version_info__ = (1, 0, 0)

# Version components
MAJOR = 1
MINOR = 0
PATCH = 0

# Pre-release and build metadata (optional)
PRERELEASE = None  # e.g., "alpha", "beta", "rc.1"
BUILD = None       # e.g., "20231215.1"

def get_version():
    """Get the full version string"""
    version = f"{MAJOR}.{MINOR}.{PATCH}"
    
    if PRERELEASE:
        version += f"-{PRERELEASE}"
    
    if BUILD:
        version += f"+{BUILD}"
    
    return version

def get_version_info():
    """Get version information as a dictionary"""
    return {
        "version": get_version(),
        "major": MAJOR,
        "minor": MINOR,
        "patch": PATCH,
        "prerelease": PRERELEASE,
        "build": BUILD,
        "version_tuple": (MAJOR, MINOR, PATCH)
    } 