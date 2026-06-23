"""Frontend smoke tests via Playwright."""

import pytest


@pytest.fixture
def dashboard(page, app_url):
    page.goto(f"{app_url}/")
    page.wait_for_selector("#project-grid")
    return page


def test_dashboard_loads(dashboard):
    assert dashboard.title() == "aud_it — PDF Redaction"
    assert dashboard.locator("h2").filter(has_text="Projects").is_visible()
    assert dashboard.locator("#project-grid").is_visible()


def test_create_project_opens_organize(dashboard, app_url):
    dashboard.locator("#new-project-btn").click()
    dashboard.locator("#new-project-create-btn").click()
    dashboard.wait_for_selector(".project-card .open-project")
    dashboard.locator(".project-card .open-project").first.click()
    dashboard.wait_for_selector("#view-organize:not(.hidden)")
    assert "organize" in dashboard.url


def test_hard_clear_fab_visible(dashboard):
    fab = dashboard.locator("#hard-clear-btn")
    assert fab.is_visible()
    box = fab.bounding_box()
    assert box is not None
    viewport = dashboard.viewport_size
    assert box["x"] + box["width"] > viewport["width"] * 0.5
    assert box["y"] + box["height"] > viewport["height"] * 0.5


def test_mark_terminology_present(app_url, page):
    page.goto(f"{app_url}/")
    assert page.locator("#mark-selected-btn").count() == 1
    assert page.locator("#mark-highconf-btn").count() == 1
    assert page.locator("#batch-apply-btn").filter(has_text="Apply redactions").count() == 1
    assert page.locator("#redact-selected-btn").count() == 0


def test_export_step_dom_without_legacy_modal(app_url, page):
    page.goto(f"{app_url}/")
    assert page.locator("#view-export").count() == 1
    assert page.locator("#export-modal").count() == 0
    assert page.locator("#export-step-run-btn").count() == 1
