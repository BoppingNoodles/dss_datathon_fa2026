"use client";

import { useEffect, useRef, useState } from "react";
import type { FeatureCollection, MultiPolygon, Polygon } from "geojson";
import type { FeatureGroup, LatLngBounds, Map as LeafletMap } from "leaflet";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { MappedPlace } from "@/lib/types";

type MapData = FeatureCollection<Polygon | MultiPolygon, { zip: string; lat: number; lon: number }>;
type MapInstance = { L: typeof import("leaflet"); map: LeafletMap; overlays: FeatureGroup };
let boundaryRequest: Promise<MapData> | undefined;

export default function AreaMap({ zip, label, places }: { zip: string | null; label: string; places: MappedPlace[] }) {
  const container = useRef<HTMLDivElement>(null);
  const instance = useRef<MapInstance | null>(null);
  const areaBounds = useRef<LatLngBounds | null>(null);
  const [data, setData] = useState<MapData | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [boundaryFailed, setBoundaryFailed] = useState(false);
  const [tileFailed, setTileFailed] = useState(false);
  const [zoom, setZoom] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    boundaryRequest ??= fetch("/maps/east-bay-zips.geojson").then((response) => {
      if (!response.ok) throw new Error("Map boundary unavailable");
      return response.json() as Promise<MapData>;
    }).catch((error) => { boundaryRequest = undefined; throw error; });
    boundaryRequest.then((result) => { if (!cancelled) setData(result); })
      .catch(() => { if (!cancelled) setBoundaryFailed(true); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let map: LeafletMap | undefined;
    let resize: ResizeObserver | undefined;
    import("leaflet").then((L) => {
      if (cancelled || !container.current) return;
      map = L.map(container.current, {
        scrollWheelZoom: false, zoomControl: true, minZoom: 9, maxZoom: 19,
        dragging: true, touchZoom: true, keyboard: true,
      }).setView([37.8, -122.27], 12);
      map.attributionControl.setPrefix(false);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors',
      }).on("tileerror", () => { if (!cancelled) setTileFailed(true); })
        .on("tileload", () => { if (!cancelled) setTileFailed(false); }).addTo(map);
      L.control.scale({ imperial: true, metric: false, maxWidth: 90 }).addTo(map);
      const overlays = L.featureGroup().addTo(map);
      instance.current = { L, map, overlays };
      map.on("zoomend", () => { if (!cancelled && map) setZoom(map.getZoom()); });
      // Clicking the map enables wheel zoom; scrolling the page past it stays easy.
      map.on("focus", () => map?.scrollWheelZoom.enable());
      map.on("blur", () => map?.scrollWheelZoom.disable());
      resize = new ResizeObserver(() => map?.invalidateSize({ pan: false }));
      resize.observe(container.current);
      setZoom(map.getZoom());
      setReady(true);
    }).catch(() => { if (!cancelled) setFailed(true); });
    return () => {
      cancelled = true;
      resize?.disconnect();
      map?.remove();
      instance.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready || !instance.current) return;
    const { L, map, overlays } = instance.current;
    overlays.clearLayers();
    const feature = data?.features.find((item) => item.properties.zip === zip);
    if (feature) {
      L.geoJSON(feature, { style: { color: "var(--primary)", weight: 2.5, fillColor: "var(--primary)", fillOpacity: .1 } })
        .bindTooltip(`ZIP ${zip}`, { sticky: true }).addTo(overlays);
    }
    places.forEach((place) => {
      const icon = L.divIcon({
        className: "phoenix-place-marker",
        html: `<span class="phoenix-pin-shape"><b>${place.number}</b></span>`,
        iconSize: [32, 32], iconAnchor: [16, 38], popupAnchor: [0, -32],
      });
      const content = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = place.name;
      const category = document.createElement("p");
      category.textContent = place.family_label.split(" (")[0];
      content.append(name, category);
      if (place.maps_url && /^https?:\/\//i.test(place.maps_url)) {
        const link = document.createElement("a");
        link.href = place.maps_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "Get directions ↗";
        content.append(link);
      }
      const marker = L.marker([place.lat, place.lon], { icon, title: place.name, keyboard: true, riseOnHover: true })
        .bindPopup(content, { maxWidth: 240 }).addTo(overlays);
      marker.getElement()?.setAttribute("aria-label", `Place ${place.number}: ${place.name}`);
    });
    const bounds = overlays.getBounds();
    areaBounds.current = bounds.isValid() ? bounds : null;
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [25, 25], maxZoom: 14, animate: false });
  }, [data, places, ready, zip]);

  const hasBoundary = data?.features.some((feature) => feature.properties.zip === zip);
  return (
    <Card id="housing-map" className="gap-3 scroll-mt-4">
      <CardHeader>
        <p className="text-xs font-medium text-brand-text">Explore the area</p>
        <div className="flex items-center justify-between gap-3">
          <CardTitle><h3 className="text-lg font-semibold">{label}</h3></CardTitle>
          <Button type="button" size="sm" variant="outline" disabled={!ready || (!hasBoundary && !places.length)} onClick={() => {
            if (areaBounds.current) instance.current?.map.fitBounds(areaBounds.current, { padding: [25, 25], maxZoom: 14 });
          }}>Fit area</Button>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {/* Size the wrapper without replacing Leaflet's runtime container classes. */}
        <div className="phoenix-map relative isolate h-80 overflow-hidden rounded-lg border border-border sm:h-96 lg:h-[clamp(26rem,60vh,40rem)]">
          <div ref={container} role="region" aria-label={`Interactive map of ${label}`} className="leaflet-container h-full w-full bg-muted" />
          {!ready && <p className="absolute inset-0 flex items-center justify-center bg-muted px-6 text-center text-sm text-muted-foreground" role="status">
            {failed ? "The interactive map couldn't load. Use the place links for directions." : "Loading map…"}
          </p>}
        </div>
        <p className="sr-only" aria-live="polite">{zoom != null ? `Map zoom level ${zoom}` : "Loading map"}</p>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground">
          {hasBoundary && <span className="flex items-center gap-2"><span className="size-2.5 rounded-sm border border-primary bg-accent" aria-hidden="true" />ZIP {zip}</span>}
          <span>{places.length} nearby place{places.length === 1 ? "" : "s"} pinned</span>
        </div>
        {tileFailed && <p role="status" className="text-xs text-muted-foreground">Street tiles couldn&apos;t load. The ZIP boundary and place pins are still shown.</p>}
        {(boundaryFailed || (data && !hasBoundary)) && <p className="text-xs text-muted-foreground">A ZIP-area boundary is unavailable for this location.</p>}
        <p className="text-xs text-muted-foreground">Drag to explore. Use + / − or pinch to zoom. Select a pin for details.</p>
        <p className="text-xs text-muted-foreground">
          <a href="https://www.census.gov/programs-surveys/geography/guidance/geo-areas/zctas.html" target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">Census ZIP-area approximation</a>. Places may be outside the ZIP.
        </p>
      </CardContent>
    </Card>
  );
}
