"""Person 1 adapter: publish aggregates only, with correctly labeled service access."""

from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from src.common import none_if_nan
from src.phoenix.housing import summarize_housing
from src.phoenix.models import ServiceLocation
from src.phoenix.normalization import city_key, request_cities
from src.phoenix.spatial import attach_service_access
from src.recommend.person1_data import Person1DataUnavailable, load_person1, native_profile


def housing_areas(location: str, services: pd.DataFrame, *, source: str = "real") -> dict:
    try:
        _, rentals, _ = load_person1(source)
    except Person1DataUnavailable as error:
        return {"status":"not_integrated", "areas":[], "notes":[str(error)]}
    profile = native_profile({"location":location, "priority_need":"housing"}, source)
    cities = request_cities(profile.location, profile.search_cities)
    if not cities:
        return {"status":"no_results", "areas":[], "notes":["Location could not be resolved; no broad-area fallback was applied."]}
    selected = [r for r in rentals if city_key(r.city) in cities]
    areas, status = summarize_housing(selected, cities=cities)
    families = {}
    locations = []
    for row in services.to_dict("records"):
        lat, lon = none_if_nan(row.get("lat")), none_if_nan(row.get("lon"))
        family = row.get("family")
        if lat is None or lon is None or not family:
            continue
        families[family] = row.get("family_label") or family
        locations.append(ServiceLocation(place_id=row["place_id"], service_family=family, latitude=lat, longitude=lon,
            permanently_closed=none_if_nan(row.get("permanently_closed")), temporarily_closed=none_if_nan(row.get("temporarily_closed"))))
    if locations:
        areas = attach_service_access(areas, selected, locations)
    records = defaultdict(list)
    for r in selected:
        records[(city_key(r.city), None)].append(r)
        if r.zipcode:
            records[(city_key(r.city), r.zipcode)].append(r)
    output = []
    for area in areas:
        group = records[(city_key(area.city), area.zipcode)]
        rents = pd.Series([r.monthly_rent for r in group])
        nearby = [{"family":a.service_family, "family_label":families.get(a.service_family, a.service_family),
                   "median_count_within_1_mile":a.median_service_count_within_radius,
                   "share_of_properties_with_service":a.share_of_properties_with_service,
                   "properties_with_coordinates":a.properties_with_coordinates,
                   "measurement":a.measurement} for a in area.service_access]
        output.append({"area_id":area.area_id, "area_type":"zip" if area.zipcode else "city",
            "label":f"{area.city} {area.zipcode}" if area.zipcode else area.city,
            "usable_rental_records":area.listing_count, "suppressed":False,
            "median_monthly_rent":area.median_monthly_rent,
            "rent_p25":float(rents.quantile(.25)), "rent_p75":float(rents.quantile(.75)), "rent_basis":"listed_rent",
            "bedrooms":dict(Counter("unknown" if r.bedrooms is None else f"{r.bedrooms:g}" for r in group)),
            "property_types":dict(Counter(r.home_type or "unknown" for r in group)),
            "nearby_services":nearby, "source_note":" ".join(area.notes)})
    return {"status":"ok" if output else "no_results", "areas":output,
            "notes":["Zillow rental snapshots; current availability and screening are unverified.",
                     "City and ZIP populations overlap; do not add their record counts.",
                     "Rents combine bedroom/property types; inspect the distributions before comparing housing options.",
                     "Service access is an aggregate over internal properties, not a count at a single user address or a travel time.",
                     f"{status['suppressed_small_groups']} groups suppressed below five distinct properties."]}
