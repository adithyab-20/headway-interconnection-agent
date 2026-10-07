// The API's shapes and calls (backend/src/interconnection_agent/api).

export type ProjectType = "Solar only" | "Solar + battery" | "Battery only" | "Wind" | "Gas";
export const PROJECT_TYPES: [ProjectType, string][] = [
  ["Solar only", "solar"],
  ["Solar + battery", "solar + battery"],
  ["Battery only", "battery"],
  ["Wind", "wind"],
  ["Gas", "gas"],
];

export type Place = { place: string; voltage_kv: number | null };

export type SiteSummary = {
  site: string;
  county: string | null;
  state: string | null;
  latitude: number | null;
  longitude: number | null;
  positioned_by: "openstreetmap" | "document" | "planned" | "county";
  position_source: string | null;
  places: Place[];
  realistic_mw: number;
  realistic_range: [number, number];
  waiting_mw: number;
  waiting_projects: number;
  new_rules_mw: number;
  new_rules_projects: number;
};

export type Sites = { as_of: string; sites: SiteSummary[] };

export type Statewide =
  | { refused: string }
  | {
      group: string;
      chance: number;
      range: [number, number];
      withdrawn: number;
      still_waiting: number;
      projects: number;
      typical_wait: number | null;
    };

export type YearCounts = Partial<
  Record<"built" | "withdrawn" | "waiting" | "new_rules_waiting" | "new_rules_withdrawn" | "new_rules_built", number>
>;

export type Overview = {
  as_of: string;
  years: Record<string, YearCounts>;
  types: Record<string, Record<string, Statewide>>;
};

export type Row = {
  id: string;
  status: "waiting" | "built" | "withdrawn";
  applied: string | null;
  ended: string | null;
  date_estimated: boolean;
  years: number | null;
  mw: number | null;
  rules: "old" | "2023 batch";
  furthest_step: string | null;
  types: string[];
  type: string | null;
};

export type Waiting = {
  id: string;
  mw: number;
  waited_years: number;
  chance: number | null;
  on_a_line: boolean;
  compared_with: string | null;
  applied: string | null;
  types: string[];
  type: string | null;
  furthest_step: string | null;
};

export type SiteDetail = Omit<SiteSummary, keyof Ahead> & {
  as_of: string;
  left_out: string[];
  ahead: Ahead & { projects: Waiting[]; new_rules: Waiting[]; not_counted: { id: string; why: string }[] };
  projects: Row[];
  upgrades: {
    plan_id: string;
    name: string;
    utility: string | null;
    year: number | null;
    cost_low_musd: number | null;
    cost_high_musd: number | null;
    source: string;
    places: string[];
  }[];
  bottlenecks: {
    bottleneck: string;
    room_left_mw: number | null;
    cost_per_kw: number | null;
    listed_in: string;
    costed_in: string | null;
    places: string[];
  }[];
};

type Ahead = Pick<
  SiteSummary,
  "realistic_mw" | "realistic_range" | "waiting_mw" | "waiting_projects" | "new_rules_mw" | "new_rules_projects"
>;

export type Chance =
  | { refused: string }
  | {
      chance: number;
      range: [number, number];
      typical_wait: number | null;
      wait_range: [number, number] | null;
      projects: number;
      built: number;
      withdrawn: number;
      waiting: number;
      watched: number;
    };

export const known = (c: Chance | null | undefined): c is Exclude<Chance, { refused: string }> =>
  !!c && !("refused" in c);

export type Rung = {
  description: string;
  area_kind: "voltage section" | "site" | "bottleneck area" | "county" | "California";
  area: string | null;
  projects: number;
  resolved: number;
  built: number;
  enough: boolean;
  used: boolean;
  chance: Chance | null;
  ids: string[]; // the past projects in it
};

export type Odds = {
  used: string;
  history_from: string;
  by_years: Record<string, Chance>;
  ladder: Rung[];
  curve: { years: number; built: number; withdrawn: number; still_waiting: number; built_range: [number, number] }[];
  rows: Row[];
};

export type Part = { text: string } | { number: string; rows: string[] };
export type Claim =
  | { id: string; kind: "factual"; parts: Part[] }
  | {
      id: string;
      kind: "judgement";
      text: string;
      based_on: string[];
      decision: "awaiting" | "agreed" | "disagreed" | "reworded";
    };

export type Answer = {
  id: string;
  request: string;
  claims: Claim[];
  rejected: number;
  lookups: { tool: string; asked: Record<string, unknown>; rows: number }[];
  cant_answer: string | null;
  proposal: { description: string; leave_out: string[]; comparison_group: string | null; why: string } | null;
};

export type Assessment = {
  id: string;
  site: string;
  project: { type: string | null; mw: number | null; describe: string };
  final: boolean;
  claims: Claim[];
  held: Answer[];
  changes: { when: string; who: string; what: string; why: string }[];
  left_out: string[];
  comparison_group: string | null;
  questions_left: number;
};

// A write-up the API is still writing.
type Writing = { id: string; status: "writing" };

const stillWriting = (a: Assessment | Writing): a is Writing => "status" in a && a.status === "writing";

const pause = (ms: number) => new Promise((done) => setTimeout(done, ms));

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const body = (await r.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = "That request wasn't valid.";
    } catch {
      /* keep the status text */
    }
    throw new ApiError(r.status, detail);
  }
  return (await r.json()) as T;
}

const post = <T,>(path: string, body: unknown): Promise<T> =>
  call<T>(path, { method: "POST", body: JSON.stringify(body) });

const query = (params: Record<string, string | number | null | undefined>): string =>
  new URLSearchParams(
    Object.entries(params).filter((e): e is [string, string | number] => e[1] != null && e[1] !== "") as [string, string][],
  ).toString();

export const api = {
  overview: () => call<Overview>("/api/overview"),
  sites: () => call<Sites>("/api/sites"),
  site: (site: string, leaveOut: string[] = []) =>
    call<SiteDetail>(`/api/sites/${encodeURIComponent(site)}?${query({ leave_out: leaveOut.join(",") })}`),
  odds: (p: {
    place: string;
    projectType: ProjectType | null;
    mw: number | null;
    years: number;
    group: string | null;
    leaveOut: string[];
  }) =>
    call<Odds>(
      `/api/odds?${query({
        place: p.place,
        project_type: p.projectType,
        mw: p.projectType ? p.mw : null,
        years: p.years,
        group: p.group,
        leave_out: p.leaveOut.join(","),
      })}`,
    ),
  rows: (ids: string[]) => post<{ rows: Row[] }>("/api/rows", { ids }),
  // Writing takes a minute or two, longer than the site's host waits for one request, so it's
  // started, then checked on until it's done.
  write: async (site: string, projectType: ProjectType | null, mw: number | null): Promise<Assessment> => {
    let got: Assessment | Writing = await post<Writing>("/api/assessments", { site, project_type: projectType, mw });
    while (stillWriting(got)) {
      await pause(2000);
      got = await call<Assessment | Writing>(`/api/assessments/${got.id}`);
    }
    return got;
  },
  adjust: (id: string, body: { why: string; leave_out?: string[]; comparison_group?: string | null }) =>
    post<Assessment>(`/api/assessments/${id}/adjust`, body),
  decide: (id: string, judgementId: string, decision: "agree" | "disagree") =>
    post<Assessment>(`/api/assessments/${id}/decide`, { judgement_id: judgementId, decision }),
  reword: (id: string, judgementId: string, text: string) =>
    post<Assessment>(`/api/assessments/${id}/reword`, { judgement_id: judgementId, text }),
  finalise: (id: string) => post<Assessment>(`/api/assessments/${id}/finalise`, {}),
  ask: (id: string, request: string) =>
    post<{ answer: Answer; assessment: Assessment }>(`/api/assessments/${id}/ask`, { request }),
  add: (id: string, answerId: string) => post<Assessment>(`/api/assessments/${id}/add`, { answer_id: answerId }),
  confirm: (id: string, answerId: string) =>
    post<Assessment>(`/api/assessments/${id}/confirm`, { answer_id: answerId }),
};
