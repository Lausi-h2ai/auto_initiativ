from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class _AssetParser(HTMLParser):
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


def _design_lab_assets(client, route: str) -> tuple[str, dict[str, str]]:
    response = client.get(route)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    parser = _AssetParser()
    parser.feed(response.text)

    assert parser.stylesheets
    assert parser.scripts

    assets: dict[str, str] = {}
    for asset_path in parser.stylesheets + parser.scripts:
        asset_url = urljoin(route, asset_path)
        asset_response = client.get(asset_url)

        assert asset_response.status_code == 200
        assets[asset_url] = asset_response.text

    return response.text, assets


def test_design_lab_concept_routes_are_static_and_isolated(client):
    routes = ["/design-lab/concept-a", "/design-lab/concept-b", "/design-lab/concept-c"]
    forbidden_fragments = {
        "fetch(",
        "XMLHttpRequest",
        "sendBeacon",
        "/dashboard/summary",
        "/profile/summary",
        "/campaigns/",
        "/application-drafts",
        "/onboarding/",
        "/send-batches",
        "/outbox/send-all",
        "/email-delivery",
        "/gate-results",
        "/audit-logs",
        "localStorage",
        "indexedDB",
    }

    for route in routes:
        html, assets = _design_lab_assets(client, route)
        combined = "\n".join([html, *assets.values()])

        assert "Design lab" in combined
        assert (
            "Nothing sends without your approval" in combined
            or "No application can be sent" in combined
            or "Nothing is sent from this concept" in combined
        )
        for forbidden in forbidden_fragments:
            assert forbidden not in combined


def test_design_lab_assets_are_served_from_design_lab_directory(client):
    _, assets = _design_lab_assets(client, "/design-lab/concept-a")

    assert all(urlparse(path).path.startswith("/static/design-lab/") for path in assets)
    assert any(urlparse(path).path.endswith(".css") for path in assets)
    assert any(urlparse(path).path.endswith(".js") for path in assets)
