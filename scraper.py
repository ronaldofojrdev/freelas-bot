import re

import config


def list_projects(page):
    """Returns [{id, title, href}] for every project card on the listing page."""
    page.goto(config.LISTING_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(1500)

    items = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('li.result-item[data-id]')).map(li => {
            const a = li.querySelector('a[href*="/project/"]');
            return {
                id: li.getAttribute('data-id'),
                title: li.getAttribute('data-nome') || (a ? a.innerText.trim() : ''),
                href: a ? a.getAttribute('href').split('?')[0] : null,
            };
        }).filter(x => x.href)
        """
    )
    return items


def get_project_details(page, href):
    """Loads a project detail page and extracts description, skills and the info table."""
    url = href if href.startswith("http") else f"{config.BASE_URL}{href}"
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_timeout(1200)

    data = page.evaluate(
        """
        () => {
            const descEl = document.querySelector('.item-text.project-description.formatted-text');
            const table = document.querySelector('table');
            const rows = {};
            if (table) {
                const cells = Array.from(table.querySelectorAll('td, th, span, div')).map(e => e.innerText.trim()).filter(Boolean);
                // table.innerText already gives "Label:\\nValue\\n..." pairs on 99Freelas markup
            }
            const skillLinks = Array.from(document.querySelectorAll('a[href*="/projects?q="]')).map(a => a.innerText.trim());
            return {
                description: descEl ? descEl.innerText.trim() : '',
                table_text: table ? table.innerText.trim() : '',
                skills: skillLinks,
            };
        }
        """
    )
    data["url"] = url
    data["table"] = _parse_table_text(data.get("table_text", ""))
    return data


def _parse_table_text(text):
    """Turns the 'Label:\\tValue' innerText block from the info table into a dict."""
    result = {}
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    i = 0
    while i < len(lines):
        if lines[i].endswith(":"):
            key = lines[i][:-1]
            value = lines[i + 1] if i + 1 < len(lines) else ""
            result[key] = value
            i += 2
        else:
            i += 1
    return result


def matches_hard_filter(title, skills, description=""):
    haystack = (title + " " + " ".join(skills) + " " + description).lower()
    blocked = config.DESIGN_KEYWORDS + config.INFRA_KEYWORDS
    return any(kw in haystack for kw in blocked)


def parse_valor_minimo(table):
    raw = table.get("Valor Mínimo", "")
    return _parse_currency(raw)


def parse_propostas(table):
    raw = table.get("Propostas", "0")
    digits = re.sub(r"\D", "", raw)
    return int(digits) if digits else 0


def _parse_currency(raw):
    digits = re.sub(r"[^\d,]", "", raw).replace(",", ".")
    try:
        return float(digits)
    except ValueError:
        return 0.0


def has_existing_proposal(page):
    """A página de proposta vem PRÉ-PREENCHIDA (modo edição) quando o
    freelancer já enviou proposta nesse projeto antes (manualmente ou em um
    ciclo anterior do bot). Descobrimos isso da forma mais dura possível:
    o bot sobrescreveu uma proposta manual anterior sem perceber que o
    formulário já vinha com dados.

    CUIDADO: o campo #oferta vem SEMPRE com um valor sugerido (o valor mínimo
    do projeto), mesmo num formulário totalmente em branco — então checar só
    esse campo dá falso positivo em projeto novo de verdade. Só considera que
    já existe proposta quando #duracao-estimada OU #proposta (texto) também
    vierem preenchidos, porque esses dois nunca têm valor padrão.
    """
    try:
        duracao = page.locator("#duracao-estimada").input_value()
        proposta = page.locator("#proposta").input_value()
    except Exception:
        return False
    return bool(duracao.strip()) or bool(proposta.strip())


def get_bid_page_averages(page):
    """Reads 'Valor médio das propostas' and 'Duração média estimada' from the open bid page."""
    text = page.evaluate("() => document.body.innerText")
    avg_price = None
    avg_days = None

    m = re.search(r"Valor médio das propostas:\s*R\$\s*([\d.,]+)", text)
    if m:
        avg_price = _parse_currency("R$ " + m.group(1))

    m = re.search(r"Duração média estimada:\s*(\d+)\s*dias", text)
    if m:
        avg_days = int(m.group(1))

    return avg_price, avg_days
