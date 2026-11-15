"""Person 1 adapter: publish aggregates only, with correctly labeled service access."""

from __future__ import annotations

from collections import Counter, defaultdict

import pandas as pd

from src.common import haversine_miles, none_if_nan
from src.phoenix.housing import summarize_housing
from src.phoenix.models import ServiceLocation
from src.phoenix.normalization import city_key, request_cities
from src.phoenix.spatial import attach_service_access
from src.recommend.person1_data import Person1DataUnavailable, load_person1, native_profile


def nearby_places(services: pd.DataFrame, city: str, zipcode: str | None, *, limit: int = 3) -> list[dict]:
    """Nearby public places, never a distance from a rental address.

    Use a center derived only from public businesses in this ZIP/city. Prefer
    verified community providers, then review-adjusted ratings and distance.
    Missing or closed places are not filled with invented recommendations.
    """
    required = {"place_id", "name", "city", "zipcode", "lat", "lon"}
    if services.empty or not required.issubset(services.columns):
        return []
    columns = [column for column in ("place_id", "name", "city", "zipcode", "lat", "lon", "family", "family_label",
        "maps_url", "permanently_closed", "temporarily_closed", "verification_status", "assistance", "rating", "reviews_count") if column in services]
    located = services[columns].dropna(subset=["lat", "lon", "name", "place_id"]).copy()
    in_area = located["zipcode"].eq(zipcode) if zipcode else located["city"].str.casefold().eq(city.casefold())
    reference = located[in_area]
    if reference.empty:
        return []
    lat, lon = float(reference["lat"].median()), float(reference["lon"].median())
    located["_distance"] = haversine_miles(lat, lon, located["lat"], located["lon"])
    local = located[located["_distance"] <= 2].copy()
    for column in ("permanently_closed", "temporarily_closed"):
        if column in local:
            local = local[~local[column].eq(True)]
    local["_verified"] = local.get("verification_status", pd.Series(index=local.index, dtype=str)).eq("verified_public_community")
    local["_support"] = local.get("assistance", pd.Series(False, index=local.index)).eq(True)
    local["_family"] = local.get("family", local.get("family_label", pd.Series("unknown", index=local.index))).fillna("unknown")
    ratings = pd.to_numeric(local.get("rating", pd.Series(index=local.index, dtype=float)), errors="coerce")
    counts = pd.to_numeric(local.get("reviews_count", pd.Series(index=local.index, dtype=float)), errors="coerce").fillna(0).clip(lower=0)
    local["_score"] = (counts * ratings.fillna(3.5) + 20 * 3.5) / (counts + 20)
    ranked = local.sort_values(["_verified", "_support", "_score", "_distance", "place_id"],
                              ascending=[False, False, False, True, True], kind="stable").drop_duplicates("place_id")
    diverse = ranked.drop_duplicates("_family").head(limit)
    top = pd.concat([diverse, ranked[~ranked["place_id"].isin(diverse["place_id"])]], ignore_index=True).head(limit)
    return [{"place_id":str(row["place_id"]), "name":str(row["name"]),
             "family_label":none_if_nan(row.get("family_label")) or "Community service",
             "maps_url":none_if_nan(row.get("maps_url"))}
            for row in top.to_dict("records")]


def service_map_points(areas: list[dict], services: pd.DataFrame) -> list[dict]:
    """Map only the named public places on the area shortlists.

    Keep business coordinates separate from the housing aggregates so the
    rental-address privacy contract stays intact.
    """
    if services.empty or not {"place_id", "lat", "lon"}.issubset(services.columns):
        return []
    wanted = {place["place_id"] for area in areas for place in area.get("nearby_places", [])}
    points = services[services["place_id"].isin(wanted)][["place_id", "lat", "lon"]].copy()
    points["lat"] = pd.to_numeric(points["lat"], errors="coerce")
    points["lon"] = pd.to_numeric(points["lon"], errors="coerce")
    points = points[points["lat"].between(-90, 90) & points["lon"].between(-180, 180)]
    return [{"place_id": str(row["place_id"]), "lat": float(row["lat"]), "lon": float(row["lon"])}
            for row in points.drop_duplicates("place_id").to_dict("records")]


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
    columns = [column for column in ("place_id", "family", "family_label", "lat", "lon", "permanently_closed", "temporarily_closed") if column in services]
    for row in services[columns].to_dict("records"):
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
            "nearby_services":nearby, "nearby_places":nearby_places(services, area.city, area.zipcode, limit=10),
            "source_note":" ".join(area.notes)})
    return {"status":"ok" if output else "no_results", "areas":output,
            "notes":["Zillow rental snapshots; current availability and screening are unverified.",
                     "City and ZIP populations overlap; do not add their record counts.",
                     "Rents combine bedroom/property types; inspect the distributions before comparing housing options.",
                     "Service access is an aggregate over internal properties, not a count at a single user address or a travel time.",
                     f"{status['suppressed_small_groups']} groups suppressed below five distinct properties."]}
