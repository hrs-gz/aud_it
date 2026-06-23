"""Playwright E2E fixtures — live uvicorn server + browser page (no pytest-playwright plugin)."""

import socket
import threading
import time

import pytest
import uvicorn

pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright

from backend.main import app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_server_url():
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        pytest.fail("E2E server did not start in time")

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(scope="session")
def playwright_manager():
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(playwright_manager):
    try:
        instance = playwright_manager.chromium.launch(headless=True)
    except Exception as exc:
        pytest.skip(
            f"Playwright Chromium not installed. Run: playwright install chromium ({exc})"
        )
    yield instance
    instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    tab = context.new_page()
    yield tab
    context.close()


@pytest.fixture
def app_url(live_server_url):
    return live_server_url
