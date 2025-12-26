import math

TIME_STEPS = [10, 30, 50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000]

def calculate_single_transformer(tx) -> dict:
    # ... (Individual logic unchanged) ...
    sn = tx.sn_kva
    u = tx.u_kv
    ratio = tx.ratio_iencl
    tau = tx.tau_ms

    if u == 0: 
        return {
            "error": "Zero Voltage", 
            "transformer_name": tx.name,
            "sn_kva": sn, "u_kv": u, "ratio_iencl": ratio, "tau_ms": tau,
            "decay_curve_rms": {k: 0 for k in [f"{t}ms" for t in TIME_STEPS]} # Return 0 to avoid breaking the sum
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
    
    # Initialize sums
    # Create dictionaries filled with 0 : {"10ms": 0.0, "30ms": 0.0 ...}
    keys = [f"{t}ms" for t in TIME_STEPS]
    total_curve = {k: 0.0 for k in keys}
    hv_curve = {k: 0.0 for k in keys}
    hv_list = []

    for tx in transformers_list:
        # 1. Individual calculation
        res = calculate_single_transformer(tx)
        results.append(res)
        
        # If error (e.g., zero voltage), ignore for sum
        if "error" in res: continue

        curve = res["decay_curve_rms"]
        is_hv = tx.u_kv > 50.0  # HV threshold set to 50 kV

        if is_hv:
            hv_list.append(tx.name)

        # 2. Step-by-step sum
        for k in keys:
            val = curve.get(k, 0)
            
            # Add to GLOBAL TOTAL
            total_curve[k] += val
            
            # Add to HV TOTAL (if condition met)
            if is_hv:
                hv_curve[k] += val

    # Final rounding
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
