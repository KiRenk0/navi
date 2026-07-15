# Faceted3D Model Limitation Diagnostics

> Generated from: `runs\0629_fields_phase4`
> Date: 2026-06-28

## 1. q_lam > q_turb Diagnosis

### Global stats

| Metric | Value |
|--------|-------|
| q_lam > q_turb points | 508 / 3240 (15.68%) |
| q_lam/q_turb min | 0.3900 |
| q_lam/q_turb max | 2.7115 |
| q_lam/q_turb mean | 0.7633 |
| q_lam/q_turb median | 0.6856 |

### x/c distribution of q_lam > q_turb points

| x/c range | q_lam > q_turb | total valid | ratio |
|-----------|----------------|-------------|-------|
| 0.00–0.02 | 1 | 1 | 100.0% |
| 0.02–0.05 | 1 | 1 | 100.0% |
| 0.05–0.10 | 3 | 3 | 100.0% |
| 0.10–0.20 | 4 | 8 | 50.0% |
| 0.20–1.00 | 39 | 179 | 21.8% |

### y/b distribution of q_lam > q_turb points

| y/b range | q_lam > q_turb | total valid | ratio |
|-----------|----------------|-------------|-------|
| 0.0–0.1 | 12 | 324 | 3.7% |
| 0.1–0.2 | 15 | 324 | 4.6% |
| 0.2–0.3 | 16 | 324 | 4.9% |
| 0.3–0.4 | 16 | 324 | 4.9% |
| 0.4–0.5 | 12 | 324 | 3.7% |
| 0.5–0.6 | 13 | 324 | 4.0% |
| 0.6–0.7 | 32 | 324 | 9.9% |
| 0.7–0.8 | 70 | 324 | 21.6% |
| 0.8–0.9 | 101 | 324 | 31.2% |
| 0.9–1.0 | 221 | 324 | 68.2% |

### q_lam > q_turb coordinate ranges

| Variable | Min | Max |
|----------|-----|-----|
| x_m | -0.0008 | 3.5917 |
| span_m | 0.0000 | 1.0053 |
| xc | 0.0000 | 0.9750 |
| yb | 0.0000 | 0.9750 |

## 2. Leeward Field Constancy

### q_l (leeward heat flux)

| Metric | Value |
|--------|-------|
| min | 1076.873378 W/m² |
| max | 1076.873378 W/m² |
| mean | 1076.873378 W/m² |
| std | 0.000000 W/m² |
| is_constant (std < 1e-6) | True |

### St_l (leeward Stanton number)

| Metric | Value |
|--------|-------|
| min | 0.0002676089 |
| max | 0.0002676089 |
| mean | 0.0002676089 |
| std | 0.0000000000 |
| is_constant | True |

### Re_ns_l (leeward reference Reynolds)

| Metric | Value |
|--------|-------|
| min | 405.729286 |
| max | 405.729286 |
| mean | 405.729286 |
| std | 0.000000 |
| is_constant | True |

### Cause of leeward constant fields

The leeward model uses a single chord-averaged normal-shock Reynolds number per strip:

    Re_ns = ρ_inf · V_inf · R_ref / μ_ns

where `R_ref` is based on the effective chord (clamped to chord_min_m=0.02 for all strips
in the isothermal300 case since the actual chord is already ≥0.02 everywhere).

The Stanton number is then:

    St = 0.00282 · (0.7905 + 1.067 · h_wwd / h_s) · Re_ns^(-0.37)

For an **isothermal wall** (Tw = 300K everywhere), h_wwd(x) = h_w = constant along the chord,
making St(x) ≈ constant. With constant St and constant h_wwd, q_l = ρ_inf · V_inf · St · (h_s - h_w)
is also constant.

**Result:** q_l, St_l, and Re_ns_l are all single-scalar constants for this isothermal case.
This is a known limitation of the leeward reference-enthalpy model — it does not capture
spatial variation in leeward heating even though the actual physics has chordwise recovery.

## 3. q_w Maximum Location

| Field | Value |
|-------|-------|
| q_w max | 387155.05 W/m² |
| j (span index) | 0 |
| i (chord index) | 0 |
| x_m | -0.000801 m |
| span_m | 0.000000 m |
| xc | 0.0000 |
| yb | 0.0000 |
| phi_w | 0.173779 rad (9.9568 deg) |
| cp_w | 0.130577 |
| T_e_w | 551.82 K |
| q_lam_w | 181247.32 W/m² |
| q_turb_w | 80691.50 W/m² |
| q_lam/q_turb | 2.2462 |

The q_w maximum is at the stagnation point (nose tip, xc=0, yb=0) where the
Kemp-Riddell stagnation-point formula dominates over the strip-theory heating.

## 4. Current Model Limitations

### Confirmed limitations

| # | Limitation | Impact | Mitigation |
|---|-----------|--------|------------|
| 1 | Leeward q, St, Re_ns are constant per isothermal case | No spanwise/chordwise variation in leeward heating | Use Fluent as high-fidelity surrogate; leeward features can be absorbed by residual model |
| 2 | Last spanwise row (j=40, y/b=1.0) has zero chord | 81 points are NaN (2.4% of grid) | Already masked; for surrogate, exclude via valid_mask |
| 3 | No 3D surface streamlines | X-length uses simple streamline integration, not true 3D particle tracing | Acceptable for engineering REM; true 3D requires Euler/CFD |
| 4 | No external Euler/CFD flowfield | Edge conditions from Busemann cone + flat-plate strip theory | Primary purpose of multi-fidelity; Fluent provides high-fi edge |
| 5 | No leeward T_e, p_e, rho_e, ma_e, v_e, mu_e output | Leeward uses normal-shock averaged state, not edge-resolved | Low priority; leeward heating is small relative to windward |

### Limitations NOT observed

- Windward heat flux shows expected spatial variation (stagnation peak, chordwise decay, spanwise variation)
- q_lam > q_turb occurs in limited regions (see Section 1) and is physically reasonable at low Re_x
- No numerical instability observed in the current case (Ma=8.3, α=2.2°, h=56.7 km)

## 5. Recommendations

### For Fluent residual surrogate modeling

1. **Include all windward edge fields** (T_e, p_e, rho_e, ma_e, v_e, mu_e, phi, cp) as low-fidelity features
2. **Include reference-enthalpy intermediates** (h_e, h_r_lam, h_r_turb, h_star_lam, q_lam, q_turb)
3. **Use valid_mask** to exclude the zero-chord tip row (j=40)
4. **Leeward side should be treated separately** — the constant leeward model means a single correction factor per case may be sufficient rather than a full spatial surrogate

### For future physics model upgrades

5. **Leeward model**: Consider a chord-resolved leeward heating correlation that captures recovery from the windward-side edge (leeward T_e(x) ≈ windward T_e(x) with expansion correction)
6. **3D streamline**: Not recommended until Euler/CFD validation is available
7. **Transition model**: Current step-function weighting may be too sharp; a smooth hyperbolic-tangent blend could be considered, but requires experimental validation

### Do NOT modify

8. **Windward reference-enthalpy formula** — it is the validated engineering core of the solver
9. **Busemann Cp** — it is the correct inviscid cone relation for slender bodies at angle of attack
10. **Kemp-Riddell stagnation formula** — it is the standard engineering stagnation-point correlation
11. **chord_min_m** — it is a numerical guard, not a physics parameter

---
*Report generated by `scripts/diagnose_faceted3d_limitations.py`*
