import type {
  HousingComparisonRequest,
  HousingComparisonResponse,
  RecommendationRequest,
  RecommendationResponse,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `The server returned an error (${res.status}).`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") detail = j.detail;
      else if (Array.isArray(j.detail) && j.detail[0]?.msg) detail = `Please check your answers: ${j.detail[0].msg}`;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export const getRecommendations = (req: RecommendationRequest) =>
  post<RecommendationResponse>("/recommendations", req);

export const compareHousing = (req: HousingComparisonRequest) =>
  post<HousingComparisonResponse>("/housing-comparison", req);

export const money = (n: number | null | undefined, digits = 0) =>
  n == null ? null : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits });
