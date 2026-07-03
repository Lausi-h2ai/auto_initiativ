from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class _DashboardAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"] or "")
        rel_values = set((attributes.get("rel") or "").split())
        if tag == "link" and "stylesheet" in rel_values and attributes.get("href"):
            self.stylesheets.append(attributes["href"] or "")


def _dashboard_assets(client) -> tuple[str, dict[str, str]]:
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    html = response.text
    assert "<html" in html.lower()
    assert "dashboard" in html.lower()

    parser = _DashboardAssetParser()
    parser.feed(html)

    assert parser.scripts
    assert parser.stylesheets

    assets: dict[str, str] = {}
    for asset_path in parser.scripts + parser.stylesheets:
        asset_url = urljoin("/dashboard", asset_path)
        asset_response = client.get(asset_url)

        assert asset_response.status_code == 200
        assets[asset_url] = asset_response.text

    return html, assets


def test_dashboard_returns_html_for_actual_app(client):
    html, assets = _dashboard_assets(client)

    combined = "\n".join([html, *assets.values()]).lower()

    assert "dashboard" in combined
    assert "/dashboard/summary" in combined


def test_dashboard_html_is_not_browser_cached(client):
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_dashboard_static_js_and_css_are_served(client):
    _, assets = _dashboard_assets(client)

    js_assets = {path: body for path, body in assets.items() if urlparse(path).path.endswith(".js")}
    css_assets = {path: body for path, body in assets.items() if urlparse(path).path.endswith(".css")}

    assert js_assets
    assert css_assets
    assert all("javascript" in client.get(path).headers["content-type"] for path in js_assets)
    assert all("text/css" in client.get(path).headers["content-type"] for path in css_assets)


def test_dashboard_assets_reference_required_read_only_api_endpoints(client):
    html, assets = _dashboard_assets(client)
    combined = "\n".join([html, *assets.values()])

    required_endpoints = {
        "/dashboard/summary",
        "/profile/summary",
        "/campaigns/company-research",
        "/campaigns/company-research/",
        "/application-drafts",
        "/application-drafts/",
        "/application-drafts/batches",
        "/launch",
        "/status",
        "/runs",
        "/onboarding/chat/",
        "/onboarding/runs/",
        "/artifacts",
        "/input-files",
        "/import-artifacts",
        "/promote",
        "/companies",
        "/contacts",
        "/fit-evaluations",
        "/email-drafts",
        "/outbox/drafts",
        "/outbox/sent",
        "/outbox/send-all",
        "/send-intents",
        "/gate/evaluations/",
        "/gate-results",
        "/outreach-records",
        "/audit-logs",
    }

    for endpoint in required_endpoints:
        assert endpoint in combined

    required_product_text = {
        "Home",
        "Profile",
        "Companies",
        "Applications",
        "Advanced/Admin",
        "Personal recruiter",
        "Next best step",
        "Needs your attention",
        "Completed recently",
        "Your career profile is ready",
        "Recruiter conversation",
        "Structured profile",
        "Resume source material",
        "Approve meaningful changes",
        "Where should your recruiter look?",
        "What kind of work should we prioritize?",
        "What kinds of companies should stand out?",
        "How broad should this search be?",
        "Review the recruiter brief.",
        "Start company search",
        "Searching for companies",
        "Save company",
        "Not for me",
        "View all companies",
        "Company detail",
        "Why it matches",
        "Concerns and uncertainties",
        "Application workspace",
        "Review applications before anything leaves",
        "Ready for your approval",
        "Final approval",
        "No application is sent without your explicit confirmation.",
        "Operational records and debugging tools",
        "Administrative view",
        "Raw records, run IDs, paths, payloads, queue state, gate results, and audit logs are shown here.",
    }
    for text in required_product_text:
        assert text in combined

    primary_nav_terms = {
        'label: "Home"',
        'label: "Profile"',
        'label: "Companies"',
        'label: "Applications"',
    }
    for text in primary_nav_terms:
        assert text in combined

    assert 'label: "Advanced"' not in combined
    assert "Start Onboarding" not in combined
    assert 'label: "Onboarding"' not in combined
    assert "Opportunities" not in combined
    assert "Today" not in combined
    assert "Local profile mode" not in combined


def test_dashboard_guided_research_slice_uses_concept_b_language(client):
    _, assets = _dashboard_assets(client)
    combined = "\n".join(assets.values())

    expected = {
        "guidedFlowShell",
        "choiceGroup",
        "reviewSummary",
        "primaryActionBar",
        "backgroundActivityMarkup",
        "inlineError",
        "companies/brief",
        "companies/progress",
        "companies/review",
        "companies/list",
        "Research brief",
        "You can leave this page. The search will continue in the background.",
        "This cannot contact companies or approve applications.",
    }
    for text in expected:
        assert text in combined

    assert "--color-canvas: #f6f8fb" in combined
    assert "--color-brand: #087c7c" in combined
    assert "#f7f4ee" not in combined
    assert "#fffdf9" not in combined


def test_dashboard_guided_slice_does_not_add_email_delivery_controls(client):
    _, assets = _dashboard_assets(client)
    combined = "\n".join(assets.values())

    guided_region_start = combined.index("function renderResearchBrief")
    guided_region_end = combined.index("function renderApplications")
    guided_region = combined[guided_region_start:guided_region_end]

    assert "/send-batches" not in guided_region
    assert "/outbox/send-all" not in guided_region
    assert "send email" not in guided_region.lower()


def test_dashboard_assets_do_not_expose_sending_or_external_ai_surfaces(client):
    html, assets = _dashboard_assets(client)
    combined = "\n".join([html, *assets.values()]).lower()

    forbidden_terms = {
        "openai",
        "email adapter",
        "send adapter",
        "reserve for send",
        "send now",
        "send email",
    }
    for term in forbidden_terms:
        assert term not in combined

    forbidden_endpoint_patterns = [
        r"['\"][^'\"]*\/send-reservations(?:['\"/?#]|\b)",
        r"['\"][^'\"]*\/dashboard\/send-reservations(?:['\"/?#]|\b)",
    ]
    for pattern in forbidden_endpoint_patterns:
        assert re.search(pattern, combined) is None
