# Briefing para Claude Code — TRK Experience

**Cole esta mensagem inteira no Claude Code na primeira interação dentro do repositório `trk-ranking-experience`.**

---

## Olá, Claude

Você está prestes a construir um pipeline automatizado de cálculo de ranking de performance para a TRK Imóveis. Este documento te dá todo o contexto que você precisa. Leia até o fim antes de propor qualquer ação.

## O que existe hoje (antes deste projeto)

O ranking TRK avalia 5 colaboradores em até 13 processos operacionais, com 30+ indicadores definidos no `manual_v4.md`. Hoje o processo é manual:

1. Pessoa baixa 15+ XLSX/CSV do Pipefy e Octadesk
2. Conversa com Claude.ai (chat) e cola os arquivos
3. Claude calcula seguindo o manual
4. Pessoa atualiza um HTML hardcoded com os números
5. Salva e abre local

Isso consome dias por edição. Existem 10 edições rodadas até hoje.

## O que você vai construir

Um pipeline Python que:

1. **Puxa via API**: Pipefy (GraphQL) e Octadesk (REST) — 12 pipes + conversas/tickets/avaliações
2. **Calcula**: aplica as 30+ regras do `manual_v4.md` em DataFrames pandas
3. **Valida**: compara com `baselines.json` (10ª Edição, validada)
4. **Gera**: um `dados/atual.json` com a estrutura `PESSOAS / IMOVEIS / PROC_RICH`
5. **O painel HTML** (também neste repo, em `docs/index.html`) lê esse JSON via fetch

Depois, isso vira **5 routines do Claude Code**: snapshot diário 02h, resumo semanal segunda 08h, fechamento mensal dia 1 06h, API sob demanda, validação semanal sexta.

## Arquivos que você tem como referência

- **`manual_v4.md`** — manual técnico das regras de cálculo. **FONTE DA VERDADE para regras.** Todas as fórmulas, pesos, cutoffs, exclusões estão aqui.
- **`baselines.json`** — resultado validado da 10ª Edição com numerador/denominador de cada indicador. **FONTE DA VERDADE para teste de regressão.**
- **`calculate.py`** — esqueleto com as funções já estruturadas. Você completa.
- **`README.md`** — visão geral do projeto.
- **`.env`** — tokens do Pipefy e Octadesk (não commitado, leia via `os.getenv`)

## Fases do trabalho (siga estritamente nessa ordem)

### Fase 1 — Descoberta (você não escreve produção, só explora)

1. Liste todos os pipes da organização TRK via query GraphQL do Pipefy.
2. Para cada um dos 12 pipes do ranking, faça uma query introspectiva listando todos os campos (nome humano + field_id interno).
3. Cruze com o manual: para cada indicador do manual, identifique qual `field_id` corresponde.
4. Salve o resultado em `config/pipes.json` (id + nome de cada pipe) e `config/fields_map.json` (mapa indicador → field_id por pipe).
5. **PAUSE e me pergunte** se há ambiguidades antes de seguir.

### Fase 2 — Extração

Escreva 2 módulos:

- **`pipeline/extract_pipefy.py`** — funções `extract_pipe(pipe_name) -> pd.DataFrame`. Cada DataFrame deve ter as colunas que o manual referencia (mesmos nomes humanos dos XLSX de hoje). Paginar de 50 em 50, respeitar rate limit (~30 req/min), tratar `phases_history` para calcular "Primeira vez que entrou na fase X" e "Última vez que saiu da fase X" (porque essas colunas dos XLSX são derivadas).

- **`pipeline/extract_octadesk.py`** — funções `extract_conversas()`, `extract_tickets()`, `extract_avaliacoes_tickets()`. Mesmos nomes de coluna dos XLSX `Total_de_conversas-XX.xlsx`, `Tickets_totais-XX.xlsx`, `Avaliacoes-TICKET.xlsx`.

**Importante:** o `calculate.py` deve ser **agnóstico à origem dos dados**. Ele recebe DataFrames com nomes de coluna iguais aos dos XLSX atuais. Isso permite que no futuro alguém troque a extração sem mexer no cálculo.

### Fase 3 — Cálculo

Complete o `calculate.py`. Cada função `calc_<colaborador>_<processo>()` retorna o score do processo para aquele colaborador. A estrutura já está esboçada — você preenche.

**Regras críticas (releia no manual):**

1. **Cutoff 180 dias** rolando — `hoje - 180`, não data fixa. Exceções: Caio Cont.ADM (01/03/2026 fixo) e DIRF/DARF (filtro Ano: 2025 com cutoff 29/05/2026 — prorrogação oficial).
2. **Horas úteis** = 08-18 seg-sex. Implementar função `horas_uteis(inicio, fim)` cuidadosamente.
3. **Excluir rascunhos** sempre (qualquer campo contendo "rascunho" case insensitive).
4. **Timestamps negativos** = 0h (cumprido ✓), não excluir do denominador.
5. **Bônus** usa fórmula `(score + N) / (peso + N) × 10`, não soma simples.
6. **Nota final** = média simples das notas de processo não-nulas, NUNCA soma ponderada global.

### Fase 4 — Validação

`pipeline/validate.py`:
1. Carrega `baselines.json`
2. Roda o pipeline contra dados atuais
3. Compara nota final de cada colaborador. Tolerância: ±0.05.
4. Para cada indicador, compara numerador/denominador. Tolerância: ±1 caso (porque a janela 180d rola).
5. Reporta divergências em ordem de impacto.

Se a nota final não bater, investigue qual indicador divergiu antes de sugerir mudanças no código. Provavelmente é problema de mapeamento de field_id ou de fase.

### Fase 5 — Painel

1. Leia o HTML da 10ª Edição (está em `docs/index_v10_original.html`).
2. Identifique os 3 blocos `const PESSOAS`, `const IMOVEIS`, `const PROC_RICH`.
3. Substitua os 3 blocos por um `fetch('./dados/atual.json')` no início do script.
4. Salve como `docs/index.html`.
5. Gere `docs/dados/atual.json` com a estrutura completa.

### Fase 6 — Routines

Crie 5 arquivos em `routines/`:
- `snapshot_diario.md`
- `resumo_semanal.md`
- `fechamento_mensal.md`
- `recalcular.md`
- `validacao_semanal.md`

Cada um é um prompt que vai dentro da configuração da routine no Claude Code on the web.

## Decisões já tomadas

- Cadência: snapshot diário, edições mensais (dia 1)
- Painel hospedado em GitHub Pages público
- Tokens em `.env` local + secrets do Claude Code routines
- **Marinho Produtividade m²/h** está temporariamente desativado: implementar a função, mas com flag `INDICADORES_ATIVOS["marinho_produtividade"] = False` em `config/feature_flags.json`. Enquanto desativado, o peso do Laudo é 10 (consolidando o peso de Produtividade). Quando religar, peso volta para 4+6=10 distribuído.
- **DIRF/DARF cutoff**: 29/05/2026 (prorrogação oficial — não usar 01/05)
- Email destino: o configurado em Claude Code settings

## Pontos onde você DEVE me perguntar antes de decidir

1. Ambiguidades no mapeamento field_id ↔ nome humano do manual.
2. Quando encontrar regras do manual que parecem contradizer o painel da 10ª Edição.
3. Qualquer caso de "alugado antes de re-anunciar" (manual §4.1) que precise validação manual do bônus Caio.
4. IDs de pipes — me mostre a lista que veio do Pipefy e eu confirmo cada um.
5. Qualquer decisão arquitetural que mude o que está nesse documento.

## Pontos onde você NÃO precisa perguntar

1. Estruturação interna do código (módulos, classes, funções privadas).
2. Tratamento de erros, logging, paginação.
3. Otimizações de performance.
4. Escolha de bibliotecas (pandas, requests, etc são padrões).
5. Format ação de código (use black).

## Resultado esperado da 10ª Edição (teste de regressão)

Quando você rodar o pipeline contra os dados atuais do Pipefy/Octadesk, deve reproduzir aproximadamente:

| Colaborador | Nota | Posição |
|---|---|---|
| Caio | 5,48 ± 0,05 | 1º |
| Vivianne | 5,22 ± 0,05 | 2º |
| Marinho | 4,76 ± 0,05 | 3º |
| Natália | 3,98 ± 0,05 | 4º |
| Gardênia | 3,97 ± 0,05 | 5º |

Detalhamento de cada indicador está em `baselines.json`.

**Atenção**: como a janela 180d rola diariamente, números EXATOS podem variar 1-2 casos por indicador. O critério de "OK" é nota final dentro da tolerância e ranking preservado.

## Vamos começar?

Por favor, primeira ação: leia `manual_v4.md` inteiro e `baselines.json` inteiro. Depois me mostre um resumo em 5 bullets do que entendeu e me pergunte se pode iniciar a Fase 1.
