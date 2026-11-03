"""Configurable fantasy D/ST scoring. ESPN-like *provisional* defaults.

Exact league rules must be confirmed before projections are treated as league-accurate.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DefenseScoring:
    sack: float = 1
    interception: float = 2
    fumble_recovery: float = 2
    safety: float = 2
    blocked_kick: float = 2
    return_td: float = 6
    # ESPN's 2026 published default, not necessarily the user's league.
    points_allowed_tiers: tuple = (
        (0, 5), (6, 4), (13, 3), (17, 1),
        (27, 0), (34, -1), (45, -3), (999, -5),
    )

    def allowance(self, points: int) -> float:
        if points < 0:
            raise ValueError("Points allowed cannot be negative")
        for maximum, value in self.points_allowed_tiers:
            if points <= maximum:
                return float(value)
        raise ValueError("Uncovered points-allowed tier")

    @classmethod
    def from_json(cls, path):
        import json
        from pathlib import Path
        v = json.loads(Path(path).read_text(encoding="utf-8"))
        allowed = set(cls.__dataclass_fields__)
        unknown = set(v) - allowed
        if unknown:
            raise ValueError(f"Unsupported defense scoring keys: {sorted(unknown)}")
        if "points_allowed_tiers" in v:
            tiers = [tuple(x) for x in v["points_allowed_tiers"]]
            if not tiers or tiers[-1][0] < 999 or sorted(x[0] for x in tiers) != [x[0] for x in tiers]:
                raise ValueError("Points-allowed tiers must be sorted and end with 999")
            v["points_allowed_tiers"] = tuple(tiers)
        return cls(**v)
