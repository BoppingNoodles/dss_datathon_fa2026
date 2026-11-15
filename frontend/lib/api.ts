import type {
  HousingComparisonRequest,
  HousingComparisonResponse,
  RecommendationRequest,
  RecommendationResponse,
} from "./types";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

async function post<T>(path: string, body: unknown): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
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
    return await res.json();
  } catch (error) {
    if (controller.signal.aborted) throw new Error("This is taking longer than expected. Try again.");
    if (error instanceof TypeError) throw new TypeError("Couldn’t connect to Phoenix. Try again.");
    throw error;
  } finally { clearTimeout(timer); }
}

export const getRecommendations = (req: RecommendationRequest) =>
  post<RecommendationResponse>("/recommendations", req);


export const compareHousing = (req: HousingComparisonRequest) =>
  post<HousingComparisonResponse>("/housing-comparison", req);

export const money = (n: number | null | undefined, digits = 0) =>
  n == null ? null : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits });
