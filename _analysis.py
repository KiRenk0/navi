import numpy as np
from scipy.spatial import KDTree
import re, time, sys, math

# ── Parse STL ──────────────────────────────────────────────────
print("Parsing STL...", flush=True)
stl_path = r"d:\ref\reference-enthalpy_03_12_26-main\new_spec\htv2_0628.stl"

verts_list = []       # list of (v1, v2, v3) in STL coords (mm)
normals_list = []     # list of (nx, ny, nz)
tri_idx = 0
v_buffer = []
current_normal = None

with open(stl_path, "r") as f:
    for line in f:
        line = line.strip()
        if line.startswith("facet normal"):
            parts = line.split()
            current_normal = np.array([float(parts[2]), float(parts[3]), float(parts[4])])
            v_buffer = []
        elif line.startswith("vertex"):
            parts = line.split()
            v_buffer.append(np.array([float(parts[1]), float(parts[2]), float(parts[3])]))
            if len(v_buffer) == 3:
                verts_list.append(tuple(v_buffer))
                normals_list.append(current_normal.copy())
                v_buffer = []
                current_normal = None

n_tri = len(verts_list)
print(f"Parsed {n_tri} triangles", flush=True)

# Convert to solver coordinates: vertex (x,y,z)_stl_mm → (x/1000, z/1000, y/1000)_m
# Normal (nx,ny,nz)_stl → (nx, nz, ny)_solver
verts_solver = np.zeros((n_tri, 3, 3))  # (tri, vertex_idx, coord)
normals_solver = np.zeros((n_tri, 3))

for i in range(n_tri):
    v0, v1, v2 = verts_list[i]
    # STL mm → solver m: (X, Z, Y) = (x_stl/1000, z_stl/1000, y_stl/1000)
    verts_solver[i, 0] = [v0[0]/1000, v0[2]/1000, v0[1]/1000]
    verts_solver[i, 1] = [v1[0]/1000, v1[2]/1000, v1[1]/1000]
    verts_solver[i, 2] = [v2[0]/1000, v2[2]/1000, v2[1]/1000]
    # Normal: (nx, nz, ny)
    n = normals_list[i]
    normals_solver[i] = [n[0], n[2], n[1]]

# Check winding: compute cross product of edges and compare with normal
d1 = verts_solver[:, 1] - verts_solver[:, 0]
d2 = verts_solver[:, 2] - verts_solver[:, 0]
cross = np.cross(d1, d2)
cross_norm = np.linalg.norm(cross, axis=1, keepdims=True)
cross_norm[cross_norm < 1e-30] = 1.0
cross_unit = cross / cross_norm
dot_winding = np.sum(cross_unit * normals_solver, axis=1)
consistent = np.mean(dot_winding > 0)
print(f"Winding check: {consistent*100:.1f}% consistent with normals (dot>0)", flush=True)

# Triangle centroids
centroids = verts_solver.mean(axis=1)  # (n_tri, 3)
print(f"Centroids range X:[{centroids[:,0].min():.3f}, {centroids[:,0].max():.3f}] Z:[{centroids[:,1].min():.3f}, {centroids[:,1].max():.3f}] Y:[{centroids[:,2].min():.3f}, {centroids[:,2].max():.3f}]", flush=True)

# ── Build KDTree on centroids ──────────────────────────────────
print("Building KDTree on centroids...", flush=True)
kdtree = KDTree(centroids)

# ── Parse CSVs ─────────────────────────────────────────────────
def parse_csv(fp):
    data = []
    with open(fp) as f:
        header = f.readline().strip()
        cols = [c.strip() for c in header.split(",")]
        for line in f:
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 9:
                continue
            row = {
                "cellnumber": int(parts[0]),
                "x": float(parts[1]),
                "y": float(parts[2]),
                "z": float(parts[3]),
                "p": float(parts[4]),
                "Tw": float(parts[5]),
                "yplus": float(parts[6]),
                "heat_flux": float(parts[7]),
                "face_area": float(parts[8]),
            }
            data.append(row)
    return cols, data

csv_files = {
    "30km_5alpha_6ma": r"d:\ref\reference-enthalpy_03_12_26-main\fluent_export\adiabatic_wall_csv\30km_5alpha_6ma.csv",
    "40km_5alpha_8ma": r"d:\ref\reference-enthalpy_03_12_26-main\fluent_export\adiabatic_wall_csv\40km_5alpha_8ma.csv",
}

# ── Exact point-to-triangle distance ───────────────────────────
def point_triangle_distance(p, v0, v1, v2):
    """Min distance from point p to triangle (v0,v1,v2). Returns (dist, closest_point)."""
    # Using robust method
    d1 = v1 - v0
    d2 = v2 - v0
    n = np.cross(d1, d2)
    nn = np.dot(n, n)
    if nn < 1e-30:
        # Degenerate triangle - fallback to edge distances
        d01 = np.linalg.norm(np.cross(p-v0, p-v1)) / max(np.linalg.norm(v1-v0), 1e-30)
        d12 = np.linalg.norm(np.cross(p-v1, p-v2)) / max(np.linalg.norm(v2-v1), 1e-30)
        d20 = np.linalg.norm(np.cross(p-v2, p-v0)) / max(np.linalg.norm(v0-v2), 1e-30)
        return min(d01, d12, d20), p
    
    # Project p onto triangle plane
    w = p - v0
    gamma = np.dot(np.cross(d1, w), n) / nn
    beta  = np.dot(np.cross(w, d2), n) / nn
    alpha = 1.0 - gamma - beta
    
    if 0 <= alpha <= 1 and 0 <= beta <= 1 and 0 <= gamma <= 1:
        # Inside triangle
        proj = alpha * v0 + beta * v1 + gamma * v2
        return np.linalg.norm(p - proj), proj
    
    # Outside triangle - min distance to edges
    # Edge v0-v1
    e01 = v1 - v0
    t01 = np.clip(np.dot(p - v0, e01) / max(np.dot(e01, e01), 1e-30), 0, 1)
    d01 = np.linalg.norm(p - (v0 + t01 * e01))
    
    # Edge v1-v2
    e12 = v2 - v1
    t12 = np.clip(np.dot(p - v1, e12) / max(np.dot(e12, e12), 1e-30), 0, 1)
    d12 = np.linalg.norm(p - (v1 + t12 * e12))
    
    # Edge v2-v0
    e20 = v0 - v2
    t20 = np.clip(np.dot(p - v2, e20) / max(np.dot(e20, e20), 1e-30), 0, 1)
    d20 = np.linalg.norm(p - (v2 + t20 * e20))
    
    # Also check vertices
    d_v0 = np.linalg.norm(p - v0)
    d_v1 = np.linalg.norm(p - v1)
    d_v2 = np.linalg.norm(p - v2)
    
    return min(d01, d12, d20, d_v0, d_v1, d_v2), p

def map_points(fluent_pts, k_shortlist=50):
    """Map fluent points to nearest triangles. Returns arrays of tri_idx and distances."""
    n_pts = len(fluent_pts)
    tri_idx_arr = np.zeros(n_pts, dtype=int)
    dist_arr = np.zeros(n_pts)
    
    # KDTree query for shortlist
    dd, ii = kdtree.query(fluent_pts, k=k_shortlist)
    
    for i in range(n_pts):
        best_dist = float("inf")
        best_tri = 0
        p = fluent_pts[i]
        for j in range(k_shortlist):
            tidx = ii[i, j]
            v0, v1, v2 = verts_solver[tidx]
            d, _ = point_triangle_distance(p, v0, v1, v2)
            if d < best_dist:
                best_dist = d
                best_tri = tidx
        tri_idx_arr[i] = best_tri
        dist_arr[i] = best_dist
    
    return tri_idx_arr, dist_arr

# ── Process ─────────────────────────────────────────────────────
U_vec = np.array([math.cos(math.radians(5)), 0, -math.sin(math.radians(5))])

for case_name, csv_path in csv_files.items():
    print(f"\n{'='*60}")
    print(f"Processing {case_name}", flush=True)
    print(f"{'='*60}")
    
    cols, rows = parse_csv(csv_path)
    n_rows = len(rows)
    print(f"CSV data rows: {n_rows}", flush=True)
    
    # Extract points
    fluent_pts = np.array([[r["x"], r["y"], r["z"]] for r in rows])
    # Fluent coords are (x_streamwise, y_vertical, z_spanwise) in meters
    # But wait - Fluent's y is vertical, while solver Y is spanwise
    # The user says STL→solver=(X,Z,Y), and Fluent points are in the solver's coordinate system already
    # Actually, let me re-read. Fluent CSV has x,y,z in meters. 
    # The user's coordinate transform is for STL→solver. 
    # For Fluent, the coordinates likely already are in solver frame (x_stream, z_vertical, y_spanwise)
    # But wait: Fluent columns are "x-coordinate, y-coordinate, z-coordinate"
    # In a typical hypersonic CFD, x is streamwise, y is vertical (up), z is spanwise
    # Solver frame: X = streamwise, Z = vertical, Y = spanwise
    # So Fluent (x, y, z) → solver (x, y_stays_as_Z?, z_stays_as_Y?)
    # Actually the user didn't specify a Fluent transform. The STL is transformed to solver,
    # and we need to map Fluent points to the transformed STL.
    # The Fluent points are already in solver coordinates... but Fluent's y is vertical, 
    # which is Z in solver. Fluent's z is spanwise, which is Y in solver.
    # So Fluent (x, y, z) → solver (x, y, z)? No...
    # Wait, let me re-read: "STL mm 转 solver=(X,Z,Y)/1000"
    # This means: STL (x_mm, y_mm, z_mm) → solver (x_mm/1000, z_mm/1000, y_mm/1000)
    # So STL's x maps to solver X, STL's z maps to solver Z, STL's y maps to solver Y.
    #
    # Now for Fluent: the CSV has x-coordinate, y-coordinate, z-coordinate.
    # What do these mean? In ANSYS Fluent, typically:
    # - x is streamwise
    # - y is vertical (up)
    # - z is spanwise
    #
    # In the solver frame: X=streamwise, Z=vertical, Y=spanwise
    # So Fluent (x, y, z) → solver (x, z, y)? That would be the same transform as STL.
    # But Fluent is already in meters, not mm.
    #
    # Hmm, actually I think the geometry being analyzed is an HTV-2 like vehicle.
    # The STL is in mm, Fluent is in meters.
    # Looking at values: STL x ≈ 2520-2650 mm → 2.52-2.65 m in solver X
    # Fluent x ≈ -0.008 m → this is very small, near the nose region
    # Fluent y ≈ 0.028 m → vertical coordinate
    # Fluent z ≈ -0.003 to 0.003 m
    #
    # Wait, that doesn't match. STL has x=2520 mm = 2.52 m, but Fluent has x≈-0.008 m.
    # These are using different coordinate origins.
    #
    # Let me think again. In CFD, the vehicle nose is often at x=0, and the body extends 
    # downstream to positive x. But Fluent x is negative (-0.008 m) which is very close to 0.
    # The STL x ranges from 520 mm to 2651 mm, then /1000 = 0.52 to 2.65 m.
    #
    # These coordinate systems clearly have different origins. The Fluent simulation likely
    # has the nose at x=0, while the STL has the nose at x=520 mm. There's an offset.
    #
    # Actually wait, let me re-read the user: they want to map Fluent points onto the STL.
    # The STL is the surface geometry, and Fluent points are CFD cell centers on the wall.
    # If they're from the same simulation, they should share the same coordinate system.
    #
    # But looking at values: STL min x ≈ 520 mm → 0.52 m, while Fluent x ≈ -0.008 m.
    # These don't match unless there's a shift.
    #
    # Actually, maybe the STL was exported from CATIA in a different coordinate system.
    # The HTV-2 is about 3.7m long (based on public info, it's a hypersonic technology vehicle).
    # STL x range: 520 to 2651 mm → 0.52 to 2.65 m. That's about 2.13 m of the vehicle.
    # Fluent x range: ~-0.009 to some positive value.
    #
    # The user didn't mention any offset. Let me check more of the Fluent data.
    # Actually the Fluent points are on the wall boundary. They might be very close to the wall.
    # But their x,y,z coordinates should match the physical geometry.
    
    # Let me check the Fluent point ranges more carefully.
    
    Tw_vals = np.array([r["Tw"] for r in rows])
    hf_vals = np.array([r["heat_flux"] for r in rows])
    
    print(f"Fluent X range: [{fluent_pts[:,0].min():.6f}, {fluent_pts[:,0].max():.6f}]", flush=True)
    print(f"Fluent Y range: [{fluent_pts[:,1].min():.6f}, {fluent_pts[:,1].max():.6f}]", flush=True)
    print(f"Fluent Z range: [{fluent_pts[:,2].min():.6f}, {fluent_pts[:,2].max():.6f}]", flush=True)
    
    # For the mapping, I need Fluent points in solver coordinates.
    # Since STL→solver is (X,Z,Y) = (x_stl/1000, z_stl/1000, y_stl/1000),
    # and Fluent coords should match solver coords...
    # Fluent (x,y,z) where x=streamwise, y=vertical, z=spanwise
    # → solver (X, Z, Y) = (x_fluent, y_fluent, z_fluent)
    # Actually this matches: Fluent x → solver X (streamwise), Fluent y → solver Z (vertical), Fluent z → solver Y (spanwise)
    
    fluent_solver = np.column_stack([fluent_pts[:, 0], fluent_pts[:, 1], fluent_pts[:, 2]])
    # This is: [x_fluent, y_fluent, z_fluent] which is [streamwise, vertical, spanwise] = [X, Z, Y] in solver
    
    print(f"Mapping {n_rows} points with KDTree shortlist...", flush=True)
    t0 = time.time()
    tri_idx_arr, dist_arr = map_points(fluent_solver, k_shortlist=80)
    t1 = time.time()
    print(f"Mapping done in {t1-t0:.1f}s", flush=True)
    
    # Distances in meters → mm for reporting
    dist_mm = dist_arr * 1000
    
    print(f"\nMapping distance (mm):", flush=True)
    for q in [0, 25, 50, 75, 90, 95, 99, 100]:
        print(f"  p{q}: {np.percentile(dist_mm, q):.4f}", flush=True)
    print(f"  >1mm: {(dist_mm>1).sum()}, >2mm: {(dist_mm>2).sum()}, >5mm: {(dist_mm>5).sum()}", flush=True)
    
    # Get normals for mapped triangles
    mapped_normals = normals_solver[tri_idx_arr]  # (n_pts, 3) in solver frame
    # n_up = Z component of solver normal
    n_up = mapped_normals[:, 1]  # Z component
    # solver X coordinate of mapped triangle centroid
    mapped_centroids = centroids[tri_idx_arr]
    x_solver = mapped_centroids[:, 0]
    
    # Build masks
    mask_upper = n_up >= 0.45
    mask_nose = x_solver <= 0.03
    mask_side = np.abs(n_up) < 0.45
    mask_chine = mask_upper & (n_up < 0.8)
    # near tangent: abs(n · U) < 0.05
    n_dot_U = np.abs(np.sum(mapped_normals * U_vec, axis=1))
    mask_tangent = n_dot_U < 0.05
    mask_clean = mask_upper & (~mask_nose) & (~mask_chine) & (~mask_tangent)
    
    print(f"\nMask counts:", flush=True)
    print(f"  upper (n_up>=0.45):       {mask_upper.sum()}", flush=True)
    print(f"  nose (x<=0.03m):          {mask_nose.sum()}", flush=True)
    print(f"  side (|n_up|<0.45):       {mask_side.sum()}", flush=True)
    print(f"  chine trans (0.45<=n_up<0.8): {mask_chine.sum()}", flush=True)
    print(f"  near tangent (|n·U|<0.05): {mask_tangent.sum()}", flush=True)
    print(f"  clean (upper-nose-chine-tangent): {mask_clean.sum()}", flush=True)
    
    # Ambiguous: points that belong to multiple masks among {upper, nose, side, chine, tangent}
    # But these are not mutually exclusive by design. Let me compute union and membership totals.
    mask_matrix = np.column_stack([mask_upper, mask_nose, mask_side, mask_chine, mask_tangent, mask_clean])
    n_memberships = mask_matrix.sum(axis=1)
    ambiguous = n_memberships > 1
    print(f"  Ambiguous (multi-mask): {ambiguous.sum()}", flush=True)
    print(f"  Total memberships: {n_memberships.sum()}", flush=True)
    
    # Statistics for all/upper/clean
    def stats(label, mask, Tw, hf):
        t = Tw[mask]
        h = hf[mask]
        print(f"\n  [{label}] n={len(t)}", flush=True)
        if len(t) > 0:
            print(f"    Tw: min={t.min():.2f}, mean={t.mean():.2f}, median={np.median(t):.2f}, p95={np.percentile(t,95):.2f}, max={t.max():.2f}, NaN={np.isnan(t).sum()}, unique={len(np.unique(np.round(t,2)))}", flush=True)
            print(f"    heat-flux maxabs={np.max(np.abs(h)):.6e}", flush=True)
        else:
            print(f"    (empty)", flush=True)
    
    stats("all", np.ones(n_rows, dtype=bool), Tw_vals, hf_vals)
    stats("upper", mask_upper, Tw_vals, hf_vals)
    stats("clean", mask_clean, Tw_vals, hf_vals)
    
    # Fixed wall temperature check
    tw_unique = np.unique(np.round(Tw_vals, 1))
    tw_unique_2 = np.unique(np.round(Tw_vals, 2))
    tw_mode_count = max(np.bincount(np.round(Tw_vals, 1).astype(int) if np.all(Tw_vals == Tw_vals.astype(int)) else [0]))
    # Better: check if most values are near a constant
    tw_median = np.median(Tw_vals)
    tw_mad = np.median(np.abs(Tw_vals - tw_median))
    tw_std = np.std(Tw_vals)
    tw_range = Tw_vals.max() - Tw_vals.min()
    print(f"\n  Fixed Tw check: median={tw_median:.2f}, MAD={tw_mad:.4f}, std={tw_std:.4f}, range={tw_range:.4f}, n_unique(1dp)={len(tw_unique)}, n_unique(2dp)={len(tw_unique_2)}", flush=True)
    print(f"  Tw unique values (1dp): {tw_unique[:20]}{'...' if len(tw_unique)>20 else ''}", flush=True)
    
    # For each mask in upper, check if Tw is constant
    for mname, mmask in [("upper", mask_upper), ("clean", mask_clean)]:
        tw_m = Tw_vals[mmask]
        if len(tw_m) > 0:
            tw_m_median = np.median(tw_m)
            tw_m_std = np.std(tw_m)
            tw_m_range = tw_m.max() - tw_m.min()
            print(f"  [{mname}] Tw median={tw_m_median:.2f}, std={tw_m_std:.4f}, range={tw_m_range:.4f}", flush=True)

print(f"\n{'='*60}")
print("DONE")
print(f"{'='*60}")