export type Priority = "low" | "medium" | "high" | "urgent";
export type WorkStatus =
  | "open"
  | "in_progress"
  | "blocked"
  | "in_review"
  | "approved"
  | "rejected"
  | "done"
  | "cancelled";
export type Role = "manager" | "contributor";
export type TransitionAction =
  | "claim"
  | "release"
  | "start_review"
  | "approve"
  | "reject"
  | "block"
  | "unblock"
  | "complete"
  | "cancel";

export interface Membership {
  team_id: number;
  team_slug: string;
  team_name: string;
  role: Role;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  memberships: Membership[];
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface WorkItem {
  id: number;
  team_id: number;
  title: string;
  description: string;
  status: WorkStatus;
  priority: Priority;
  assignee_id: number | null;
  version: number;
  due_at: string | null;
  created_at: string;
  updated_at: string;
  assignee_name: string | null;
  team_name?: string | null;
}

export interface WorkItemListResponse {
  items: WorkItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardSummary {
  assigned_to_me: number;
  unassigned_urgent: number;
  awaiting_my_approval: number;
  total_visible: number;
}

export interface Comment {
  id: number;
  work_item_id: number;
  author_id: number;
  author_name: string | null;
  body: string;
  created_at: string;
}

export interface ActivityEvent {
  id: number;
  work_item_id: number;
  actor_id: number;
  actor_name: string | null;
  action: string;
  detail: string;
  version_after: number;
  created_at: string;
}

export interface ApiError {
  status: number;
  message: string;
  detail?: unknown;
}
