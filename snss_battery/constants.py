"""물리 상수 (SI 단위)."""

FARADAY = 96485.33212  # C/mol
GAS_CONSTANT = 8.314462618  # J/(mol·K)
KELVIN_OFFSET = 273.15

NACL_MOLAR_MASS = 58.44  # g/mol
NACL_SATURATION_MOLAR = 6.1  # mol/L, 25°C 부근 포화 농도


def celsius_to_kelvin(t_c: float) -> float:
    return t_c + KELVIN_OFFSET


def thermal_voltage(t_c: float) -> float:
    """RT/F [V]."""
    return GAS_CONSTANT * celsius_to_kelvin(t_c) / FARADAY
