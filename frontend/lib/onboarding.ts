import type { OnboardingDraft } from "./saved-session";
import type { RecommendationRequest } from "./types";

export const ONBOARDING_VERSION = 3 as const;
export const RETURN_ESSENTIALS = ["has_immediate_housing", "has_id", "has_transportation", "has_phone_access"] as const;
const NEEDS = ["work", "housing", "food", "health_care", "transportation", "community_support"];
const LEVELS = ["no_diploma", "high_school_or_ged", "some_college", "associate", "bachelor", "graduate", "not_sure"];
const STAGES = ["preparing_for_release", "already_released", "unsure", "prefer_not_to_say"];
const ANSWERS = ["yes", "no", "unsure", "prefer_not_to_say"];
const WORK_GOALS = ["find_work", "prepare_for_work", "keep_work", "not_now", "unsure"];

function dateOk(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(value))
    && new Date(value).toISOString().slice(0, 10) === value;
}

// Required answers permit uncertainty. Unknown never becomes "no" or an
// assertion that someone has no experience, credentials, or appointment.
export function onboardingErrors(answers: OnboardingDraft): Record<string, string> {
  const errors: Record<string, string> = {};
  const reentry = answers.reentry ?? {};
  if (!STAGES.includes(reentry.release_status ?? "")) errors["release-status"] = "Choose where you are in your return, Unsure, or Prefer not to answer.";
  if (answers.location.trim().length < 2 || answers.location.trim().length > 80) errors.location = "Enter the city or ZIP where you plan to return.";
  if (!answers.need || !NEEDS.includes(answers.need)) errors.need = "Choose what you need help with first.";
  for (const key of RETURN_ESSENTIALS) {
    if (!ANSWERS.includes(reentry[key] ?? "")) errors[key] = "Choose an answer, Unsure, or Prefer not to answer.";
  }
  if (!ANSWERS.includes(reentry.has_required_appointment ?? "")) errors.has_required_appointment = "Choose an answer, Unsure, or Prefer not to answer.";
  if (reentry.release_date && !dateOk(reentry.release_date)) errors["release-date"] = "Enter a valid date, or leave it blank if you don't know yet.";
  if (!WORK_GOALS.includes(reentry.employment_goal ?? "")) errors["employment-goal"] = "Choose your work goal, or Unsure.";
  if (!answers.noExp && !answers.expUnsure && !answers.skills.length && !answers.expText.trim()) errors.experience = "Choose a skill, describe your experience, or choose one of the answers below.";
  if (!answers.noExp && !answers.expUnsure && answers.years.trim() && (!Number.isFinite(Number(answers.years)) || Number(answers.years) < 0 || Number(answers.years) > 60)) errors.years = "Enter years from 0 to 60, or leave it blank if you don't know.";
  if (!LEVELS.includes(answers.level)) errors.level = "Choose your education level, or Not sure.";
  if (!answers.noCerts && !answers.certsUnsure && !answers.certs.length && !answers.otherCerts.split(",").some((c) => c.trim())) errors.certificates = "Select a certificate, choose None yet, or choose Not sure.";
  if (answers.adaptive) {
    if (!["stable", "temporary", "no_confirmed_housing", "unsure"].includes(answers.housingStatus ?? "")) errors.housing = "Choose a housing answer, or Unsure.";
    if (answers.housingEnd && !dateOk(answers.housingEnd)) errors.housingEnd = "Enter a valid date or leave it blank.";
    if (answers.housingBudget && (!Number.isFinite(Number(answers.housingBudget)) || Number(answers.housingBudget) < 0)) errors.housingBudget = "Enter a monthly amount of zero or more, or leave it blank.";
    for (const key of ["phone", "internet"] as const) if (!["yes", "no", "limited", "unsure", "prefer_not_to_say"].includes(answers[key] ?? "")) errors[key] = "Choose an answer or Unsure.";
    if ((answers.appointments ?? []).some((a) => !a.label.trim() || a.date && !dateOk(a.date))) errors.appointments = "Give each appointment a short label and a valid date, or leave the date blank.";
  }
  return errors;
}

export function hasRequiredReentryAnswers(request: RecommendationRequest): boolean {
  const r = request.reentry;
  return !!r && STAGES.includes(r.release_status ?? "")
    && RETURN_ESSENTIALS.every((key) => ANSWERS.includes(r[key] ?? ""))
    && WORK_GOALS.includes(r.employment_goal ?? "")
    && ANSWERS.includes(r.has_required_appointment ?? "")
    && request.location.trim().length >= 2 && request.location.trim().length <= 80
    && NEEDS.includes(request.priority_need) && LEVELS.includes(request.education.level ?? "")
    && (!r.release_date || dateOk(r.release_date));
}

export function onboardingRequest(answers: OnboardingDraft, initial: RecommendationRequest | null): RecommendationRequest {
  const unknownExperience = answers.noExp || answers.expUnsure;
  const request: RecommendationRequest = {
    age: null,
    location: answers.location.trim(), priority_need: answers.need!,
    experience: {
      skills: unknownExperience ? [] : answers.skills,
      text: unknownExperience || !answers.expText.trim() ? null : answers.expText.trim(),
      years: unknownExperience || !answers.years.trim() ? null : Number(answers.years),
      no_experience_yet: answers.noExp,
    },
    education: {
      level: answers.level,
      credentials: answers.noCerts || answers.certsUnsure ? [] : [...new Set([...answers.certs, ...answers.otherCerts.split(",").map((c) => c.trim()).filter(Boolean)])],
      no_credentials: answers.noCerts,
    },
    service_sort: initial?.service_sort ?? "highly_rated", job_sort: initial?.job_sort ?? "highest_pay",
    reentry: { ...answers.reentry, priority_need: answers.need },
    reentry_completed_ids: initial?.reentry_completed_ids ?? [],
    reentry_start_date: initial?.reentry_start_date ?? null,
  };
  if (initial && request.location.toLowerCase() === initial.location.trim().toLowerCase()) {
    request.selected_job_id = initial.selected_job_id;
    // Keep existing qualification reports when reviewing the same background.
    // Changed education/experience should be assessed from the new answers.
    if (JSON.stringify(request.experience) === JSON.stringify(initial.experience)
      && JSON.stringify(request.education) === JSON.stringify({ ...initial.education, no_credentials: initial.education.no_credentials ?? false })) {
      request.qualification_answers = initial.qualification_answers;
    }
  }
  if (answers.adaptive) {
    const r = answers.reentry!;
    const yesNo = (v: string | null | undefined) => v === "yes" ? true : v === "no" ? false : null;
    const workStatus = { find_work: "unemployed", keep_work: "employed", prepare_for_work: "seeking_training", not_now: "not_seeking", unsure: "unsure" } as const;
    const needs = answers.supportNeeds ?? [];
    const needMap = { employment: "work", healthcare: "health_care", identification: "community_support", education: "work" } as const;
    request.priority_need = needs.length ? (needMap[needs[0] as keyof typeof needMap] ?? needs[0]) as RecommendationRequest["priority_need"] : request.priority_need;
    request.reentry = { ...request.reentry, priority_need: request.priority_need };
    request.profile = {
      profileId: initial?.profile?.profileId ?? crypto.randomUUID(),
      location: { city: /^\d{5}$/.test(request.location) ? "" : request.location, zipCode: /^\d{5}$/.test(request.location) ? request.location : null },
      release: { status: r.release_status === "preparing_for_release" ? "pre_release" : r.release_status === "already_released" ? "post_release" : r.release_status === "prefer_not_to_say" ? "prefer_not_to_answer" : "unsure", date: r.release_date ?? null },
      housing: { status: answers.housingStatus!, temporaryHousingEndDate: answers.housingStatus === "temporary" ? answers.housingEnd || null : null, monthlyBudget: answers.housingBudget ? Number(answers.housingBudget) : null },
      employment: { status: workStatus[r.employment_goal ?? "unsure"], preferredJobTypes: answers.preferredJobs ?? [],
        experienceYears: request.experience.years, skills: request.experience.skills, experienceText: request.experience.text,
        noExperienceYet: request.experience.no_experience_yet, educationLevel: request.education.level,
        certifications: request.education.credentials, noCertifications: !!request.education.no_credentials },
      barriers: { hasGovernmentId: yesNo(r.has_id), hasTransportation: yesNo(r.has_transportation),
        hasFoodAccess: yesNo(answers.food),
        hasPhoneAccess: yesNo(answers.phone), hasInternetAccess: yesNo(answers.internet),
        communicationAccess: answers.phone === "limited" || answers.internet === "limited" ? "limited" : answers.phone === "yes" || answers.internet === "yes" ? "reliable" : answers.phone === "no" && answers.internet === "no" ? "none" : "unsure" },
      supportNeeds: needs, upcomingAppointments: answers.appointments ?? [], goals: (answers.goals ?? "").split("\n").map((v) => v.trim()).filter(Boolean),
      appointmentStatus: r.has_required_appointment === "prefer_not_to_say" ? "prefer_not_to_answer" : r.has_required_appointment ?? "unsure",
      ...(initial?.profile?.finances ? { finances: structuredClone(initial.profile.finances) } : {}),
    };
    if (initial?.phoenix_session) request.phoenix_session = initial.phoenix_session;
  }
  return request;
}

// Accept server-derived state only after a confirmed action. Event payloads are
// removed so refreshes cannot accidentally replay an update.
export function adoptSession(request: RecommendationRequest, response: import("./types").RecommendationResponse): RecommendationRequest {
  const state = response.phoenix_session;
  if (!state) return request;
  const p = state.profile;
  const yesNo = (v: boolean | null) => v === true ? "yes" : v === false ? "no" : "unsure";
  const goal = { unemployed: "find_work", employed: "keep_work", seeking_training: "prepare_for_work", not_seeking: "not_now", unsure: "unsure" } as const;
  return { ...request, user_event: undefined, phoenix_session: state, profile: p,
    selected_job_id: response.selected_job_id ?? null,
    location: p.location.zipCode || p.location.city,
    experience: { skills: p.employment.skills, text: p.employment.experienceText, years: p.employment.experienceYears, no_experience_yet: p.employment.noExperienceYet },
    education: { level: p.employment.educationLevel, credentials: p.employment.certifications, no_credentials: p.employment.noCertifications },
    reentry: { ...request.reentry,
      release_status: p.release.status === "pre_release" ? "preparing_for_release" : p.release.status === "post_release" ? "already_released" : p.release.status === "prefer_not_to_answer" ? "prefer_not_to_say" : "unsure",
      release_date: p.release.date, employment_goal: goal[p.employment.status],
      has_immediate_housing: p.housing.status === "stable" || p.housing.status === "temporary" ? "yes" : p.housing.status === "no_confirmed_housing" ? "no" : "unsure",
      has_id: yesNo(p.barriers.hasGovernmentId), has_transportation: yesNo(p.barriers.hasTransportation),
      has_phone_access: p.barriers.hasPhoneAccess === true || p.barriers.hasInternetAccess === true ? "yes" : p.barriers.hasPhoneAccess === false && p.barriers.hasInternetAccess === false ? "no" : "unsure",
      has_required_appointment: p.upcomingAppointments.length ? "yes" : p.appointmentStatus === "prefer_not_to_answer" ? "prefer_not_to_say" : p.appointmentStatus,
    },
  };
}
