#!/usr/bin/env python3
"""Execute or validate the frozen N6.3 layered error portrait package."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from ref_enthalpy_method.analysis.n6_3_layered_error_portrait import (
    CANONICAL_PACKAGE_PATH,
    DEFAULT_OUTPUT_ROOT,
    execute_analysis,
    validate_analysis_root,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--validate-existing", action="store_true")
    parser.add_argument("--package-root", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--analysis-root", type=Path)
    return parser.parse_args()


def _relative_command(args: argparse.Namespace) -> tuple[str, ...]:
    command = (
        "python",
        "-B",
        "scripts/tools/n6_3_layered_error_portrait.py",
        "--execute",
        "--package-root",
        args.package_root.as_posix(),
        "--output-root",
        args.output_root.as_posix(),
    )
    if any(Path(token).is_absolute() for token in command):
        raise ValueError("execute paths must be repository-relative")
    return command


def main() -> int:
    args = _parse_args()
    if args.execute:
        if args.analysis_root is not None:
            raise ValueError("--analysis-root is only valid with --validate-existing")
        args.package_root = args.package_root or Path(CANONICAL_PACKAGE_PATH)
        args.output_root = args.output_root or DEFAULT_OUTPUT_ROOT.relative_to(ROOT)
        publication = execute_analysis(
            package_root=args.package_root,
            output_root=args.output_root,
            exact_execution_command=_relative_command(args),
        )
    else:
        if args.analysis_root is None:
            raise ValueError("--analysis-root is required with --validate-existing")
        if args.package_root is not None or args.output_root is not None:
            raise ValueError("package/output roots are only valid with --execute")
        publication = validate_analysis_root(args.analysis_root)
    print(
        json.dumps(
            {
                "analysis_root": publication.analysis_root.as_posix(),
                "run_id": publication.run_id,
                "generation_git_sha": publication.generation_git_sha,
                "manifest_sha256": publication.manifest_sha256,
                "artifact_inventory_count": publication.artifact_inventory_count,
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
