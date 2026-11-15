import type { PhoenixSession, ReentryProfile, UserEvent } from "./domain";

export type QuickChange = "stable_housing" | "temporary_housing" | "lost_housing" | "housing_ending" | "started_work" | "lost_work" | "transport_gained" | "transport_lost" | "id_obtained" | "task_completed" | "provider_unavailable" | "application_rejected" | "appointment";
export interface QuickValues { resourceId: string; taskId: string; endDate: string; appointmentId: string; appointmentLabel: string; appointmentDate: string; appointmentLocation: string }
export function quickProposal(kind: QuickChange, values: QuickValues, session: PhoenixSession): { profile: ReentryProfile; event?: Pick<UserEvent, "type" | "payload"> } {
  const profile = structuredClone(session.profile);
  if (kind === "stable_housing" || kind === "lost_housing") {
    profile.housing.status = kind === "stable_housing" ? "stable" : "no_confirmed_housing";
    profile.housing.temporaryHousingEndDate = null;
  } else if (kind === "temporary_housing" || kind === "housing_ending") {
    if (kind === "housing_ending" && !values.endDate) throw new Error("Enter the housing end date, or use the full form if it is unknown.");
    profile.housing.status = "temporary";
    profile.housing.temporaryHousingEndDate = values.endDate || null;
  } else if (kind === "started_work" || kind === "lost_work") profile.employment.status = kind === "started_work" ? "employed" : "unemployed";
  else if (kind === "transport_gained" || kind === "transport_lost") profile.barriers.hasTransportation = kind === "transport_gained";
  else if (kind === "id_obtained") profile.barriers.hasGovernmentId = true;
  else if (kind === "appointment") {
    if (!values.appointmentLabel.trim()) throw new Error("Enter a short appointment label. No private case details are needed.");
    profile.appointmentStatus = "yes";
    profile.upcomingAppointments.push({ id: values.appointmentId, label: values.appointmentLabel.trim(), date: values.appointmentDate || null, location: values.appointmentLocation.trim() || null });
  } else if (kind === "task_completed") {
    const task = session.tasks.find(t => t.id === values.taskId && !t.archived && t.status !== "completed");
    if (!task || !task.prerequisiteTaskIds.every(id => session.tasks.find(t => t.id === id)?.status === "completed")) throw new Error("Choose a step whose prerequisites are complete.");
    return { profile, event: { type: "task_status", payload: { taskId: task.id, status: "completed" } } };
  } else {
    const resource = session.recommendations.find(r => r.id === values.resourceId);
    if (!resource || (kind === "provider_unavailable" ? resource.mode !== "temporary_housing" : resource.mode !== "job")) throw new Error("Choose a relevant opportunity from your plan.");
    return { profile, event: kind === "provider_unavailable" ? { type: "resource_unavailable", payload: { recommendationId: resource.id } } : { type: "resource_status", payload: { recommendationId: resource.id, status: "rejected" } } };
  }
  return { profile };
}
