import json

import requests

import config


class OllamaError(Exception):
    pass


def evaluate_project(project_info: str) -> dict:
    """Sends the project info to the local Ollama model and returns the parsed decision dict."""
    prompt = f"{config.POLICY_PROMPT}\n\nPROJETO A AVALIAR:\n{project_info}\n"

    resp = requests.post(
        config.OLLAMA_URL,
        json={
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.4},
        },
        timeout=300,
    )
    resp.raise_for_status()
    raw = resp.json().get("response", "").strip()

    try:
        decision = json.loads(raw)
    except json.JSONDecodeError as e:
        raise OllamaError(f"Modelo não retornou JSON válido: {raw[:300]!r}") from e

    if decision.get("decision") not in ("bid", "skip"):
        raise OllamaError(f"Campo 'decision' inválido: {decision!r}")

    return decision
