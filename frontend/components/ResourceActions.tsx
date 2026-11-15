"use client";

import { createContext, useContext } from "react";
import type { PhoenixSession, ResourceStatus, UserEvent } from "@/lib/domain";
import { userEvent } from "@/lib/domain";
import { Button } from "@/components/ui/button";

export const ResourceContext = createContext<{ session: PhoenixSession | null; disabled: boolean; onEvent: (event: UserEvent) => void }>({ session: null, disabled: true, onEvent: () => {} });
export const useResources = () => useContext(ResourceContext);

export default function ResourceActions({ id }: { id: string }) {
  const { session, disabled, onEvent } = useResources();
  const resource = session?.recommendations.find((r) => r.id === id);
  if (!resource) return null;
  const update = (status: ResourceStatus) => onEvent(userEvent("resource_status", { recommendationId: id, status }));
  const value = session!.selectedRecommendationIds.includes(id) ? "selected" : resource.userStatus === "saved" ? "saved" : resource.userStatus === "dismissed" || resource.userStatus === "rejected" ? "dismissed" : null;
  const options: [ResourceStatus, string][] = [["selected", "Selected for Plan"], ["saved", "Interested"], ["dismissed", "Not Interested"]];
  return <div data-resource-id={id} role="group" aria-label={`Plan choice for ${resource.title}`} className="flex flex-wrap gap-2">
    {options.map(([status, label]) => <Button key={status} type="button" size="sm" variant={value === status ? "default" : "outline"} aria-pressed={value === status} disabled={disabled} onClick={() => { if (value !== status) update(status); }}>{label}</Button>)}
  </div>;
}
