import re

import config
from scraper import get_bid_page_averages, has_existing_proposal


class BidError(Exception):
    pass


def build_bid_url(href):
    path = href.replace("/project/", "/project/bid/", 1)
    return path if path.startswith("http") else f"{config.BASE_URL}{path}"


def _parse_currency(raw):
    digits = re.sub(r"[^\d,]", "", raw).replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return None


def submit_bid(page, href, price_reais, duration_days, proposal_text):
    """Fills and submits the proposal form. Returns (success, info_dict).

    Known bug (see memory feedback_bugs_propostas_freelas.md): the 'Sua oferta'
    field has a currency mask that reads keystrokes as cents from the right, so a
    stale value or a mistyped click can make the offer come out ~100x too high.
    We always clear the field first and verify the rendered value before
    submitting; on mismatch we abort instead of risking a wrong price.
    """
    bid_url = build_bid_url(href)
    page.goto(bid_url, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    if has_existing_proposal(page):
        return False, {"error": "Formulário já vinha preenchido (proposta existente). Abortado pra não sobrescrever."}

    avg_price, avg_days = get_bid_page_averages(page)

    cents = str(int(round(price_reais * 100)))

    oferta = page.locator("#oferta")
    oferta.click()
    page.keyboard.press("Control+A")
    for _ in range(15):
        page.keyboard.press("Backspace")
    oferta.type(cents, delay=30)

    page.wait_for_timeout(300)
    shown_value = oferta.input_value()
    shown_reais = _parse_currency(shown_value)

    if shown_reais is None or abs(shown_reais - price_reais) > 0.02:
        return False, {
            "error": f"Valor no campo 'oferta' não bate com o esperado: mostrou "
                     f"{shown_value!r}, esperado R$ {price_reais:.2f}. Abortado antes de enviar.",
            "avg_price": avg_price,
            "avg_days": avg_days,
        }

    duracao = page.locator("#duracao-estimada")
    duracao.click()
    page.keyboard.press("Control+A")
    duracao.type(str(int(duration_days)), delay=30)

    proposta = page.locator("#proposta")
    proposta.click()
    proposta.fill(proposal_text[:3000])

    if config.DRY_RUN:
        return True, {
            "dry_run": True,
            "avg_price": avg_price,
            "avg_days": avg_days,
            "shown_value": shown_value,
        }

    page.locator("#btnConcluirEnvioProposta").click()
    page.wait_for_timeout(2500)

    return True, {
        "avg_price": avg_price,
        "avg_days": avg_days,
        "shown_value": shown_value,
        "final_url": page.url,
    }
