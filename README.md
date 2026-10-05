# freelas-bot

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

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

## Problemas que apareceram e como resolvi

**Proposta saindo 100 vezes mais cara.** O campo "Sua oferta" do site tem uma máscara de moeda. Digitar em cima de um valor que já estava no campo fazia a oferta sair cerca de 100 vezes maior que a calculada. Passei a limpar o campo antes de digitar e, antes de enviar, ler de volta o que ficou escrito e comparar com o valor calculado. Se não bater, o envio é cancelado e o erro vai para o log (`bidder.py`).

**O modelo inventando experiência.** O modelo local escrevia frases como "já fizemos um projeto parecido" sobre casos que nunca existiram, e às vezes deixava placeholders como "[links de projetos]" sem preencher. Pedir no prompt para não fazer isso não bastou. Então `validate_proposal_text` (`bot.py`) procura esses padrões no texto gerado e descarta a proposta se encontrar algum, em vez de confiar na obediência do modelo.

**Preço fora da realidade.** O modelo de 7B errava a conta do preço. O bot lê o valor médio real das propostas já enviadas ao projeto e, depois da resposta do modelo, força a oferta a ficar dentro de uma faixa proporcional a essa média (`enforce_price_bounds`).

**Projetos saturados.** Com muitas propostas já enviadas, a chance é baixa e o esforço é o mesmo. Projetos acima de um limite de propostas são pulados antes de gastar uma chamada ao modelo.

A lição que ficou: com um modelo pequeno, o que não pode dar errado tem de ser garantido pelo código, e o prompt serve só para o que tolera erro.

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
