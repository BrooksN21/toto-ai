from __future__ import annotations

import re
import unicodedata


def _country_key(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-zа-яё0-9]+", " ", without_marks).split())


def _aliases(identity: str, *values: str) -> dict[str, str]:
    return {_country_key(value): identity for value in values}


# Stable country identities are ISO alpha-2 where one exists. The UK home
# nations and global competitions use explicit stable pseudo-identities. This
# is shared domain normalization, never a drawing- or team-specific alias list.
_COUNTRY_IDENTITIES = {
    **_aliases("AR", "AR", "ARG", "Argentina", "Аргентина"),
    **_aliases("AM", "AM", "ARM", "Armenia", "Армения"),
    **_aliases("AU", "AU", "AUS", "Australia", "Австралия"),
    **_aliases("AT", "AT", "AUT", "Austria", "Австрия"),
    **_aliases("AZ", "AZ", "AZE", "Azerbaijan", "Азербайджан"),
    **_aliases("BY", "BY", "BLR", "Belarus", "Беларусь", "Белоруссия"),
    **_aliases("BE", "BE", "BEL", "Belgium", "Бельгия"),
    **_aliases("BO", "BO", "BOL", "Bolivia", "Боливия"),
    **_aliases("BR", "BR", "BRA", "Brazil", "Бразилия"),
    **_aliases("BG", "BG", "BGR", "Bulgaria", "Болгария"),
    **_aliases("CA", "CA", "CAN", "Canada", "Канада"),
    **_aliases("CL", "CL", "CHL", "Chile", "Чили"),
    **_aliases("CN", "CN", "CHN", "China", "Китай"),
    **_aliases("CO", "CO", "COL", "Colombia", "Колумбия"),
    **_aliases("HR", "HR", "HRV", "Croatia", "Хорватия"),
    **_aliases(
        "CZ",
        "CZ",
        "CZE",
        "Czechia",
        "Czech Republic",
        "Чехия",
    ),
    **_aliases("DK", "DK", "DNK", "Denmark", "Дания"),
    **_aliases("EC", "EC", "ECU", "Ecuador", "Эквадор"),
    **_aliases("GB-ENG", "ENG", "England", "Англия"),
    **_aliases("FI", "FI", "FIN", "Finland", "Финляндия"),
    **_aliases("FR", "FR", "FRA", "France", "Франция"),
    **_aliases("GE", "GE", "GEO", "Georgia", "Грузия"),
    **_aliases("DE", "DE", "DEU", "GER", "Germany", "Германия"),
    **_aliases("GR", "GR", "GRC", "Greece", "Греция"),
    **_aliases("HU", "HU", "HUN", "Hungary", "Венгрия"),
    **_aliases("IS", "IS", "ISL", "Iceland", "Исландия"),
    **_aliases("IE", "IE", "IRL", "Ireland", "Ирландия"),
    **_aliases("IL", "IL", "ISR", "Israel", "Израиль"),
    **_aliases("IT", "IT", "ITA", "Italy", "Италия"),
    **_aliases("JP", "JP", "JPN", "Japan", "Япония"),
    **_aliases("KZ", "KZ", "KAZ", "Kazakhstan", "Казахстан"),
    **_aliases(
        "KR",
        "KR",
        "KOR",
        "South Korea",
        "Korea Republic",
        "Republic of Korea",
        "Южная Корея",
    ),
    **_aliases("MX", "MX", "MEX", "Mexico", "Мексика"),
    **_aliases(
        "NL",
        "NL",
        "NLD",
        "Netherlands",
        "Holland",
        "Нидерланды",
        "Голландия",
    ),
    **_aliases("NO", "NO", "NOR", "Norway", "Норвегия"),
    **_aliases("PY", "PY", "PRY", "Paraguay", "Парагвай"),
    **_aliases("PE", "PE", "PER", "Peru", "Перу"),
    **_aliases("PL", "PL", "POL", "Poland", "Польша"),
    **_aliases("PT", "PT", "PRT", "Portugal", "Португалия"),
    **_aliases("RO", "RO", "ROU", "Romania", "Румыния"),
    **_aliases(
        "RU",
        "RU",
        "RUS",
        "Russia",
        "Russian Federation",
        "Россия",
        "Российская Федерация",
    ),
    **_aliases("GB-SCT", "SCO", "Scotland", "Шотландия"),
    **_aliases("RS", "RS", "SRB", "Serbia", "Сербия"),
    **_aliases("SK", "SK", "SVK", "Slovakia", "Словакия"),
    **_aliases("SI", "SI", "SVN", "Slovenia", "Словения"),
    **_aliases(
        "ZA",
        "ZA",
        "ZAF",
        "South Africa",
        "Republic of South Africa",
        "ЮАР",
        "Южная Африка",
    ),
    **_aliases("ES", "ES", "ESP", "Spain", "Испания"),
    **_aliases("SE", "SE", "SWE", "Sweden", "Швеция"),
    **_aliases("CH", "CH", "CHE", "Switzerland", "Швейцария"),
    **_aliases("TR", "TR", "TUR", "Turkey", "Türkiye", "Турция"),
    **_aliases("UA", "UA", "UKR", "Ukraine", "Украина"),
    **_aliases(
        "US",
        "US",
        "USA",
        "U.S.",
        "U.S.A.",
        "United States",
        "United States of America",
        "США",
        "Соединенные Штаты",
        "Соединённые Штаты",
        "Соединенные Штаты Америки",
        "Соединённые Штаты Америки",
    ),
    **_aliases("UY", "UY", "URY", "Uruguay", "Уругвай"),
    **_aliases("UZ", "UZ", "UZB", "Uzbekistan", "Узбекистан"),
    **_aliases("VE", "VE", "VEN", "Venezuela", "Венесуэла"),
    **_aliases("GB-WLS", "WAL", "Wales", "Уэльс"),
    **_aliases(
        "GLOBAL",
        "World",
        "International",
        "Global",
        "Мир",
        "Международные",
    ),
}


def country_identity(value: str) -> str:
    """Return a stable identity for country comparison.

    Known Russian, English, ISO alpha-2/alpha-3, and common provider forms map
    to one identity. Unknown values remain deterministic exact identities and
    never become fuzzy aliases for another country.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("country must be a non-empty string")
    key = _country_key(value)
    return _COUNTRY_IDENTITIES.get(key, f"NAME:{key}")


def countries_equivalent(left: str, right: str) -> bool:
    return country_identity(left) == country_identity(right)
