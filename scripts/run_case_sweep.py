import argparse
import math
import subprocess
import sys
from pathlib import Path


def _parse_list(text: str) -> list[float]:
    s = str(text or "").strip()
    if not s:
        return []
    if ":" in s:
        parts = [p for p in s.split(":") if p != ""]
        if len(parts) != 3:
            raise ValueError("Range format must be start:stop:step")
        start, stop, step = (float(p) for p in parts)
        if step == 0.0:
            raise ValueError("Step must be non-zero")
        vals = []
        v = start
        if step > 0:
            while v <= stop + 1e-12:
                vals.append(float(v))
                v += step
        else:
            while v >= stop - 1e-12:
                vals.append(float(v))
                v += step
        return vals
    return [float(p) for p in s.split(",") if p.strip() != ""]


def _key(v: float) -> str:
    s = f"{v}".replace("-", "m")
    return s.replace(".", "p")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vehicle", required=True)
    ap.add_argument("--case", required=True)
    ap.add_argument("--sampling", required=True)
    ap.add_argument("--run_dir_base", required=True)
    ap.add_argument("--mach_list", required=True)
    ap.add_argument("--alpha_list", required=True)
    ap.add_argument("--h_m", type=float, default=None)
    ap.add_argument("--h_km", type=float, default=None)
    ap.add_argument("--plot_x_over_c_min", type=float, default=None)
    ap.add_argument("--no_plots", action="store_true", default=False)
    ap.add_argument("--f3_effective_alpha", choices=["case", "on", "off"], default="case")
    ap.add_argument("--f3_effective_mach", choices=["case", "on", "off"], default="case")
    ap.add_argument("--f3_x_length_mode", choices=["case", "local", "global", "streamline"], default="case")
    args = ap.parse_args()

    if args.h_m is not None and args.h_km is not None:
        raise ValueError("Use only one of --h_m or --h_km")

    mach_list = _parse_list(args.mach_list)
    alpha_list = _parse_list(args.alpha_list)
    if not mach_list or not alpha_list:
        raise ValueError("mach_list and alpha_list must be non-empty")

    base = Path(args.run_dir_base)
    base.mkdir(parents=True, exist_ok=True)

    for mach in mach_list:
        for alpha in alpha_list:
            run_dir = base / f"ma{_key(mach)}_a{_key(alpha)}"
            cmd = [
                sys.executable,
                "scripts/run_case_rem.py",
                "--vehicle",
                str(args.vehicle),
                "--case",
                str(args.case),
                "--sampling",
                str(args.sampling),
                "--run_dir",
                str(run_dir),
                "--mach",
                str(mach),
                "--alpha",
                str(alpha),
            ]
            if args.h_m is not None:
                cmd += ["--h_m", str(args.h_m)]
            if args.h_km is not None:
                cmd += ["--h_km", str(args.h_km)]
            if args.plot_x_over_c_min is not None:
                cmd += ["--plot_x_over_c_min", str(args.plot_x_over_c_min)]
            if args.no_plots:
                cmd += ["--no_plots"]
            if str(args.f3_effective_alpha) != "case":
                cmd += ["--f3_effective_alpha", str(args.f3_effective_alpha)]
            if str(args.f3_effective_mach) != "case":
                cmd += ["--f3_effective_mach", str(args.f3_effective_mach)]
            if str(args.f3_x_length_mode) != "case":
                cmd += ["--f3_x_length_mode", str(args.f3_x_length_mode)]
            subprocess.run(cmd, check=True, cwd=str(Path(__file__).resolve().parents[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
