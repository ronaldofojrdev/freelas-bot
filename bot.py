"""Roda um ciclo: busca projetos novos, avalia com o modelo local (Ollama) e
propõe nos que passarem no critério. Pensado pra ser chamado a cada ~20 min
pelo Agendador de Tarefas do Windows (ver README.md), mas também roda solto.
"""

import csv
import os
import re
import sys
import time
import traceback
from datetime import datetime

from playwright.sync_api import sync_playwright

import bidder
import config
import scraper
import state
from ollama_client import OllamaError, evaluate_project


def log(msg):
    os.makedirs(os.path.dirname(config.LOG_FILE), exist_ok=True)
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def log_proposal(project_id, title, price, days, avg_price, avg_days):
    os.makedirs(os.path.dirname(config.PROPOSALS_CSV), exist_ok=True)
    is_new = not os.path.exists(config.PROPOSALS_CSV)
    with open(config.PROPOSALS_CSV, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if is_new:
            w.writerow(["timestamp", "project_id", "title", "price_reais", "duration_days", "avg_price", "avg_days"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), project_id, title, price, days, avg_price, avg_days])


def build_project_info(details, table, avg_price, avg_days):
    avg_price_txt = f"R$ {avg_price:.2f}" if avg_price else "não informado (projeto ainda sem propostas ou média indisponível)"
    avg_days_txt = f"{avg_days} dias" if avg_days else "não informado"
    return (
        f"Título: {details.get('title', '')}\n"
        f"Descrição: {details['description']}\n"
        f"Habilidades: {', '.join(details['skills'])}\n"
        f"Categoria: {table.get('Categoria', '')}\n"
        f"Subcategoria: {table.get('Subcategoria', '')}\n"
        f"Nível de experiência: {table.get('Nível de experiência', '')}\n"
        f"Propostas já enviadas: {table.get('Propostas', '0')}\n"
        f"Valor mínimo do projeto: {table.get('Valor Mínimo', '')}\n"
        f"Valor médio das propostas (use isso pra calcular o preço, entre 1/3 e 1/2 deste valor): {avg_price_txt}\n"
        f"Duração média estimada: {avg_days_txt}\n"
        f"Tempo restante: {table.get('Tempo restante', '')}\n"
    )


SUSPICIOUS_TEXT_PATTERNS = [
    r"\[[^\]]{1,40}\]",  # placeholders tipo [link], [nome do projeto], [exemplo]
    r"https?://", r"www\.", r"github\.com",
    r"portf[óo]lio",
    # qualquer alegação de experiência/histórico passado tende a inventar um caso que não existe
    r"j[áa]\s+(homologamos|implementamos|entregamos|fizemos|desenvolvemos|usamos|utilizamos|integramos|criamos)",
    r"(usamos|utilizamos|implementamos|fizemos|entregamos)\s+.{0,60}\s+(com\s+sucesso|em\s+outros?\s+projetos?|em\s+produ[çc][ãa]o|anteriormente)",
    r"temos\s+experi[êe]ncia\s+com\s+integra[çc][ãa]o",
    r"tenho\s+experi[êe]ncia\s+com\s+esse\s+tipo",
    r"aplica[çc][õo]es\s+complexas\s+em\s+produ[çc][ãa]o",
]


def validate_proposal_text(text):
    """Trava de código: o modelo local já inventou experiência que a conta não
    tem e deixou placeholders tipo '[links de projetos]' sem preencher — coisa
    que denuncia na hora que é gerado por bot e queima a credibilidade com o
    cliente. Em vez de confiar só no prompt, bloqueia esses padrões aqui."""
    for pattern in SUSPICIOUS_TEXT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return False, pattern
    return True, None


def enforce_price_bounds(price, avg_price):
    """Trava de código: se soubermos a média real, força o preço a ficar
    dentro de PRICE_MIN_RATIO..PRICE_MAX_RATIO dela, independente do que o
    modelo local tenha sugerido (ele já errou esse cálculo antes)."""
    if not avg_price:
        return price
    lo = avg_price * config.PRICE_MIN_RATIO
    hi = avg_price * config.PRICE_MAX_RATIO
    return max(lo, min(price, hi))


def run_once():
    if not os.path.isdir(config.PROFILE_DIR):
        log("Perfil do navegador não encontrado. Rode 'python auth_setup.py' primeiro pra logar.")
        return

    seen = state.load_seen()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            config.PROFILE_DIR,
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        page = context.new_page()

        try:
            items = scraper.list_projects(page)
        except Exception:
            log(f"Falha ao carregar a listagem de projetos:\n{traceback.format_exc()}")
            context.close()
            return

        new_items = [it for it in items if it["id"] not in seen][: config.MAX_PROJECTS_PER_RUN]

        if not new_items:
            log("Nenhum projeto novo.")
            context.close()
            return

        for item in new_items:
            pid, title, href = item["id"], item["title"], item["href"]
            try:
                details = scraper.get_project_details(page, href)
                table = details["table"]

                if scraper.matches_hard_filter(title, details["skills"], details["description"]):
                    log(f"[SKIP-filtro] {title} (id={pid}): bate com palavra-chave de design/infra bloqueada.")
                    state.mark_seen(seen, pid, "skip", "filtro de design/infra")
                    continue

                propostas_count = scraper.parse_propostas(table)
                if propostas_count >= config.SATURATION_THRESHOLD:
                    log(f"[SKIP-saturado] {title} (id={pid}): {propostas_count} propostas já enviadas.")
                    state.mark_seen(seen, pid, "skip", f"saturado ({propostas_count} propostas)")
                    continue

                # Busca a média real de preço/prazo na página de proposta ANTES de
                # perguntar pro modelo, pra ele calcular o preço com o número certo
                # (o modelo já errou esse cálculo quando só via o valor mínimo).
                bid_url = bidder.build_bid_url(href)
                page.goto(bid_url, wait_until="domcontentloaded")
                page.wait_for_timeout(1000)

                if scraper.has_existing_proposal(page):
                    log(f"[SKIP-já-proposto] {title} (id={pid}): formulário já vinha preenchido "
                        f"(proposta enviada antes, manual ou em outro ciclo). Não mexi pra não sobrescrever.")
                    state.mark_seen(seen, pid, "skip", "proposta já existente (evitado overwrite)")
                    continue

                avg_price, avg_days = scraper.get_bid_page_averages(page)

                info = build_project_info(details, table, avg_price, avg_days)
                decision = evaluate_project(info)

                if decision["decision"] != "bid":
                    log(f"[SKIP] {title} (id={pid}): {decision.get('reason', '')}")
                    state.mark_seen(seen, pid, "skip", decision.get("reason", ""))
                    continue

                price = enforce_price_bounds(float(decision["price_reais"]), avg_price)
                days = int(decision["duration_days"])
                text = decision["proposal_text"]

                ok, bad_pattern = validate_proposal_text(text)
                if not ok:
                    log(f"[SKIP-texto-suspeito] {title} (id={pid}): texto bateu no padrão bloqueado "
                        f"({bad_pattern!r}). Não enviei, vou tentar de novo no próximo ciclo. Texto: {text!r}")
                    # não marca como visto: dá outra chance ao modelo no próximo ciclo
                    continue

                success, info_result = bidder.submit_bid(page, href, price, days, text)

                if success:
                    tag = "[DRY-RUN]" if info_result.get("dry_run") else "[PROPOSTA ENVIADA]"
                    log(f"{tag} {title} (id={pid}): R$ {price:.2f} / {days} dias. "
                        f"Média do projeto: {info_result.get('avg_price')}")
                    log_proposal(pid, title, price, days, info_result.get("avg_price"), info_result.get("avg_days"))
                    state.mark_seen(seen, pid, "bid", decision.get("reason", ""))
                else:
                    log(f"[ERRO-envio] {title} (id={pid}): {info_result.get('error')}")
                    state.mark_seen(seen, pid, "error", info_result.get("error", ""))

            except OllamaError as e:
                log(f"[ERRO-modelo] {title} (id={pid}): {e}")
                # não marca como visto: tenta de novo no próximo ciclo
            except Exception:
                log(f"[ERRO] {title} (id={pid}):\n{traceback.format_exc()}")
                state.mark_seen(seen, pid, "error", "exceção não tratada")

            state.save_seen(seen)
            time.sleep(2)

        context.close()

    state.save_seen(seen)


def watch_loop(interval_seconds=1200):
    log(f"Modo contínuo: checando a cada {interval_seconds}s. Ctrl+C pra parar.")
    while True:
        run_once()
        time.sleep(interval_seconds)


if __name__ == "__main__":
    if "--watch" in sys.argv:
        watch_loop()
    else:
        run_once()
