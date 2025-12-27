import pandas as pd
import math
import os
from app.calculations import db_converter
from app.schemas.loadflow_schema import TransformerData, SwingBusInfo, StudyCaseInfo

def analyze_loadflow(files_content: dict, settings, only_winners: bool = False) -> dict:
    results = []
    target = settings.target_mw
    tol = settings.tolerance_mw
    champions = {}

    for filename, content in files_content.items():
        clean_name = os.path.basename(filename)
        if not clean_name.lower().endswith(('.lf1s', '.si2s', '.mdb')): continue

        res = {"filename": filename, "is_valid": False, "study_case": {}, "swing_bus_found": {}, "status_color": "red", "is_winner": False}
        try:
            dfs = db_converter.extract_data_from_db(content)
            if dfs: res["is_valid"] = True
            # (Note: Basic validation for this fix script)
        except: pass
        results.append(res)
    
    return {"status": "success", "results": results}
