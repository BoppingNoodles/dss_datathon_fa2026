import type { SupportNeed } from "./domain";

export const SUPPORT_OPTIONS: [SupportNeed, string, string][] = [
  ["housing", "Housing", "A place to stay or housing referrals"],
  ["employment", "Work", "Applications, a resume or a job search"],
  ["food", "Food", "Groceries or meals"],
  ["healthcare", "Health care", "Appointments or treatment"],
  ["transportation", "Transportation", "Transit routes, fares or rides"],
  ["identification", "Identification", "Getting or replacing ID"],
  ["education", "Education or training", "GED, courses or work training"],
  ["community_support", "Community support", "A support person or local group"],
];
export const GOAL_PRESETS = ["Arrange a place to stay", "Apply for jobs that fit my skills", "Get or replace my ID", "Arrange reliable transportation", "Explore training or education", "Connect with a support person"];
export const goalLines = (text: string) => [...new Set(text.split("\n").map(v => v.trim()).filter(Boolean))];
export const ownGoals = (text: string) => text.split("\n").filter(v => !GOAL_PRESETS.includes(v.trim())).join("\n");
export function toggleGoal(text: string, goal: string, checked: boolean): string {
  const lines = text ? text.split("\n") : [];
  return (checked ? goalLines(text).includes(goal) ? lines : [...lines, goal] : lines.filter(v => v.trim() !== goal)).join("\n");
}
export function replaceOwnGoals(text: string, own: string): string {
  return [...goalLines(text).filter(v => GOAL_PRESETS.includes(v)), ...(own ? [own] : [])].join("\n");
}
