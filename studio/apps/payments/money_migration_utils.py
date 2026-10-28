"""Helper congelado para las data migrations de. No cambiar su
comportamiento: migraciones históricas dependen de él."""
import re
from decimal import Decimal, InvalidOperation

_NON_NUMERIC = re.compile(r"[^0-9.,-]")

def parse_amount_to_decimal_str(raw):
    if raw is None:
        return "0.00"
    s = str(raw).strip()
    if not s:
        return "0.00"
    s = _NON_NUMERIC.sub("", s)          # saca $, espacios, letras
    if s.count(",") and s.count("."):
        # el último separador que aparece es el decimal
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")   # 1.234,50 -> 1234.50
        else:
            s = s.replace(",", "")                       # 1,234.50 -> 1234.50
    elif s.count(","):
        s = s.replace(",", ".")                          # 1234,50 -> 1234.50
    try:
        return str(Decimal(s).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        return "0.00"
