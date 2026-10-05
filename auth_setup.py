"""Run this once: `python auth_setup.py`.

Opens a real (visible) Chromium window using a persistent profile folder.
Log in to 99Freelas by hand in that window (including any 2FA/captcha).
This script polls the page for a logged-in indicator and closes itself
automatically once it detects you're in (no need to type anything in the
terminal). The same profile folder is then reused headlessly by bot.py.
"""

import sys
import time

from playwright.sync_api import sync_playwright

import config

TIMEOUT_SECONDS = 10 * 60

with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        config.PROFILE_DIR,
        headless=False,
        channel="chrome",
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    page = context.new_page()
    page.goto(f"{config.BASE_URL}/login")

    print("Faça login normalmente na janela do Chromium que abriu.", flush=True)
    print(f"Aguardando login (até {TIMEOUT_SECONDS // 60} min)...", flush=True)

    logged_in = False
    start = time.time()
    while time.time() - start < TIMEOUT_SECONDS:
        try:
            # "Sair" (logout) button only exists in the account dropdown once logged in.
            if page.locator("button:has-text('Sair')").count() > 0:
                logged_in = True
                break
        except Exception:
            pass
        time.sleep(2)

    if logged_in:
        # Let cookies/localStorage settle and navigate once more so everything persists to disk.
        page.wait_for_timeout(1500)
        page.goto(f"{config.BASE_URL}/dashboard", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        print(f"Login detectado. Sessão salva em: {config.PROFILE_DIR}", flush=True)
        print("Pode rodar: python bot.py", flush=True)
    else:
        print("Não detectei login dentro do tempo limite. Rode de novo se precisar.", flush=True)

    context.close()
    sys.exit(0 if logged_in else 1)
