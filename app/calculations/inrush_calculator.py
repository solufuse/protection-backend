import math

# Les pas de temps demandés
TIME_STEPS = [10, 30, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

def calculate_single_transformer(tx) -> dict:
    sn = tx.sn_kva
    u = tx.u_kv
    ratio = tx.ratio_iencl
    tau = tx.tau_ms

    # 1. Calcul du Courant Nominal (In) en Ampères
    if u == 0: return {"error": "Tension nulle", "name": tx.name}
    
    i_nom = sn / (math.sqrt(3) * u)
    
    # 2. Calcul du Pic Max Théorique
    i_peak_max = i_nom * ratio

    # 3. Calcul de la décroissance
    curve = {}
    for t_ms in TIME_STEPS:
        if tau > 0:
            val = i_peak_max * math.exp(-t_ms / tau)
        else:
            val = 0
        curve[f"{t_ms}ms"] = round(val, 2)

    return {
        "transformer_name": tx.name,
        "i_nominal": round(i_nom, 2),
        "i_peak": round(i_peak_max, 2),
        "decay_curve": curve
    }

def process_inrush_request(transformers_list):
    results = []
    for tx in transformers_list:
        results.append(calculate_single_transformer(tx))
    return results
