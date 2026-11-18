"""Strip leading-edge reference incidence for the windward entropy reference.

Each spanwise strip (one ``y/b`` row of the structured parameter grid) owns
one reference shock.  Its incidence ``s_le`` is the largest positive pressure
incidence among the valid geometry samples inside the leading-edge window
``x/c <= x_first_valid + LEADING_EDGE_WINDOW_XC``.  Taking the maximum over a
window, instead of the first sample, keeps the definition independent of
where exactly the first valid sample falls.

Any point (structured, inserted or standalone) reads its reference from this
object at its own ``y/b``: rows are linearly interpolated, and the value at
the first/last defined row is held outside them.  A sheet with no strip that
has a positive leading-edge incidence raises instead of inventing a value.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

LEADING_EDGE_WINDOW_XC = 0.05
REFERENCE_SCHEMA = "strip-leading-edge-max-incidence/v1"


@dataclass(frozen=True)
class StripLeadingEdgeReference:
    y_over_b: np.ndarray  # rows with a defined reference, ascending
    incidence_s: np.ndarray  # s_le per defined row
    x_over_c: np.ndarray  # x/c of the sample that set s_le

    @classmethod
    def from_structured(
        cls,
        *,
        x_over_c: np.ndarray,
        y_over_b: np.ndarray,
        incidence_s: np.ndarray,
        geometry_valid: np.ndarray,
        window_xc: float = LEADING_EDGE_WINDOW_XC,
    ) -> StripLeadingEdgeReference:
        xc = np.asarray(x_over_c, dtype=np.float64)
        yb = np.asarray(y_over_b, dtype=np.float64)
        incidence = np.asarray(incidence_s, dtype=np.float64)
        valid = np.asarray(geometry_valid, dtype=np.bool_) & np.isfinite(incidence)
        if incidence.shape != (yb.size, xc.size) or valid.shape != incidence.shape:
            raise ValueError("strip reference arrays must have shape (ny, nx)")
        rows, values, positions = [], [], []
        for j in range(yb.size):
            columns = np.flatnonzero(valid[j])
            if columns.size == 0:
                continue
            first = float(xc[columns[0]])
            window = columns[xc[columns] <= first + float(window_xc) + 1.0e-12]
            best = int(window[np.argmax(incidence[j, window])])
            value = float(incidence[j, best])
            if value <= 0.0:
                continue
            rows.append(float(yb[j]))
            values.append(value)
            positions.append(float(xc[best]))
        if not rows:
            raise ValueError("no strip has a positive leading-edge incidence")
        return cls(
            y_over_b=np.asarray(rows),
            incidence_s=np.asarray(values),
            x_over_c=np.asarray(positions),
        )

    def at(self, *, x_over_c: float, y_over_b: float) -> float:
        del x_over_c  # the reference is a strip property
        value = float(y_over_b)
        if not np.isfinite(value):
            raise ValueError("y/b must be finite for the strip reference")
        return float(np.interp(value, self.y_over_b, self.incidence_s))
