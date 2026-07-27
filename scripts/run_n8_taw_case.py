#!/usr/bin/env python3
"""Run one explicit N8 Taw-only geometric upper/lower case."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _repo_root() -> Path:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
    return root


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run one N8 Taw case. A paired --T_inf_K/--p_inf_Pa override "
            "takes precedence over altitude; otherwise altitude uses USSA1976."
        )
    )
    parser.add_argument("--case", required=True)
    parser.add_argument("--run_dir", required=True)
    parser.add_argument("--mach", type=float, required=True)
    parser.add_argument("--alpha_deg", type=float, required=True)
    parser.add_argument("--T_inf_K", type=float, default=None)
    parser.add_argument("--p_inf_Pa", type=float, default=None)
    altitude = parser.add_mutually_exclusive_group()
    altitude.add_argument("--h_m", type=float, default=None)
    altitude.add_argument("--h_km", type=float, default=None)
    altitude.add_argument(
        "--h_label_km",
        type=float,
        default=None,
        help="legacy alias for --h_km",
    )
    args = parser.parse_args()

    h_m = args.h_m
    if args.h_km is not None:
        h_m = float(args.h_km) * 1000.0
    elif args.h_label_km is not None:
        h_m = float(args.h_label_km) * 1000.0

    root = _repo_root()
    from ref_enthalpy_method.n8_taw_surface import run_n8_taw_case

    try:
        result = run_n8_taw_case(
            repo_root=root,
            case_spec_path=args.case,
            run_dir=args.run_dir,
            mach=args.mach,
            alpha_deg=args.alpha_deg,
            T_inf_K=args.T_inf_K,
            p_inf_Pa=args.p_inf_Pa,
            h_m=h_m,
        )
    except Exception as error:
        print(f"N8 Taw case failed: {error}", file=sys.stderr)
        return 1
    print(f"N8 Taw case PASS: {result.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
