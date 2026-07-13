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
    assert "auto initiativ" in html.lower()

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

    assert "mission control" in combined
    assert "/product/summary" in combined


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


def test_dashboard_assets_reference_guided_product_endpoints(client):
    html, assets = _dashboard_assets(client)
    combined = "\n".join([html, *assets.values()])

    required_endpoints = {
        "/product/summary",
        "/profile/summary",
        "/companies",
        "/campaigns",
        "/agent-activity",
        "/exceptions",
        "/documents",
        "/me",
        "/email-delivery/settings",
    }

    for endpoint in required_endpoints:
        assert endpoint in combined

    required_product_text = {
        "Mission control",
        "My story",
        "Companies",
        "Documents",
        "Needs me",
        "Settings",
        "Your search deserves a dedicated team.",
        "Start a campaign",
        "Working on your behalf",
        "Companies your team is moving forward",
        "A short inbox, not another task list",
        "What kind of work should we pursue?",
        "Where should your team look?",
        "How far should this campaign proceed?",
        "Everything your team needs to begin",
        "Start my campaign",
        "Prepare everything for me",
        "Gated autopilot",
    }
    for text in required_product_text:
        assert text in combined

    assert "Advanced/Admin" not in combined
    assert "Local profile mode" not in combined


def test_dashboard_assets_do_not_expose_sending_or_external_ai_surfaces(client):
    html, assets = _dashboard_assets(client)
    combined = "\n".join([html, *assets.values()]).lower()

    forbidden_terms = {
        "openai",
        "email adapter",
        "send adapter",
        "reserve for send",
        "reserve for send",
    }
    for term in forbidden_terms:
        assert term not in combined

    forbidden_endpoint_patterns = [
        r"['\"][^'\"]*\/send-reservations(?:['\"/?#]|\b)",
        r"['\"][^'\"]*\/dashboard\/send-reservations(?:['\"/?#]|\b)",
    ]
    for pattern in forbidden_endpoint_patterns:
        assert re.search(pattern, combined) is None
