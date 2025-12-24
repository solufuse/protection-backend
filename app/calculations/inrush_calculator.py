import math

# Les pas de temps demandés
TIME_STEPS = [10, 30, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

def calculate_single_transformer(tx) -> dict:
    sn = tx.sn_kva
    u = tx.u_kv
    ratio = tx.ratio_iencl
    tau = tx.tau_ms

    if u == 0: 
        return {
            "error": "Tension nulle", 
            "transformer_name": tx.name,
            "sn_kva": sn, "u_kv": u, "ratio_iencl": ratio, "tau_ms": tau
        }
    
    # 1. Nominal
    i_nom = sn / (math.sqrt(3) * u)
    
    # 2. Pic Max
    i_peak_max = i_nom * ratio

    # 3. Calcul des courbes
    curve_peak = {}
    curve_rms = {}
    
    for t_ms in TIME_STEPS:
        if tau > 0:
            val_peak = i_peak_max * math.exp(-t_ms / tau)
        else:
            val_peak = 0
            
        # RMS = Peak / sqrt(2)
        val_rms = val_peak / math.sqrt(2)

        curve_peak[f"{t_ms}ms"] = round(val_peak, 2)
        curve_rms[f"{t_ms}ms"] = round(val_rms, 2)

    return {
        "transformer_name": tx.name,
        "sn_kva": sn,
        "u_kv": u,
        "ratio_iencl": ratio,
        "tau_ms": tau,
        "i_nominal": round(i_nom, 2),
        "i_peak": round(i_peak_max, 2),
        "decay_curve": curve_peak,       # Crête
        "decay_curve_rms": curve_rms     # Efficace (Ce que vous voulez)
    }

def process_inrush_request(transformers_list):
    results = []
    for tx in transformers_list:
        results.append(calculate_single_transformer(tx))
    return results
