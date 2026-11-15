// Mirrors backend/app/schemas.py. Keep in sync with docs/api_contract.md.

export type Need = "work" | "housing" | "food" | "health_care" | "transportation" | "community_support";
export type Tab = "jobs" | "housing" | "services" | "plan";
export type ServiceSort = "highly_rated" | "nearest";
export type JobSort = "highest_pay" | "nearest";

export interface RecommendationRequest {
  age: number | null;
  location: string;
  priority_need: Need;
  experience: { skills: string[]; text: string | null; years: number | null; no_experience_yet: boolean };
  education: { level: string | null; credentials: string[]; no_credentials?: boolean };
  qualification_answers?: Record<string, Record<string, boolean>>;
  service_sort: ServiceSort;
  job_sort: JobSort;
  selected_job_id?: string | null;
}

export interface ServiceCard {
  place_id: string;
  name: string;
  family_label: string;
  group: string;
  verification: {
    status: string;
    provider_type: string | null;
    official_url: string | null;
    checked_on: string | null;
    cost_eligibility_notes: string | null;
    service_area: string | null;
  };
  eligibility: { age_status: string; note: string };
  rating: {
    overall_rating: number | null;
    overall_review_count: number | null;
    overall_star_distribution: Record<string, number> | null;
  };
  review_evidence: {
    sampled_review_count: number;
    date_min: string | null;
    date_max: string | null;
    star_distribution: Record<string, number>;
    snippets: { text: string; topic: string | null; attribution: string }[];
    note: string;
  };
  distance: { miles: number | null; reference_point: string | null; measure: string | null };
  availability: { temporarily_closed: boolean | null; hours_text: string; note: string };
  contact: {
    address: string | null;
    phone: string | null;
    website: string | null;
    maps_url: string | null;
  };
  confirm_prompt: string;
}

export interface ServiceGroup {
  key: string;
  label: string;
  note: string | null;
  total: number;
  items: ServiceCard[];
}

export interface ServicesSection {
  status: "ok" | "no_results";
  need_label: string;
  sort: ServiceSort;
  search_area: string;
  ranking_settings: { highly_rated_min_rating: number; highly_rated_min_reviews: number };
  groups: ServiceGroup[];
  notes: string[];
}

export interface Pay {
  needs_confirmation?: boolean;
  currency?: string | null;
  min: number | null;
  max: number | null;
  period: "hour" | "day" | "week" | "month" | "year" | null;
  raw_text: string | null;
  hours_per_week: number | null;
  hours_basis: string;
  conversion_note: string | null;
}

export interface JobCard {
  job_id: string;
  title: string;
  description?: string | null;
  employer: string | null;
  posted_date: string | null;
  url: string | null;
  suitability_tier: "strong_match" | "possible_match" | "known_gaps";
  requirements: { label: string; status: string; evidence: string | null; source?: string | null }[];
  matches: string[];
  gaps: string[];
  unknowns: string[];
  pay: Pay;
  location: { text: string | null; city: string | null; precision: string; distance_miles: number | null; reference_point: string | null };
  rank_explanation: string;
  source?: { dataset?: string };
  selectable?: boolean;
  is_selected?: boolean;
  credential_summary?: string | null;
  matches_reported_role?: boolean | null;
  qualification_checks?: {
    key: string;
    field: "education" | "experience_years" | "certification";
    requirement_kind: "required" | "preferred" | "alternative" | "uncertain";
    label: string;
    status: "reported_met" | "gap" | "needs_confirmation" | "preferred";
    detail: string;
  }[];
}


export type PayComparisonJob = Pick<JobCard, "job_id" | "title" | "pay">;

export interface PlanLink {
  label: string;
  url: string;
  role: "job_posting" | "official_requirements" | "provider_finder" | "funding_support";
}

export interface InterimJob {
  job_id: string;
  title: string;
  company: string;
  pay: {
    minimum: number | null;
    maximum: number | null;
    period: Pay["period"] | "unknown";
    raw: string | null;
    notes: string[];
  };
  credential_summary: string;
  confirmation_needed: string[];
  source_url: string | null;
  is_selected: boolean;
}

export interface ThirtyDayPlan {
  target_job_id: string;
  target_job_title: string;
  selected_interim_job_id: string | null;
  credential_paths: {
    credential: string;
    requirement_kind: "required" | "preferred" | "alternative" | "uncertain";
    user_status: "reported_held" | "not_confirmed";
    job_evidence: string;
    evidence_source: string;
    completion_within_30_days: "not_guaranteed";
    links: PlanLink[];
  }[];
  interim_jobs: InterimJob[];
  steps: {
    step_id: string;
    day_start: number;
    day_end: number;
    title: string;
    action: string;
    track: "job_confirmation" | "credential" | "interim_work" | "application" | "experience";
    depends_on: string[];
    links: PlanLink[];
  }[];
  daily_actions?: {
    action_id: string;
    day: number;
    title: string;
    action: string;
    phase: string;
    links: PlanLink[];
  }[];
  notes: string[];
}

export interface JobsSection {
  status: "ok" | "no_results" | "not_integrated";
  sort: JobSort;
  groups: { key: string; label: string; total: number; items: JobCard[] }[];
  other_groups?: { key: string; label: string; total: number; items: JobCard[] }[];
  notes: string[];
}

export interface NearbyPlace {
  place_id: string;
  name: string;
  family_label: string;
  maps_url: string | null;
}

export interface ServiceMapPoint {
  place_id: string;
  lat: number;
  lon: number;
}

export type MappedPlace = NearbyPlace & ServiceMapPoint & { number: number };

export interface HousingArea {
  area_id: string;
  area_type: "zip" | "city";
  label: string;
  usable_rental_records: number;
  suppressed: boolean;
  median_monthly_rent: number | null;
  rent_p25: number | null;
  rent_p75: number | null;
  rent_basis: "listed_rent" | "rent_estimate";
  bedrooms: Record<string, number>;
  nearby_services: { family: string; family_label: string; count_within_1_mile: number | null; nearest_miles: number | null }[];
  nearby_places?: NearbyPlace[];
  source_note: string | null;
}

export interface HousingSection {
  status: "ok" | "no_results" | "not_integrated";
  areas: HousingArea[];
  notes: string[];
}

export interface RecommendationResponse {
  open_tab: Tab;
  jobs: JobsSection;
  housing_areas: HousingSection;
  service_map_points?: ServiceMapPoint[];
  services: ServicesSection;
  data_coverage: { mode: "real" | "synthetic"; notes: string[] };
  next_steps: { id: string; text: string; tab: Tab }[];
  disclaimer: string;
  selected_job_id: string | null;
  thirty_day_plan: ThirtyDayPlan | null;
}

export interface HousingComparisonRequest {
  pay_min: number | null;
  pay_max: number | null;
  pay_period: Pay["period"];
  hours_per_week: number | null;
  monthly_rent: number | null;
}

export interface HousingComparisonResponse {
  annual_gross_min: number | null;
  annual_gross_max: number | null;
  rent_burden_min: number | null;
  rent_burden_max: number | null;
  status: "ok" | "unknown";
  assumptions: string[];
  caveat: string;
}
