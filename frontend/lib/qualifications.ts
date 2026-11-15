import type { JobCard, JobsSection } from "./types";

export function qualificationProgress(job: JobCard) {
  const checks = job.qualification_checks ?? [];
  const required = checks.filter((check) => check.requirement_kind === "required");
  return { total: checks.length, reported: checks.filter((check) => check.status === "reported_met").length,
    required: required.length, requiredMet: required.filter((check) => check.status === "reported_met").length };
}

export function matchLabel(job: JobCard): string {
  const checks = job.qualification_checks ?? [];
  const mandatory = checks.filter((check) => check.requirement_kind === "required");
  if (mandatory.length > 0 && mandatory.every((check) => check.status === "reported_met")) return "Clear match";
  const experience = checks.some((check) => check.field === "experience_years" && check.status === "reported_met");
  const related = job.matches_reported_role ?? (job.matches.length ? true : null);
  if ((related === true || experience) && mandatory.length > 0
      && mandatory.every((check) => check.status !== "reported_met")
      && mandatory.some((check) => check.status === "gap")) return "Needs preparation";
  return related === true || experience ? "Related experience" : related === false ? "Different work area" : "Not assessed";
}

export function withQualificationAnswer(section: JobsSection, jobId: string, key: string, checked: boolean): JobsSection {
  const update = (groups: JobsSection["groups"]) => groups.map((group) => ({ ...group,
    items: group.items.map((job) => job.job_id !== jobId ? job : { ...job,
      qualification_checks: job.qualification_checks?.map((check) => check.key !== key ? check : { ...check,
        status: checked ? "reported_met" as const : check.requirement_kind === "preferred" ? "preferred" as const : "gap" as const,
      }),
    }),
  }));
  return { ...section, groups: update(section.groups), other_groups: update(section.other_groups ?? []) };
}
