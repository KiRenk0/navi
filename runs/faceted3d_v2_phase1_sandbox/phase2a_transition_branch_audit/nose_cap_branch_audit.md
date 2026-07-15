# Nose-Cap Branch Audit

Key question: why does true_nose_cap q_v2 still overpredict 2.35-2.73x
after Cp correction to ~1.0x?

## Region definition
true_nose_cap: x < 5*Rn (0.15m) AND span < 0.10m
Count per case: ~3530 aligned points (nose-dominant)

## Branch source

In the current solver, nose-cap points are processed through the same
windward reference enthalpy branch as body points, EXCEPT the first x/c=0
point which uses Kemp-Riddell stagnation heating.

However, for x/c>0 points near the nose cap:
- w_tr=0 (fully laminar) due to low Re_x
- q = q_lam (laminar reference enthalpy branch)
- q_lam is governed by Re_x^(-0.5), where x ≈ streamline length from nose

## Root cause of remaining overprediction

1. **Re_x is too low** — x_eff near nose is ~0.001-0.01m → Re_x ~10^3-10^4
   → q ~ Re_x^(-0.5) amplifies the heat flux
2. **q_lam formula at low Re_x** — the laminar branch q = 0.332*Pr^(-2/3)*rho_e*v_e*
   Re_x^(-0.5)*(h_r-h_w) with the density-viscosity ratio factor. At ~1cm from nose,
   this formula is operating outside its intended domain (flat plate)
3. **Cp is not the issue** — cp_ratio_v2 ~ 1.0x for nose cap
4. **Transition smoothing cannot help** — w_tr=0 already, the issue is the
   laminar branch formula itself at extremely low x

## Conclusion

Nose-cap overprediction is NOT a transition problem. It is inherent to the
reference enthalpy strip-theory closure at extreme leading-edge proximity.
Kemp-Riddell handles the stagnation point; the adjacent points suffer from
Re_x^(-0.5) singularity in the laminar branch.

**Fix**: nose-cap x_eff blending or near-nose laminar branch limit.
**Transition smoothing does NOT address this.**
