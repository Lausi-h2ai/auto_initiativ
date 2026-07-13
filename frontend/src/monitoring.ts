type BrowserIssue = {
  kind: "javascript_error" | "unhandled_rejection" | "api_error";
  message: string;
  source?: string;
  stack?: string;
  status?: number;
  url?: string;
};

const recentlyReported = new Map<string, number>();

export function reportBrowserIssue(issue: BrowserIssue) {
  const key = `${issue.kind}:${issue.source || ""}:${issue.message}`;
  const now = Date.now();
  if ((recentlyReported.get(key) || 0) > now - 60_000) return;
  recentlyReported.set(key, now);
  void fetch("/monitoring/client-errors", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    keepalive: true,
    body: JSON.stringify({ ...issue, url: issue.url || window.location.href }),
  }).catch(() => undefined);
}

export function installBrowserIssueMonitoring() {
  window.addEventListener("error", (event) => {
    reportBrowserIssue({
      kind: "javascript_error",
      message: event.message || "Unknown browser error",
      source: event.filename || "window.error",
      stack: event.error instanceof Error ? event.error.stack : undefined,
    });
  });
  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason;
    reportBrowserIssue({
      kind: "unhandled_rejection",
      message: reason instanceof Error ? reason.message : String(reason || "Unhandled promise rejection"),
      source: "window.unhandledrejection",
      stack: reason instanceof Error ? reason.stack : undefined,
    });
  });
}
