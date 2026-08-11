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


# Reusable, country-scoped identity aliases only. These entries describe a
# team, never a drawing position or fixture. Short acronyms are intentionally
# unusable outside their country scope.
_TEAM_ALIAS_FAMILIES = (
    _family(
        "BR",
        "BR:CLUBE_REGATAS_BRASIL",
        ("CRB", "Clube de Regatas Brasil", "Клуб Регатас Бразил", "КРБ"),
    ),
    _family("BR", "BR:AVAI", ("Avai", "Avaí", "Аваи")),
    _family(
        "FI",
        "FI:JJK",
        ("JJK", "JJK Jyväskylä", "JJK Jyvaskyla", "ЯЮК"),
    ),
    _family(
        "FI",
        "FI:TAMPERE_UNITED",
        ("Tampere United", "Тампере Юнайтед"),
    ),
    _family(
        "CO",
        "CO:REAL_SANTANDER",
        ("Real Santander", "Реал Сантандер"),
    ),
    _family(
        "CO",
        "CO:BARRANQUILLA",
        ("Barranquilla", "Барранкилья"),
    ),
    _family(
        "CL",
        "CL:DEPORTES_PUERTO_MONTT",
        ("D. Puerto Montt", "Deportes Puerto Montt", "Пуэрто Монтт"),
    ),
    _family(
        "CL",
        "CL:UNION_ESPANOLA",
        ("Union Espanola", "Unión Española", "Унион Эспаньола"),
    ),
)


def _build_alias_index() -> dict[tuple[str, str], str]:
    index: dict[tuple[str, str], str] = {}
    for country, identity, aliases in _TEAM_ALIAS_FAMILIES:
        stable_country = country_identity(country)
        if not aliases:
            raise ValueError("team alias family must not be empty")
        for alias in aliases:
            key = (stable_country, transliterate_team_name(alias))
            previous = index.setdefault(key, identity)
            if previous != identity:
                raise ValueError("country-scoped team alias collision")
    return index


_TEAM_ALIAS_INDEX = _build_alias_index()


def canonical_team_alias_identity(name: str, *, country: str | None) -> str | None:
    """Return a reviewed reusable identity for an exact country-scoped alias.

    Unknown aliases intentionally return ``None``. The function never falls
    back to fuzzy matching and never treats the same acronym as global.
    """
    if country is None or not country.strip():
        return None
    return _TEAM_ALIAS_INDEX.get(
        (country_identity(country), transliterate_team_name(name))
    )
