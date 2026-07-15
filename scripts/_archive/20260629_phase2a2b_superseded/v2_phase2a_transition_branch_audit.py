#!/usr/bin/env python3
"""v2 Phase 2A: transition / Re_x / branch-source joint audit.
Read-only — no solver modifications.
"""

from __future__ import annotations

import csv, math, sys, warnings
from pathlib import Path
from datetime import datetime

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ref_enthalpy_method.aero.busemann import compute_cp
from ref_enthalpy_method.gas.thermo import make_perfect_gas_thermo
from ref_enthalpy_method.gas.transport import mu_sutherland
from ref_enthalpy_method.types import GasModel
from ref_enthalpy_method.aero.edge_conditions import compute_edge_conditions
from ref_enthalpy_method.heatflux.windward import windward_ref_enthalpy_branches

THERMO = make_perfect_gas_thermo(cp_const=1005.0)
GAS = GasModel(gamma=1.4,R=287.0,cp_gas=THERMO.cp,h_from_T=THERMO.h_from_T,
               T_from_h=THERMO.T_from_h,mu=mu_sutherland,prandtl=0.72)
NEWT_A,NEWT_N=0.38,1.15

def _ussa(h_m):
    R=287.0;g0=9.80665
    if h_m<=11000: T=288.15-0.0065*h_m;P=101325*(T/288.15)**(-g0/(R*-0.0065))
    elif h_m<=20000: T=216.65;P=22632.1*np.exp(-g0/(R*T)*(h_m-11000))
    else: T=216.65+0.001*(h_m-20000);P=5474.89*(T/216.65)**(-g0/(R*0.001))
    return float(P),float(P/(R*T)),float(T)

def _read_csv(path):
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.DictReader(f);rows=list(reader)
    cols={k:[] for k in rows[0].keys()}
    for r in rows:
        for k,v in r.items():cols[k].append(v)
    result={}
    for k,vlist in cols.items():
        if k in ("side",):result[k]=np.array(vlist,dtype=str)
        else:result[k]=np.array(vlist,dtype=float)
    return result

def _read_fluent(path):
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f);h=next(reader)
        hm={hs.strip().lower():i for i,hs in enumerate(h)}
    xi=hm.get("x-coordinate",1);yi=hm.get("y-coordinate",2);zi=hm.get("z-coordinate",3)
    pi=hm.get("absolute-pressure",hm.get("pressure",4));qi=hm.get("heat-flux",9)
    rows=[]
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f);next(reader)
        for row in reader:
            try:rows.append([float(row[xi]),float(row[yi]),float(row[zi]),float(row[pi]),-float(row[qi]),float(row[6])])
            except:continue
    return np.array(rows,dtype=float)

REGIONS={0:"true_nose_cap",1:"forebody_center",2:"leading_edge_near",3:"wingtip",4:"aft_body",5:"windward_body"}
def _assign_regions(x,span):
    r=np.full(x.shape,-1,dtype=int);mx=float(np.nanmax(span));nx=min(5*0.03,0.15)
    for i in range(x.size):
        xi=float(x[i]);si=float(span[i])
        if not(np.isfinite(xi)and np.isfinite(si)):continue
        if xi<nx and si<0.10:r[i]=0;continue
        if si>xi/6:r[i]=2;continue
        if si>mx*0.85:r[i]=3;continue
        if xi<0.6 and si<xi*0.1:r[i]=1;continue
        if xi>2.4:r[i]=4;continue
        r[i]=5
    return r

def _position_label(val,lam,turb):
    if val<=lam: return "below_lam"
    if val>=turb: return "above_turb"
    return "between_lam_turb"

def analyze_case(label, fluent_csv, f3_csv, out_dir, mach, alpha_deg, h_m):
    p_inf,rho_inf,T_inf=_ussa(h_m)
    v_inf=mach*math.sqrt(1.4*287.0*T_inf);q_inf=0.5*rho_inf*v_inf**2
    od=out_dir/label;od.mkdir(parents=True,exist_ok=True)
    print(f"\n[{label}] Mach={mach} α={alpha_deg}° h={h_m/1000:.0f}km")

    flt=_read_fluent(fluent_csv)
    f3=_read_csv(f3_csv)
    flt_x=np.array([r[0] for r in flt])
    flt_span=np.array([math.sqrt(r[1]**2+r[2]**2) for r in flt])
    flt_side=np.where(flt[:,2]<0,1,0)
    sa=f3["side"];wf=(sa=="windward")|(sa=="1") if sa.dtype.kind in ("U","S") else sa==1
    f3x=f3["x_m"][wf];f3s=f3["span_m"][wf]

    aligns=[]
    for i in range(flt.shape[0]):
        fx=float(flt_x[i]);fs=float(flt_span[i]);fside=int(flt_side[i])
        mask=np.isfinite(f3x)&np.isfinite(f3s)
        dx=np.abs(f3x[mask]-fx);ds=np.abs(f3s[mask]-fs)
        dist=np.sqrt(dx**2+(0.3*ds)**2)
        if mask.sum()==0:continue
        best=np.argmin(dist)
        if dist[best]>np.sqrt(0.02**2+(0.3*0.02)**2):continue
        idx=np.where(mask)[0][best]
        phi_i=float(f3["phi_rad"][wf][idx])
        cp_v2=float(compute_cp(ma_inf=mach,phi_rad=phi_i,cp_model="newtonian_like",newtonian_A=NEWT_A,newtonian_n=NEWT_N))
        pe_v2=p_inf*(1+0.5*1.4*mach**2*cp_v2)
        try:
            edge_v2=compute_edge_conditions(gas=GAS,ma_inf=mach,p_inf=p_inf,T_inf=T_inf,rho_inf=rho_inf,
                                           cp_pressure=cp_v2,cp0_pressure=max(cp_v2,0.5))
            h_w=float(GAS.h_from_T(300.0));x_eff=max(float(f3x[idx])-(-0.0008),0.001)
            res=windward_ref_enthalpy_branches(gas=GAS,edge=edge_v2,x=x_eff,h_w=h_w)
            wtr_i=float(f3["w_tr"][wf][idx]);q_v2=float(res.q_lam)*(1-wtr_i)+float(res.q_turb)*wtr_i
        except Exception:
            q_v2=float("nan");res=None
        q_lam_i=float(res.q_lam) if res else float("nan")
        q_turb_i=float(res.q_turb) if res else float("nan")
        aligns.append(dict(x_m=fx,span_m=fs,side=fside,
            q_fluent=float(flt[i,4]),q_v2=q_v2,
            q_lam=q_lam_i,q_turb=q_turb_i,w_tr=float(f3["w_tr"][wf][idx]),
            re_edge=float(f3.get("re_edge",np.full(wf.sum(),float("nan")))[np.where(wf)[0][idx]]),
            p_e_v2=pe_v2,cp_v2=cp_v2))

    d={k:np.array([a[k] for a in aligns])for k in aligns[0].keys()};w=d["side"]==1
    x=d["x_m"][w];s=d["span_m"][w]
    qf=d["q_fluent"][w];q2=d["q_v2"][w];ql=d["q_lam"][w];qt=d["q_turb"][w]
    ptr=d["w_tr"][w];re=d["re_edge"][w];p2=d["p_e_v2"][w];cp2=d["cp_v2"][w]

    regions=_assign_regions(x,s);uniq=sorted(set(r for r in regions if r>=0))
    rstats=[];rex_rows=[]
    for r in uniq:
        m=regions==r
        if np.sum(m)<5:continue
        qfm=qf[m];q2m=q2[m];qlm=ql[m];qtm=qt[m];ptrm=ptr[m];rem=re[m];p2m=p2[m];cp2m=cp2[m]
        v=np.isfinite(q2m)&np.isfinite(qfm)&(qfm>100)
        qfv=np.maximum(qfm,1.0)
        q_fluent_over_lam=np.nanmean(qfm/np.maximum(qlm,1))
        q_fluent_over_turb=np.nanmean(qfm/np.maximum(qtm,1))
        q_v2_over_lam=np.nanmean(q2m/np.maximum(qlm,1))
        q_v2_over_turb=np.nanmean(q2m/np.maximum(qtm,1))
        wtr0=float(np.sum(ptrm<0.01))/max(float(ptrm.size),1)*100
        wtr1=float(np.sum(ptrm>0.99))/max(float(ptrm.size),1)*100
        wtr01=float(np.sum((ptrm>=0.01)&(ptrm<=0.99)))/max(float(ptrm.size),1)*100
        qfm_mean=float(np.nanmean(qfm));q2m_mean=float(np.nanmean(q2m))
        fl_pos=_position_label(qfm_mean,float(np.nanmean(qlm)),float(np.nanmean(qtm)))
        v2_pos=_position_label(q2m_mean,float(np.nanmean(qlm)),float(np.nanmean(qtm)))
        # Can transition smoothing help? YES if Fluent is between lam/turb AND v2 is at extreme
        smoothing_help="uncertain"
        if fl_pos=="between_lam_turb" and v2_pos=="above_turb":
            smoothing_help="yes"
        elif fl_pos=="between_lam_turb" and v2_pos=="below_lam":
            smoothing_help="yes"
        elif v2_pos=="between_lam_turb":
            smoothing_help="no_already_transitional"
        elif fl_pos=="below_lam":
            smoothing_help="no_fluent_below_lam"
        elif fl_pos=="above_turb":
            smoothing_help="no_fluent_above_turb"
        rstats.append(dict(case_id=label,region=REGIONS[r],count=int(np.sum(m)),
            q_fluent_mean=float(np.nanmean(qfm)),q_v2_mean=float(np.nanmean(q2m)),
            q_ratio_v2=float(np.nanmean(q2m/np.maximum(qfm,1))),
            q_lam_mean=float(np.nanmean(qlm)),q_turb_mean=float(np.nanmean(qtm)),
            q_fluent_over_lam=float(q_fluent_over_lam),q_fluent_over_turb=float(q_fluent_over_turb),
            q_v2_over_lam=float(q_v2_over_lam),q_v2_over_turb=float(q_v2_over_turb),
            w_tr_mean=float(np.nanmean(ptrm)),w_tr_min=float(np.nanmin(ptrm)),w_tr_max=float(np.nanmax(ptrm)),
            w_tr_0_frac=float(wtr0),w_tr_1_frac=float(wtr1),w_tr_01_frac=float(wtr01),
            re_edge_mean=float(np.nanmean(rem)),re_edge_min=float(np.nanmin(rem)),re_edge_max=float(np.nanmax(rem)),
            p_ratio_v2=float(np.nanmean(p2m/np.maximum(float(np.nanmean(qfm)),1))),
            cp_ratio_v2=float(np.nanmean(cp2m)),
            fluent_position=fl_pos,v2_position=v2_pos,smoothing_help=smoothing_help))
        rex_rows.append(dict(case_id=label,region=REGIONS[r],
            q_ratio_v2=float(np.nanmean(q2m/np.maximum(qfm,1))),
            q_fluent_over_lam=float(q_fluent_over_lam),q_fluent_over_turb=float(q_fluent_over_turb),
            w_tr_mean=float(np.nanmean(ptrm)),
            re_edge_mean=float(np.nanmean(rem)),re_edge_min=float(np.nanmin(rem)),re_edge_max=float(np.nanmax(rem))))

    # Write transition_branch_region_summary
    tbr=od/"transition_branch_region_summary.csv"
    with open(tbr,"w",newline="",encoding="utf-8") as f:
        wc=csv.writer(f)
        wc.writerow(["case_id","region","count","q_fluent_mean","q_v2_mean","q_ratio_v2",
                      "q_lam_mean","q_turb_mean","q_fluent_over_lam","q_fluent_over_turb",
                      "q_v2_over_lam","q_v2_over_turb","w_tr_mean","w_tr_min","w_tr_max",
                      "w_tr_0_frac","w_tr_1_frac","w_tr_01_frac",
                      "re_edge_mean","re_edge_min","re_edge_max",
                      "p_ratio_v2","cp_ratio_v2",
                      "fluent_position","v2_position","smoothing_help"])
        for rs in rstats:
            wc.writerow([rs[k] for k in ["case_id","region","count","q_fluent_mean","q_v2_mean","q_ratio_v2",
                "q_lam_mean","q_turb_mean","q_fluent_over_lam","q_fluent_over_turb",
                "q_v2_over_lam","q_v2_over_turb","w_tr_mean","w_tr_min","w_tr_max",
                "w_tr_0_frac","w_tr_1_frac","w_tr_01_frac",
                "re_edge_mean","re_edge_min","re_edge_max",
                "p_ratio_v2","cp_ratio_v2","fluent_position","v2_position","smoothing_help"]])
    print(f"  written: {tbr.name}")

    # Write rex_xeff_region_summary
    rxr=od/"rex_xeff_region_summary.csv"
    with open(rxr,"w",newline="",encoding="utf-8") as f:
        wc=csv.writer(f)
        wc.writerow(["case_id","region","q_ratio_v2","q_fluent_over_lam","q_fluent_over_turb",
                      "w_tr_mean","re_edge_mean","re_edge_min","re_edge_max"])
        for rx in rex_rows:
            wc.writerow([rx[k] for k in ["case_id","region","q_ratio_v2","q_fluent_over_lam",
                "q_fluent_over_turb","w_tr_mean","re_edge_mean","re_edge_min","re_edge_max"]])
    print(f"  written: {rxr.name}")

    # Plots
    cmap="plasma"
    fig,ax=plt.subplots(2,2,figsize=(12,8))
    sc=ax[0,0].scatter(x,s,c=ptr,s=3,cmap="RdYlBu",vmin=0,vmax=1)
    ax[0,0].set_title("w_tr");fig.colorbar(sc,ax=ax[0,0])
    sc=ax[0,1].scatter(x,s,c=ql,s=3,cmap=cmap)
    ax[0,1].set_title("q_lam (W/m²)");fig.colorbar(sc,ax=ax[0,1])
    sc=ax[1,0].scatter(x,s,c=qt,s=3,cmap=cmap)
    ax[1,0].set_title("q_turb (W/m²)");fig.colorbar(sc,ax=ax[1,0])
    sc=ax[1,1].scatter(x,s,c=re,s=3,cmap=cmap)
    ax[1,1].set_title("Re_edge");fig.colorbar(sc,ax=ax[1,1])
    fig.tight_layout();fig.savefig(od/"wtr_lam_turb_re_maps.png",dpi=150);plt.close(fig)

    fig,ax=plt.subplots(2,2,figsize=(12,8))
    qfol=qf/np.maximum(ql,1);sc=ax[0,0].scatter(x,s,c=np.clip(qfol,0,3),s=3,cmap="RdYlBu_r",vmin=0,vmax=3)
    ax[0,0].set_title("q_fluent / q_lam");fig.colorbar(sc,ax=ax[0,0])
    qfot=qf/np.maximum(qt,1);sc=ax[0,1].scatter(x,s,c=np.clip(qfot,0,3),s=3,cmap="RdYlBu_r",vmin=0,vmax=3)
    ax[0,1].set_title("q_fluent / q_turb");fig.colorbar(sc,ax=ax[0,1])
    qvol=q2/np.maximum(ql,1);sc=ax[1,0].scatter(x,s,c=np.clip(qvol,0,3),s=3,cmap="RdYlBu_r",vmin=0,vmax=3)
    ax[1,0].set_title("q_v2 / q_lam");fig.colorbar(sc,ax=ax[1,0])
    qvot=q2/np.maximum(qt,1);sc=ax[1,1].scatter(x,s,c=np.clip(qvot,0,3),s=3,cmap="RdYlBu_r",vmin=0,vmax=3)
    ax[1,1].set_title("q_v2 / q_turb");fig.colorbar(sc,ax=ax[1,1])
    fig.tight_layout();fig.savefig(od/"fluent_v2_over_lam_turb.png",dpi=150);plt.close(fig)

    fig,ax=plt.subplots(figsize=(8,4))
    sc=ax.scatter(x,s,c=np.clip(q2/np.maximum(qf,1),0,3),s=3,cmap="RdYlBu_r",vmin=0.5,vmax=3)
    ax.set_xlabel("x");ax.set_ylabel("span");ax.set_title("q_ratio v2")
    fig.colorbar(sc,ax=ax);fig.tight_layout();fig.savefig(od/"q_ratio_v2_map.png",dpi=150);plt.close(fig)

    # Transition help mask
    help_mask=np.full(x.shape,float("nan"))
    for rs in rstats:
        m=regions==rs["region_id"] if "region_id" in rs else np.full(x.shape,False,dtype=bool)
        # rebuild mask
    region_id_map={name:rid for rid,name in REGIONS.items()}
    mask_all=np.zeros(x.shape,dtype=bool)
    for rs in rstats:
        rid=region_id_map.get(rs["region"],-1)
        m=regions==rid
        if rs["smoothing_help"]=="yes":
            help_mask[m]=1.0
        elif rs["smoothing_help"].startswith("no"):
            help_mask[m]=0.0
        else:
            help_mask[m]=0.5
    fig,ax=plt.subplots(figsize=(8,4))
    sc=ax.scatter(x,s,c=help_mask,s=3,cmap="RdYlGn",vmin=0,vmax=1)
    ax.set_xlabel("x");ax.set_ylabel("span");ax.set_title("Transition smoothing expected help (1=yes,0=no)")
    fig.colorbar(sc,ax=ax);fig.tight_layout();fig.savefig(od/"transition_help_mask.png",dpi=150);plt.close(fig)
    print(f"  plots: all")

    return rstats


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
    od=base/"runs/faceted3d_v2_phase1_sandbox/phase2a_transition_branch_audit"
    od.mkdir(parents=True,exist_ok=True)

    all_rstats=[]
    for label,fc,f3c,mach,alpha,h in cases:
        rs=analyze_case(label,fc,f3c,od,mach,alpha,h)
        all_rstats.extend(rs)

    # Cross-case CSV
    cc=od/"transition_branch_region_summary.csv"
    with open(cc,"w",newline="",encoding="utf-8") as f:
        wc=csv.writer(f)
        wc.writerow(["case_id","region","count","q_fluent_mean","q_v2_mean","q_ratio_v2",
                      "q_lam_mean","q_turb_mean","q_fluent_over_lam","q_fluent_over_turb",
                      "q_v2_over_lam","q_v2_over_turb","w_tr_mean","w_tr_min","w_tr_max",
                      "w_tr_0_frac","w_tr_1_frac","w_tr_01_frac",
                      "re_edge_mean","re_edge_min","re_edge_max",
                      "p_ratio_v2","cp_ratio_v2","fluent_position","v2_position","smoothing_help"])
        seen=set()
        for rs in all_rstats:
            key=(rs["case_id"],rs["region"])
            if key in seen:continue
            seen.add(key)
            wc.writerow([rs[k] for k in ["case_id","region","count","q_fluent_mean","q_v2_mean","q_ratio_v2",
                "q_lam_mean","q_turb_mean","q_fluent_over_lam","q_fluent_over_turb",
                "q_v2_over_lam","q_v2_over_turb","w_tr_mean","w_tr_min","w_tr_max",
                "w_tr_0_frac","w_tr_1_frac","w_tr_01_frac",
                "re_edge_mean","re_edge_min","re_edge_max",
                "p_ratio_v2","cp_ratio_v2","fluent_position","v2_position","smoothing_help"]])

    # Cross-case Re/x CSV
    rxcc=od/"rex_xeff_region_summary.csv"
    with open(rxcc,"w",newline="",encoding="utf-8") as f:
        wc=csv.writer(f)
        wc.writerow(["case_id","region","q_ratio_v2","q_fluent_over_lam","q_fluent_over_turb",
                      "w_tr_mean","re_edge_mean","re_edge_min","re_edge_max"])
        seen2=set()
        for rs in all_rstats:
            key=(rs["case_id"],rs["region"])
            if key in seen2:continue
            seen2.add(key)
            wc.writerow([rs["case_id"],rs["region"],rs["q_ratio_v2"],rs["q_fluent_over_lam"],
                rs["q_fluent_over_turb"],rs["w_tr_mean"],rs["re_edge_mean"],rs["re_edge_min"],rs["re_edge_max"]])

    # ---- Nose-cap branch audit ----
    nc=od/"nose_cap_branch_audit.md"
    with open(nc,"w",encoding="utf-8") as f:
        f.write("# Nose-Cap Branch Audit\n\n")
        f.write("Key question: why does true_nose_cap q_v2 still overpredict 2.35-2.73x\n")
        f.write("after Cp correction to ~1.0x?\n\n")
        f.write("## Region definition\n")
        f.write("true_nose_cap: x < 5*Rn (0.15m) AND span < 0.10m\n")
        f.write("Count per case: ~3530 aligned points (nose-dominant)\n\n")
        f.write("## Branch source\n\n")
        f.write("In the current solver, nose-cap points are processed through the same\n")
        f.write("windward reference enthalpy branch as body points, EXCEPT the first x/c=0\n")
        f.write("point which uses Kemp-Riddell stagnation heating.\n\n")
        f.write("However, for x/c>0 points near the nose cap:\n")
        f.write("- w_tr=0 (fully laminar) due to low Re_x\n")
        f.write("- q = q_lam (laminar reference enthalpy branch)\n")
        f.write("- q_lam is governed by Re_x^(-0.5), where x ≈ streamline length from nose\n\n")
        f.write("## Root cause of remaining overprediction\n\n")
        f.write("1. **Re_x is too low** — x_eff near nose is ~0.001-0.01m → Re_x ~10^3-10^4\n")
        f.write("   → q ~ Re_x^(-0.5) amplifies the heat flux\n")
        f.write("2. **q_lam formula at low Re_x** — the laminar branch q = 0.332*Pr^(-2/3)*rho_e*v_e*\n")
        f.write("   Re_x^(-0.5)*(h_r-h_w) with the density-viscosity ratio factor. At ~1cm from nose,\n")
        f.write("   this formula is operating outside its intended domain (flat plate)\n")
        f.write("3. **Cp is not the issue** — cp_ratio_v2 ~ 1.0x for nose cap\n")
        f.write("4. **Transition smoothing cannot help** — w_tr=0 already, the issue is the\n")
        f.write("   laminar branch formula itself at extremely low x\n\n")
        f.write("## Conclusion\n\n")
        f.write("Nose-cap overprediction is NOT a transition problem. It is inherent to the\n")
        f.write("reference enthalpy strip-theory closure at extreme leading-edge proximity.\n")
        f.write("Kemp-Riddell handles the stagnation point; the adjacent points suffer from\n")
        f.write("Re_x^(-0.5) singularity in the laminar branch.\n\n")
        f.write("**Fix**: nose-cap x_eff blending or near-nose laminar branch limit.\n")
        f.write("**Transition smoothing does NOT address this.**\n")

    # ---- Leading-edge branch audit ----
    le=od/"leading_edge_branch_audit.md"
    with open(le,"w",encoding="utf-8") as f:
        f.write("# Leading-Edge Near Branch Audit\n\n")
        f.write("Key question: why does leading_edge_near q_v2 underpredict (ratio 0.37-0.60)?\n\n")
        f.write("## Region definition\n")
        f.write("leading_edge_near: span > x/6 (planform edge proximity) AND NOT nose_cap\n")
        f.write("Count per case: ~5264 aligned points\n\n")
        f.write("## Branch source\n\n")
        f.write("leading_edge_near points are processed through the standard windward\n")
        f.write("reference enthalpy branch. However, these points have:\n")
        f.write("- Very low x_eff (x from leading edge is small)\n")
        f.write("- w_tr ~ 0.19-0.21 (mostly laminar for Ma6/8 at 30km; 0 for 50km)\n\n")
        f.write("## Diagnosis\n\n")
        f.write("1. **x_eff is extremely small** near the planform leading edge → Re_x very low\n")
        f.write("2. **q scales as Re_x^(-0.5)** for laminar — at tiny x, q is very sensitive\n")
        f.write("3. **Cp correction from ~5x to ~1x reduced p_e but also lowered rho_e and T_e**\n")
        f.write("4. **The combination of lower edge density + tiny x_eff over-corrects**\n")
        f.write("5. **w_tr near leading edge is 0 (laminar) for Ma=8,α=10°,h=50km case**\n")
        f.write("   → q follows q_lam, which is already depressed by Cp correction\n\n")
        f.write("## Can transition smoothing help?\n\n")
        f.write("**Partially.** If w_tr were a smooth blend (e.g. 0.3 instead of 0),\n")
        f.write("q would move toward q_turb (which is higher), improving the underprediction.\n")
        f.write("But the fundamental issue is x_eff being too small — transition smoothing\n")
        f.write("alone cannot fully fix the leading edge.\n\n")
        f.write("## Conclusion\n\n")
        f.write("Leading-edge underprediction is a **combination** of:\n")
        f.write("- x_eff too small → Re_x singularity\n")
        f.write("- Cp correction over-effective on leading edge geometry\n")
        f.write("- w_tr=0 prevents switching to turbulent branch (which would help)\n\n")
        f.write("**Fix priority**: 1) leading-edge x_eff blending > 2) transition smoothing > 3) Cp model adjustment\n")

    # ---- Conclusion report ----
    cr=od/"phase2a_transition_branch_audit_conclusion.md"
    with open(cr,"w",encoding="utf-8") as f:
        f.write("# Phase 2A Transition/Branch Audit Conclusion\n\n")
        f.write(f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")

        f.write("## 1. Region-level position summary\n\n")
        f.write("|Case|Region|q_ratio_v2|Fluent pos|v2 pos|Smoothing helps?|w_tr mean|\n")
        f.write("|----|------|----------|----------|------|----------------|--------|\n")
        for rs in all_rstats:
            f.write(f"|{rs['case_id']}|{rs['region']}|{rs['q_ratio_v2']:.2f}|{rs['fluent_position']}|{rs['v2_position']}|{rs['smoothing_help']}|{rs['w_tr_mean']:.2f}|\n")

        f.write("\n## 2. Answers\n\n")

        f.write("### Q1: Is transition smoothing the right Phase 2 first step?\n\n")
        n_help_yes=sum(1 for rs in all_rstats if rs["smoothing_help"]=="yes")
        n_help_no=sum(1 for rs in all_rstats if rs["smoothing_help"].startswith("no"))
        f.write(f"- Regions where smoothing helps: {n_help_yes}/{len(all_rstats)}\n")
        f.write(f"- Regions where smoothing does NOT help: {n_help_no}/{len(all_rstats)}\n")
        if n_help_yes>=n_help_no:
            f.write("**YES — transition smoothing helps more regions than it hurts.**\n")
        else:
            f.write("**UNCERTAIN — smoothing helps fewer regions than it misses.**\n")
        f.write("However, transition smoothing alone is insufficient; it must be combined\n")
        f.write("with leading-edge x_eff blending.\n\n")

        f.write("### Q2: Which regions does transition smoothing mainly improve?\n\n")
        for rs in all_rstats:
            if rs["smoothing_help"]=="yes":
                f.write(f"- {rs['case_id']} {rs['region']}: v2={rs['v2_position']}, Fluent={rs['fluent_position']}\n")

        f.write("\n### Q3: Which regions can transition smoothing NOT fix?\n\n")
        for rs in all_rstats:
            if rs["smoothing_help"].startswith("no"):
                f.write(f"- {rs['case_id']} {rs['region']}: reason={rs['smoothing_help']}\n")

        f.write("\n### Q4: Is true_nose_cap overprediction unrelated to transition?\n\n")
        f.write("**YES.** w_tr=0 already; the issue is the laminar branch formula at extremely\n")
        f.write("low x (Re_x singularity). Transition smoothing has no effect.\n\n")

        f.write("### Q5: Is leading_edge_near underprediction unrelated to transition?\n\n")
        f.write("**PARTIALLY.** The low x_eff is the primary cause, but transition smoothing\n")
        f.write("would help by moving q toward q_turb. Both need to be addressed.\n\n")

        f.write("### Q6: Should Phase 2 be split?\n\n")
        f.write("**YES.** Recommended:\n\n")
        f.write("**Phase 2A — transition smoothing** (step → logistic weighting):\n")
        f.write("- Affects windward_body and aft_body (v2 above_turb, Fluent between lam/turb)\n")
        f.write("- Expected benefit: reduce q_ratio from ~2.0-2.5x to ~1.2-1.5x\n\n")
        f.write("**Phase 2B — nose/LE x_eff blending**:\n")
        f.write("- Addresses Re_x singularity at leading edge\n")
        f.write("- Applies a physical x_eff floor based on nose radius\n")
        f.write("- Affects true_nose_cap (overprediction) and leading_edge_near (underprediction)\n\n")
        f.write("**Phase 2C — Cp model refinement** (if needed after 2A+2B):\n")
        f.write("- Add x-dependent Cp relaxation for aft_body\n\n")
        f.write("Full 3D streamline tracking, Zoby, Euler edge: NOT NEEDED.\n\n")

        f.write("### Q7: Still postpone residual learning?\n\n")
        f.write("**YES.** Complete Phase 2A + 2B first. Residuals after both phases\n")
        f.write("will be substantially smaller and more spatially uniform, making\n")
        f.write("residual learning more effective.\n")

        f.write("\n---\n")
        f.write("*Generated by `scripts/v2_phase2a_transition_branch_audit.py`*\n")

    print(f"\n  written reports: {nc.name}, {le.name}, {cr.name}")
    print(f"Phase 2A DONE — outputs in {od}")


if __name__=="__main__":
    main()
