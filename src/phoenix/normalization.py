"""Conservative geography/field normalization for the actual supplied CSV headers."""

from __future__ import annotations

import math
import re

BAY_COUNTIES = {"alameda", "contra costa", "marin", "napa", "san francisco", "san mateo", "santa clara", "solano", "sonoma"}
# Deliberately explicit: 'California' and 'California City' are not Bay Area cities.
BAY_CITIES = {
    "alameda", "albany", "american canyon", "antioch", "atherton", "belmont", "belvedere",
    "benicia", "berkeley", "brentwood", "brisbane", "burlingame", "calistoga", "campbell",
    "clayton", "cloverdale", "colma", "concord", "corte madera", "cotati", "cupertino",
    "daly city", "danville", "dixon", "dublin", "east palo alto", "el cerrito", "emeryville",
    "fairfax", "fairfield", "foster city", "fremont", "gilroy", "half moon bay", "hayward",
    "healdsburg", "hercules", "hillsborough", "lafayette", "larkspur", "livermore", "los altos",
    "los altos hills", "los gatos", "martinez", "menlo park", "mill valley", "millbrae",
    "milpitas", "monte sereno", "moraga", "morgan hill", "mountain view", "napa", "newark",
    "novato", "oakland", "oakley", "orinda", "pacifica", "palo alto", "petaluma", "piedmont",
    "pinole", "pittsburg", "pleasant hill", "pleasanton", "portola valley", "redwood city",
    "richmond", "rio vista", "rohnert park", "ross", "saint helena", "san anselmo", "san bruno",
    "san carlos", "san francisco", "san jose", "san leandro", "san mateo", "san pablo",
    "san rafael", "san ramon", "santa clara", "santa rosa", "saratoga", "sausalito",
    "sebastopol", "sonoma", "south san francisco", "suisun city", "sunnyvale", "tiburon",
    "union city", "vacaville", "vallejo", "walnut creek", "windsor", "woodside", "yountville",
    # Included in the Places bounding box, kept as an explicitly recognized nearby area.
    "santa cruz", "watsonville", "capitola", "scotts valley",
}


def clean_text(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def city_key(value: str | None) -> str:
    return clean_text(value).casefold().replace("st. helena", "saint helena")


def display_city(value: str) -> str:
    return city_key(value).title()


def optional_bool(value: object) -> bool | None:
    text = clean_text(value).casefold()
    return True if text in {"true", "1", "yes"} else False if text in {"false", "0", "no"} else None


def number(value: object) -> float | None:
    text = clean_text(value).replace(",", "").replace("$", "")
    try:
        result = float(text)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def parse_job_city(location: str, region: str = "") -> str | None:
    """Match longest city before ', CA'; avoid street-name and non-CA false positives."""
    if region and region.upper() not in {"CA", "CALIFORNIA"}:
        return None
    text = clean_text(location).casefold()
    for city in sorted(BAY_CITIES, key=lambda x: (-len(x), x)):
        if re.search(r"(?<!\w)" + re.escape(city) + r",\s*(?:ca\b|california\b)", text):
            return display_city(city)
    return None


def request_cities(location: str, explicit_cities: list[str]) -> set[str]:
    if explicit_cities:
        return {city_key(c) for c in explicit_cities}
    city = parse_job_city(location) or (display_city(location) if city_key(location) in BAY_CITIES else None)
    return {city_key(city)} if city else set()


def valid_coordinate(lat: object, lon: object) -> tuple[float | None, float | None]:
    a, b = number(lat), number(lon)
    return (a, b) if a is not None and b is not None and -90 <= a <= 90 and -180 <= b <= 180 else (None, None)


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a, b, c, d = map(math.radians, (lat1, lon1, lat2, lon2))
    h = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 3958.7613 * 2 * math.asin(min(1, math.sqrt(h)))
