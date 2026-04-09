"""
Singleton Playwright browser — reused across all scraper tools.

Auto-loads LinkedIn auth state if `config.LINKEDIN_AUTH_PATH` exists,
so Mostafa walks LinkedIn as the logged-in user without intervention.
"""
import os
from playwright.async_api import async_playwright
import config

_playwright = None
_browser = None
_context = None


async def get_page():
    global _playwright, _browser, _context
    if _playwright is None:
        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx_kwargs = dict(
            user_agent=("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
            locale="en-US",
            viewport={"width": 1440, "height": 900},
        )
        # Auto-attach LinkedIn auth if available
        if os.path.exists(config.LINKEDIN_AUTH_PATH):
            ctx_kwargs["storage_state"] = config.LINKEDIN_AUTH_PATH
            print(f"[browser] using LinkedIn auth from {config.LINKEDIN_AUTH_PATH}")
        _context = await _browser.new_context(**ctx_kwargs)
    return await _context.new_page()


async def linkedin_auth_exists() -> bool:
    return os.path.exists(config.LINKEDIN_AUTH_PATH)


def linkedin_auth_setup_command() -> str:
    """Return the exact command the user needs to run to set up LinkedIn auth."""
    return (
        f"playwright codegen --save-storage={config.LINKEDIN_AUTH_PATH} "
        f"https://www.linkedin.com/login"
    )


async def close_browser():
    global _playwright, _browser, _context
    if _browser:
        await _browser.close()
    if _playwright:
        await _playwright.stop()
    _playwright = _browser = _context = None
