import type { ReentryPlan, ReentrySituation } from "./types";

export function validReentry(value: unknown): value is ReentrySituation {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const entry = value as Record<string, unknown>;
  const choices: Record<string, string[]> = {
    release_status: ["preparing_for_release", "already_released", "unsure", "prefer_not_to_say"],
    has_immediate_housing: ["yes", "no", "unsure", "prefer_not_to_say"], has_id: ["yes", "no", "unsure", "prefer_not_to_say"],
    has_transportation: ["yes", "no", "unsure", "prefer_not_to_say"], has_phone_access: ["yes", "no", "unsure", "prefer_not_to_say"],
    has_required_appointment: ["yes", "no", "unsure", "prefer_not_to_say"],
    priority_need: ["work", "housing", "food", "health_care", "transportation", "community_support"],
    employment_goal: ["find_work", "prepare_for_work", "keep_work", "not_now", "unsure"],
  };
  return Object.entries(entry).every(([key, answer]) => key === "release_date"
    ? answer == null || (typeof answer === "string" && /^\d{4}-\d{2}-\d{2}$/.test(answer)
      && !Number.isNaN(Date.parse(answer)) && new Date(answer).toISOString().slice(0, 10) === answer)
    : Object.hasOwn(choices, key) && (answer == null || choices[key].includes(String(answer))));
}

// Mirror the task graph locally while the server recomputes. Undoing a
// prerequisite reopens its dependents, including their calendar completion.
export function withReentryCompletion(plan: ReentryPlan, previous: string[], id: string, checked: boolean): ReentryPlan {
  const done = new Set(previous);
  const day = plan.daily_actions.find((entry) => entry.action_id === id);
  const affected = day?.task_ids.length ? day.task_ids : [id];
  for (const key of affected) {
    const task = plan.tasks.find((entry) => entry.task_id === key);
    if (checked && (!task || task.prerequisites.every((p) => done.has(p)))) done.add(key);
    else done.delete(key);
  }
  const tasks = plan.tasks.map((task) => {
    const eligible = task.prerequisites.every((key) => done.has(key));
    if (!eligible) done.delete(task.task_id);
    return { ...task, status: done.has(task.task_id) ? "completed" as const : eligible ? "todo" as const : "waiting" as const };
  });
  for (const entry of plan.daily_actions) {
    if (!entry.task_ids.length) continue;
    if (entry.task_ids.every((key) => done.has(key))) done.add(entry.action_id);
    else done.delete(entry.action_id);
  }
  return { ...plan, tasks, completed_ids: [...done], next_task_ids: tasks.filter((task) => task.status === "todo").slice(0, 3).map((task) => task.task_id) };
}
