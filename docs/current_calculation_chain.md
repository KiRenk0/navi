# Current calculation chain

The mathematical derivation for the active adiabatic-wall problem is in
[Reference_Enthalpy_Method_Technical_Doc.md](../Reference_Enthalpy_Method_Technical_Doc.md).
The 2026-11-18 audit and the repairs it led to are recorded in
[calculation_audit_2026-11-18.md](calculation_audit_2026-11-18.md).

The only production contract is the 0920 geometry, fully turbulent flow, and
adiabatic wall temperature (Taw). There is one active pressure closure and one
active gas-property chain; neither is selected by a fallback flag in YAML.

## Authorities

```text
scripts/run_n8_taw_case.py
  -> specs/cases/n8_taw_*.yaml
  -> specs/vehicles/htv2_faceted3d_0920.yaml
  -> data/geometry/0920/htv2_0920_aligned_clean_ascii.stl
  -> data/geometry/0920/outline_xz_right_0920.csv
  -> baselines/0920_fully_turbulent_taw/projection_cache/
  -> src/ref_enthalpy_method/n8_taw_surface.py
  -> summary.json / Taw_surface_fields.npz / plots
```

The STL owns surface position and local geometry. The outline CSV owns the
planform boundary, local leading edge, and chord. The vehicle spec therefore
does not repeat root chord, sweep, pressure-model constants, or edge-state
switches that could disagree with those authorities.

## Freestream and material properties

The run uses either a USSA1976 altitude or an explicit, paired `T_inf_K` and
`p_inf_Pa`, which must match the case spec. The Fluent export is identified by
its bytes (SHA-256, header, row count); its filename carries no authority. The active air model is:

- ideal-gas density with the case gas constant;
- Fluent-aligned NASA-9 piecewise `Cp(T)`, enthalpy, and standard entropy;
- Sutherland viscosity with `C1=1.716e-5`, `Tref=273.11 K`, and `S=110.56 K`;
- kinetic-theory conductivity represented by the modified Eucken relation
  `k=mu*(Cp+1.25*R)`.

The local Prandtl number is computed from those active properties as
`Pr(T)=mu(T)*Cp(T)/k(T)`. No independent constant-Prandtl case field exists.

## Geometry and pressure incidence

The body-axis velocity direction without sideslip is
`u=(cos(alpha), 0, sin(alpha))`. Continuous STL normals are explicitly oriented
outward for the geometric upper or lower sheet. The sole incidence definition
is then

```text
s = -dot(u, n_out)
```

The same incidence implementation owns surface classification and pressure;
there is no separate upper/lower slope-sign formula. Domain-conforming inserted
nodes read their own `geometric_sheet`, so an upper node cannot inherit a lower
sheet orientation from a previous loop.

## Pressure and edge state

Windward pressure uses modified Newtonian theory:

```text
Cp_max = 2/(gamma*M_inf^2) * (p_02/p_inf - 1)
Cp     = Cp_max * max(s, 0)^2
```

`p_02/p_inf` is the perfect-gas normal-shock stagnation-pressure ratio. The
actual body-axis Mach number is used because the full 3D normal already contains
sweep geometry. The retired fixed `0.38*sin(phi)^1.15` closure, phi floor,
effective-alpha/Mach switches, and Cp0 supersonic regularization are absent.

Edge states use one thermodynamic model (Fluent NASA-9 `h(T)`, `s0(T)`,
`p = rho R T`). Each spanwise strip owns a reference incidence `s_le`: the
largest positive incidence among valid samples in the leading-edge window
`x/c <= x/c_first_valid + 0.05` (`aero/strip_reference.py`). Every point,
structured or inserted, reads `s_ref = max(s_le(y/b), s_local)` and solves a
TPG normal shock at `M_inf*s_ref` (mass, momentum, total enthalpy). The edge
state lies on that reference isentrope at the modified-Newtonian surface
pressure; `V_e^2 = 2(h0 - h_e)`. `h_e > h0` is reported as a failed edge state
(`edge_status`), never capped into a stagnation point. Inserted nodes are
solved directly with the strip reference, not interpolated from parent Taw.
Per-point energy and entropy residuals are serialized with the product.

Outside the 200-6000 K NASA-9 fit range, Cp is held at the endpoint value and
`h`, `s0` are integrated consistently; `property_in_fit_range` flags each
windward point and the summary counts points outside the range.

## Taw and provider dispatch

For a windward edge state,

```text
h*   = h_e + 0.72 (h_aw - h_e)        (Eckert, adiabatic h_w = h_aw)
r_aw = Pr(T(h*))^(1/3)               (fixed-point iteration with h_aw)
h_aw = h_e + r_aw*V_e^2/2
Taw  = T(h_aw)
```

Provider dispatch is based on the same signed incidence:

- `s<=0`: freestream-recovery candidate;
- `0<s<0.05`: C1 smoothstep blending in enthalpy space;
- `s>=0.05`: fully turbulent windward candidate.

Both candidates and the blend weight are serialized for auditability.

## Fluent comparison and validation scope

The regression case `specs/cases/n8_taw_c01.yaml` reads
`fluent_export/adiabatic_wall_csv/fenqu1/fenqu1.csv` (C01) with the explicit
`x, up, span` coordinate transform and the 76,892-point vehicle-wall geometry.
Exact projection is bound to the canonical Fluent geometry and 0920 geometry
identities. Batch LF+HF pairing for the 25 training and 15 development
validation cases is done by `scripts/build_lf_hf_baseline.py`.

Full-surface error plots use their valid data range. Nose plots use `x<0.1 m`,
a common `181 x 321` grid, and a controlled nearest-supported boundary
extension limited to three times the local Fluent-triangle P95 edge length.

The engineering envelope is altitude 20--60 km, Mach 5--12, and angle of attack
-10--10 degrees. The closure is parameterized across that envelope, but the
40 Fluent cases (25 training, 15 development validation) give a mean absolute
relative LF error of 3.3--5.4% per case, with LF consistently above Fluent.
The frozen C01 baseline is a regression point, not an accuracy claim.
