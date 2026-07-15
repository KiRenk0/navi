import numpy as np
from scipy.spatial import KDTree
import math, time, sys, os

np.set_printoptions(precision=4, suppress=True, linewidth=120)

STL_PATH = r"d:\ref\reference-enthalpy_03_12_26-main\new_spec\htv2_0628.stl"
CACHE = r"d:\ref\reference-enthalpy_03_12_26-main\_mapping_cache.npz"
CSV_FILES = {
    "30km_5alpha_6ma": r"d:\ref\reference-enthalpy_03_12_26-main\fluent_export\adiabatic_wall_csv\30km_5alpha_6ma.csv",
    "40km_5alpha_8ma": r"d:\ref\reference-enthalpy_03_12_26-main\fluent_export\adiabatic_wall_csv\40km_5alpha_8ma.csv",
}

# ── Parse STL (once) ──────────────────────────────────────────
t0 = time.time()
print("Parsing STL...", flush=True)
verts_list = []
normals_list = []
with open(STL_PATH) as f:
    vbuf = []; cnorm = None
    for line in f:
        line = line.strip()
        if line.startswith("facet normal"):
            p = line.split(); cnorm = np.array([float(p[2]), float(p[3]), float(p[4])])
            vbuf = []
        elif line.startswith("vertex"):
            p = line.split(); vbuf.append(np.array([float(p[1]), float(p[2]), float(p[3])]))
            if len(vbuf) == 3:
                verts_list.append(tuple(vbuf)); normals_list.append(cnorm.copy())
n_tri = len(verts_list)
print(f"  {n_tri} triangles in {time.time()-t0:.1f}s", flush=True)

# Convert to solver: vertex (x,y,z)_stl_mm -> (x/1000, z/1000, y/1000)_m, normal (nx,ny,nz)->(nx,nz,ny)
v_solver = np.zeros((n_tri, 3, 3))
n_solver = np.zeros((n_tri, 3))
for i in range(n_tri):
    v0, v1, v2 = verts_list[i]
    v_solver[i,0] = [v0[0]/1000, v0[2]/1000, v0[1]/1000]
    v_solver[i,1] = [v1[0]/1000, v1[2]/1000, v1[1]/1000]
    v_solver[i,2] = [v2[0]/1000, v2[2]/1000, v2[1]/1000]
    n = normals_list[i]; n_solver[i] = [n[0], n[2], n[1]]

# Winding
d1 = v_solver[:,1] - v_solver[:,0]; d2 = v_solver[:,2] - v_solver[:,0]
cross = np.cross(d1, d2)
cn = np.linalg.norm(cross, axis=1, keepdims=True); cn[cn<1e-30] = 1.0
dot_w = np.sum(cross/cn * n_solver, axis=1)
print(f"Winding: {np.mean(dot_w>0)*100:.1f}% dot>0 (all {'opposite' if np.all(dot_w<0) else 'mixed'})", flush=True)

# Centroids & KDTree
centroids = v_solver.mean(axis=1)
print(f"Centroids X:[{centroids[:,0].min():.3f},{centroids[:,0].max():.3f}] Z:[{centroids[:,1].min():.3f},{centroids[:,1].max():.3f}] Y:[{centroids[:,2].min():.3f},{centroids[:,2].max():.3f}]", flush=True)
kdt = KDTree(centroids)

# ── Point-to-triangle distance ──────────────────────────────
def pt_tri_dist(p, v0, v1, v2):
    e1 = v1 - v0; e2 = v2 - v0
    n = np.cross(e1, e2); nn = np.dot(n,n)
    if nn < 1e-30:
        return min(np.linalg.norm(p-v0), np.linalg.norm(p-v1), np.linalg.norm(p-v2))
    w = p - v0
    gamma = np.dot(np.cross(e1,w), n)/nn
    beta  = np.dot(np.cross(w,e2), n)/nn
    alpha = 1.0 - gamma - beta
    if 0<=alpha<=1 and 0<=beta<=1 and 0<=gamma<=1:
        return np.linalg.norm(p - (alpha*v0 + beta*v1 + gamma*v2))
    # edges
    e01=v1-v0; t01=np.clip(np.dot(p-v0,e01)/max(np.dot(e01,e01),1e-30),0,1); d01=np.linalg.norm(p-(v0+t01*e01))
    e12=v2-v1; t12=np.clip(np.dot(p-v1,e12)/max(np.dot(e12,e12),1e-30),0,1); d12=np.linalg.norm(p-(v1+t12*e12))
    e20=v0-v2; t20=np.clip(np.dot(p-v2,e20)/max(np.dot(e20,e20),1e-30),0,1); d20=np.linalg.norm(p-(v2+t20*e20))
    return min(d01,d12,d20, np.linalg.norm(p-v0), np.linalg.norm(p-v1), np.linalg.norm(p-v2))

# ── Parse CSV ────────────────────────────────────────────────
def parse_csv(fp):
    rows = []
    with open(fp) as f:
        f.readline()  # header
        for line in f:
            line = line.strip()
            if not line: continue
            p = [x.strip() for x in line.split(",")]
            if len(p) < 9: continue
            rows.append({
                "cell": int(p[0]), "x": float(p[1]), "y": float(p[2]), "z": float(p[3]),
                "p": float(p[4]), "Tw": float(p[5]), "yplus": float(p[6]),
                "hf": float(p[7]), "area": float(p[8])
            })
    return rows

# ── Do or load mapping ───────────────────────────────────────
if os.path.exists(CACHE):
    print(f"Loading cached mapping from {CACHE}", flush=True)
    c = np.load(CACHE)
    tri_idx = c["tri_idx"]; dist_arr = c["dist_arr"]; fluent_pts_ref = c["fluent_pts"]
else:
    # Use first CSV for mapping (same mesh for both)
    first_csv = list(CSV_FILES.values())[0]
    rows0 = parse_csv(first_csv)
    fluent_pts = np.array([[r["x"], r["y"], r["z"]] for r in rows0])
    n_pts = len(fluent_pts)
    print(f"Mapping {n_pts} points (k=120 shortlist)...", flush=True)
    
    tri_idx = np.zeros(n_pts, dtype=np.int32)
    dist_arr = np.zeros(n_pts)
    
    dd, ii = kdt.query(fluent_pts, k=120)
    
    tmap0 = time.time()
    for i in range(n_pts):
        best_d = float("inf"); best_t = 0
        p = fluent_pts[i]
        for j in range(120):
            tidx = ii[i,j]
            d = pt_tri_dist(p, v_solver[tidx,0], v_solver[tidx,1], v_solver[tidx,2])
            if d < best_d: best_d = d; best_t = tidx
        tri_idx[i] = best_t; dist_arr[i] = best_d
        if (i+1) % 5000 == 0: print(f"  {i+1}/{n_pts} ({time.time()-tmap0:.1f}s)", flush=True)
    print(f"Mapping done in {time.time()-tmap0:.1f}s", flush=True)
    
    np.savez_compressed(CACHE, tri_idx=tri_idx, dist_arr=dist_arr, fluent_pts=fluent_pts)

dist_mm = dist_arr * 1000
n_pts = len(dist_mm)

# ── Normals, masks (same for both) ──────────────────────────
mapped_n = n_solver[tri_idx]        # (N,3) solver normals
mapped_c = centroids[tri_idx]       # (N,3) solver centroids

n_up = mapped_n[:, 1]               # Z component = "up"
x_sol = mapped_c[:, 0]              # X = streamwise

U = np.array([math.cos(math.radians(5)), 0, -math.sin(math.radians(5))])
n_dot_U = np.abs(np.sum(mapped_n * U, axis=1))

mask_upper   = n_up >= 0.45
mask_nose    = x_sol <= 0.03
mask_side    = np.abs(n_up) < 0.45
mask_chine   = mask_upper & (n_up < 0.8)
mask_tangent = n_dot_U < 0.05
mask_clean   = mask_upper & (~mask_nose) & (~mask_chine) & (~mask_tangent)

# ── Print mapping stats ─────────────────────────────────────
print(f"\n{'='*60}")
print("MAPPING (shared for both cases)")
print(f"{'='*60}")
print(f"  CSV rows: {n_pts}")
for q in [0,25,50,75,90,95,99,100]:
    print(f"  dist p{q:>3d}: {np.percentile(dist_mm,q):.3f} mm")
print(f"  >1mm: {(dist_mm>1).sum()}, >2mm: {(dist_mm>2).sum()}, >5mm: {(dist_mm>5).sum()}")
print(f"  upper: {mask_upper.sum()}, nose: {mask_nose.sum()}, side: {mask_side.sum()}, chine: {mask_chine.sum()}, tangent: {mask_tangent.sum()}, clean: {mask_clean.sum()}")

mm = np.column_stack([mask_upper,mask_nose,mask_side,mask_chine,mask_tangent,mask_clean])
n_mem = mm.sum(axis=1)
print(f"  ambiguous (multi-mask): {(n_mem>1).sum()}, total memberships: {n_mem.sum()}")

# ── Per-case stats ──────────────────────────────────────────
for case, path in CSV_FILES.items():
    print(f"\n{'='*60}")
    print(f"CASE: {case}")
    print(f"{'='*60}")
    rows = parse_csv(path)
    Tw = np.array([r["Tw"] for r in rows])
    Hf = np.array([r["hf"] for r in rows])
    
    def stat(label, mask):
        t = Tw[mask]; h = Hf[mask]
        if len(t)==0: return f"[{label}] EMPTY"
        return (f"[{label}] n={len(t)} Tw:min={t.min():.1f} mean={t.mean():.1f} med={np.median(t):.1f} "
                f"p95={np.percentile(t,95):.1f} max={t.max():.1f} NaN={np.isnan(t).sum()} "
                f"uniq={len(np.unique(np.round(t,1)))} hf_maxabs={np.max(np.abs(h)):.2e}")
    
    print(stat("all", np.ones(n_pts,bool)))
    print(stat("upper", mask_upper))
    print(stat("clean", mask_clean))
    
    # Fixed Tw
    tw_u = np.unique(np.round(Tw, 1))
    tw_u2 = np.unique(np.round(Tw, 2))
    print(f"  Tw fixed-wall: median={np.median(Tw):.1f} std={np.std(Tw):.2f} range={Tw.max()-Tw.min():.2f} "
          f"n_uniq(1dp)={len(tw_u)} n_uniq(2dp)={len(tw_u2)}")
    for mn, mmk in [("upper",mask_upper),("clean",mask_clean)]:
        tm = Tw[mmk]
        if len(tm): print(f"  [{mn}] Tw med={np.median(tm):.1f} std={np.std(tm):.2f} range={tm.max()-tm.min():.2f}")

print(f"\n{'='*60}")
print("DONE")
print(f"{'='*60}")