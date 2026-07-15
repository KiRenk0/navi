# Leading-Edge Near Branch Audit

Key question: why does leading_edge_near q_v2 underpredict (ratio 0.37-0.60)?

## Region definition
leading_edge_near: span > x/6 (planform edge proximity) AND NOT nose_cap
Count per case: ~5264 aligned points

## Branch source

leading_edge_near points are processed through the standard windward
reference enthalpy branch. However, these points have:
- Very low x_eff (x from leading edge is small)
- w_tr ~ 0.19-0.21 (mostly laminar for Ma6/8 at 30km; 0 for 50km)

## Diagnosis

1. **x_eff is extremely small** near the planform leading edge → Re_x very low
2. **q scales as Re_x^(-0.5)** for laminar — at tiny x, q is very sensitive
3. **Cp correction from ~5x to ~1x reduced p_e but also lowered rho_e and T_e**
4. **The combination of lower edge density + tiny x_eff over-corrects**
5. **w_tr near leading edge is 0 (laminar) for Ma=8,α=10°,h=50km case**
   → q follows q_lam, which is already depressed by Cp correction

## Can transition smoothing help?

**Partially.** If w_tr were a smooth blend (e.g. 0.3 instead of 0),
q would move toward q_turb (which is higher), improving the underprediction.
But the fundamental issue is x_eff being too small — transition smoothing
alone cannot fully fix the leading edge.

## Conclusion

Leading-edge underprediction is a **combination** of:
- x_eff too small → Re_x singularity
- Cp correction over-effective on leading edge geometry
- w_tr=0 prevents switching to turbulent branch (which would help)

**Fix priority**: 1) leading-edge x_eff blending > 2) transition smoothing > 3) Cp model adjustment
