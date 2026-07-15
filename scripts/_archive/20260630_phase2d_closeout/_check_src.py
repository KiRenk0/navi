#!/usr/bin/env python3
"""Check if src/ files contain ablation-related markers."""
import pathlib

base = pathlib.Path(".")

for f in ["src/ref_enthalpy_method/solver.py", "src/ref_enthalpy_method/solver_faceted3d.py"]:
    p = base / f
    content = p.read_text(encoding="utf-8")
    markers = ["G_qscale", "ablation", "q_scale_override", "q_scale_lam", "q_scale_turb"]
    print(f"{f}:")
    found_any = False
    for m in markers:
        count = content.count(m)
        if count > 0:
            print(f"  contains '{m}': {count} occurrences")
            found_any = True
    if not found_any:
        print("  CLEAN: no ablation markers found")
    lines = content.split("\n")
    print(f"  line count: {len(lines)}")
    print()
