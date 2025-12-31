
import os

# Protection : SI2S (Standard) + MDB (Legacy). EXCLURE LF1S (Loadflow).
PROTECTION_EXTENSIONS = ('.si2s', '.mdb')

# Loadflow : LF1S (Standard) + MDB (Legacy). EXCLURE SI2S.
LOADFLOW_EXTENSIONS = ('.lf1s', '.mdb')

def is_protection_file(filename: str) -> bool:
    name = filename.lower()
    if name.endswith('.lf1s'): return False
    if os.path.basename(name).startswith('~$'): return False
    return name.endswith(PROTECTION_EXTENSIONS)

def is_loadflow_file(filename: str) -> bool:
    name = filename.lower()
    if name.endswith('.si2s'): return False
    if os.path.basename(name).startswith('~$'): return False
    return name.endswith(LOADFLOW_EXTENSIONS)
