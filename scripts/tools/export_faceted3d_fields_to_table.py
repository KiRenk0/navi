"""Export Faceted3D fields.npz + summary.json to multi-fidelity tabular CSVs.

Usage:
    python scripts/export_faceted3d_fields_to_table.py --run_dir runs/0629_fields_phase2a

Outputs:
    low_fidelity_points_windward.csv    (3321 rows)
    low_fidelity_points_leeward.csv     (3321 rows)
    low_fidelity_points_all.csv         (6642 rows)
    low_fidelity_points_all_valid.csv   (finites only)
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np


def _ensure_import_path() -> None:
    import sys
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src"
    for p in (repo_root, src_root):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))


_ensure_import_path()


def load_fields(run_dir: str | Path) -> dict[str, np.ndarray]:
    p = Path(run_dir) / "fields.npz"
    if not p.exists():
        raise FileNotFoundError(f"fields.npz not found: {p}")
    return dict(np.load(p, allow_pickle=True))


def load_summary(run_dir: str | Path) -> dict:
    p = Path(run_dir) / "summary.json"
    if not p.exists():
        raise FileNotFoundError(f"summary.json not found: {p}")
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _scalar_or_none(d: dict, *keys: str) -> float | None:
    for k in keys:
        v = d.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def build_table(
    fields: dict[str, np.ndarray],
    summary: dict,
    side: str,
) -> list[dict]:
    """Build a list of row-dicts for one side (windward or leeward).

    side must be "windward" or "leeward".
    """
    side_id = 1 if side == "windward" else -1

    inputs = summary.get("inputs", {})

    mach = float(inputs.get("mach", 0.0))
    alpha_deg = float(inputs.get("alpha_deg", 0.0))

    case_path = inputs.get("case_config", "")
    altitude_km = None
    try:
        import yaml
        p = Path(case_path)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                case_raw = yaml.safe_load(f)
            cspec = case_raw.get("canonical_case_spec", case_raw)
            h_m = _scalar_or_none(cspec, "fixed_h_m", "h_m", "altitude_m")
            if h_m is not None:
                altitude_km = round(h_m / 1000.0, 4)
    except Exception:
        pass

    if altitude_km is None:
        freestream = summary.get("freestream", {})
        h_m = _scalar_or_none(freestream, "altitude_m", "h_m")
        if h_m is not None:
            altitude_km = round(h_m / 1000.0, 4)

    Tw_K = None
    if side == "windward":
        Tw_arr = fields.get("Tw_w")
    else:
        Tw_arr = fields.get("Tw_l")

    if side == "windward":
        q_raw = fields.get("q_w")
        x_raw = fields.get("x_w_m")
        span_raw = fields.get("span_w_m")
        xc_raw = fields.get("xc_w")
        yb_raw = fields.get("yb_w")
        w_tr_raw = fields.get("w_tr")
        re_edge_raw = fields.get("re_edge")
        re_tri_raw = fields.get("re_tri")
        T_e_raw = fields.get("T_e_w")
        p_e_raw = fields.get("p_e_w")
        rho_e_raw = fields.get("rho_e_w")
        ma_e_raw = fields.get("ma_e_w")
        v_e_raw = fields.get("v_e_w")
        mu_e_raw = fields.get("mu_e_w")
        phi_raw = fields.get("phi_w")
        cp_raw = fields.get("cp_w")
        cp0_raw = fields.get("cp0_w")
        h_e_raw = fields.get("h_e_w")
        T_r_lam_raw = fields.get("T_r_lam_w")
        h_r_lam_raw = fields.get("h_r_lam_w")
        h_star_lam_raw = fields.get("h_star_lam_w")
        T_r_turb_raw = fields.get("T_r_turb_w")
        h_r_turb_raw = fields.get("h_r_turb_w")
        h_star_turb_raw = fields.get("h_star_turb_w")
        q_lam_raw = fields.get("q_lam_w")
        q_turb_raw = fields.get("q_turb_w")
        St_l_raw = None
        Re_ns_l_raw = None
    else:
        q_raw = fields.get("q_l")
        x_raw = fields.get("x_l_m")
        span_raw = fields.get("span_l_m")
        xc_raw = fields.get("xc_l")
        yb_raw = fields.get("yb_l")
        w_tr_raw = fields.get("w_tr")
        re_edge_raw = fields.get("re_edge")
        re_tri_raw = fields.get("re_tri")
        St_l_raw = fields.get("St_l")
        Re_ns_l_raw = fields.get("Re_ns_l")
        T_e_raw = None
        p_e_raw = None
        rho_e_raw = None
        ma_e_raw = None
        v_e_raw = None
        mu_e_raw = None
        phi_raw = None
        cp_raw = None
        cp0_raw = None
        h_e_raw = None
        T_r_lam_raw = None
        h_r_lam_raw = None
        h_star_lam_raw = None
        T_r_turb_raw = None
        h_r_turb_raw = None
        h_star_turb_raw = None
        q_lam_raw = None
        q_turb_raw = None

    n = q_raw.size
    rows: list[dict] = []
    for i in range(n):
        q_val = float(q_raw.flat[i]) if q_raw is not None else float("nan")
        Tw_val = float(Tw_arr.flat[i]) if Tw_arr is not None else float("nan")
        valid = np.isfinite(q_val)

        row: dict[str, float | int | str | None] = {
            "point_id": i,
            "side": side,
            "side_id": side_id,
            "mach": mach,
            "alpha_deg": alpha_deg,
            "altitude_km": altitude_km,
            "Tw_K": Tw_val,
            "valid_mask": int(valid),
        }

        row["x_m"] = float(x_raw.flat[i]) if x_raw is not None else float("nan")
        row["span_m"] = float(span_raw.flat[i]) if span_raw is not None else float("nan")
        row["xc"] = float(xc_raw.flat[i]) if xc_raw is not None else float("nan")
        row["yb"] = float(yb_raw.flat[i]) if yb_raw is not None else float("nan")

        row["q_low_W_m2"] = q_val
        row["w_tr"] = float(w_tr_raw.flat[i]) if w_tr_raw is not None else float("nan")
        row["re_edge"] = float(re_edge_raw.flat[i]) if re_edge_raw is not None else float("nan")
        row["re_tri"] = float(re_tri_raw.flat[i]) if re_tri_raw is not None else float("nan")

        if side == "windward":
            row["T_e_K"] = float(T_e_raw.flat[i]) if T_e_raw is not None else float("nan")
            row["p_e_Pa"] = float(p_e_raw.flat[i]) if p_e_raw is not None else float("nan")
            row["rho_e_kg_m3"] = float(rho_e_raw.flat[i]) if rho_e_raw is not None else float("nan")
            row["ma_e"] = float(ma_e_raw.flat[i]) if ma_e_raw is not None else float("nan")
            row["v_e_m_s"] = float(v_e_raw.flat[i]) if v_e_raw is not None else float("nan")
            row["mu_e_Pa_s"] = float(mu_e_raw.flat[i]) if mu_e_raw is not None else float("nan")
            row["phi_rad"] = float(phi_raw.flat[i]) if phi_raw is not None else float("nan")
            row["cp"] = float(cp_raw.flat[i]) if cp_raw is not None else float("nan")
            row["cp0"] = float(cp0_raw.flat[i]) if cp0_raw is not None else float("nan")
            row["h_e_J_per_kg"] = float(h_e_raw.flat[i]) if h_e_raw is not None else float("nan")
            row["T_r_lam_K"] = float(T_r_lam_raw.flat[i]) if T_r_lam_raw is not None else float("nan")
            row["h_r_lam_J_per_kg"] = float(h_r_lam_raw.flat[i]) if h_r_lam_raw is not None else float("nan")
            row["h_star_lam_J_per_kg"] = float(h_star_lam_raw.flat[i]) if h_star_lam_raw is not None else float("nan")
            row["T_r_turb_K"] = float(T_r_turb_raw.flat[i]) if T_r_turb_raw is not None else float("nan")
            row["h_r_turb_J_per_kg"] = float(h_r_turb_raw.flat[i]) if h_r_turb_raw is not None else float("nan")
            row["h_star_turb_J_per_kg"] = float(h_star_turb_raw.flat[i]) if h_star_turb_raw is not None else float("nan")
            row["q_lam_W_m2"] = float(q_lam_raw.flat[i]) if q_lam_raw is not None else float("nan")
            row["q_turb_W_m2"] = float(q_turb_raw.flat[i]) if q_turb_raw is not None else float("nan")
        else:
            row["T_e_K"] = float("nan")
            row["p_e_Pa"] = float("nan")
            row["rho_e_kg_m3"] = float("nan")
            row["ma_e"] = float("nan")
            row["v_e_m_s"] = float("nan")
            row["mu_e_Pa_s"] = float("nan")
            row["phi_rad"] = float("nan")
            row["cp"] = float("nan")
            row["cp0"] = float("nan")
            row["h_e_J_per_kg"] = float("nan")
            row["T_r_lam_K"] = float("nan")
            row["h_r_lam_J_per_kg"] = float("nan")
            row["h_star_lam_J_per_kg"] = float("nan")
            row["T_r_turb_K"] = float("nan")
            row["h_r_turb_J_per_kg"] = float("nan")
            row["h_star_turb_J_per_kg"] = float("nan")
            row["q_lam_W_m2"] = float("nan")
            row["q_turb_W_m2"] = float("nan")
            row["St_l"] = float("nan")
            row["Re_ns_l"] = float("nan")

        # Leeward-side fields: windward side gets NaN, leeward gets actual values
        if side == "leeward":
            if St_l_raw is not None:
                row["St_l"] = float(St_l_raw.flat[i])
            else:
                row["St_l"] = float("nan")
            if Re_ns_l_raw is not None:
                row["Re_ns_l"] = float(Re_ns_l_raw.flat[i])
            else:
                row["Re_ns_l"] = float("nan")
        if side == "windward":
            row["St_l"] = float("nan")
            row["Re_ns_l"] = float("nan")

        rows.append(row)

    return rows


WINDWARD_COLUMNS = [
    "point_id", "side", "side_id",
    "mach", "alpha_deg", "altitude_km", "Tw_K",
    "x_m", "span_m", "xc", "yb", "valid_mask",
    "q_low_W_m2",
    "T_e_K", "p_e_Pa", "rho_e_kg_m3", "ma_e", "v_e_m_s", "mu_e_Pa_s",
    "phi_rad", "cp", "cp0",
    "h_e_J_per_kg", "T_r_lam_K", "h_r_lam_J_per_kg", "h_star_lam_J_per_kg",
    "T_r_turb_K", "h_r_turb_J_per_kg", "h_star_turb_J_per_kg",
    "q_lam_W_m2", "q_turb_W_m2",
    "St_l", "Re_ns_l",
    "w_tr", "re_edge", "re_tri",
]

LEEWARD_COLUMNS = [
    "point_id", "side", "side_id",
    "mach", "alpha_deg", "altitude_km", "Tw_K",
    "x_m", "span_m", "xc", "yb", "valid_mask",
    "q_low_W_m2",
    "T_e_K", "p_e_Pa", "rho_e_kg_m3", "ma_e", "v_e_m_s", "mu_e_Pa_s",
    "phi_rad", "cp", "cp0",
    "h_e_J_per_kg", "T_r_lam_K", "h_r_lam_J_per_kg", "h_star_lam_J_per_kg",
    "T_r_turb_K", "h_r_turb_J_per_kg", "h_star_turb_J_per_kg",
    "q_lam_W_m2", "q_turb_W_m2",
    "St_l", "Re_ns_l",
    "w_tr", "re_edge", "re_tri",
]


def write_csv(rows: list[dict], path: str | Path, columns: list[str]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, mode="w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"written: {p}")


def _summarize(rows: list[dict], label: str) -> None:
    qs = [r["q_low_W_m2"] for r in rows]
    arr = np.array(qs, dtype=float)
    finite = np.isfinite(arr)
    n_finite = int(finite.sum())
    n_nan = int((~finite).sum())
    if n_finite > 0:
        print(f"  {label}: rows={len(rows)} finite={n_finite} NaN={n_nan} "
              f"min={float(arr[finite].min()):.2f} "
              f"max={float(arr[finite].max()):.2f} "
              f"mean={float(arr[finite].mean()):.6f}")
    else:
        print(f"  {label}: rows={len(rows)} finite={n_finite} NaN={n_nan} (all NaN)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Export Faceted3D fields to multi-fidelity CSV table")
    ap.add_argument("--run_dir", type=str, default="runs/0629_fields_phase2a",
                    help="run directory containing fields.npz and summary.json")
    ap.add_argument("--out_prefix", type=str, default="low_fidelity_points",
                    help="output CSV prefix (default: low_fidelity_points)")
    ap.add_argument("--out_dir", type=str, default=None,
                    help="output directory (default: same as --run_dir)")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    out_dir = Path(args.out_dir) if args.out_dir else run_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    prefix = args.out_prefix

    print(f"Loading fields from {run_dir / 'fields.npz'} ...")
    fields = load_fields(run_dir)

    print(f"Loading summary from {run_dir / 'summary.json'} ...")
    summary = load_summary(run_dir)

    print("Building windward table ...")
    windward_rows = build_table(fields, summary, side="windward")

    print("Building leeward table ...")
    leeward_rows = build_table(fields, summary, side="leeward")

    all_rows = windward_rows + leeward_rows

    valid_rows = [r for r in all_rows if r["valid_mask"]]

    columns = WINDWARD_COLUMNS

    wpath = out_dir / f"{prefix}_windward.csv"
    write_csv(windward_rows, wpath, columns)

    lpath = out_dir / f"{prefix}_leeward.csv"
    write_csv(leeward_rows, lpath, columns)

    apath = out_dir / f"{prefix}_all.csv"
    write_csv(all_rows, apath, columns)

    vpath = out_dir / f"{prefix}_all_valid.csv"
    write_csv(valid_rows, vpath, columns)

    print()
    print("=== SUMMARY ===")
    _summarize(windward_rows, "windward")
    _summarize(leeward_rows, "leeward")
    _summarize(all_rows, "all")
    _summarize(valid_rows, "all_valid")
    print("Done.")


if __name__ == "__main__":
    main()
