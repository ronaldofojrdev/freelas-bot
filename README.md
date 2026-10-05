# freelas-bot

Bot que olha os projetos novos de Web, Mobile e Software no 99Freelas, pede para um modelo de IA local decidir se vale a pena e, se valer, preenche e envia a proposta. Roda no próprio PC, sem pagar API: o modelo é o `qwen2.5:7b` servido pelo Ollama.

Comecei esse projeto para parar de perder tempo lendo anúncio por anúncio. Ele é uma ferramenta pessoal e um experimento, então leia a seção de limitações antes de usar.

## Como funciona

1. `scraper.py` abre o 99Freelas com o Playwright e lista os projetos novos, ignorando os que já viu (`state.py`).
2. `ollama_client.py` manda cada projeto para o modelo local junto com as regras de `config.py` (o que aceitar, o que descartar, faixa de preço, tom da proposta).
3. Se o modelo aceitar, `bidder.py` preenche o formulário e envia.
4. Tudo fica registrado em `logs/`.

As regras de decisão ficam em `POLICY_PROMPT`, no `config.py`. Se quiser outro critério, é lá que se mexe.

## Instalação

Precisa de Python 3.10 ou mais novo e do [Ollama](https://ollama.com) instalado.

```bash
ollama pull qwen2.5:7b

pip install -r requirements.txt
playwright install chromium
```

Faça o login uma vez. Isso abre um Chromium, você entra na sua conta e a sessão fica salva em `browser_profile/`:

```bash
python auth_setup.py
```

## Uso

Comece sempre em modo de teste. Ele avalia e preenche, mas não envia nada. Atenção: se `FREELAS_BOT_DRY_RUN` não estiver definida, o bot envia as propostas de verdade.

```bash
# Linux / macOS
FREELAS_BOT_DRY_RUN=1 python bot.py

# Windows (cmd)
set FREELAS_BOT_DRY_RUN=1 && python bot.py
```

Olhe o `logs/bot.log` para ver o que ele decidiu e por quê. Quando estiver satisfeito:

```bash
FREELAS_BOT_DRY_RUN=0 python bot.py
```

Cada execução faz um ciclo e termina. Para rodar a cada 20 minutos, use o agendador do sistema (Task Scheduler no Windows, cron no Linux) ou deixe `python bot.py --watch` aberto em um terminal.

## Limitações

- Um modelo de 7B local erra mais que um modelo grande, principalmente em contexto ambíguo e na escrita das propostas. Por isso as travas mais importantes estão no código e não no prompt.
- Antes de enviar, o bot confere se o campo de valor mostra o preço certo. O site tem uma máscara de moeda que já fez uma proposta sair 100 vezes maior; se o valor não bater, ele cancela e registra o erro.
- Se o layout do 99Freelas mudar, os seletores de `scraper.py` e `bidder.py` quebram. O bot registra o erro, mas alguém precisa ajustar.
- Automatizar o envio pode ir contra os termos de uso da plataforma. Use por sua conta e risco.

## Estrutura

```
bot.py           ciclo principal
scraper.py       leitura dos projetos
bidder.py        preenchimento e envio da proposta
ollama_client.py chamada ao modelo local
config.py        regras e prompt de decisão
state.py         controle do que já foi visto
auth_setup.py    login inicial
```
