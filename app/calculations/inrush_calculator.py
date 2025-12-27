import math

TIME_STEPS = [10, 30, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

def calculate_single_transformer(tx) -> dict:
    # ... (Logique individuelle inchangée) ...
    sn = tx.sn_kva
    u = tx.u_kv
    ratio = tx.ratio_iencl
    tau = tx.tau_ms

    if u == 0: 
        return {
            "error": "Tension nulle", 
            "transformer_name": tx.name,
            "sn_kva": sn, "u_kv": u, "ratio_iencl": ratio, "tau_ms": tau,
            "decay_curve_rms": {k: 0 for k in [f"{t}ms" for t in TIME_STEPS]} # Retourne 0 pour ne pas casser la somme
        }
    
    i_nom = sn / (math.sqrt(3) * u)
    i_peak_max = i_nom * ratio

    curve_rms = {}
    for t_ms in TIME_STEPS:
        if tau > 0:
            val_peak = i_peak_max * math.exp(-t_ms / tau)
        else:
            val_peak = 0
        
        val_rms = val_peak / math.sqrt(2)
        curve_rms[f"{t_ms}ms"] = round(val_rms, 2)

    return {
        "transformer_name": tx.name,
        "sn_kva": sn,
        "u_kv": u,
        "ratio_iencl": ratio,
        "tau_ms": tau,
        "i_nominal": round(i_nom, 2),
        "i_peak": round(i_peak_max, 2),
        "decay_curve_rms": curve_rms
    }

def process_inrush_request(transformers_list):
    results = []
    
    # Initialisation des sommes
    # On crée des dictionnaires remplis de 0 : {"10ms": 0.0, "30ms": 0.0 ...}
    keys = [f"{t}ms" for t in TIME_STEPS]
    total_curve = {k: 0.0 for k in keys}
    hv_curve = {k: 0.0 for k in keys}
    hv_list = []

    for tx in transformers_list:
        # 1. Calcul individuel
        res = calculate_single_transformer(tx)
        results.append(res)
        
        # Si erreur (ex: tension nulle), on ignore pour la somme
        if "error" in res: continue

        curve = res["decay_curve_rms"]
        is_hv = tx.u_kv > 50.0  # Seuil HV fixé à 50 kV

        if is_hv:
            hv_list.append(tx.name)

        # 2. Somme pas à pas
        for k in keys:
            val = curve.get(k, 0)
            
            # Ajout au TOTAL GLOBAL
            total_curve[k] += val
            
            # Ajout au TOTAL HV (si condition remplie)
            if is_hv:
                hv_curve[k] += val

    # Arrondi final des sommes pour faire propre
    total_curve = {k: round(v, 2) for k, v in total_curve.items()}
    hv_curve = {k: round(v, 2) for k, v in hv_curve.items()}

    return {
        "summary": {
            "total_curve_rms": total_curve,
            "hv_curve_rms": hv_curve,
            "hv_transformers_list": hv_list
        },
        "details": results
    }
