#!/usr/bin/env python3
"""Build the LF (reference-enthalpy Taw) + HF (Fluent) paired baseline.

Two datasets are written under ``fenqu_zanshi/data/raw``:

* ``conditions_25_baseline_20261118``: initial training DOE, fenqu1-25 -> C01-C25
* ``dev_validation_15_baseline_20261118``: development validation, dv01-15 -> DV01-DV15

Each case directory keeps only what downstream work needs:

* ``Taw_surface_fields.npz``  LF product (all solver fields, edge audit fields)
* ``summary.json``            LF run summary (models, contracts, residual maxima)
* ``residual_field.npz``      LF, mapped HF (center/node fused), HF-LF, masks,
                              per-node mapping provenance (CSV line, record id, weights)
* ``mapping_audit.json``      mapping settings and counts
* ``case.json``               flow condition, data role, input paths and SHA-256
  (the LF run reads the Fluent export in place; no CSV copy or link is made)
* PNGs: LF Taw, provider, validity, LF-vs-Fluent error (full and nose), HF-LF residual

Not kept per case (reproducible from the inputs recorded in ``case.json``):
Fluent CSV copies, ``surface_mapping_evidence.npz`` (shared mapping operators).

Dataset level: ``case_manifest.csv``, ``case_metrics.csv``, ``DATASET.json``
(solver source hashes, git state, counts).

Usage (from the repository root)::

    python scripts/build_lf_hf_baseline.py --set train --workers 4
    python scripts/build_lf_hf_baseline.py --set dev --workers 4
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "fenqu_zanshi/src"), str(ROOT / "src")]

RAW = ROOT / "fenqu_zanshi/data/raw"
STL = ROOT / "data/geometry/0920/htv2_0920_aligned_clean_ascii.stl"
TEMPLATE = ROOT / "specs/cases/n8_taw_c01.yaml"
CACHES = ROOT / "baselines/0920_fully_turbulent_taw/projection_cache"
TRAIN_SHEET = ROOT / "fenqu_zanshi/configs/conditions_25_run_sheet.csv"
DEV_SHEET = Path(
    r"E:\toy_results\real25\independent_validation_doe_v2_20261114"
    r"\development_validation_15_with_tan.csv"
)
SETS = {
    "train": dict(
        out="conditions_25_baseline_20261118",
        role="initial_training",
        sheet=TRAIN_SHEET,
        export=lambda n: ROOT / f"fluent_export/adiabatic_wall_csv/fenqu{n}/fenqu{n}",
        prefix="C",
        count=25,
    ),
    "dev": dict(
        out="dev_validation_15_baseline_20261118",
        role="development_validation",
        sheet=DEV_SHEET,
        export=lambda n: ROOT / f"fluent_export/dv/dv{n:02d}/dv{n:02d}",
        prefix="DV",
        count=15,
    ),
}
NODE_BOUNDARY_PLANES = [
    dict(axis=0, coordinate_m=3.6, source_tolerance_m=3e-7, stl_tolerance_m=3e-7,
         max_projection_distance_m=0.0009),
    dict(axis=1, coordinate_m=0.0, source_tolerance_m=3e-7, stl_tolerance_m=1e-9,
         max_projection_distance_m=0.0009),
]
KEPT_PNG_PREFIXES = ("Taw_surface_", "Taw_provider_", "Taw_validity_", "Taw_error_vs_fluent_")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_rows(spec: dict) -> list[dict]:
    with Path(spec["sheet"]).open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    expected = [f"{spec['prefix']}{i:02d}" for i in range(1, spec["count"] + 1)]
    if [r["case_id"] for r in rows] != expected:
        raise ValueError(f"unexpected case ids in {spec['sheet']}")
    return rows


def projection_cache_for(center_csv: Path) -> Path:
    from ref_enthalpy_method.mapping.fluent_surface import read_fluent_surface_geometry_csv

    geometry = read_fluent_surface_geometry_csv(
        center_csv, x_offset_m=0.030, coordinate_order="x,up,span"
    )
    digest = hashlib.sha256(
        np.ascontiguousarray(geometry.canonical_solver_xyz).tobytes(order="C")
    ).hexdigest()
    cache = CACHES / f"{digest}.npz"
    if not cache.is_file():
        raise FileNotFoundError(f"no projection cache for {center_csv}: {cache}")
    return cache


# Per-process cache of geometry-only mapping operators (keyed by input hashes).
_OPERATOR_CACHE: dict = {}


def run_case(set_name: str, number: int, row: dict, staging_root: str) -> dict:
    spec = SETS[set_name]
    cid = row["case_id"]
    dest = RAW / spec["out"] / cid
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"refusing to overwrite {dest}")
    stem = spec["export"](number)
    center_csv = stem.with_suffix(".csv")
    node_csv = stem.parent / f"{stem.name}_node.csv"
    for path in (center_csv, node_csv):
        if not path.is_file():
            raise FileNotFoundError(path)
    cache = projection_cache_for(center_csv)
    flow = dict(h_label_km=float(row["H_km"]), mach=float(row["M"]),
                alpha_deg=float(row["alpha_deg"]), T_inf_K=float(row["T_inf_K"]),
                p_inf_Pa=float(row["p_inf_Pa"]))

    stage = Path(staging_root) / cid
    stage.mkdir(parents=True)
    try:
        return _build_case(spec, cid, flow, row, stage, dest, center_csv, node_csv, cache)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def _build_case(spec, cid, flow, row, stage, dest, center_csv, node_csv, cache) -> dict:
    from ref_enthalpy_method.n8_taw_surface import run_n8_taw_case, validate_n8_run_artifacts
    from taw_partition.evaluation.residual_map import plot_residual_field
    from taw_partition.ingest.n8_export import export_paired_case

    case = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    case["case"].update(case_id=cid, observation_csv=center_csv.relative_to(ROOT).as_posix(),
                        mach=flow["mach"], alpha_deg=flow["alpha_deg"], T_inf_K=flow["T_inf_K"],
                        p_inf_Pa=flow["p_inf_Pa"], h_label_km=flow["h_label_km"])
    case["geometry"]["projection_cache"] = cache.relative_to(ROOT).as_posix()
    case_path = stage / "case.yaml"
    case_path.write_text(yaml.safe_dump(case, sort_keys=False), encoding="utf-8")

    t0 = time.monotonic()
    lf_dir = stage / "lf"
    result = run_n8_taw_case(repo_root=ROOT, case_spec_path=case_path,
                             run_dir=lf_dir.relative_to(ROOT), mach=flow["mach"],
                             alpha_deg=flow["alpha_deg"], T_inf_K=flow["T_inf_K"],
                             p_inf_Pa=flow["p_inf_Pa"])
    validate_n8_run_artifacts(result.run_dir)
    fields = lf_dir / "Taw_surface_fields.npz"
    summary = lf_dir / "summary.json"

    paired = dict(
        schema="n8-paired-mapping-input/v1", role="mapping_validation_only", case_id=cid,
        coordinate_unit="m", temperature_unit="K", coordinate_order="x,up,span", x_offset_m=0.03,
        same_solution_assertion=(f"{center_csv.name} and {node_csv.name} are the cell-center and "
                                 "node exports of the same Fluent solution (user supplied)."),
        freestream=flow, node_boundary_planes=NODE_BOUNDARY_PLANES)
    for key, path in [("fields", fields), ("summary", summary), ("projection_cache", cache),
                      ("stl", STL), ("center_csv", center_csv), ("node_csv", node_csv)]:
        paired[key] = dict(path=Path(os.path.relpath(path, stage)).as_posix(), sha256=sha(path))
    paired_path = stage / "paired_input.json"
    paired_path.write_text(json.dumps(paired, indent=2) + "\n", encoding="utf-8")
    mapping_dir = stage / "mapping"
    values, audit = export_paired_case(paired_path, mapping_dir, spec["out"],
                                       operator_cache=_OPERATOR_CACHE)

    # Role in this dataset replaces the generic mapping-candidate labels.
    values.update(role=np.asarray(spec["role"]), data_version=np.asarray(spec["out"]),
                  candidate_only=np.asarray(False), not_for_training=np.asarray(spec["role"] != "initial_training"),
                  theta=np.asarray([flow["h_label_km"], flow["mach"], flow["alpha_deg"]]))
    dest.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dest / "residual_field.npz", **values)
    shutil.copy2(fields, dest / "Taw_surface_fields.npz")
    shutil.copy2(summary, dest / "summary.json")
    for png in lf_dir.glob("*.png"):
        if png.name.startswith(KEPT_PNG_PREFIXES):
            shutil.copy2(png, dest / png.name)
    plot_residual_field(dest / "Taw_surface_fields.npz", dest / "residual_field.npz", dest,
                        display_extension="none")
    for unused in ("Taw_error_stats.json",):
        (dest / unused).unlink(missing_ok=True)
    audit.update(role=spec["role"], candidate_only=False,
                 not_for_training=spec["role"] != "initial_training",
                 output_sha256={"residual_field.npz": sha(dest / "residual_field.npz")},
                 surface_mapping_evidence="not retained; reproducible from case.json inputs")
    audit.pop("input_manifest", None)
    (dest / "mapping_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")

    valid = values["valid"]
    diff = values["residual_HF_minus_LF_K"][valid]
    hf = values["T_fluent_mapped_K"][valid]
    rel = np.abs(diff) / hf
    lf_summary = json.loads(summary.read_text(encoding="utf-8"))
    fit = lf_summary["contracts"]["property_fit_range"]["windward_points_outside_range"]
    metrics = dict(
        case_id=cid, role=spec["role"], H_km=flow["h_label_km"], M=flow["mach"],
        alpha_deg=flow["alpha_deg"], T_inf_K=flow["T_inf_K"], p_inf_Pa=flow["p_inf_Pa"],
        nodes=int(valid.size), hf_valid=int(valid.sum()),
        center_valid=int(values["center_valid"].sum()), node_added=int(values["node_added"].sum()),
        LF_max_K=float(np.nanmax(values["T_ref_full_K"])), HF_max_K=float(hf.max()),
        mean_HF_minus_LF_K=float(diff.mean()), MAE_K=float(np.abs(diff).mean()),
        RMSE_K=float(np.sqrt(np.mean(diff**2))), max_abs_K=float(np.abs(diff).max()),
        mean_abs_rel_pct=float(100 * rel.mean()), p95_abs_rel_pct=float(100 * np.quantile(rel, 0.95)),
        lf_points_outside_nasa9_range=int(fit), seconds=round(time.monotonic() - t0, 1))
    case_record = dict(
        schema="lf-hf-baseline-case/v1", case_id=cid, role=spec["role"], freestream=flow,
        theta_order=["h_label_km", "mach", "alpha_deg"],
        run_sheet=str(spec["sheet"]), run_sheet_sha256=sha(spec["sheet"]),
        inputs={k: dict(path=Path(os.path.relpath(p, ROOT)).as_posix(), sha256=sha(p))
                for k, p in [("center_csv", center_csv), ("node_csv", node_csv),
                             ("projection_cache", cache), ("stl", STL)]},
        lf_model=dict(recovery=lf_summary["contracts"].get("recovery_model"),
                      edge_closure=lf_summary["contracts"].get("edge_closure"),
                      property_fit_range=lf_summary["contracts"].get("property_fit_range"),
                      dispatch_schema=lf_summary["contracts"].get("taw_dispatch_schema")),
        residual_convention="residual_HF_minus_LF_K = HF - LF; residual_K = LF - HF (legacy)",
        metrics=metrics,
        files={p.name: sha(p) for p in sorted(dest.iterdir()) if p.is_file()})
    (dest / "case.json").write_text(json.dumps(case_record, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    return metrics


def source_identity() -> dict:
    files = sorted((ROOT / "src/ref_enthalpy_method").rglob("*.py")) + sorted(
        (ROOT / "fenqu_zanshi/src/taw_partition").rglob("*.py")) + [Path(__file__)]
    def git(*args):
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    return dict(git_head=git("rev-parse", "HEAD"), git_branch=git("rev-parse", "--abbrev-ref", "HEAD"),
                git_dirty_source=bool(git("status", "--porcelain", "--", "src", "fenqu_zanshi/src", "scripts")),
                source_sha256={Path(os.path.relpath(p, ROOT)).as_posix(): sha(p) for p in files})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", choices=sorted(SETS), required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--only", nargs="*", help="case ids to run (default: all)")
    args = parser.parse_args()
    spec = SETS[args.set]
    out = RAW / spec["out"]
    rows = read_rows(spec)
    selected = [(i + 1, r) for i, r in enumerate(rows) if not args.only or r["case_id"] in args.only]
    out.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".staging_{args.set}_", dir=ROOT / "runs/n8_taw_surface"))
    results, failures = [], []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_case, args.set, n, r, str(staging)): r["case_id"] for n, r in selected}
        for future in as_completed(futures):
            cid = futures[future]
            try:
                m = future.result()
                results.append(m)
                print(f"{cid}: DONE hf_valid={m['hf_valid']} MAE={m['MAE_K']:.1f}K "
                      f"rel={m['mean_abs_rel_pct']:.2f}% {m['seconds']}s", flush=True)
            except Exception as exc:  # report every case, then fail
                failures.append(dict(case_id=cid, error=f"{type(exc).__name__}: {exc}"))
                print(f"{cid}: FAILED {type(exc).__name__}: {exc}", flush=True)
    shutil.rmtree(staging, ignore_errors=True)

    # Dataset-level tables are rebuilt from every completed case on disk.
    done = sorted((json.loads((d / "case.json").read_text(encoding="utf-8"))["metrics"]
                   for d in out.iterdir() if (d / "case.json").is_file()), key=lambda m: m["case_id"])
    if done:
        with (out / "case_metrics.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(done[0]))
            writer.writeheader()
            writer.writerows(done)
        with (out / "case_manifest.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["case_id", "role", "H_km", "M", "alpha_deg", "T_inf_K", "p_inf_Pa",
                             "fields_npz", "residual_npz"])
            for m in done:
                writer.writerow([m["case_id"], m["role"], m["H_km"], m["M"], m["alpha_deg"],
                                 m["T_inf_K"], m["p_inf_Pa"], f"{m['case_id']}/Taw_surface_fields.npz",
                                 f"{m['case_id']}/residual_field.npz"])
    dataset = dict(schema="lf-hf-baseline-dataset/v1", dataset=spec["out"], role=spec["role"],
                   built=time.strftime("%Y-%m-%dT%H:%M:%S%z"), run_sheet=str(spec["sheet"]),
                   expected_cases=spec["count"], completed_cases=len(done),
                   failures=failures, solver=source_identity(),
                   notes=("LF: fully turbulent reference-enthalpy Taw (Eckert Pr(T*)), strip "
                          "leading-edge TPG shock entropy, NASA-9 with flagged extension above 6000 K. "
                          "HF: Fluent adiabatic wall temperature, cell-center first, node exports fill gaps."))
    (out / "DATASET.json").write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{spec['out']}: {len(done)}/{spec['count']} cases, {len(failures)} failures", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
