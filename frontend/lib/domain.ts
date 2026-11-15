// Source evidence, predictions, user reports, and progress remain separate.
export type SupportNeed = "housing" | "employment" | "food" | "healthcare" | "transportation" | "identification" | "education" | "community_support";
export type FinanceField = "monthlyTakeHomePay" | "monthlyHousingCost" | "monthlyFoodCost" | "monthlyOtherCosts";
export interface FinanceProjection {
  jobId: string | null; housingId: string | null; hoursPerWeek: number; takeHomePercent: number;
  estimatedFields: FinanceField[];
}
export interface Finances {
  monthlyTakeHomePay: number | null; monthlyHousingCost: number | null; monthlyFoodCost: number | null; monthlyOtherCosts: number | null;
  projection?: FinanceProjection | null;
}
export interface ReentryProfile {
  profileId: string;
  location: { city: string; zipCode: string | null };
  release: { status: "pre_release" | "post_release" | "unsure" | "prefer_not_to_answer"; date: string | null };
  housing: { status: "stable" | "temporary" | "no_confirmed_housing" | "unsure"; temporaryHousingEndDate: string | null; monthlyBudget: number | null };
  employment: { status: "unemployed" | "employed" | "seeking_training" | "not_seeking" | "unsure";
    preferredJobTypes: string[]; experienceYears: number | null; skills: string[]; experienceText: string | null;
    noExperienceYet: boolean; educationLevel: string | null; certifications: string[]; noCertifications: boolean };
  barriers: { hasFoodAccess?: boolean | null; hasGovernmentId: boolean | null; hasTransportation: boolean | null; hasPhoneAccess: boolean | null; hasInternetAccess: boolean | null;
    communicationAccess: "reliable" | "limited" | "none" | "unsure" };
  supportNeeds: SupportNeed[];
  upcomingAppointments: { id: string; label: string; date: string | null; location: string | null }[];
  appointmentStatus: "yes" | "no" | "unsure" | "prefer_not_to_answer";
  goals: string[];
  finances?: Finances;
}
export type ResourceStatus = "recommended" | "saved" | "selected" | "contacted" | "applied" | "accepted" | "rejected" | "dismissed";
export type TaskStatus = "not_started" | "in_progress" | "blocked" | "completed" | "skipped";
export type ResourceType = "job_posting" | "transitional_housing" | "housing_assistance" | "rental_market" | "transportation_assistance" | "public_transit" | "identification_assistance" | "workforce_training" | "food_assistance" | "healthcare" | "community_support";
export interface Recommendation {
  id: string; category: "job" | "housing" | "service"; title: string; description: string;
  source: string; sourceUrl: string | null; location: Record<string, string>; score: number;
  matchReasons: string[]; uncertainties: string[];
  verificationStatus: "verified" | "partially_verified" | "unverified";
  availabilityStatus: "confirmed_available" | "confirmed_unavailable" | "unknown";
  userStatus: ResourceStatus; userReportedAvailability: "available" | "unavailable" | null;
  mode: "job" | "temporary_housing" | "long_term_area" | "service"; active: boolean;
  details: Record<string, unknown>;
  resourceType?: ResourceType;
  supportedResourceTypes?: ResourceType[];
  serviceEvidence?: Record<string, string>;
}
export interface PlanTask {
  id: string; title: string; description: string;
  category: "housing" | "employment" | "documents" | "transportation" | "healthcare" | "community_support" | "other";
  priority: "critical" | "high" | "medium" | "low"; status: TaskStatus;
  prerequisiteTaskIds: string[]; relatedRecommendationIds: string[]; rationale: string;
  deadline: string | null; estimatedDurationDays: number | null; source: "profile" | "recommendation" | "user" | "planner";
  userEditable: boolean; notes: string; stage: "immediate_stability" | "removing_barriers" | "building_independence";
  archived: boolean; blockedByUser: boolean;
  allowedResourceTypes?: ResourceType[];
  resourceMatchReasons?: Record<string, string>;
  referenceLinks?: { label: string; url: string }[];
  resourceEmptyState?: string | null;
  completionOutcome?: "housing_arranged" | "food_secured" | "transportation_arranged" | null;
}
export interface UserEvent {
  id: string; timestamp: string;
  type: "profile_updated" | "resource_status" | "resource_unavailable" | "task_status" | "job_obtained" | "job_lost" | "housing_changed" | "transportation_changed";
  payload: Record<string, unknown>;
}
export interface PhoenixSession {
  schemaVersion: 1; profile: ReentryProfile; recommendations: Recommendation[]; tasks: PlanTask[];
  selectedRecommendationIds: string[]; dismissedRecommendationIds: string[]; events: UserEvent[];
  lastPlannedAt: string | null; changes: { type: string; task_id: string | null; reason: string }[];
  scheduleStartDate: string | null;
  warnings: string[]; topJobIds: string[];
  schedule: { action_id: string; day: number; title: string; action: string; phase: string; links: import("./types").PlanLink[]; task_ids: string[] }[];
}
export const userEvent = (type: UserEvent["type"], payload: UserEvent["payload"]): UserEvent =>
  ({ id: crypto.randomUUID(), timestamp: new Date().toISOString(), type, payload });

export function profileDifferences(before: ReentryProfile, after: ReentryProfile): string[] {
  const groups = ["location", "release", "housing", "employment", "barriers", "supportNeeds", "upcomingAppointments", "goals", "finances"] as const;
  const labels = ["Location", "Release stage or date", "Housing", "Employment and qualifications", "ID, transportation or communication", "Support needs", "Appointments", "30-day goals", "Financial budget and assumptions"];
  return groups.flatMap((group, i) => JSON.stringify(before[group]) === JSON.stringify(after[group]) ? [] : [labels[i]]);
}

export function extractSituation(text: string, profile: ReentryProfile): { profile: ReentryProfile; understood: string[]; needsReview: boolean; requiresDateConfirmation?: boolean } {
  // Conservative deterministic extraction. No dates, providers, or legal rules
  // are inferred; users confirm the interpreted fields before recalculation.
  const result = structuredClone(profile);
  const understood: string[] = [];
  text = text.replace(/[‘’]/g, "'");
  if (/\b(?:if|might|maybe|could|would|haven't|hadn't|never|not sure|last year|used to|my friend|my partner|someone)\b/i.test(text)) return { profile: result, understood, needsReview: true };
  const accessWords = "(?:(?:food|groceries|meals|transport|transportation|housing|reliable|temporary|stable|permanent|a|an|place|to|stay|job|car|bus|pass|ride|and)\\b[\\s,]*){0,14}";
  const access = (target: string) => new RegExp(`\\b(?:I|we)\\s+(?:now\\s+)?(?:have|got|found|secured)\\s+${accessWords}(?:${target})\\b(?=$|[,.;!?]|\\s+(?:and|but|now|today|at|for|until)\\b)`, "i");
  const tests: [RegExp, () => void, string][] = [
    [/\bI\s+(?:just\s+)?(?:got|found|started|have)\s+(?:(?:a|my|new)\s+)?(?:[a-z'-]+\s+){0,3}job\b(?!\s+(?:offer|interview|application|lead)\b)|\bI (?:just )?started working\b/i, () => { result.employment.status = "employed"; }, "Employment → employed"],
    [/\b(?:lost my job|lost a job|no longer employed|unemployed)\b/i, () => { result.employment.status = "unemployed"; }, "Employment → unemployed"],
    [/\b(?:no transportation|lost (?:my )?transportation|do not have transportation|don't have transportation)\b/i, () => { result.barriers.hasTransportation = false; }, "Transportation → no reliable access"],
    [/\b(?:now have transportation|got transportation|have reliable transportation)\b/i, () => { result.barriers.hasTransportation = true; }, "Transportation → reliable access"],
    [access("transport(?:ation)?|car|bus pass|ride"), () => { result.barriers.hasTransportation = true; }, "Transportation → reliable access"],
    [access("food|groceries|meals"), () => { result.barriers.hasFoodAccess = true; }, "Food → available"],
    [/\b(?:no food|don't have food|do not have food|ran out of food)\b/i, () => { result.barriers.hasFoodAccess = false; }, "Food → assistance needed"],
    [/\b(?:no place to stay|now homeless|lost my housing)\b/i, () => { result.housing.status = "no_confirmed_housing"; result.housing.temporaryHousingEndDate = null; }, "Housing → no confirmed place"],
    [/\b(?:now have stable housing|found stable housing)\b/i, () => { result.housing.status = "stable"; result.housing.temporaryHousingEndDate = null; }, "Housing → stable"],
    [access("housing|place to stay"), () => { if (result.housing.status !== "stable") { result.housing.status = "temporary"; result.housing.temporaryHousingEndDate = null; } }, "Housing → arranged; long-term stability not reported"],
    [/\btemporary\s+(?:housing|accommodation|place)\s+(?:ends?|is ending|runs out)\b/i, () => { result.housing.status = "temporary"; result.housing.temporaryHousingEndDate = null; }, "Housing → temporary; end date needs your confirmation"],
  ];
  const matched = tests.filter(([pattern, , label]) => pattern.test(text)
    && (!label.includes("arranged;") || !/\b(?:stable|permanent) housing\b/i.test(text))
    && (!(label.includes("reliable access") || label === "Food → available" || label.includes("arranged;")) || !/\b(?:no|not|don't|do not|without|lost|looking)\b/i.test(text.split(/\bbut\b/i).find(clause => pattern.test(clause)) ?? text))
    && (label !== "Employment → employed"
    || text.split(/[.!?;,]|\bbut\b/i).some(clause => pattern.test(clause)
      && !/\b(?:offer|offered|interview|call|letter|application|applied|invitation|lead)\b/i.test(clause)))).filter((entry, index, all) => all.findIndex(other => other[2] === entry[2]) === index);
  // Conflicting descriptions require the structured form, never last-rule wins.
  if (matched.some(([, , label]) => label.startsWith("Employment")) && matched.filter(([, , label]) => label.startsWith("Employment")).length > 1
    || matched.filter(([, , label]) => label.startsWith("Transportation")).length > 1
    || matched.filter(([, , label]) => label.startsWith("Housing")).length > 1
    || matched.filter(([, , label]) => label.startsWith("Food")).length > 1) return { profile: structuredClone(profile), understood: [], needsReview: true };
  for (const [, apply, label] of matched) { apply(); understood.push(label); }
  return { profile: result, understood, needsReview: true, requiresDateConfirmation: understood.some(label => label.includes("end date needs")) };
}
