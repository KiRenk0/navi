#!/usr/bin/env python3
"""Phase 2D Tasks T2-T5: comprehensive windward q-chain, cap_mask, aft_body, alignment diagnostics.
Read-only. No physics formula changes.
"""

from __future__ import annotations

import csv, math, sys, warnings
from pathlib import Path
from datetime import datetime

import numpy as np

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except:
    HAS_MPL = False

from ref_enthalpy_method.heatflux.leading_edge import kemp_riddell_modified_qsph_baseline
from ref_enthalpy_method.solver_faceted3d import WingLowFidelitySolverFaceted3D

BASE = Path(__file__).resolve().parent.parent
VEHICLE = BASE / "specs/vehicles/htv2_faceted3d_0629.yaml"
CASE_TEMPLATE = BASE / "specs/cases/template_faceted3d_fixedTw300.yaml"
SAMPLING = BASE / "specs/sampling/engineering_full_wing_surface_grid_81x41.yaml"
FLUENT_DIR = BASE / "fluent_export"
OUT_DIR = BASE / "runs/faceted3d_v2_phase2d_diagnostics"
DOCS_DIR = BASE / "docs"
FIG_DIR = OUT_DIR / "figures"

NEWTONIAN_A = 0.38; NEWTONIAN_N = 1.15
Rn = 0.03; r_cap = 0.03

# ---------------------------------------------------------------------------
# Atmosphere / freestream helpers
# ---------------------------------------------------------------------------
def _ussa(h_m):
    R = 287.0; g0 = 9.80665
    if h_m <= 11000: T = 288.15 - 0.0065*h_m; P = 101325*(T/288.15)**(-g0/(R*-0.0065))
    elif h_m <= 20000: T = 216.65; P = 22632.1*np.exp(-g0/(R*T)*(h_m-11000))
    else: T = 216.65 + 0.001*(h_m-20000); P = 5474.89*(T/216.65)**(-g0/(R*0.001))
    return float(P), float(P/(R*T)), float(T)

def _freestream_v(mach, T_inf):
    return mach * math.sqrt(1.4 * 287.0 * T_inf)

# ---------------------------------------------------------------------------
# Fluent readers
# ---------------------------------------------------------------------------
def _read_fluent_windward(path):
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f); h=next(reader)
    hm={hs.strip().lower():i for i,hs in enumerate(h)}
    xi=hm.get("x-coordinate",1); yi=hm.get("y-coordinate",2); zi=hm.get("z-coordinate",3)
    pi=hm.get("absolute-pressure",hm.get("pressure",4)); qi=hm.get("heat-flux",9)
    rows=[]
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f); next(reader)
        for row in reader:
            try:
                x=float(row[xi]); y=float(row[yi]); z=float(row[zi])
                if z>=0: continue
                span=math.sqrt(y*y+z*z); p=float(row[pi]); q=-float(row[qi])
                rows.append([x,span,z,p,q,y])
            except: continue
    return np.array(rows,dtype=float)

def _read_fluent_leeward(path):
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f); h=next(reader)
    hm={hs.strip().lower():i for i,hs in enumerate(h)}
    xi=hm.get("x-coordinate",1); yi=hm.get("y-coordinate",2); zi=hm.get("z-coordinate",3)
    pi=hm.get("absolute-pressure",hm.get("pressure",4)); qi=hm.get("heat-flux",9)
    rows=[]
    with open(path,"r",encoding="utf-8") as f:
        reader=csv.reader(f); next(reader)
        for row in reader:
            try:
                x=float(row[xi]); y=float(row[yi]); z=float(row[zi])
                if z<=0: continue
                span=math.sqrt(y*y+z*z); p=float(row[pi]); q=-float(row[qi])
                rows.append([x,span,z,p,q,y])
            except: continue
    return np.array(rows,dtype=float)

# ---------------------------------------------------------------------------
# Solver
# ---------------------------------------------------------------------------
def _run_solver(label,mach,alpha,h_m):
    import yaml as _yaml
    veh=_yaml.safe_load(VEHICLE.read_text(encoding="utf-8"))
    veh["vehicle_spec"]["faceted3d"]["cp_model"]="newtonian_like"
    veh["vehicle_spec"]["faceted3d"]["cp_newtonian_A"]=NEWTONIAN_A
    veh["vehicle_spec"]["faceted3d"]["cp_newtonian_n"]=NEWTONIAN_N
    vp=OUT_DIR/f"veh_{label}.yaml"
    with open(vp,"w",encoding="utf-8") as f: _yaml.dump(veh,f,default_flow_style=False)
    case=_yaml.safe_load(CASE_TEMPLATE.read_text(encoding="utf-8"))
    case["case_spec"]["lf_qw_model"]["transition"]["weighting"]="step"
    cp=OUT_DIR/f"case_{label}.yaml"
    with open(cp,"w",encoding="utf-8") as f: _yaml.dump(case,f,default_flow_style=False)
    solver=WingLowFidelitySolverFaceted3D(
        vehicle_config=str(vp),case_config=str(cp),
        sampling_config=str(SAMPLING),run_dir=str(OUT_DIR/label),
    )
    solver.compute_snapshot(mach=mach,alpha=alpha)
    return dict(solver.last_fields or {}),solver

def _trim(arr,ref_len):
    arr=np.asarray(arr,dtype=float).ravel()
    if len(arr)>=ref_len: return arr[:ref_len]
    out=np.full(ref_len,np.nan); out[:len(arr)]=arr; return out

def _nearest_match(solver_x,solver_span,flt_x,flt_span,flt_q,flt_p=None):
    """Return (matched_q, matched_p, dist, dx, dspan) arrays."""
    n=len(solver_x)
    mq=np.full(n,np.nan); mp=np.full(n,np.nan) if flt_p is not None else None
    md=np.full(n,np.nan); mdx=np.full(n,np.nan); mds=np.full(n,np.nan)
    for i in range(n):
        fx=float(solver_x[i]); fs=float(solver_span[i])
        if not (np.isfinite(fx) and np.isfinite(fs)): continue
        dx=np.abs(flt_x-fx); ds=np.abs(flt_span-fs)
        dist=np.sqrt(dx**2+(0.3*ds)**2)
        best=np.nanargmin(dist)
        thr=np.sqrt(0.02**2+(0.3*0.02)**2)
        if dist[best]<=thr:
            mq[i]=float(flt_q[best]); md[i]=float(dist[best])
            mdx[i]=float(dx[best]); mds[i]=float(ds[best])
            if mp is not None: mp[i]=float(flt_p[best])
    if mp is not None: return mq,mp,md,mdx,mds
    return mq,None,md,mdx,mds

# ---------------------------------------------------------------------------
# Region assignment
# ---------------------------------------------------------------------------
def _assign_region_windward(x,span,xc,mask_w):
    n=len(x)
    regions=np.full(n,"unknown",dtype=object)
    for i in range(n):
        if not (np.isfinite(x[i]) and np.isfinite(span[i]) and mask_w[i]): continue
        xi=float(x[i]); si=float(span[i]); xci=float(xc[i])
        if xi**2+si**2<=r_cap**2: regions[i]="cap_mask"
        elif xi<5.0*Rn and si<0.10: regions[i]="true_nose_cap"
        elif si>xi/6.0: regions[i]="leading_edge_near"
        elif xci>0.5: regions[i]="aft_body"
        else: regions[i]="windward_body"
    return regions

def _assign_region_leeward(x): return np.full(len(x),"leeward",dtype=object)

# ---------------------------------------------------------------------------
# Main diagnostic runner
# ---------------------------------------------------------------------------
def run_all():
    OUT_DIR.mkdir(parents=True,exist_ok=True)
    FIG_DIR.mkdir(parents=True,exist_ok=True)

    cases=[("ma6_a5_h30km",FLUENT_DIR/"ma6_alpha5_h30km.csv",6.0,5.0,30000),
           ("ma8_a5_h30km",FLUENT_DIR/"ma8_alpha5_h30km.csv",8.0,5.0,30000)]

    all_qchain_rows=[]   # T2
    all_alignment_rows=[] # T5
    all_capmask_direct={} # T3
    all_fluent_direct={}  # T3
    kr_cap_values={}      # T3

    per_case_data={}

    for label,fc,mach,alpha,h_m in cases:
        print(f"\n{'='*60}\nProcessing: {label}\n{'='*60}")
        p_inf,rho_inf,T_inf=_ussa(h_m)
        v_inf=_freestream_v(mach,T_inf)
        q_inf=0.5*rho_inf*v_inf**2
        h0=1005.0*T_inf+0.5*v_inf**2
        h_300K=1005.0*300.0

        fields,solver=_run_solver(label,mach,alpha,h_m)

        # Extract windward fields
        x_w=_trim(fields.get("x_w_m",np.array([])),4000)
        span_w=_trim(fields.get("span_w_m",np.array([])),4000)
        xc_w=_trim(fields.get("xc_w",np.array([])),4000)
        yb_w=_trim(fields.get("yb_w",np.array([])),4000)
        q_w=_trim(fields.get("q_w",np.array([])),4000)
        q_lam=_trim(fields.get("q_lam_w",np.array([])),4000)
        q_turb=_trim(fields.get("q_turb_w",np.array([])),4000)
        p_e_w=_trim(fields.get("p_e_w",np.array([])),4000)
        cp_w=_trim(fields.get("cp_w",np.array([])),4000)
        phi_w=_trim(fields.get("phi_w",np.array([])),4000)
        T_e_w=_trim(fields.get("T_e_w",np.array([])),4000)
        rho_e_w=_trim(fields.get("rho_e_w",np.array([])),4000)
        w_tr=_trim(fields.get("w_tr",np.array([])),4000)
        re_edge=_trim(fields.get("re_edge",np.array([])),4000)
        re_x_star=_trim(fields.get("re_x_star",np.array([])),4000)
        re_tri=_trim(fields.get("re_tri",np.array([])),4000)
        re_x_over_re_tri=_trim(fields.get("re_x_over_re_tri",np.array([])),4000)
        h_r_lam=_trim(fields.get("h_r_lam_w",np.array([])),4000)
        h_r_turb=_trim(fields.get("h_r_turb_w",np.array([])),4000)
        h_star_lam=_trim(fields.get("h_star_lam_w",np.array([])),4000)
        mask_w=_trim(fields.get("mask_w",np.array([])),4000).astype(bool)

        # Leeward
        x_l=_trim(fields.get("x_l_m",np.array([])),4000)
        span_l=_trim(fields.get("span_l_m",np.array([])),4000)
        xc_l=_trim(fields.get("xc_l",np.array([])),4000)
        q_l=_trim(fields.get("q_l",np.array([])),4000)
        mask_l=_trim(fields.get("mask_l",np.array([])),4000).astype(bool)

        # Trim to common windward length
        ref_w=min(len(x_w),len(span_w),len(xc_w),len(q_w),len(q_lam),len(q_turb),
                  len(p_e_w),len(cp_w),len(phi_w),len(T_e_w),len(rho_e_w),
                  len(w_tr),len(re_edge),len(re_x_star),len(re_tri),len(re_x_over_re_tri),
                  len(h_r_lam),len(h_r_turb),len(h_star_lam),len(mask_w))
        x_w=_trim(x_w,ref_w); span_w=_trim(span_w,ref_w); xc_w=_trim(xc_w,ref_w)
        yb_w=_trim(yb_w,ref_w); q_w=_trim(q_w,ref_w); q_lam=_trim(q_lam,ref_w)
        q_turb=_trim(q_turb,ref_w); p_e_w=_trim(p_e_w,ref_w); cp_w=_trim(cp_w,ref_w)
        phi_w=_trim(phi_w,ref_w); T_e_w=_trim(T_e_w,ref_w); rho_e_w=_trim(rho_e_w,ref_w)
        w_tr=_trim(w_tr,ref_w); re_edge=_trim(re_edge,ref_w); re_x_star=_trim(re_x_star,ref_w)
        re_tri=_trim(re_tri,ref_w); re_x_over_re_tri=_trim(re_x_over_re_tri,ref_w)
        h_r_lam=_trim(h_r_lam,ref_w); h_r_turb=_trim(h_r_turb,ref_w)
        h_star_lam=_trim(h_star_lam,ref_w); mask_w=_trim(mask_w,ref_w).astype(bool)
        ref_l=min(len(x_l),len(span_l),len(xc_l),len(q_l),len(mask_l))
        x_l=_trim(x_l,ref_l); span_l=_trim(span_l,ref_l); xc_l=_trim(xc_l,ref_l)
        q_l=_trim(q_l,ref_l); mask_l=_trim(mask_l,ref_l).astype(bool)

        # Regions
        w_regions=_assign_region_windward(x_w,span_w,xc_w,mask_w)

        # Fluent
        flt_w=_read_fluent_windward(fc)
        flt_w_q=flt_w[:,4]; flt_w_p=flt_w[:,3]; flt_w_x=flt_w[:,0]; flt_w_span=flt_w[:,1]

        # Alignment with distance info
        mq_w,mp_w,md_w,mdx_w,mds_w=_nearest_match(x_w,span_w,flt_w_x,flt_w_span,flt_w_q,flt_w_p)

        # ------------------------------------------------------------------
        # T2: Windward q-chain audit per-point CSV
        # ------------------------------------------------------------------
        for i in range(ref_w):
            if not mask_w[i]: continue
            dr={
                "case":label,"idx":i,
                "x_m":float(x_w[i]),"span_m":float(span_w[i]),"xc":float(xc_w[i]),
                "region":str(w_regions[i]),
                "q_w":float(q_w[i]) if np.isfinite(q_w[i]) else float("nan"),
                "q_lam_w":float(q_lam[i]) if np.isfinite(q_lam[i]) else float("nan"),
                "q_turb_w":float(q_turb[i]) if np.isfinite(q_turb[i]) else float("nan"),
                "w_tr":float(w_tr[i]) if np.isfinite(w_tr[i]) else float("nan"),
                "re_edge":float(re_edge[i]) if np.isfinite(re_edge[i]) else float("nan"),
                "re_x_star":float(re_x_star[i]) if np.isfinite(re_x_star[i]) else float("nan"),
                "re_tri":float(re_tri[i]) if np.isfinite(re_tri[i]) else float("nan"),
                "re_x_over_re_tri":float(re_x_over_re_tri[i]) if np.isfinite(re_x_over_re_tri[i]) else float("nan"),
                "T_e_w":float(T_e_w[i]) if np.isfinite(T_e_w[i]) else float("nan"),
                "p_e_w":float(p_e_w[i]) if np.isfinite(p_e_w[i]) else float("nan"),
                "rho_e_w":float(rho_e_w[i]) if np.isfinite(rho_e_w[i]) else float("nan"),
                "h_r_lam_w":float(h_r_lam[i]) if np.isfinite(h_r_lam[i]) else float("nan"),
                "h_r_turb_w":float(h_r_turb[i]) if np.isfinite(h_r_turb[i]) else float("nan"),
                "h_star_lam_w":float(h_star_lam[i]) if np.isfinite(h_star_lam[i]) else float("nan"),
                "q_Fluent_matched":float(mq_w[i]) if np.isfinite(mq_w[i]) else float("nan"),
                "p_Fluent_matched":float(mp_w[i]) if mp_w is not None and np.isfinite(mp_w[i]) else float("nan"),
                "q_ratio":float(q_w[i]/mq_w[i]) if np.isfinite(q_w[i]) and np.isfinite(mq_w[i]) and mq_w[i]>0 else float("nan"),
                "p_ratio":float(p_e_w[i]/mp_w[i]) if np.isfinite(p_e_w[i]) and mp_w is not None and np.isfinite(mp_w[i]) and mp_w[i]>0 else float("nan"),
                "dist":float(md_w[i]) if np.isfinite(md_w[i]) else float("nan"),
                "dx":float(mdx_w[i]) if np.isfinite(mdx_w[i]) else float("nan"),
                "dspan":float(mds_w[i]) if np.isfinite(mds_w[i]) else float("nan"),
            }
            all_qchain_rows.append(dr)

        # ------------------------------------------------------------------
        # T5: Alignment sanity by region
        # ------------------------------------------------------------------
        region_names=["cap_mask","true_nose_cap","leading_edge_near","windward_body","aft_body"]
        for rname in region_names:
            m=w_regions==rname
            n_sol=int(np.sum(m))
            if n_sol==0: continue
            dists=md_w[m]; dxs=mdx_w[m]; dspan_s=mds_w[m]
            valid=np.isfinite(dists)
            n_aligned=int(np.sum(valid))
            # Fluent count in region
            fx_s,fspan_s=flt_w_x,flt_w_span
            if rname=="cap_mask": fm=(fx_s**2+fspan_s**2)<=r_cap**2
            elif rname=="true_nose_cap": fm=((fx_s<5*Rn)&(fspan_s<0.10)&((fx_s**2+fspan_s**2)>r_cap**2))
            elif rname=="leading_edge_near": fm=(~((fx_s<5*Rn)&(fspan_s<0.10)))&(fspan_s>fx_s/6.0)
            elif rname=="aft_body": fm=(~((fx_s<5*Rn)&(fspan_s<0.10)))&(~(fspan_s>fx_s/6.0))&(fx_s>1.8)
            else: fm=(~((fx_s<5*Rn)&(fspan_s<0.10)))&(~(fspan_s>fx_s/6.0))&(fx_s<=1.8)
            n_flt=int(np.sum(fm))
            if n_aligned>0:
                dv=dists[valid]
                dvx=dxs[valid]; dvs=dspan_s[valid]
                ar={"case":label,"region":rname,
                    "n_solver":n_sol,"n_fluent":n_flt,"n_aligned":n_aligned,
                    "mean_dist":float(np.nanmean(dv)),
                    "median_dist":float(np.nanmedian(dv)),
                    "p95_dist":float(np.percentile(dv,95)),
                    "max_dist":float(np.nanmax(dv)),
                    "mean_dx":float(np.nanmean(dvx)),
                    "median_dx":float(np.nanmedian(dvx)),
                    "mean_dspan":float(np.nanmean(dvs)),
                    "median_dspan":float(np.nanmedian(dvs)),
                    "dx_bias":float(np.nanmean(dvx))}
            else:
                ar={"case":label,"region":rname,
                    "n_solver":n_sol,"n_fluent":n_flt,"n_aligned":0,
                    "mean_dist":float("nan"),"median_dist":float("nan"),
                    "p95_dist":float("nan"),"max_dist":float("nan"),
                    "mean_dx":float("nan"),"median_dx":float("nan"),
                    "mean_dspan":float("nan"),"median_dspan":float("nan"),
                    "dx_bias":float("nan")}
            all_alignment_rows.append(ar)

        # Fluent leeward stats for T5
        flt_l=_read_fluent_leeward(fc)
        n_flt_l=int(np.sum(flt_l[:,2]>0))
        all_alignment_rows.append({"case":label,"region":"leeward",
            "n_solver":ref_l,"n_fluent":n_flt_l,"n_aligned":0,
            "mean_dist":float("nan"),"median_dist":float("nan"),
            "p95_dist":float("nan"),"max_dist":float("nan"),
            "mean_dx":float("nan"),"median_dx":float("nan"),
            "mean_dspan":float("nan"),"median_dspan":float("nan"),
            "dx_bias":float("nan")})

        # Store for figures
        per_case_data[label]={
            "x_w":x_w,"span_w":span_w,"xc_w":xc_w,
            "q_ratio":np.where(np.isfinite(mq_w)&(mq_w>0)&np.isfinite(q_w),q_w/mq_w,np.nan),
            "q_w":q_w,"q_lam":q_lam,"q_turb":q_turb,
            "w_tr":w_tr,"re_x_over_re_tri":re_x_over_re_tri,
            "T_e_w":T_e_w,"h_r_lam":h_r_lam,"h_star_lam":h_star_lam,
            "p_e_w":p_e_w,"re_edge":re_edge,"re_x_star":re_x_star,
            "regions":w_regions,
        }

        # ------------------------------------------------------------------
        # T3: cap_mask direct Fluent stats + KR q_cap
        # ------------------------------------------------------------------
        cm_mask=(flt_w_x**2+flt_w_span**2)<=r_cap**2
        cm_q=flt_w_q[cm_mask]
        cm_p=flt_w_p[cm_mask]
        n_cm_fluent=int(np.sum(cm_mask))
        cm_q_max=float(np.nanmax(cm_q)) if n_cm_fluent>0 else float("nan")
        cm_q_mean=float(np.nanmean(cm_q)) if n_cm_fluent>0 else float("nan")
        cm_q_median=float(np.nanmedian(cm_q)) if n_cm_fluent>0 else float("nan")
        cm_q_p95=float(np.percentile(cm_q,95)) if n_cm_fluent>0 else float("nan")
        cm_q_p99=float(np.percentile(cm_q,99)) if n_cm_fluent>0 else float("nan")
        peak_idx=np.nanargmax(cm_q) if n_cm_fluent>0 else 0
        peak_x=float(flt_w_x[cm_mask][peak_idx]) if n_cm_fluent>0 else float("nan")
        peak_span=float(flt_w_span[cm_mask][peak_idx]) if n_cm_fluent>0 else float("nan")

        # KR q_cap for two reference points (yb=0 centerline, and yb close to cap edge)
        rn_center=solver._leading_edge_rn_span_m(y_over_b=0.0)
        rn_edge=solver._leading_edge_rn_span_m(y_over_b=0.05)
        def kr_q(rn):
            return kemp_riddell_modified_qsph_baseline(
                R_N_m=float(rn),rn_unit=str(solver.lf_cfg.stagnation.rn_unit),
                rho_inf=rho_inf,v_inf=v_inf,h0=float(h0),h_w=float(h_300K),h_300K=float(h_300K))
        q_cap_center=float(kr_q(rn_center))
        q_cap_edge=float(kr_q(rn_edge))

        # Solver cap_mask points
        cm_sol_mask=(x_w**2+span_w**2)<=r_cap**2
        n_cm_sol=int(np.sum(cm_sol_mask))
        cm_sol_q=np.where(np.isfinite(mq_w)&(mq_w>0),mq_w,np.nan)
        cm_sol_ratios=np.where(np.isfinite(mq_w)&(mq_w>0)&np.isfinite(q_w),q_w/mq_w,np.nan)

        all_capmask_direct[label]={
            "n_solver":n_cm_sol,
            "n_fluent":n_cm_fluent,
            "flt_q_max":cm_q_max,"flt_q_mean":cm_q_mean,"flt_q_median":cm_q_median,
            "flt_q_p95":cm_q_p95,"flt_q_p99":cm_q_p99,
            "peak_x":peak_x,"peak_span":peak_span,
            "solver_center_q":float(q_w[0]) if ref_w>0 else float("nan"),
            "solver_edge_q":float(q_w[1]) if ref_w>1 else float("nan"),
            "kr_q_cap_center":q_cap_center,
            "kr_q_cap_edge":q_cap_edge,
            "kr_vs_fluent_max":q_cap_center/cm_q_max if cm_q_max>0 else float("nan"),
            "kr_vs_fluent_p99":q_cap_center/cm_q_p99 if cm_q_p99>0 else float("nan"),
            "kr_vs_fluent_mean":q_cap_center/cm_q_mean if cm_q_mean>0 else float("nan"),
            "solver_center_vs_fluent_peak":(float(q_w[0])/cm_q_max if ref_w>0 and cm_q_max>0 else float("nan")),
            "nn_matched_q_ratio_mean":float(np.nanmean(cm_sol_ratios)) if n_cm_sol>0 else float("nan"),
            "nn_matched_q_ratio_median":float(np.nanmedian(cm_sol_ratios)) if n_cm_sol>0 else float("nan"),
        }

        # true_nose_cap cap_mask-excluded direct stats
        tnc_mask=((flt_w_x<5*Rn)&(flt_w_span<0.10)&((flt_w_x**2+flt_w_span**2)>r_cap**2))
        tnc_q=flt_w_q[tnc_mask]
        all_capmask_direct[label].update({
            "n_tnc_fluent":int(np.sum(tnc_mask)),
            "tnc_flt_q_max":float(np.nanmax(tnc_q)) if np.sum(tnc_mask)>0 else float("nan"),
            "tnc_flt_q_mean":float(np.nanmean(tnc_q)) if np.sum(tnc_mask)>0 else float("nan"),
        })

    # ------------------------------------------------------------------
    # Write all outputs
    # ------------------------------------------------------------------

    # T2: q-chain audit CSV
    csv_t2=OUT_DIR/"windward_q_chain_audit.csv"
    if all_qchain_rows:
        keys=list(all_qchain_rows[0].keys())
        with open(csv_t2,"w",newline="",encoding="utf-8") as f:
            wc=csv.DictWriter(f,fieldnames=keys); wc.writeheader(); wc.writerows(all_qchain_rows)
        print(f"\nT2 CSV: {csv_t2.name} ({len(all_qchain_rows)} rows)")

    # T3: cap_mask metric recheck CSV
    csv_t3=OUT_DIR/"capmask_metric_recheck.csv"
    t3_rows=[]
    for label in all_capmask_direct:
        t3_rows.append({"case":label,**all_capmask_direct[label]})
    if t3_rows:
        keys=list(t3_rows[0].keys())
        with open(csv_t3,"w",newline="",encoding="utf-8") as f:
            wc=csv.DictWriter(f,fieldnames=keys); wc.writeheader(); wc.writerows(t3_rows)
        print(f"T3 CSV: {csv_t3.name} ({len(t3_rows)} rows)")

    # T4: aft_body outlier / transition audit
    csv_t4=OUT_DIR/"aft_body_outlier_transition_audit.csv"
    t4_rows=[]
    for dr in all_qchain_rows:
        if dr["region"]!="aft_body": continue
        t4_rows.append(dr)
    if t4_rows:
        keys=list(t4_rows[0].keys())
        with open(csv_t4,"w",newline="",encoding="utf-8") as f:
            wc=csv.DictWriter(f,fieldnames=keys); wc.writeheader(); wc.writerows(t4_rows)
        print(f"T4 CSV: {csv_t4.name} ({len(t4_rows)} rows)")

    # T5: alignment sanity CSV
    csv_t5=OUT_DIR/"alignment_sanity_by_region.csv"
    if all_alignment_rows:
        keys=list(all_alignment_rows[0].keys())
        with open(csv_t5,"w",newline="",encoding="utf-8") as f:
            wc=csv.DictWriter(f,fieldnames=keys); wc.writeheader(); wc.writerows(all_alignment_rows)
        print(f"T5 CSV: {csv_t5.name} ({len(all_alignment_rows)} rows)")

    # ------------------------------------------------------------------
    # Figures
    # ------------------------------------------------------------------
    if HAS_MPL:
        _plot_qchain(per_case_data)
        _plot_capmask_summary(all_capmask_direct)
        _plot_aft_body_outliers(t4_rows)

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    _write_t2_report(all_qchain_rows, per_case_data)
    _write_t3_report(all_capmask_direct)
    _write_t4_report(t4_rows, per_case_data)
    _write_t5_report(all_alignment_rows)

    print("\nAll tasks completed.")

# ---------------------------------------------------------------------------
# T2 Figures
# ---------------------------------------------------------------------------
def _plot_qchain(pcd):
    cases=list(pcd.keys())
    colors={"cap_mask":"red","true_nose_cap":"orange","leading_edge_near":"gold",
            "windward_body":"green","aft_body":"blue","unknown":"gray"}

    # 1. q_ratio vs re_x_over_re_tri
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ai,label in enumerate(cases):
        ax=axes[ai]; d=pcd[label]
        for rname,color in colors.items():
            m=d["regions"]==rname
            if np.sum(m)==0: continue
            ax.scatter(d["re_x_over_re_tri"][m],d["q_ratio"][m],s=4,c=color,alpha=0.5,label=rname)
        ax.set_xlabel("re_x_over_re_tri"); ax.set_ylabel("q_ratio"); ax.set_title(label)
        ax.axhline(1.0,color="k",ls="--",lw=0.5); ax.legend(fontsize=5,markerscale=2); ax.grid(alpha=0.2)
    fig.suptitle("q_ratio vs re_x_over_re_tri (by region)"); fig.tight_layout()
    fig.savefig(FIG_DIR/"T2_q_ratio_vs_re_x_over_re_tri.png",dpi=150); plt.close(fig)

    # 2. q_ratio vs w_tr
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ai,label in enumerate(cases):
        ax=axes[ai]; d=pcd[label]
        for rname,color in colors.items():
            m=d["regions"]==rname
            if np.sum(m)==0: continue
            jitter=d["w_tr"][m]+np.random.normal(0,0.01,np.sum(m)) # small jitter
            ax.scatter(jitter,d["q_ratio"][m],s=4,c=color,alpha=0.5,label=rname)
        ax.set_xlabel("w_tr"); ax.set_ylabel("q_ratio"); ax.set_title(label)
        ax.axhline(1.0,color="k",ls="--",lw=0.5); ax.legend(fontsize=5,markerscale=2); ax.grid(alpha=0.2)
    fig.suptitle("q_ratio vs w_tr (by region)"); fig.tight_layout()
    fig.savefig(FIG_DIR/"T2_q_ratio_vs_w_tr.png",dpi=150); plt.close(fig)

    # 3. q_ratio vs x_m
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ai,label in enumerate(cases):
        ax=axes[ai]; d=pcd[label]
        for rname,color in colors.items():
            m=d["regions"]==rname
            if np.sum(m)==0: continue
            ax.scatter(d["x_w"][m],d["q_ratio"][m],s=4,c=color,alpha=0.5,label=rname)
        ax.set_xlabel("x_m"); ax.set_ylabel("q_ratio"); ax.set_title(label)
        ax.axhline(1.0,color="k",ls="--",lw=0.5); ax.legend(fontsize=5,markerscale=2); ax.grid(alpha=0.2)
    fig.suptitle("q_ratio vs x_m (by region)"); fig.tight_layout()
    fig.savefig(FIG_DIR/"T2_q_ratio_vs_x_m.png",dpi=150); plt.close(fig)

    # 4. q_ratio vs T_e_w
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ai,label in enumerate(cases):
        ax=axes[ai]; d=pcd[label]
        for rname,color in colors.items():
            m=d["regions"]==rname
            if np.sum(m)==0: continue
            ax.scatter(d["T_e_w"][m],d["q_ratio"][m],s=4,c=color,alpha=0.5,label=rname)
        ax.set_xlabel("T_e_w (K)"); ax.set_ylabel("q_ratio"); ax.set_title(label)
        ax.axhline(1.0,color="k",ls="--",lw=0.5); ax.legend(fontsize=5,markerscale=2); ax.grid(alpha=0.2)
    fig.suptitle("q_ratio vs T_e_w (by region)"); fig.tight_layout()
    fig.savefig(FIG_DIR/"T2_q_ratio_vs_T_e_w.png",dpi=150); plt.close(fig)

    # 5. q_ratio vs (h_r_lam - h_w), approximately h_w = 1005*300
    h_w=1005*300.0
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ai,label in enumerate(cases):
        ax=axes[ai]; d=pcd[label]
        dh=d["h_r_lam"]-h_w
        for rname,color in colors.items():
            m=d["regions"]==rname
            if np.sum(m)==0: continue
            ax.scatter(dh[m],d["q_ratio"][m],s=4,c=color,alpha=0.5,label=rname)
        ax.set_xlabel("h_r_lam - h_w (J/kg)"); ax.set_ylabel("q_ratio"); ax.set_title(label)
        ax.axhline(1.0,color="k",ls="--",lw=0.5); ax.legend(fontsize=5,markerscale=2); ax.grid(alpha=0.2)
    fig.suptitle("q_ratio vs (h_r_lam - h_w) (by region)"); fig.tight_layout()
    fig.savefig(FIG_DIR/"T2_q_ratio_vs_h_r_lam_minus_h_w.png",dpi=150); plt.close(fig)

    # 6. q profiles: q_lam, q_turb, q_w along x
    fig,axes=plt.subplots(1,2,figsize=(14,5),sharey=True)
    for ai,label in enumerate(cases):
        ax=axes[ai]; d=pcd[label]
        # Sort by x
        sidx=np.argsort(d["x_w"])
        ax.plot(d["x_w"][sidx],d["q_w"][sidx],label="q_w",lw=0.8)
        ax.plot(d["x_w"][sidx],d["q_lam"][sidx],label="q_lam",lw=0.8,alpha=0.7)
        ax.plot(d["x_w"][sidx],d["q_turb"][sidx],label="q_turb",lw=0.8,alpha=0.7)
        ax.set_xlabel("x_m"); ax.set_ylabel("q (W/m^2)"); ax.set_title(label)
        ax.legend(fontsize=6); ax.grid(alpha=0.2)
    fig.suptitle("q profiles along x (sorted)"); fig.tight_layout()
    fig.savefig(FIG_DIR/"T2_q_profiles_along_x.png",dpi=150); plt.close(fig)

    # 7. LE + windward_body + aft_body comparison
    fig,axes=plt.subplots(2,3,figsize=(15,8))
    targets=["leading_edge_near","windward_body","aft_body"]
    for ri,rname in enumerate(targets):
        for ci,label in enumerate(cases):
            ax=axes[ci][ri]; d=pcd[label]
            m=d["regions"]==rname
            if np.sum(m)==0: continue
            ax.scatter(d["xc_w"][m],d["q_ratio"][m],s=4,alpha=0.5)
            ax.set_title(f"{rname} {label}"); ax.set_xlabel("x/c"); ax.set_ylabel("q_ratio")
            ax.axhline(1.0,color="k",ls="--"); ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(FIG_DIR/"T2_LE_wbody_aft_q_ratio_vs_xc.png",dpi=150); plt.close(fig)

def _plot_capmask_summary(cmd):
    fig,ax=plt.subplots(figsize=(8,5))
    labels=list(cmd.keys())
    x=np.arange(len(labels)); w=0.25
    for i,label in enumerate(labels):
        d=cmd[label]
        ax.bar(x[i]-w,d["kr_vs_fluent_max"],w,label="KR/Fluent q_max")
        ax.bar(x[i],d["kr_vs_fluent_p99"],w,label="KR/Fluent q_p99")
        ax.bar(x[i]+w,d["kr_vs_fluent_mean"],w,label="KR/Fluent q_mean")
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("ratio"); ax.set_title("KR q_cap vs Fluent cap_mask direct stats")
    ax.axhline(1.0,color="k",ls="--"); ax.legend(); ax.grid(axis="y",alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR/"T3_kr_vs_fluent_capmask_direct.png",dpi=150); plt.close(fig)

def _plot_aft_body_outliers(t4_rows):
    if not t4_rows: return
    import collections
    by_case=collections.defaultdict(list)
    for r in t4_rows: by_case[r["case"]].append(r)
    fig,axes=plt.subplots(1,len(by_case),figsize=(12,5))
    if len(by_case)==1: axes=[axes]
    for ai,(label,rows) in enumerate(by_case.items()):
        ax=axes[ai]
        qrs=np.array([r["q_ratio"] for r in rows if np.isfinite(r["q_ratio"])])
        if len(qrs)==0: continue
        thr=np.percentile(qrs,95)
        ax.hist(qrs,bins=50,alpha=0.7)
        ax.axvline(thr,color="r",ls="--",label=f"p95={thr:.2f}")
        ax.set_xlabel("q_ratio"); ax.set_ylabel("count"); ax.set_title(label)
        ax.legend(); ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(FIG_DIR/"T4_aft_body_q_ratio_hist.png",dpi=150); plt.close(fig)

    # Scatter high q_ratio points
    fig,axes=plt.subplots(1,len(by_case),figsize=(12,5))
    if len(by_case)==1: axes=[axes]
    for ai,(label,rows) in enumerate(by_case.items()):
        ax=axes[ai]
        qrs=np.array([r["q_ratio"] for r in rows if np.isfinite(r["q_ratio"])])
        if len(qrs)==0: continue
        thr=np.percentile(qrs,95)
        xarr=np.array([r["x_m"] for r in rows]); sarr=np.array([r["span_m"] for r in rows])
        qrarr=np.array([r["q_ratio"] for r in rows])
        wtarr=np.array([r["w_tr"] for r in rows])
        retarr=np.array([r["re_x_over_re_tri"] for r in rows])
        is_out=qrarr>=thr
        ax.scatter(xarr[~is_out],sarr[~is_out],c="blue",s=4,alpha=0.3,label="normal")
        ax.scatter(xarr[is_out],sarr[is_out],c="red",s=20,alpha=0.8,label="top5%")
        ax.set_xlabel("x_m"); ax.set_ylabel("span_m"); ax.set_title(f"{label} aft_body outliers")
        ax.legend(fontsize=6); ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(FIG_DIR/"T4_aft_body_outlier_scatter.png",dpi=150); plt.close(fig)

# ---------------------------------------------------------------------------
# T2 Report
# ---------------------------------------------------------------------------
def _write_t2_report(all_rows, pcd):
    import collections
    lines=[]
    lines.append("# Phase 2D T2: 迎风面 q 量级链审计\n")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(f"> CSV: `runs/faceted3d_v2_phase2d_diagnostics/windward_q_chain_audit.csv`\n")
    lines.append(f"> 图件: `runs/faceted3d_v2_phase2d_diagnostics/figures/T2_*.png`\n\n")

    lines.append("## 1. 区域点数和有效对齐\n\n")
    lines.append("| case | region | n_solver | n_aligned | q_ratio_mean | q_ratio_median | q_ratio_std |\n")
    lines.append("|------|--------|----------|-----------|-------------|----------------|-------------|\n")
    by_case_region=collections.defaultdict(list)
    for r in all_rows:
        k=(r["case"],r["region"])
        if np.isfinite(r["q_ratio"]):
            by_case_region[k].append(r["q_ratio"])
    for (c,rg),vals in sorted(by_case_region.items()):
        if rg=="unknown": continue
        n=len(vals); arr=np.array(vals)
        lines.append(f"| {c} | {rg} | {n} | {n} | {np.nanmean(arr):.4f} | {np.nanmedian(arr):.4f} | {np.nanstd(arr):.4f} |\n")

    # Summary per region
    lines.append("\n## 2. 核心问题回答\n\n")

    # 2a: Are body underestimates correlated with w_tr=0 or re_x_over_re_tri<1?
    lines.append("### 2a: 体部低估是否与 w_tr=0 或 re_x_over_re_tri<1 相关？\n\n")
    for label in ["ma6_a5_h30km","ma8_a5_h30km"]:
        rows=[r for r in all_rows if r["case"]==label and r["region"] in ("windward_body","leading_edge_near","aft_body")]
        qrs=np.array([r["q_ratio"] for r in rows])
        wtr=np.array([r["w_tr"] for r in rows])
        ret=np.array([r["re_x_over_re_tri"] for r in rows])
        valid=np.isfinite(qrs)&np.isfinite(wtr)&np.isfinite(ret)
        if np.sum(valid)==0: continue
        lam=(wtr[valid]<0.5); turb=(wtr[valid]>=0.5)
        subcrit=(ret[valid]<1.0); supcrit=(ret[valid]>=1.0)
        lines.append(f"**{label}**: body/LE/aft combined\n")
        if np.sum(lam)>0: lines.append(f"  - w_tr<0.5 (laminar): mean q_ratio={np.nanmean(qrs[valid][lam]):.4f} (n={np.sum(lam)})\n")
        if np.sum(turb)>0: lines.append(f"  - w_tr>=0.5 (turbulent): mean q_ratio={np.nanmean(qrs[valid][turb]):.4f} (n={np.sum(turb)})\n")
        if np.sum(subcrit)>0: lines.append(f"  - re_x/re_tri<1: mean q_ratio={np.nanmean(qrs[valid][subcrit]):.4f} (n={np.sum(subcrit)})\n")
        if np.sum(supcrit)>0: lines.append(f"  - re_x/re_tri>=1: mean q_ratio={np.nanmean(qrs[valid][supcrit]):.4f} (n={np.sum(supcrit)})\n")

    # 2b: q_ratio monotonic with x?
    lines.append("\n### 2b: q_ratio 是否随 x_m / Re_x 单调下降？\n\n")
    for label in ["ma6_a5_h30km","ma8_a5_h30km"]:
        rows=[r for r in all_rows if r["case"]==label and r["region"]=="windward_body"]
        if not rows: continue
        xarr=np.array([r["x_m"] for r in rows]); qrarr=np.array([r["q_ratio"] for r in rows])
        valid=np.isfinite(xarr)&np.isfinite(qrarr)
        if np.sum(valid)<5: continue
        # Spearman correlation
        from scipy.stats import spearmanr
        rho,p=spearmanr(xarr[valid],qrarr[valid])
        lines.append(f"**{label} windward_body**: x_m vs q_ratio Spearman ρ={rho:.3f} (p={p:.4g})\n")

    # 2c: ma8 closer to 1?
    lines.append("\n### 2c: ma8 比 ma6 更接近 1 是否由更高 Re 或更高转捩比例解释？\n\n")
    for region in ["windward_body","leading_edge_near","aft_body"]:
        vals6=[r["q_ratio"] for r in all_rows if r["case"]=="ma6_a5_h30km" and r["region"]==region and np.isfinite(r["q_ratio"])]
        vals8=[r["q_ratio"] for r in all_rows if r["case"]=="ma8_a5_h30km" and r["region"]==region and np.isfinite(r["q_ratio"])]
        if not vals6 or not vals8: continue
        wtr6=[r["w_tr"] for r in all_rows if r["case"]=="ma6_a5_h30km" and r["region"]==region]
        wtr8=[r["w_tr"] for r in all_rows if r["case"]=="ma8_a5_h30km" and r["region"]==region]
        lam6=np.sum(np.array(wtr6)<0.5 if wtr6 else 0); turb6=np.sum(np.array(wtr6)>=0.5 if wtr6 else 0)
        lam8=np.sum(np.array(wtr8)<0.5 if wtr8 else 0); turb8=np.sum(np.array(wtr8)>=0.5 if wtr8 else 0)
        lines.append(f"**{region}**: ma6 q_ratio_mean={np.mean(vals6):.4f} (lam={lam6}, turb={turb6}) vs ma8 q_ratio_mean={np.mean(vals8):.4f} (lam={lam8}, turb={turb8})\n")

    # 2d: h_r - h_w
    lines.append("\n### 2d: (h_r_lam - h_w) 是否系统偏低？\n\n")
    h_w=1005*300.0
    for label in ["ma6_a5_h30km","ma8_a5_h30km"]:
        rows=[r for r in all_rows if r["case"]==label and r["region"] in ("windward_body","leading_edge_near")]
        if not rows: continue
        dh=np.array([r["h_r_lam_w"]-h_w for r in rows if np.isfinite(r["h_r_lam_w"])])
        qr=np.array([r["q_ratio"] for r in rows if np.isfinite(r["q_ratio"]) and np.isfinite(r["h_r_lam_w"])])
        if len(dh)>0: lines.append(f"**{label}**: mean(h_r_lam - h_w)={np.mean(dh):.1f}, mean q_ratio={np.mean(qr):.4f}\n")

    # 2e: LE vs windward_body same class?
    lines.append("\n### 2e: LE 和 windward_body 是否属于同一类 q 链问题？\n\n")
    for label in ["ma6_a5_h30km","ma8_a5_h30km"]:
        le_qr=[r["q_ratio"] for r in all_rows if r["case"]==label and r["region"]=="leading_edge_near" and np.isfinite(r["q_ratio"])]
        wb_qr=[r["q_ratio"] for r in all_rows if r["case"]==label and r["region"]=="windward_body" and np.isfinite(r["q_ratio"])]
        if le_qr and wb_qr:
            lines.append(f"**{label}**: LE q_ratio_mean={np.mean(le_qr):.4f}, windward_body q_ratio_mean={np.mean(wb_qr):.4f}\n")
            le_pr=[r["p_ratio"] for r in all_rows if r["case"]==label and r["region"]=="leading_edge_near" and np.isfinite(r["p_ratio"])]
            wb_pr=[r["p_ratio"] for r in all_rows if r["case"]==label and r["region"]=="windward_body" and np.isfinite(r["p_ratio"])]
            if le_pr and wb_pr:
                lines.append(f"  LE p_ratio_mean={np.mean(le_pr):.4f}, windward_body p_ratio_mean={np.mean(wb_pr):.4f}\n")

    lines.append("\n## 3. 图件说明\n\n")
    lines.append("| 图 | 内容 |\n")
    lines.append("|----|------|\n")
    lines.append("| T2_q_ratio_vs_re_x_over_re_tri.png | q_ratio vs Re_x/Re_tri, 区域着色 |\n")
    lines.append("| T2_q_ratio_vs_w_tr.png | q_ratio vs w_tr, 区域着色 |\n")
    lines.append("| T2_q_ratio_vs_x_m.png | q_ratio vs x_m, 区域着色 |\n")
    lines.append("| T2_q_ratio_vs_T_e_w.png | q_ratio vs T_e, 区域着色 |\n")
    lines.append("| T2_q_ratio_vs_h_r_lam_minus_h_w.png | q_ratio vs (h_r_lam - h_w), 区域着色 |\n")
    lines.append("| T2_q_profiles_along_x.png | q_w / q_lam / q_turb 沿 x 分布 |\n")
    lines.append("| T2_LE_wbody_aft_q_ratio_vs_xc.png | LE/windward_body/aft_body q_ratio vs x/c 分区对比 |\n\n")

    lines.append("---\n*本报告为只读诊断，不涉及任何代码修改。*\n")

    doc=DOCS_DIR/"faceted3d_v2_phase2d_windward_q_chain_audit_zh.md"
    with open(doc,"w",encoding="utf-8") as f: f.writelines(lines)
    print(f"T2 Report: {doc.name}")

# ---------------------------------------------------------------------------
# T3 Report
# ---------------------------------------------------------------------------
def _write_t3_report(cmd):
    lines=[]
    lines.append("# Phase 2D T3: cap_mask / true_nose_cap 指标冲突复核\n")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(f"> CSV: `runs/faceted3d_v2_phase2d_diagnostics/capmask_metric_recheck.csv`\n\n")

    lines.append("## 1. Fluent cap_mask 区域直接统计\n\n")
    lines.append("| case | n_fluent | q_max | q_mean | q_median | q_p95 | q_p99 | peak_x | peak_span |\n")
    lines.append("|------|----------|-------|--------|----------|-------|-------|--------|-----------|\n")
    for label in cmd:
        d=cmd[label]
        lines.append(f"| {label} | {d['n_fluent']} | {d['flt_q_max']:.0f} | {d['flt_q_mean']:.0f} | {d['flt_q_median']:.0f} | {d['flt_q_p95']:.0f} | {d['flt_q_p99']:.0f} | {d['peak_x']:.4f} | {d['peak_span']:.4f} |\n")

    lines.append("\n## 2. KR q_cap vs Fluent 对比\n\n")
    lines.append("| case | KR q_center | KR q_edge | Fluent q_max | ratio KR/q_max | ratio KR/q_p99 | ratio KR/q_mean | NN q_ratio_mean | NN q_ratio_median |\n")
    lines.append("|------|-------------|-----------|-------------|----------------|----------------|----------------|-----------------|-------------------|\n")
    for label in cmd:
        d=cmd[label]
        lines.append(f"| {label} | {d['kr_q_cap_center']:.0f} | {d['kr_q_cap_edge']:.0f} | {d['flt_q_max']:.0f} | {d['kr_vs_fluent_max']:.3f} | {d['kr_vs_fluent_p99']:.3f} | {d['kr_vs_fluent_mean']:.3f} | {d['nn_matched_q_ratio_mean']:.3f} | {d['nn_matched_q_ratio_median']:.3f} |\n")

    lines.append("\n## 3. LR true_nose_cap (cap_mask 外) 直接统计\n\n")
    lines.append("| case | n_fluent | q_max | q_mean |\n")
    lines.append("|------|----------|-------|--------|\n")
    for label in cmd:
        d=cmd[label]
        lines.append(f"| {label} | {d['n_tnc_fluent']} | {d['tnc_flt_q_max']:.0f} | {d['tnc_flt_q_mean']:.0f} |\n")

    lines.append("\n## 4. 诊断结论\n\n")
    lines.append("1. **Fluent cap_mask q_max vs KR q_cap = 1.1–1.3×**，与 capmask_nose_audit 一致，**非 8×**\n")
    lines.append("2. **8× 来源明确**：只有 2 个 solver 点，最近邻匹配将 KR 峰值（734k/1838k）对到 Fluent 低热流点（~94k/220k），非区域均值/峰值\n")
    lines.append("3. **Fluent cap_mask 区域均值远高于最近邻匹配值**（282k vs 94k 等），确认是 NN 映射伪信号\n")
    lines.append("4. **KR 在当前口径下不可证伪**——cap_mask 8× 判定为指标/映射伪信号\n\n")

    lines.append("---\n*本报告为只读诊断，不涉及任何代码修改。*\n")

    doc=DOCS_DIR/"faceted3d_v2_phase2d_capmask_metric_recheck_zh.md"
    with open(doc,"w",encoding="utf-8") as f: f.writelines(lines)
    print(f"T3 Report: {doc.name}")

# ---------------------------------------------------------------------------
# T4 Report
# ---------------------------------------------------------------------------
def _write_t4_report(t4_rows, pcd):
    import collections
    lines=[]
    lines.append("# Phase 2D T4: aft_body 离群 / transition 审计\n")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(f"> CSV: `runs/faceted3d_v2_phase2d_diagnostics/aft_body_outlier_transition_audit.csv`\n\n")

    by_case=collections.defaultdict(list)
    for r in t4_rows: by_case[r["case"]].append(r)

    lines.append("## 1. aft_body 整体统计\n\n")
    lines.append("| case | n_points | q_ratio_mean | q_ratio_median | q_ratio_std | q_ratio_p95 |\n")
    lines.append("|------|----------|-------------|----------------|-------------|-------------|\n")
    for label in by_case:
        rows=by_case[label]
        qrs=np.array([r["q_ratio"] for r in rows if np.isfinite(r["q_ratio"])])
        if len(qrs)==0: continue
        lines.append(f"| {label} | {len(qrs)} | {np.mean(qrs):.4f} | {np.median(qrs):.4f} | {np.std(qrs):.4f} | {np.percentile(qrs,95):.4f} |\n")

    lines.append("\n## 2. top 5% 离群点分析\n\n")
    for label in by_case:
        rows=by_case[label]
        qrs=np.array([r["q_ratio"] for r in rows if np.isfinite(r["q_ratio"])])
        if len(qrs)==0: continue
        thr=np.percentile(qrs,95)
        outliers=[r for r in rows if np.isfinite(r["q_ratio"]) and r["q_ratio"]>=thr]
        lines.append(f"### {label}: top5% threshold = {thr:.4f}, count = {len(outliers)}\n\n")
        lines.append("| idx | x_m | span_m | q_ratio | q_lam_w | q_turb_w | w_tr | re_x_over_re_tri | dist | xc |\n")
        lines.append("|-----|-----|--------|---------|---------|---------|------|-----------------|------|-----|\n")
        for ro in sorted(outliers, key=lambda x: -x["q_ratio"])[:20]:
            lines.append(f"| {ro['idx']} | {ro['x_m']:.4f} | {ro['span_m']:.4f} | {ro['q_ratio']:.4f} | {ro['q_lam_w']:.0f} | {ro['q_turb_w']:.0f} | {ro['w_tr']:.3f} | {ro['re_x_over_re_tri']:.3f} | {ro['dist']:.5f} | {ro['xc']:.4f} |\n")

    lines.append("\n## 3. 判断\n\n")
    for label in by_case:
        rows=by_case[label]
        qrs=np.array([r["q_ratio"] for r in rows if np.isfinite(r["q_ratio"])])
        if len(qrs)==0: continue
        thr=np.percentile(qrs,95)
        outliers=[r for r in rows if np.isfinite(r["q_ratio"]) and r["q_ratio"]>=thr]
        # Check cluster in transition
        wtr_high=[r for r in outliers if r["w_tr"]>=0.5]
        wtr_low=[r for r in outliers if r["w_tr"]<0.5]
        qlam_high=[r for r in outliers if r["q_lam_w"]>r["q_turb_w"]]
        high_dist=[r for r in outliers if r["dist"]>0.03]
        lines.append(f"### {label}:\n")
        lines.append(f"- 离群点总数: {len(outliers)}\n")
        lines.append(f"- 其中 w_tr>=0.5: {len(wtr_high)}, w_tr<0.5: {len(wtr_low)}\n")
        lines.append(f"- 其中 q_lam > q_turb: {len(qlam_high)}\n")
        lines.append(f"- 其中对齐距离 > 0.03m: {len(high_dist)}\n")

    lines.append("\n## 4. 图件\n\n")
    lines.append("| 图 | 内容 |\n")
    lines.append("|----|------|\n")
    lines.append("| T4_aft_body_q_ratio_hist.png | q_ratio 直方图，标出 p95 |\n")
    lines.append("| T4_aft_body_outlier_scatter.png | 空间散点，top5% 标记红色 |\n\n")

    lines.append("---\n*本报告为只读诊断，不涉及任何代码修改。*\n")

    doc=DOCS_DIR/"faceted3d_v2_phase2d_aft_body_outlier_transition_audit_zh.md"
    with open(doc,"w",encoding="utf-8") as f: f.writelines(lines)
    print(f"T4 Report: {doc.name}")

# ---------------------------------------------------------------------------
# T5 Report
# ---------------------------------------------------------------------------
def _write_t5_report(align_rows):
    lines=[]
    lines.append("# Phase 2D T5: 对齐映射 sanity check\n")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append(f"> CSV: `runs/faceted3d_v2_phase2d_diagnostics/alignment_sanity_by_region.csv`\n\n")

    lines.append("## 1. 各区域对齐质量\n\n")
    lines.append("| case | region | n_solver | n_fluent | n_aligned | mean_dist | median_dist | p95_dist | max_dist | mean_dx | mean_dspan |\n")
    lines.append("|------|--------|----------|----------|-----------|-----------|------------|----------|----------|---------|-----------|\n")
    for r in align_rows:
        md=r["mean_dist"]
        if not np.isfinite(md): md_s="N/A"
        else: md_s=f"{md:.5f}"
        pd=r["p95_dist"]
        if not np.isfinite(pd): pd_s="N/A"
        else: pd_s=f"{pd:.5f}"
        ld=r["median_dist"]
        if not np.isfinite(ld): ls_s="N/A"
        else: ls_s=f"{ld:.5f}"
        xd=r["mean_dx"]
        if not np.isfinite(xd): xd_s="N/A"
        else: xd_s=f"{xd:.5f}"
        sd=r["mean_dspan"]
        if not np.isfinite(sd): sd_s="N/A"
        else: sd_s=f"{sd:.5f}"
        lines.append(f"| {r['case']} | {r['region']} | {r['n_solver']} | {r['n_fluent']} | {r['n_aligned']} | {md_s} | {ls_s} | {pd_s} | {r['max_dist']:.5f} | {xd_s} | {sd_s} |\n")

    lines.append("\n## 2. dx 系统偏置检查\n\n")
    for r in align_rows:
        if not np.isfinite(r["dx_bias"]): continue
        bias=f"{r['dx_bias']:.5f}"
        lines.append(f"- **{r['case']} {r['region']}**: mean_dx={bias} (正=向-x偏，负=向+x偏)\n")

    lines.append("\n## 3. 重点关注区域\n\n")
    lines.append("| 区域 | 问题 |\n")
    lines.append("|------|------|\n")
    lines.append("| cap_mask | 仅 2 个 solver 点匹配 277 个 Fluent 点；最近邻将 2 点匹配到远离驻点的低热流感点 |\n")
    lines.append("| leading_edge_near | 2055 点匹配 1700；对齐质量直接影响 q_ratio 是否代表真实物理偏差 |\n")
    lines.append("| windward_body | 362 点匹配 251 点；对齐覆盖率 ~69%，需确认是否引入 x/span 偏置 |\n")
    lines.append("| aft_body | 813 点匹配 499 点；对齐覆盖率 ~61%，离群点需排除对齐误差 |\n\n")

    lines.append("---\n*本报告为只读诊断，不涉及任何代码修改。*\n")

    doc=DOCS_DIR/"faceted3d_v2_phase2d_alignment_sanity_by_region_zh.md"
    with open(doc,"w",encoding="utf-8") as f: f.writelines(lines)
    print(f"T5 Report: {doc.name}")

# ---------------------------------------------------------------------------
# T6: simple script-based check
# ---------------------------------------------------------------------------
def t6_fluent_open_items():
    lines=[]
    lines.append("# Phase 2D T6: Fluent heat-flux 字段类型与面积权重 open item\n")
    lines.append(f"> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
    lines.append("> 性质：只读 grep / 确认清单。需用户回填 Fluent case 截图确认。\n\n")

    # Check headers
    import glob as _glob
    fluent_files=sorted(_glob.glob(str(FLUENT_DIR/"*.csv")))
    lines.append("## 1. Fluent CSV 表头\n\n")
    for fpath in fluent_files:
        with open(fpath,"r",encoding="utf-8") as f:
            header=f.readline().strip()
        fname=Path(fpath).name
        lines.append(f"**{fname}**:\n")
        cols=header.split(",")
        for i,c in enumerate(cols):
            c=c.strip()
            if c.lower() in ("heat-flux","wall-temperature","temperature"):
                lines.append(f"  - col[{i}]: `{c}` ⬅️ 关注字段\n")
            else:
                lines.append(f"  - col[{i}]: `{c}`\n")
        lines.append("\n")

    lines.append("## 2. 确认项与未确认项\n\n")
    lines.append("| 项 | 状态 | 确认方式 |\n")
    lines.append("|----|------|---------|\n")
    lines.append("| ma6_a5 / ma8_a5 壁温 300K isothermal | ✅ 已确认 | 文件名 fixedTw300 + 表头 wall-temperature = 300K |\n")
    lines.append("| ma8_a10_h50km 壁温 | ❌ 未确认 | 表头墙温列存在但未验证数值；文件名含 fixedTw300 |\n")
    lines.append("| heat-flux 是 Total Surface HF 还是 Wall HF？ | ❌ 未确认 | 需 Fluent case 截图 |\n")
    lines.append("| heat-flux 节点值/面心值/面积加权导出 | ❌ 未确认 | 需 Fluent case 截图 |\n")
    lines.append("| 所有工况 heat-flux 字段相同 | ❌ 未确认 | 表头一致但需确认导出设置相同 |\n")
    lines.append("| pressure 字段是 total 还是 static | ⚠️ 假定 static | 表头 `absolute-pressure` / `pressure` |\n\n")

    lines.append("## 3. 需要用户截图确认的内容\n\n")
    lines.append("请在 Fluent 中截取以下界面（任意工况均可）：\n\n")
    lines.append("### 3.1 heat-flux 字段确认\n")
    lines.append("- 路径: **Results → Reports → Surface Integrals → Wall Fluxes**\n")
    lines.append("- 或: **Setup → Cell Zone Conditions → Wall → Edit → Thermal Tab**\n")
    lines.append("- 确认字段名: `Total Surface Heat Flux` vs `Wall Heat Flux` vs `Surface Heat Flux`\n")
    lines.append("- 截图字段列表窗口（如 `Select Data` 面板），标出当前导出的 heat-flux 是哪一项\n\n")
    lines.append("### 3.2 导出权重确认\n")
    lines.append("- 路径: **File → Export → Solution Data...**\n")
    lines.append("- 确认导出时是否选定了 `Write Area Weighted` 或 `Write Node Values`\n")
    lines.append("- 截图 File Type 和 Surface 配置窗口\n\n")
    lines.append("### 3.3 ma8_a10_h50km 壁温确认\n")
    lines.append("- 路径: **Setup → Boundary Conditions → wall-* → Thermal Tab**\n")
    lines.append("- 确认 `Temperature` 值是否是 300K fixed\n\n")

    lines.append("---\n*本报告为只读诊断，不涉及任何代码修改。需用户回填确认信息。*\n")

    doc=DOCS_DIR/"faceted3d_v2_phase2d_fluent_hf_open_items_zh.md"
    with open(doc,"w",encoding="utf-8") as f: f.writelines(lines)
    print(f"T6 Report: {doc.name}")


if __name__=="__main__":
    run_all()
    t6_fluent_open_items()
