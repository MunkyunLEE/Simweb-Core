import re

SYSTEM = {"length": "mm", "mass": "tonne", "time": "s", "force": "N", "stress": "MPa", "density": "tonne/mm3", "velocity": "mm/s", "acceleration": "mm/s2", "dynamic_viscosity": "MPa·s", "kinematic_viscosity": "mm2/s"}

G = 9810.0

FACTORS = {
    "length": {"mm": 1.0, "cm": 10.0, "m": 1000.0, "km": 1e6, "inch": 25.4, "in": 25.4},
    "time": {"s": 1.0, "ms": 1e-3, "min": 60.0, "h": 3600.0},
    "force": {"N": 1.0, "kN": 1e3, "MN": 1e6, "kgf": 9.80665, "tf": 9806.65},
    "stress": {"MPa": 1.0, "kPa": 1e-3, "Pa": 1e-6, "GPa": 1e3, "bar": 0.1, "N/mm2": 1.0},
    "density": {"tonne/mm3": 1.0, "kg/m3": 1e-12, "g/cm3": 1e-9, "kg/mm3": 1e-3},
    "velocity": {"mm/s": 1.0, "m/s": 1e3, "cm/s": 10.0, "km/h": 1e6 / 3600.0},
    "acceleration": {"mm/s2": 1.0, "m/s2": 1e3, "g": G},
    "dynamic_viscosity": {"MPa·s": 1.0, "MPa*s": 1.0, "Pa·s": 1e-6, "Pa*s": 1e-6, "mPa·s": 1e-9, "mPa*s": 1e-9, "cP": 1e-9},
    "kinematic_viscosity": {"mm2/s": 1.0, "m2/s": 1e6, "cSt": 1.0},
    "flow": {"mm3/s": 1.0, "m3/s": 1e9, "L/s": 1e6, "L/min": 1e6 / 60.0, "m3/h": 1e9 / 3600.0},
}

FLUIDS = {
    "water": {"name": "물 20°C", "rho": 0.998e-9, "mu": 1.002e-9},
    "air": {"name": "공기 20°C", "rho": 1.204e-12, "mu": 1.81e-11},
    "oil": {"name": "윤활유", "rho": 0.87e-9, "mu": 0.1e-6},
}

_ALIASES = {"㎜": "mm", "㎝": "cm", "㎧": "m/s", "m³/s": "m3/s", "mm³/s": "mm3/s", "m²/s": "m2/s", "mm²/s": "mm2/s", "m/s²": "m2/s", "mm/s²": "mm/s2", "kg/m³": "kg/m3", "g/cm³": "g/cm3", "N/mm²": "N/mm2", "초": "s", "분": "min", "시간": "h"}


def to_internal(value, unit, kind=None):
    unit = _ALIASES.get(unit, unit)
    kinds = [kind] if kind else list(FACTORS)
    for k in kinds:
        f = FACTORS[k]
        if unit in f:
            return float(value) * f[unit], k
        low = {u.lower(): v for u, v in f.items()}
        if unit.lower() in low:
            return float(value) * low[unit.lower()], k
    raise ValueError(f"단위 '{unit}' 을(를) 알 수 없습니다")


def from_internal(value, unit, kind):
    return float(value) / FACTORS[kind][_ALIASES.get(unit, unit)]


_NUM = r"([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"


def find(text, kind):
    units = sorted(FACTORS[kind], key=len, reverse=True) + [a for a, b in _ALIASES.items() if b in FACTORS[kind]]
    pat = _NUM + r"\s*(" + "|".join(re.escape(u) for u in units) + r")(?![A-Za-z0-9])"
    out = []
    for m in re.finditer(pat, text):
        out.append(to_internal(float(m.group(1)), m.group(2), kind)[0])
    return out


def to_si(value, kind):
    si = {"length": 1e-3, "time": 1.0, "force": 1.0, "stress": 1e6, "density": 1e12, "velocity": 1e-3, "acceleration": 1e-3, "dynamic_viscosity": 1e6, "kinematic_viscosity": 1e-6, "flow": 1e-9}
    return float(value) * si[kind]
