import type {
  ActivityEvent,
  ApiError,
  Comment,
  DashboardSummary,
  TokenResponse,
  TransitionAction,
  User,
  WorkItem,
  WorkItemListResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("ops_token");
}

function setToken(token: string | null, user: User | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem("ops_token", token);
  } else {
    localStorage.removeItem("ops_token");
  }
  if (user) {
    localStorage.setItem("ops_user", JSON.stringify(user));
  } else {
    localStorage.removeItem("ops_user");
  }
}

function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("ops_user");
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch {
    const err: ApiError = {
      status: 0,
      message: "The operations service is not connected. Start or deploy the backend service, then try again.",
    };
    throw err;
  }

  if (res.status === 401) {
    setToken(null, null);
    const err: ApiError = { status: 401, message: "Your session has expired. Please sign in again." };
    throw err;
  }

  if (res.status === 403) {
    const body = await res.json().catch(() => ({}));
    const err: ApiError = {
      status: 403,
      message: (body.detail as string) || "You do not have permission to do that.",
    };
    throw err;
  }

  if (res.status === 409) {
    const body = await res.json().catch(() => ({}));
    const detail = body.detail;
    let message = "This item was modified by someone else. Refresh and try again.";
    if (typeof detail === "object" && detail !== null && detail.message) {
      message = detail.message;
    } else if (typeof detail === "string") {
      message = detail;
    }
    const err: ApiError = { status: 409, message, detail };
    throw err;
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message =
      (body.detail as string) ||
      (typeof body.detail === "object" && body.detail?.message) ||
      `Request failed (${res.status})`;
    const err: ApiError = { status: res.status, message: String(message) };
    throw err;
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

// --- Auth API ---------------------------------------------------------------

export const api = {
  async login(email: string, password: string): Promise<TokenResponse> {
    const data = await request<TokenResponse>("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(data.access_token, data.user);
    return data;
  },

  logout(): void {
    setToken(null, null);
  },

  getStoredUser,

  async me(): Promise<User> {
    return request<User>("/api/me");
  },

  async getTeams(): Promise<User["memberships"]> {
    return request("/api/teams");
  },

  // --- Work items ----------------------------------------------------------

  async listWorkItems(params: {
    page?: number;
    page_size?: number;
    status?: string[];
    priority?: string[];
    assignee_id?: number;
    view?: string;
    search?: string;
    team_id?: number;
  }): Promise<WorkItemListResponse> {
    const sp = new URLSearchParams();
    if (params.page) sp.set("page", String(params.page));
    if (params.page_size) sp.set("page_size", String(params.page_size));
    if (params.search) sp.set("search", params.search);
    if (params.view) sp.set("view", params.view);
    if (params.team_id) sp.set("team_id", String(params.team_id));
    if (params.assignee_id) sp.set("assignee_id", String(params.assignee_id));
    (params.status || []).forEach((s) => sp.append("status", s));
    (params.priority || []).forEach((p) => sp.append("priority", p));
    return request(`/api/work-items?${sp.toString()}`);
  },

  async getWorkItem(id: number): Promise<WorkItem> {
    return request(`/api/work-items/${id}`);
  },

  async createWorkItem(data: {
    team_id: number;
    title: string;
    description: string;
    priority: string;
    due_at?: string | null;
    assignee_id?: number | null;
  }): Promise<WorkItem> {
    return request("/api/work-items", {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  async updateWorkItem(
    id: number,
    data: {
      title?: string;
      description?: string;
      priority?: string;
      due_at?: string | null;
      assignee_id?: number | null;
      version: number;
    },
  ): Promise<WorkItem> {
    return request(`/api/work-items/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    });
  },

  async transition(
    id: number,
    action: TransitionAction,
    version: number,
  ): Promise<WorkItem> {
    return request(`/api/work-items/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ action, version }),
    });
  },

  async getComments(id: number): Promise<Comment[]> {
    return request(`/api/work-items/${id}/comments`);
  },

  async addComment(id: number, body: string): Promise<Comment> {
    return request(`/api/work-items/${id}/comments`, {
      method: "POST",
      body: JSON.stringify({ body }),
    });
  },

  async getActivity(id: number): Promise<ActivityEvent[]> {
    return request(`/api/work-items/${id}/activity`);
  },

  async getDashboardSummary(): Promise<DashboardSummary> {
    return request("/api/dashboard/summary");
  },
};
