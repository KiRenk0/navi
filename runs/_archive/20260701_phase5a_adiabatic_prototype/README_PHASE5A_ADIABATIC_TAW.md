# Phase 5-A-P1 Route A Taw Prototype Archive

## Purpose

Route A adiabatic wall temperature (recovery temperature) prototype evidence.
Sandbox-only, wrapper-only. No Fluent adiabatic wall comparison. No temperature model validation.

## Archive Structure

\\\
runs/_archive/20260701_phase5a_adiabatic_prototype/
├── README_PHASE5A_ADIABATIC_TAW.md
├── step_baseline/
│   ├── ma6_a5_h30km/
│   │   ├── taw_fields.npz
│   │   ├── taw_summary.json
│   │   └── region_taw_metrics.csv
│   └── ma8_a5_h30km/
│       ├── taw_fields.npz
│       ├── taw_summary.json
│       └── region_taw_metrics.csv
└── logs/
    └── phase5a_adiabatic_taw_prototype.log
\\\

## Formula Reference

See \docs/phase5a_adiabatic_wall_temperature_formula_architecture_zh.md\.

## Current Status

Both cases PASS range checks. Evidence archived after Phase 5-A-P1/P2 final closeout.

