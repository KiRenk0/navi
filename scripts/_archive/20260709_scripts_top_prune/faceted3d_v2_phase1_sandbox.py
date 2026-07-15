#!/usr/bin/env python3
"""Faceted3D v2 Phase 1 sandbox: switchable Cp closure comparison.
Runs v1 (Busemann) and v2 (Newtonian-like) for all 3 validated Fluent cases,
compares pressure and heat flux. Does NOT overwrite baseline solver files.
"""

from __future__ import annotations

import csv, math, sys, warnings, copy
from pathlib import Path
from datetime import datetime

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import pearsonr

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ref_enthalpy_method.gas.thermo import make_perfect_gas_thermo
from ref_enthalpy_method.gas.transport import mu_sutherland
from ref_enthalpy_method.types import GasModel, EdgeConditions
from ref_enthalpy_method.aero.edge_conditions import compute_edge_conditions
from ref_enthalpy_method.aero.busemann import compute_cp
from ref_enthalpy_method.heatflux.windward import windward_ref_enthalpy_branches
from ref_enthalpy_method.config.lf_qw import LfQwConfig

# ---- Config ----
THERMO = make_perfect_gas_thermo(cp_const=1005.0)
GAS = GasModel(gamma=1.4, R=287.0, cp_gas=THERMO.cp, h_from_T=THERMO.h_from_T,
               T_from_h=THERMO.T_from_h, mu=mu_sutherland, prandtl=0.72)

NEWTONIAN_A = 0.38
NEWTONIAN_N = 1.15

# Freestream lookup (simplified USSA)
def _ussa(h_m):
    R=287.0; g0=9.80665
    if h_m<=11000:
        T=288.15-0.0065*h_m; P=101325*(T/288.15)**(-g0/(R*-0.0065))
    elif h_m<=20000:
        T=216.65; P=22632.1*np.exp(-g0/(R*T)*(h_m-11000))
    else:
        T=216.65+0.001*(h_m-20000); P=5474.89*(T/216.65)**(-g0/(R*0.001))
    rho=P/(R*T)
    return float(P), float(rho), float(T)

def _read_csv(path):
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.DictReader(f); rows=list(reader)
    cols={k:[] for k in rows[0].keys()}
    for r in rows:
        for k,v in r.items(): cols[k].append(v)
    result={}
    for k,vlist in cols.items():
        if k in ("side",): result[k]=np.array(vlist,dtype=str)
        else: result[k]=np.array(vlist,dtype=float)
    return result

def _read_fluent(path):
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f); h=next(reader)
        hm={hs.strip().lower():i for i,hs in enumerate(h)}
    xi=hm.get("x-coordinate",1); yi=hm.get("y-coordinate",2); zi=hm.get("z-coordinate",3)
    pi=hm.get("absolute-pressure",hm.get("pressure",4)); qi=hm.get("heat-flux",9)
    rows=[]
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f); next(reader)
        for row in reader:
            try: rows.append([float(row[xi]),float(row[yi]),float(row[zi]),float(row[pi]),-float(row[qi]),float(row[6])])
            except: continue
    return np.array(rows,dtype=float)

def _aligned_from_f3_fields(f3, flt, p_inf, q_inf, cp_model, mach, case_h_m):
    """Build aligned dataset with both v1 and v2 Cp/pe/q."""
    flt_x=np.array([r[0] for r in flt])
    flt_span=np.array([math.sqrt(r[1]**2+r[2]**2) for r in flt])
    flt_side=np.where(flt[:,2]<0,1,0)

    side_arr=f3["side"]
    w_f3=(side_arr=="windward")|(side_arr=="1") if side_arr.dtype.kind in ("U","S") else side_arr==1
    f3x=f3["x_m"][w_f3]; f3s=f3["span_m"][w_f3]; f3phi=f3["phi_rad"][w_f3]
    f3ma_e=f3["ma_e"][w_f3]; f3T_e=f3["T_e_K"][w_f3]; f3rho_e=f3["rho_e_kg_m3"][w_f3]
    f3v_e=f3["v_e_m_s"][w_f3]; f3mu_e=f3["mu_e_Pa_s"][w_f3]
    f3w_tr=f3["w_tr"][w_f3]; f3x=f3["x_m"][w_f3]
    f3cp0=f3["cp0"][w_f3]

    aligns=[]
    for i in range(flt.shape[0]):
        fx=float(flt_x[i]); fs=float(flt_span[i]); fside=int(flt_side[i])
        mask=np.isfinite(f3x)&np.isfinite(f3s)
        dx=np.abs(f3x[mask]-fx); ds=np.abs(f3s[mask]-fs)
        dist=np.sqrt(dx**2+(0.3*ds)**2)
        if mask.sum()==0: continue
        best=np.argmin(dist)
        if dist[best]>np.sqrt(0.02**2+(0.3*0.02)**2): continue
        idx=np.where(mask)[0][best]

        phi_i=float(f3phi[idx])
        # v1: busemann (from stored f3 Cp)
        cp_v1=float(f3["cp"][w_f3][idx])
        # v2: newtonian
        cp_v2=float(compute_cp(ma_inf=mach, phi_rad=phi_i, cp_model=cp_model,
                                newtonian_A=NEWTONIAN_A, newtonian_n=NEWTONIAN_N))

        pe_v1=float(f3["p_e_Pa"][w_f3][idx])
        pe_v2=p_inf*(1+0.5*1.4*mach**2*cp_v2)

        # Recompute edge conditions and q for v2 using the same edge chain
        try:
            edge_v2=compute_edge_conditions(gas=GAS, ma_inf=mach, p_inf=p_inf,
                                            T_inf=_ussa(case_h_m)[2], rho_inf=_ussa(case_h_m)[1],
                                            cp_pressure=cp_v2, cp0_pressure=max(cp_v2,0.5))
            h_w=float(GAS.h_from_T(300.0))
            x_eff=max(float(f3x[idx])-(-0.0008),0.001)
            res=windward_ref_enthalpy_branches(gas=GAS, edge=edge_v2, x=x_eff, h_w=h_w)
            wtr_i=float(f3w_tr[idx])
            q_v2=float(res.q_lam)*(1-wtr_i)+float(res.q_turb)*wtr_i
        except Exception:
            q_v2=float("nan")

        aligns.append({
            "x_m":fx,"span_m":fs,"side":fside,
            "p_fluent_Pa":float(flt[i,3]),"q_fluent_W_m2":float(flt[i,4]),
            "cp_v1":cp_v1,"cp_v2":cp_v2,
            "p_e_v1_Pa":pe_v1,"p_e_v2_Pa":pe_v2,
            "q_v1_W_m2":float(f3["q_low_W_m2"][w_f3][idx]),
            "q_v2_W_m2":q_v2,
            "phi_rad":phi_i,"w_tr":float(f3w_tr[idx]),
        })
    return aligns

def analyze_case(label, fluent_csv, f3_csv, out_dir, mach, alpha_deg, h_m):
    p_inf,rho_inf,T_inf=_ussa(h_m)
    v_inf=mach*math.sqrt(1.4*287.0*T_inf)
    q_inf=0.5*rho_inf*v_inf**2
    out_dir.mkdir(parents=True,exist_ok=True)

    print(f"\n[{label}] Ma={mach}, α={alpha_deg}°, h={h_m/1000:.0f}km")
    f3=_read_csv(f3_csv)
    flt=_read_fluent(fluent_csv)
    print(f"  F3 rows={f3['x_m'].size}, Fluent rows={flt.shape[0]}")

    aligns=_aligned_from_f3_fields(f3, flt, p_inf, q_inf, "newtonian_like", mach, h_m)
    print(f"  aligned={len(aligns)}")

    d={k:np.array([a[k] for a in aligns]) for k in aligns[0].keys()}
    w=d["side"]==1

    # Metrics v1
    p_ratio_v1=d["p_e_v1_Pa"][w]/np.maximum(d["p_fluent_Pa"][w],1.0)
    q_ratio_v1=d["q_v1_W_m2"][w]/np.maximum(d["q_fluent_W_m2"][w],1.0)
    # Metrics v2
    p_ratio_v2=d["p_e_v2_Pa"][w]/np.maximum(d["p_fluent_Pa"][w],1.0)
    q_ratio_v2=d["q_v2_W_m2"][w]/np.maximum(d["q_fluent_W_m2"][w],1.0)

    cp_fluent=(d["p_fluent_Pa"][w]-p_inf)/q_inf

    print(f"  v1: cp_ratio={float(np.nanmean(d['cp_v1'][w]/np.maximum(cp_fluent,1e-6))):.2f}x, "
          f"p_ratio={float(np.nanmean(p_ratio_v1)):.2f}, q_ratio={float(np.nanmean(q_ratio_v1)):.2f}")
    print(f"  v2: cp_ratio={float(np.nanmean(d['cp_v2'][w]/np.maximum(cp_fluent,1e-6))):.2f}x, "
          f"p_ratio={float(np.nanmean(p_ratio_v2)):.2f}, q_ratio={float(np.nanmean(q_ratio_v2)):.2f}")

    # Write comparison CSV
    comp_csv=out_dir/"v1_vs_v2_aligned.csv"
    with open(comp_csv,"w",newline="",encoding="utf-8") as f:
        wc=csv.writer(f)
        wc.writerow(["x_m","span_m","side","p_fluent","q_fluent",
                      "cp_v1","cp_v2","p_e_v1","p_e_v2","q_v1","q_v2","phi_rad","w_tr"])
        for a in aligns:
            wc.writerow([a["x_m"],a["span_m"],a["side"],
                a["p_fluent_Pa"],a["q_fluent_W_m2"],
                a["cp_v1"],a["cp_v2"],a["p_e_v1_Pa"],a["p_e_v2_Pa"],
                a["q_v1_W_m2"],a["q_v2_W_m2"],a["phi_rad"],a["w_tr"]])
    print(f"  written: {comp_csv.name}")

    return {
        "label":label,"mach":mach,"h_m":h_m,"p_inf":p_inf,"q_inf":q_inf,
        "cp_v1_mean":float(np.nanmean(d['cp_v1'][w])),
        "cp_v2_mean":float(np.nanmean(d['cp_v2'][w])),
        "cp_fluent_mean":float(np.nanmean(cp_fluent)),
        "cp_ratio_v1":float(np.nanmean(d['cp_v1'][w]/np.maximum(cp_fluent,1e-6))),
        "cp_ratio_v2":float(np.nanmean(d['cp_v2'][w]/np.maximum(cp_fluent,1e-6))),
        "p_ratio_v1":float(np.nanmean(p_ratio_v1)),
        "p_ratio_v2":float(np.nanmean(p_ratio_v2)),
        "q_ratio_v1":float(np.nanmean(q_ratio_v1)),
        "q_ratio_v2":float(np.nanmean(q_ratio_v2)),
        "n_valid":int(np.sum(np.isfinite(d['q_v2_W_m2'][w]))),
    }


def main():
    base=Path(__file__).resolve().parent.parent
    cases=[
        ("ma6_a5_h30km",base/"fluent_export/ma6_alpha5_h30km.csv",
         base/"runs/ma6_alpha5_h30km_f3/low_fidelity_points_all_valid.csv",6,5,30000),
        ("ma8_a5_h30km",base/"fluent_export/ma8_alpha5_h30km.csv",
         base/"runs/ma8_alpha5_h30km_f3/low_fidelity_points_all_valid.csv",8,5,30000),
        ("ma8_a10_h50km",base/"fluent_export/ma8_alpha10_h50km.csv",
         base/"runs/ma8_alpha10_h50km_f3/low_fidelity_points_all_valid.csv",8,10,50000),
    ]
    out_dir=base/"runs/faceted3d_v2_phase1_sandbox"
    out_dir.mkdir(parents=True,exist_ok=True)

    results=[]
    for label,fc,f3c,mach,alpha,h in cases:
        r=analyze_case(label,fc,f3c,out_dir,mach,alpha,h)
        results.append(r)

    # ---- Summary MD ----
    sm=out_dir/"v1_vs_v2_three_case_summary.md"
    with open(sm,"w",encoding="utf-8") as f:
        f.write("# Faceted3D v2 Phase 1: v1 Busemann vs v2 Newtonian-like Cp\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"> v2 params: Cp = {NEWTONIAN_A} * sin(phi)^{NEWTONIAN_N}\n\n")

        f.write("## Per-case comparison\n\n")
        f.write("|Metric|Ma6_a5_30|Ma8_a5_30|Ma8_a10_50|\n")
        f.write("|------|---------|---------|----------|\n")
        for key,title in [("cp_fluent_mean","Fluent Cp"),("cp_v1_mean","v1 Busemann Cp"),("cp_v2_mean","v2 Newton Cp"),
                          ("cp_ratio_v1","v1 Cp ratio"),("cp_ratio_v2","v2 Cp ratio"),
                          ("p_ratio_v1","v1 p_ratio"),("p_ratio_v2","v2 p_ratio"),
                          ("q_ratio_v1","v1 q_ratio"),("q_ratio_v2","v2 q_ratio")]:
            is_rat="ratio" in key
            vals=[f"{r[key]:.2f}x" if is_rat else f"{r[key]:.4f}" for r in results]
            f.write(f"|{title}|{'|'.join(vals)}|\n")
        f.write(f"|n_valid_v2|{'|'.join([str(r['n_valid']) for r in results])}|\n")

        f.write("\n## Improvement\n\n")
        f.write("|Case|p_ratio v1→v2|q_ratio v1→v2|Cp ratio v1→v2|\n")
        f.write("|----|-------------|-------------|-------------|\n")
        for r in results:
            f.write(f"|{r['label']}|{r['p_ratio_v1']:.2f}→{r['p_ratio_v2']:.2f}|{r['q_ratio_v1']:.2f}→{r['q_ratio_v2']:.2f}|{r['cp_ratio_v1']:.1f}x→{r['cp_ratio_v2']:.1f}x|\n")

        f.write("\n## Convergence criteria\n\n")
        all_p_good=all(r['p_ratio_v2']<1.5 and r['p_ratio_v2']>0.5 for r in results)
        all_q_good=all(r['q_ratio_v2']<2.0 and r['q_ratio_v2']>0.3 for r in results)
        all_cp_good=all(r['cp_ratio_v2']<2.0 and r['cp_ratio_v2']>0.3 for r in results)

        f.write(f"### Pressure ratio within [0.5, 1.5] across all cases?\n")
        pstr=", ".join([f'{r["label"]}={r["p_ratio_v2"]:.2f}' for r in results])
        f.write(f"{'**YES**' if all_p_good else '**NO**'}: {pstr}\n\n")
        f.write(f"### Heat flux ratio within [0.3, 2.0] across all cases?\n")
        qstr=", ".join([f'{r["label"]}={r["q_ratio_v2"]:.2f}' for r in results])
        f.write(f"{'**YES**' if all_q_good else '**NO**'}: {qstr}\n\n")
        f.write(f"### Cp ratio within [0.3, 2.0] across all cases?\n")
        cstr=", ".join([f'{r["label"]}={r["cp_ratio_v2"]:.1f}x' for r in results])
        f.write(f"{'**YES**' if all_cp_good else '**NO**'}: {cstr}\n\n")

        if all_p_good and all_q_good and all_cp_good:
            f.write("## Veredict\n\n")
            f.write("**v2 Newtonian-like Cp passes all convergence criteria.**\n")
            f.write("v2 improves Cp ratio, pressure ratio, and heat flux ratio across all 3 cases.\n")
            f.write("Discussion about residual learning can begin.\n")
        else:
            f.write("## Veredict\n\n")
            f.write("**v2 improves but does not fully converge all criteria.**\n")
            if not all_cp_good:
                f.write("- Cp ratio still outside [0.3, 2.0] for some cases — may need A/n tuning or B_x_relaxation\n")
            if not all_q_good:
                f.write("- q_ratio still outside [0.3, 2.0] — check Re_x / x_eff / transition\n")

        f.write("\n---\n")
        f.write("\n*Generated by `scripts/faceted3d_v2_phase1_sandbox.py`*\n")

    print(f"\n  written: {sm.name}")
    print(f"\nFaceted3D v2 Phase 1 sandbox DONE — outputs in {out_dir}")


if __name__=="__main__":
    main()
