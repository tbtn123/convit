import random
import re
from py_evalexpr import evaluate

class AmountParseError(ValueError):
    pass

SUFFIXES = {
    "k": 1000,
    "m": 1000000,
    "mil": 1000000,
    "b": 1000000000,
    "bil": 1000000000,
}

def pct_fix(expr: str):
    return re.sub(r"(\d+(\.\d+)?)%", r"(\1/100)", expr)

def parse_suffix_number(expr: str):
    m = re.fullmatch(r"(\d+(\.\d+)?)([a-z]+)", expr)
    if not m:
        return None
    num = float(m.group(1))
    suf = m.group(3).lower()
    if suf not in SUFFIXES:
        return None
    return int(num * SUFFIXES[suf])

def parse_amount(expr: str, total: int) -> int:
    if total <= 0:
        raise AmountParseError("Total must be > 0.")
    expr = expr.strip().lower()
    if expr == "all":
        return total
    if expr == "random":
        return random.randint(1, total)
    if expr.startswith("!"):
        try:
            keep = int(expr[1:])
        except:
            raise AmountParseError("Invalid reverse format: use !<number>")
        give = total - keep
        if give < 0:
            raise AmountParseError("Reverse amount exceeds total.")
        return give
    suffix_val = parse_suffix_number(expr)
    if suffix_val is not None:
        if suffix_val > total:
            raise AmountParseError("Amount exceeds total.")
        return suffix_val
    if expr.isdigit():
        val = int(expr)
        if val > total:
            raise AmountParseError("Amount exceeds total.")
        return val
    expr = pct_fix(expr)
    try:
        result = evaluate(expr)
    except:
        raise AmountParseError(f"Invalid amount format: '{expr}'")
    if isinstance(result, (int, float)):
        if result <= 1:
            val = int(total * result)
        else:
            val = int(result)
    else:
        raise AmountParseError("Unsupported expression result.")
    if val < 0:
        raise AmountParseError("Resulting amount is negative.")
    if val > total:
        raise AmountParseError("Amount exceeds total.")
    return val
