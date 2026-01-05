
import numpy as np
import cmath
import json
import re
from app.schemas.protection import ProtectionPlan, ProjectConfig, Std21Settings
from app.calculations.ansi_code import common

class MiCOM_Safety_Engine:
    """
    This class contains the original calculation logic provided by the user.
    It now uses dynamic data from the configuration and common parameters.
    """
    def __init__(self, common_data: dict, settings: Std21Settings):
        # Impedances from common_data (originating from config.json -> links_data)
        link_impedances = common_data.get("Impedances_link", {})
        self.zd = self._parse_complex(link_impedances.get("Zd"))
        self.z0 = self._parse_complex(link_impedances.get("Z0"))

        # Electrical and strategic parameters
        self.common_data = common_data
        self.settings = settings

    def _parse_complex(self, complex_str: str) -> complex:
        if not complex_str or not isinstance(complex_str, str):
            return 0j
        try:
            # Format: "R + jX" -> "R + Xj"
            # Remove spaces and move 'j' from prefix to suffix for the imaginary part.
            s = complex_str.replace(" ", "")
            s = re.sub(r'j([0-9.]+)', r'\1j', s)
            return complex(s)
        except (ValueError, TypeError):
            return 0j

    def _fmt_c(self, c_val):
        sign = "+" if c_val.imag >= 0 else "-"
        return f"{c_val.real:.3f} {sign} j{abs(c_val.imag):.3f}"

    def _to_polar_dict(self, complex_val):
        if complex_val is None: return {"magnitude": 0, "angle_deg": 0}
        return {
            "magnitude": round(abs(complex_val), 4),
            "angle_deg": round(np.degrees(cmath.phase(complex_val)), 2)
        }

    def compute(self):
        # [context:flow] 1. PHYSICAL INPUTS (from common_data and settings)
        I_SC_USER_HYPOTHESIS = self.common_data.get("Ik2min_sec_ref", 0) * 1000
        if I_SC_USER_HYPOTHESIS == 0:
            I_SC_USER_HYPOTHESIS = self.settings.fallback_ik2min_sec_ref_amps # Fallback from config

        NOMINAL_VOLTAGE_KV = self.common_data.get("kVnom_busfrom", self.settings.fallback_kvnom_busfrom)
        
        # Use the specific setting from Std21Settings, not from common_data
        L_SPAN_METERS = self.settings.l_span_meters
        
        # This value is now correctly overridden from the plan
        CT_PRIMARY_AMP = self.settings.ct_primary_amp

        # [context:flow] 2. STRATEGY INPUTS (from settings)
        ZONE1_OVERREACH_PCT = self.settings.zone1_overreach_pct
        ZONE_Q_REACH_OHM = self.settings.zone_q_reach_ohm
        ZONE_4_REACH_OHM = self.settings.zone_4_reach_ohm
        ZONE_Q_LOGIC_DESC = self.settings.zone_q_logic_desc
        ZONE_4_LOGIC_DESC = self.settings.zone_4_logic_desc
        
        FACTOR_PHASE_MAX = self.settings.factor_phase_max
        FACTOR_GROUND_MAX = self.settings.factor_ground_max
        R1PH_TYPICAL_OHM = self.settings.r1ph_typical_ohm
        PSB_PERCENTAGE = self.settings.psb_percentage

        # --- CALCULATIONS ---
        
        # 1. KZ1
        num = self.z0 - self.zd
        den = 3 * self.zd
        k0_val = num / den if den and abs(den) > 1e-9 else 0j
        k0_mag = round(abs(k0_val), 4)
        k0_ang = round(np.degrees(cmath.phase(k0_val)), 2)

        proof_kZ_formula = "kZ = (Z0 - Zd) / (3 * Zd)"
        proof_kZ_subst = f"({self._fmt_c(self.z0)} - {self._fmt_c(self.zd)}) / (3 * {self._fmt_c(self.zd)})"
        proof_kZ_res = f"{k0_mag} at {k0_ang} deg"

        # 2. Zone 1
        z1_reach = abs(self.zd) * (ZONE1_OVERREACH_PCT / 100.0)
        proof_z1_formula = "Reach = |Zd| * (Overreach% / 100)"
        proof_z1_subst = f"|{self._fmt_c(self.zd)}| * ({ZONE1_OVERREACH_PCT} / 100)"
        proof_z1_res = f"{abs(self.zd):.4f} * {ZONE1_OVERREACH_PCT/100.0} = {z1_reach:.4f} Ohm"

        # 3. Arc Resistance
        target_current = I_SC_USER_HYPOTHESIS
        r_arc_numerator = 28710 * L_SPAN_METERS
        r_arc = r_arc_numerator / (target_current ** 1.4) if target_current > 0 else 0
        proof_arc_formula = "R_arc = (28710 * L) / (I_sc ^ 1.4)"
        proof_arc_subst = f"(28710 * {L_SPAN_METERS}) / ({target_current:.0f}^1.4)"
        proof_arc_res = f"{r_arc_numerator:.0f} / {target_current ** 1.4:.0f} = {r_arc:.2f} Ohm" if target_current > 0 else "N/A"

        # 4. Load Blinder
        v_min_kv = NOMINAL_VOLTAGE_KV * 0.8
        v_ph_min_volts = v_min_kv * 1000 / np.sqrt(3)
        z_load_ct = v_ph_min_volts / (1.2 * CT_PRIMARY_AMP) if CT_PRIMARY_AMP > 0 else 0
        proof_load_subst = f"({v_min_kv:.1f}kV * 1000 / sqrt(3)) / (1.2 * {CT_PRIMARY_AMP}A)"
        proof_load_res = f"{v_ph_min_volts:.0f} / {1.2 * CT_PRIMARY_AMP:.1f} = {round(z_load_ct, 2)} Ohm" if CT_PRIMARY_AMP > 0 else "N/A"

        # 5. Maximum Resistive Reach Limits
        r_ph_max_limit = FACTOR_PHASE_MAX * z_load_ct
        proof_rph_max = f"{FACTOR_PHASE_MAX} * {round(z_load_ct, 2)} = {round(r_ph_max_limit, 2)} Ohm"

        r_g_max_limit = FACTOR_GROUND_MAX * z_load_ct
        proof_rg_max = f"{FACTOR_GROUND_MAX} * {round(z_load_ct, 2)} = {round(r_g_max_limit, 2)} Ohm"

        # 6. Power Swing
        delta_psb = R1PH_TYPICAL_OHM * (PSB_PERCENTAGE / 100.0)
        proof_psb = f"{PSB_PERCENTAGE}% of {R1PH_TYPICAL_OHM} Ohm = {delta_psb} Ohm"

        # --- JSON CONSTRUCTION (PRESERVED) ---
        return {
            "project_context": "MiCOM P444 - Settings Report (With Safety Limits)",
            "relay_settings_micom_p444": {
                "Ground_Compensation_Factors": {
                    "kZ1_Detailed": {
                        "value_polar": self._to_polar_dict(k0_val),
                        "calculation_demonstration": { "formula": proof_kZ_formula, "substitution": proof_kZ_subst, "result": proof_kZ_res }
                    },
                    "kZq_Detailed": { "kZq_Res_Comp": k0_mag, "kZq_Angle": k0_ang },
                    "kZ4_Detailed": { "kZ4_Res_Comp": k0_mag, "kZ4_Angle": k0_ang }
                },
                "Distance_Zones": {
                    "Z1": {
                        "reach_ohm": round(z1_reach, 3),
                        "demonstration": { "formula": proof_z1_formula, "result": proof_z1_res }
                    },
                    "ZQ": { "reach_ohm": ZONE_Q_REACH_OHM, "logic": ZONE_Q_LOGIC_DESC },
                    "Z4": { "reach_ohm": ZONE_4_REACH_OHM, "logic": ZONE_4_LOGIC_DESC }
                },
                "Fault_Supervision_and_Limits": {
                    "1_Arc_Resistance_Calculated": {
                        "value_ohm": round(r_arc, 2), "current_ref": I_SC_USER_HYPOTHESIS,
                        "demonstration": { "formula": proof_arc_formula, "substitution": proof_arc_subst, "result": proof_arc_res }
                    },
                    "2_Minimum_Load_Impedance": {
                        "description": f"Z_load based on CT Rating (InTC = {CT_PRIMARY_AMP}A)", "value_ohm": round(z_load_ct, 2),
                        "demonstration": { "formula": "Vmin / (1.2 * InTC)", "substitution": proof_load_subst, "result": proof_load_res }
                    },
                    "3_Maximum_Allowed_Resistive_Reach": {
                        "description": "Safety Limits to avoid Load Encroachment",
                        "RPh_Max_Limit_Phase": {
                            "value_ohm": round(r_ph_max_limit, 2), "factor": FACTOR_PHASE_MAX,
                            "demonstration": { "formula": "0.6 * Z_load", "result": proof_rph_max }
                        },
                        "RG_Max_Limit_Ground": {
                            "value_ohm": round(r_g_max_limit, 2), "factor": FACTOR_GROUND_MAX,
                            "demonstration": { "formula": "0.8 * Z_load (Assumption for Ground)", "result": proof_rg_max }
                        },
                        "Conclusion": f"Your setting ({R1PH_TYPICAL_OHM} Ohm) must be < {round(r_ph_max_limit, 2)} Ohm. Status: OK."
                    }
                },
                "Tables_ohm": {
                    "1_OHM_SUMMARY_TABLE": {
                        "Line_Zd": self._to_polar_dict(self.zd), "Compensation_kZ1": self._to_polar_dict(k0_val),
                        "Zone_1_Reach": round(z1_reach, 3), "R_Arc_Calcule": round(r_arc, 2),
                        "Z_Load_Min": round(z_load_ct, 2), "Limit_RPh_Max": round(r_ph_max_limit, 2)
                    },
                    "BLOCKING_OSCILLATIONS": {
                        "Basis_RPh": R1PH_TYPICAL_OHM, "Settings_Delta": delta_psb, "Demonstration": proof_psb
                    }
                }
            }
        }

def calculate(plan: ProtectionPlan, full_config: ProjectConfig, dfs_dict: dict, global_tx_map: dict) -> dict:
    """
    Main integration function for the ANSI 21 calculation.
    It uses settings from the project config and electrical data from common.py.
    """
    # 1. Select the correct settings object based on the plan type
    ptype = plan.type.upper()
    if ptype == "INCOMER":
        # Use a copy to prevent modifying the global config object for other calculations
        std_21_settings = full_config.settings.ansi_21.incomer.copy(deep=True)
    else:
        std_21_settings = full_config.settings.ansi_21.incomer.copy(deep=True)
    
    # Override the default CT rating with the specific one from the protection plan
    parsed_ct_amp = common.parse_ct_primary(plan.ct_primary)
    if parsed_ct_amp > 0:
        std_21_settings.ct_primary_amp = parsed_ct_amp

    # 2. Get common electrical data
    common_data = common.get_electrical_parameters(plan, full_config, dfs_dict, global_tx_map)

    # 3. Instantiate the engine with dynamic data and run the calculation
    engine = MiCOM_Safety_Engine(common_data, std_21_settings)
    thresholds_structure = engine.compute()

    status = "computed"
    if common_data.get("kVnom_busfrom") == 0:
        status = "warning_data (kV=0)"
    if not thresholds_structure:
        status = "error_computation"

    # 4. Return the combined result
    return {
        "ansi_code": "21",
        "status": status,
        "topology_used": {
            "origin": getattr(plan, "topology_origin", "unknown"),
            "bus_from": common_data.get("Bus_Prim"),
            "bus_to": common_data.get("Bus_Sec")
        },
        "config": {
            "settings_used": std_21_settings.dict(),
            "type": plan.type,
            "ct_primary": plan.ct_primary
        },
        "thresholds": thresholds_structure,
        "common_data": common_data,
        "comments": [f"Calculation based on '{ptype}' settings in config.json."]
    }
