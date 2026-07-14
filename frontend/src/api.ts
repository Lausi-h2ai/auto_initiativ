export type Me = {
  id: number;
  email: string;
  display_name: string;
  avatar_url?: string | null;
  role: "user" | "admin";
  workspace: { id: string; name: string };
  csrf_token: string;
  local_registration_enabled: boolean;
};

export type Campaign = {
  id: string;
  name: string;
  status: string;
  sending_mode: "prepare_only" | "gated_autosend";
  brief: Record<string, unknown>;
  stages: Record<string, number>;
  company_count: number;
  active_task_count: number;
  exception_count: number;
  started_at?: string | null;
  updated_at: string;
};

export type AgentTask = {
  id: string;
  agent_role: string;
  task_type?: string;
  status: string;
  progress: number;
  narrative: string;
  updated_at?: string;
};

export type ProductSummary = {
  campaigns: Campaign[];
  active_campaign: Campaign | null;
  pipeline: Record<string, number>;
  active_tasks: AgentTask[];
  exception_count: number;
  document_count: number;
  sent_count: number;
};

export type Company = {
  id?: number | string;
  company_id?: string;
  name: string;
  domain?: string | null;
  normalized_domain?: string | null;
  description?: string | null;
  locations?: unknown[];
  industry_tags?: unknown[];
  stage?: string;
  fit_score?: number | null;
  fit_decision?: string | null;
  fit_reasons?: unknown[];
  confidence?: number;
  has_draft?: boolean;
  has_application_draft?: boolean;
  has_been_contacted?: boolean;
};

export type ExceptionItem = {
  id: string;
  company_id?: number | null;
  company_name?: string | null;
  external_company_id?: string | null;
  category: string;
  title: string;
  explanation: string;
  recommended_action: string;
  status: string;
  created_at: string;
};

export type DocumentItem = {
  id: string;
  title: string;
  type: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  company_id?: number | null;
  campaign_id?: number | null;
  status: string;
  preview_url: string;
  download_url?: string;
  created_at: string;
};

export type ProfileSummary = {
  has_approved_profile: boolean;
  approved_user_profile?: unknown;
  approved_master_cv_profile?: unknown;
  approved_policy?: unknown;
  candidate_user_profiles?: unknown[];
};

export type Provenance = {
  source_type: "verified_document" | "user_claim" | "inferred" | "needs_review";
  confidence: number;
  needs_review: boolean;
  source_refs: string[];
};

export type ProvenancedText = { value: string; provenance: Provenance };

export type ApprovedProfileBundle = {
  user_profile: { snapshot: { created_at: string; status: string }; content: Record<string, any> };
  master_cv_profile: { snapshot: { created_at: string; status: string }; content: Record<string, any> };
  policy: { snapshot: { created_at: string; status: string }; content: Record<string, any> };
};

export type Delivery = {
  sending_enabled: boolean;
  provider: string;
  allow_real_recipients: boolean;
  gmail_configured: boolean;
  gmail_connection_available: boolean;
  gmail_connection_source?: "database" | "local_file" | null;
  mode: string;
};

let csrf = "";

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (options.method && !["GET", "HEAD", "OPTIONS"].includes(options.method.toUpperCase()) && csrf) {
    headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the HTTP fallback.
    }
    if (response.status >= 500) {
      reportBrowserIssue({ kind: "api_error", message, source: path, status: response.status });
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function loadMe(): Promise<Me> {
  const me = await request<Me>("/me");
  csrf = me.csrf_token;
  return me;
}

export async function loadWorkspace() {
  const me = await loadMe();
  const [summary, profile, delivery, campaigns, exceptions, documents, agents] = await Promise.all([
    request<ProductSummary>("/product/summary"),
    request<ProfileSummary>("/profile/summary"),
    request<Delivery>("/email-delivery/settings"),
    request<Campaign[]>("/campaigns"),
    request<ExceptionItem[]>("/exceptions"),
    request<DocumentItem[]>("/documents"),
    request<AgentTask[]>("/agent-activity"),
  ]);
  return { me, summary, profile, delivery, campaigns, exceptions, documents, agents };
}

export function mutate<T>(path: string, method: string, payload?: unknown): Promise<T> {
  return request<T>(path, { method, body: payload === undefined ? undefined : JSON.stringify(payload) });
}
import { reportBrowserIssue } from "./monitoring";
