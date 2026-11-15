"""Bounded grid joins for property/service proximity, publishing only area aggregates."""

from __future__ import annotations

import math
from collections import defaultdict
from statistics import median

import numpy as np

from .models import AreaServiceAccess, HousingArea, Rental, ServiceLocation
from .normalization import city_key


class ServiceIndex:
    def __init__(self, services: list[ServiceLocation]):
        self.grid: dict[tuple[int, int], list[ServiceLocation]] = defaultdict(list)
        self.families = set()
        seen: dict[str, ServiceLocation] = {}
        for service in services:
            if service.permanently_closed is True or service.temporarily_closed is True:
                continue
            if service.place_id in seen:
                if service != seen[service.place_id]:
                    raise ValueError("Conflicting duplicate place_id; deduplicate service locations before joining")
                continue
            seen[service.place_id] = service
            self.grid[self._cell(service.latitude, service.longitude)].append(service)
            self.families.add(service.service_family)
        self.family_names = sorted(self.families)
        family_ids = {family: index for index, family in enumerate(self.family_names)}
        self.cells = {}
        for cell, points in self.grid.items():
            coordinates = np.radians([(point.latitude, point.longitude) for point in points])
            self.cells[cell] = (coordinates[:, 0], coordinates[:, 1], np.cos(coordinates[:, 0]),
                                np.array([family_ids[point.service_family] for point in points]))

    @staticmethod
    def _cell(latitude: float, longitude: float) -> tuple[int, int]:
        return math.floor(latitude / .02), math.floor(longitude / .02)

    def counts(self, latitude: float, longitude: float, radius: float) -> dict[str, int]:
        # Conservative bounding box, followed by the exact spherical-distance check.
        lat_delta = radius / 68
        lon_delta = radius / (68 * max(.01, math.cos(math.radians(latitude))))
        low = self._cell(latitude-lat_delta, longitude-lon_delta)
        high = self._cell(latitude+lat_delta, longitude+lon_delta)
        counts = np.zeros(len(self.family_names), dtype=np.int64)
        lat, lon = math.radians(latitude), math.radians(longitude)
        for i in range(low[0], high[0]+1):
            for j in range(low[1], high[1]+1):
                cell = self.cells.get((i, j))
                if cell is None:
                    continue
                lats, lons, cos_lats, families = cell
                h = np.sin((lats-lat)/2)**2 + math.cos(lat)*cos_lats*np.sin((lons-lon)/2)**2
                distances = 3958.7613 * 2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))
                counts += np.bincount(families[distances <= radius], minlength=len(self.family_names))
        return {family: int(counts[index]) for index, family in enumerate(self.family_names)}


def attach_service_access(areas: list[HousingArea], rentals: list[Rental], services: list[ServiceLocation],
                           *, radius_miles: float = 1) -> list[HousingArea]:
    if not 0 < radius_miles <= 10:
        raise ValueError("Service proximity radius must be >0 and <=10 miles")
    index = ServiceIndex(services)
    grouped: dict[tuple[str, str | None], dict[str, Rental]] = defaultdict(dict)
    for rental in rentals:
        grouped[(city_key(rental.city), None)][rental.property_id] = rental
        if rental.zipcode:
            grouped[(city_key(rental.city), rental.zipcode)][rental.property_id] = rental
    result = []
    # Apartment units can share coordinates, and city/ZIP views overlap. Reuse
    # geometry queries while still counting each distinct property in aggregates.
    coordinate_counts = {}
    for area in areas:
        properties = [r for r in grouped[(city_key(area.city), area.zipcode)].values()
                      if r.latitude is not None and r.longitude is not None]
        if len(properties) < 5:
            result.append(area.model_copy(update={"service_access_status": "insufficient_coordinates"}))
            continue
        if not index.families:
            result.append(area.model_copy(update={"service_access_status": "no_candidates"}))
            continue
        counts = []
        for rental in properties:
            coordinate = (rental.latitude, rental.longitude)
            if coordinate not in coordinate_counts:
                coordinate_counts[coordinate] = index.counts(*coordinate, radius_miles)
            counts.append(coordinate_counts[coordinate])
        summaries = [AreaServiceAccess(service_family=family, radius_miles=radius_miles,
            properties_with_coordinates=len(properties),
            median_service_count_within_radius=median(c[family] for c in counts),
            share_of_properties_with_service=sum(c[family] > 0 for c in counts)/len(properties))
            for family in sorted(index.families)]
        result.append(area.model_copy(update={"service_access": summaries, "service_access_status": "available",
            "notes": area.notes + ["Service access describes supplied candidate locations, not verified eligibility, hours, or current capacity."]}))
    return result
