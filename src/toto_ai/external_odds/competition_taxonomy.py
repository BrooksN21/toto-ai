from __future__ import annotations

from collections.abc import Iterable

from toto_ai.external_odds.countries import country_identity
from toto_ai.external_odds.team_registry import transliterate_team_name


def _family(
    country: str,
    identity: str,
    aliases: Iterable[str],
) -> tuple[str, str, tuple[str, ...]]:
    return country, identity, tuple(aliases)


# TotoBrief sometimes exposes a country-local translated tier label while the
# schedule provider uses the federation/league name. Equivalence is explicit
# per country; no alias is global and no unknown league is silently accepted.
_COMPETITION_FAMILIES = (
    _family(
        "CO",
        "CO:PRIMERA_B",
        (
            "1-й дивизион",
            "Primera B",
            "Categoría Primera B",
            "Categoria Primera B",
            "Ascenso",
        ),
    ),
    _family(
        "CL",
        "CL:PRIMERA_B",
        ("1-й дивизион", "Primera B", "Ascenso"),
    ),
    _family(
        "FI",
        "FI:YKKONEN",
        ("2-й дивизион", "Ykkönen", "Ykkonen"),
    ),
)


def _build_competition_index() -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for country, identity, aliases in _COMPETITION_FAMILIES:
        stable_country = country_identity(country)
        if not aliases:
            raise ValueError("competition alias family must not be empty")
        for alias in aliases:
            key = (stable_country, transliterate_team_name(alias))
            previous = index.setdefault(key, identity)
            if previous != identity:
                raise ValueError("country-scoped competition alias collision")
    return index


_COMPETITION_INDEX = _build_competition_index()


def competition_identity(value: str, *, country: str | None) -> str | None:
    """Return a country-scoped taxonomy identity for an exact known alias."""
    if country is None or not country.strip():
        return None
    return _COMPETITION_INDEX.get(
        (country_identity(country), transliterate_team_name(value))
    )


def equivalent_competitions(
    left: str,
    right: str,
    *,
    country: str | None,
) -> bool:
    left_identity = competition_identity(left, country=country)
    return left_identity is not None and left_identity == competition_identity(
        right, country=country
    )
