"""Utility functions for time parsing and formatting."""


def parse_time_to_seconds(s: str) -> float:
    """
    Parse a time string to seconds. Accepts:
        - Plain numbers (assumed seconds): e.g., "0.128"
        - With units: "ns", "us" (or "µs"), "ms", "s"
          Examples: "45ns", "3.2us", "64ms", "0.128s"
    """
    s = s.strip().lower().replace("µs", "us")
    unit = None
    for candidate in ("ns", "us", "ms", "s"):
        if s.endswith(candidate):
            unit = candidate
            numeric = s[: -len(candidate)].strip()
            break
    if unit is None:
        try:
            return float(s)
        except ValueError:
            raise ValueError(f"Invalid time format: '{s}'")
    try:
        value = float(numeric)
    except ValueError:
        raise ValueError(f"Invalid numeric time: '{s}'")

    return {
        "s": value,
        "ms": value * 1e-3,
        "us": value * 1e-6,
        "ns": value * 1e-9,
    }[unit]


def human_time(seconds: float) -> str:
    """Format a time in seconds using a friendly unit selection."""
    abs_s = abs(seconds)
    if abs_s >= 1.0:
        return f"{seconds:.6f} s"
    elif abs_s >= 1e-3:
        return f"{seconds * 1e3:.3f} ms"
    elif abs_s >= 1e-6:
        return f"{seconds * 1e6:.3f} us"
    else:
        return f"{seconds * 1e9:.3f} ns"
