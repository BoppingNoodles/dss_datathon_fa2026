"use client";

import ResourceActions, { useResources } from "./ResourceActions";
import type { Recommendation } from "@/lib/domain";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { resourceLabel } from "@/lib/plan-view";

export default function ResourceCandidates({ mode, excludeIds = [] }: { mode: Recommendation["mode"]; excludeIds?: string[] }) {
  const { session } = useResources();
  if (!session) return null;
  const candidates = session.recommendations.filter(resource => resource.mode === mode && resource.active && !excludeIds.includes(resource.id)
    && !["dismissed", "rejected"].includes(resource.userStatus) && resource.userReportedAvailability !== "unavailable");
  if (!candidates.length && (mode === "service" || session.profile.housing.status === "stable" && !session.profile.supportNeeds.includes("housing"))) return null;
  return <section aria-label={mode === "temporary_housing" ? "Immediate housing assistance" : "Support for your reported needs"} className="space-y-3">
    <h3 className="text-lg font-semibold">{mode === "temporary_housing" ? "Housing support" : "Recommended support"}</h3>
    {!candidates.length ? <p className="rounded-lg border p-4 text-sm text-muted-foreground">No matching housing support in this area. Ask a local community organization for a referral.</p> : <ul className="grid gap-4 md:grid-cols-2">{candidates.map(resource => {
      const contact = resource.details.contact as Record<string, unknown> | undefined;
      const phone = typeof contact?.phone === "string" ? contact.phone : typeof resource.details.phone === "string" ? resource.details.phone : null;
      return <li key={resource.id}><Card className="h-full gap-3">
        <CardHeader><CardTitle><h4 className="text-lg">{resource.title}</h4></CardTitle><p className="text-xs text-brand-text">{resourceLabel(resource)}</p><p className="text-xs text-muted-foreground">{resource.verificationStatus === "unverified" ? "Service details unverified" : "Confirm availability"}</p></CardHeader>
        <CardContent className="space-y-3">
          {Object.values(resource.location).some(Boolean) && <p className="text-xs text-muted-foreground">{Object.values(resource.location).filter(Boolean).join(", ")}</p>}
          <details className="text-sm"><summary className="cursor-pointer text-brand-text">Details</summary><div className="mt-2 space-y-2"><p>{resource.description}</p>{resource.matchReasons[0] && <p className="text-muted-foreground">{resource.matchReasons[0]}</p>}{resource.uncertainties.map(note => <p key={note} className="text-xs text-muted-foreground">{note}</p>)}</div></details>
          <div className="flex flex-wrap gap-2">
            {phone && <Button asChild variant="outline"><a href={"tel:" + phone.replace(/[^\d+]/g, "")}>Call</a></Button>}
            {resource.sourceUrl && /^https?:\/\//i.test(resource.sourceUrl) && <Button asChild variant="outline"><a href={resource.sourceUrl} target="_blank" rel="noopener noreferrer">Website</a></Button>}
          </div>
        </CardContent>
        <CardFooter className="mt-auto"><ResourceActions id={resource.id} /></CardFooter>
      </Card></li>;
    })}</ul>}
  </section>;
}
