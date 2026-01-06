
import os

# --- Constants for file extensions ---
# Protection Analysis: SI2S (Standard) + MDB (Legacy). LF1S (Loadflow) is excluded.
PROTECTION_EXTENSIONS = ('.si2s', '.mdb')

# Loadflow Analysis: LF1S (Standard) + MDB (Legacy). SI2S (Protection) is excluded.
LOADFLOW_EXTENSIONS = ('.lf1s', '.mdb')

# Generic Database Files that can be parsed by db_converter
DATABASE_EXTENSIONS = ('.si2s', '.lf1s', '.mdb')

# --- File Type Checkers ---

def is_protection_file(filename: str) -> bool:
    """Checks if a file is a valid protection study file."""
    name = filename.lower()
    if name.endswith('.lf1s'): return False # Explicitly exclude loadflow
    if os.path.basename(name).startswith('~$'): return False # Exclude temp files
    return name.endswith(PROTECTION_EXTENSIONS)

def is_loadflow_file(filename: str) -> bool:
    """Checks if a file is a valid loadflow study file."""
    name = filename.lower()
    if name.endswith('.si2s'): return False # Explicitly exclude protection
    if os.path.basename(name).startswith('~$'): return False # Exclude temp files
    return name.endswith(LOADFLOW_EXTENSIONS)

def is_database_file(filename: str) -> bool:
    """
    Checks if a file is a generic database file that can be parsed for tables.
    This is used for features like topology analysis that can run on any data source.
    """
    name = filename.lower()
    if os.path.basename(name).startswith('~$'): return False # Exclude temp files
    return name.endswith(DATABASE_EXTENSIONS)

