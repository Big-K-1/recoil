# Config module
import os
from .settings import *

# Path normalization
def _normalize_config_paths():
    """Normalize configuration path parameters"""
    global SOURCE_DIR, WORKSPACE, OUTPUT_DIR

    # Normalize separators to backslash (Windows format) and trim trailing slash
    # NOTE: only normalizes format — does not convert path type (absolute stays absolute)
    if isinstance(SOURCE_DIR, str):
        SOURCE_DIR = SOURCE_DIR.replace('/', '\\').rstrip('\\')

    if isinstance(WORKSPACE, str):
        WORKSPACE = WORKSPACE.replace('/', '\\').rstrip('\\')

    if isinstance(OUTPUT_DIR, str):
        OUTPUT_DIR = OUTPUT_DIR.replace('/', '\\').rstrip('\\')

# Run path normalization
_normalize_config_paths()
