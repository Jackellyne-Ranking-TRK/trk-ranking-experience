# RELATÓRIO FINAL — 11ª EDIÇÃO DO RANKING TRK EXPERIENCE

**Data:** 14/05/2026
**Pipeline:** 100% Pipefy + Octadesk + Imobiliar (local, sem API externa)
**Snapshot:** `painel/dados/atual.json` (16.081 bytes)

---

## NOTAS FINAIS

| Pos | Nome | Nota 11ª | Nota 10ª | Δ | Bônus aplicado |
|----:|------|---------:|---------:|---:|----------------|
| 1 | Caio Rodrigues Lima | **5,34** | 5,48 | -0,14 | N=3 em Com. Locação |
| 2 | Vivianne Fontes | **5,01** | 5,22 | -0,21 | N=61 em Inadimplência |
| 3 | Gardênia | **4,10** | 3,97 | +0,13 | N=5 em Cont. ADM |
| 4 | Natália Teixeira | **4,02** | 3,98 | +0,04 | N=5 em Cont. ADM |
| 5 | Albérico Marinho | **3,91** | 4,76 | -0,85 | — |

---

## DETALHAMENTO POR COLABORADOR

### 1. Caio Rodrigues Lima — 5,34 (Comercial)

| Processo | Nota | Indicadores |
|---|---:|---|
| Com. Locação | 5,53 | Início 7/41 · Anúncio 26/66 · Coluna 15/27 · **bônus N=3** |
| Cont. Locação | 7,29 | Ocupação 5/6 · Documentação 24/42 |
| Cont. ADM | 4,00 | NIDO 2/5 |
| Renovação | 2,89 | Avaliação >90d 11/38 |
| WhatsApp | 6,71 | Resposta ≤5min 1194/2396 · Avals 139/154 |
| Ticket | 6,19 | SLA 749/1738 · Avals 20/23 |

**Bônus N=3** (IM39, IM123, IM135 — continuação da 10ª). 15 novos candidatos validados pela gestora e **todos descartados** (11 por publicação anterior fora do recorte, 4 por entrada direta em ADM). IM1567 da 10ª saiu da janela 180d.

Drifts vs 10ª:
- Indicadores Pipefy: TODOS dentro de ±1 (drift natural).
- WhatsApp/Tickets: pequeno crescimento natural do dataset (~+2/+4 dos casos).

### 2. Vivianne Fontes — 5,01 (BackOffice · Inadimplência)

| Processo | Nota | Indicadores |
|---|---:|---|
| Cont. ADM | 4,07 | Confecção 11/27 |
| Rescisão ADM | 2,00 | Encerramento 1/5 |
| Cont. Locação | 7,90 | NIDO 11/34 · Confecção 36/42 |
| Rescisão Loc. | 5,69 | Taxas Prop 10/20 · Taxas Final 13/20 |
| Renovação | 2,73 | Confecção 11/23 · Finalização 2/18 |
| Inadimplência | 9,80 | Cobrança 240/275 · CredPago 12/14 · Negativação 1/16 · **bônus N=61** |
| BackOffice | 5,78 | Concluído 103/148 · Troca Tit 13/29 |
| Ticket | 3,69 | SLA 106/288 |

Drifts vs 10ª:
- Inadimplência ★ N: **61 vs 124** (drift -63 INTENCIONAL pela regra 11ª — ver mudanças de metodologia).
- Indicadores Pipefy: 3-4 com drift natural Δ≤+3.
- Renovação Confecção: 11/23 vs 9/21 (+2/+2 drift natural).

### 3. Gardênia — 4,10 (Assessora)

| Processo | Nota | Indicadores |
|---|---:|---|
| Cont. ADM | 2,86 | Conferência 0/12 · **bônus N=5** |
| Rescisão ADM | 0,00 | Repasse 0/2 · Distrato 0/5 |
| Rescisão Loc. | 7,67 | Boleto prop 7/12 · Boleto final 8/9 |
| Reparos | 4,87 | Orçamento 51/73 · Pós-venda 15/44 |
| Renovação | 4,00 | Contato >60d 5/15 · Assinado 4/9 |
| BackOffice | 0,00 | Pendência 0/10 |
| DIRF/DARF | 3,33 | Concluído 2/6 |
| WhatsApp | 8,71 | Resposta 1791/2190 · Avals 169/178 |
| Ticket | 4,93 | SLA 73/202 · Avals 5/8 |

**Bônus N=5** (anteriormente N=6 — fix do array vazio em "Criar Card de Vistoria Técnica": IM1845 excluído).

Drifts vs 10ª: pequenos (+1 a +5 casos) — todos compatíveis com janela rolando.

### 4. Natália Teixeira — 4,02 (Assessora)

| Processo | Nota | Indicadores |
|---|---:|---|
| Cont. ADM | 4,44 | Conferência 2/12 · **bônus N=5** |
| Rescisão ADM | 0,00 | Repasse 0/2 · Distrato 0/2 |
| Rescisão Loc. | 4,69 | Boleto prop 5/8 · Boleto final 2/5 |
| Reparos | 4,90 | Orçamento 41/52 · Pós-venda 14/53 |
| Renovação | 1,59 | Contato 3/13 · Assinado 1/9 |
| BackOffice | 0,00 | Pendência 0/2 |
| DIRF/DARF | 4,19 | Concluído 14/31 |
| WhatsApp | 9,04 | Resposta 1805/2091 · Avals 137/144 |
| Ticket | 6,98 | SLA 169/281 · Avals 19/24 |

**Bônus N=5** (IM1831, IM1827, IM1841, IM1842, IM1843).

Drifts vs 10ª: Reparos Pós-venda 14/53 vs 15/51 (Δok=-1, Δtot=+2) — drift natural assimétrico.

### 5. Albérico Marinho — 3,91 (Vistoriador)

| Processo | Nota |
|---|---:|
| Vistorias (Laudo + Contestações) | 3,91 |

Indicadores:
- Laudos entregues ≤24h: 28/46 (baseline 28/36) — Δtot=+10 **DRIFT DE MODELO INTENCIONAL**.
- Contestações respondidas <24h: 4/23 (idêntico ao baseline).

---

## MUDANÇAS DE METODOLOGIA NA 11ª ED

A documentar no manual v5:

### 1. Marinho · Vistorias — Laudo conta tempo até saída da fase
Cards parados em "Em produção" depois do laudo entregue contam como atraso operacional.
**Justificativa:** o Marinho deve fechar o card no Pipefy assim que entrega o laudo — métrica é educativa, força disciplina de uso da ferramenta. A 10ª Ed excluía implicitamente esses casos.
**Impacto:** Δtot=+10 cards no denominador (esperado). Documentado em `baselines.json._aviso_drift_modelo`.

### 2. Vivianne · Inadimplência — Bônus por cobrança PROATIVA
Bônus só conta se a Vivianne abriu o card de cobrança **ANTES ou NO MESMO DIA** do pagamento (proativa) E a multa for compatível com atraso (≤15% do valor — exclui rescisões).
**Justificativa:** a 10ª Ed contava qualquer boleto com encargo pago antes do repasse, incluindo casos onde a Vivianne abriu o card depois (reativa). A nova regra reflete cobrança ativa real.
**Impacto:** N=124 → N=61, drift -63 INTENCIONAL. Documentado em `config/bonus_vivianne.json._aviso_drift_vs_baseline`.

### 3. Caio · Comercial — Bônus N=3 (revisão da 10ª + descarte de novos)
Continua os 3 IMs validados na 10ª (IM39, IM123, IM135). IM1567 saiu da janela 180d. 15 candidatos novos foram analisados pela gestora e descartados (11 por publicação anterior; 4 por entrada direta em ADM).
**Impacto:** N=4 → N=3 (perdeu IM1567).
Documentado em `config/bonus_caio.json.edicao_11_descartados`.

### 4. Gardênia · Cont. ADM — Fix de array vazio
"Criar Card de Vistoria Técnica" com valor `'[]'` (array vazio em formato string) era contado como preenchido. Agora exige conteúdo real.
**Impacto:** N=6 → N=5 (IM1845 excluído).

### 5. Assessoras · Rescisão Loc. — Refino da ordem de prioridade
Para identificar quando a assessora assumiu o caso, prioridade: (1) campo "Data do recebimento das chaves:" (com dois-pontos); (2) firstTimeIn da fase "CHAVES RECEBIDAS"; (3) fallback antigo (Vistoria recebida / Agendamento de vistoria out).
**Impacto numérico:** zero — a regra (2) não foi disparada nos dados atuais (todos os cards com fase preenchida também têm o campo). Salvaguarda implementada para o futuro.

---

## OFFs REAIS

**0** OFFs reais (bugs de modelo). ✓

Todos os deltas vs baseline 10ª têm explicação documentada (drift natural ou mudança de regra confirmada pela gestora).

---

## DRIFTS NATURAIS ACEITOS (10ª → 11ª Ed)

| Colaborador | Indicador | Calc | Baseline | Classificação |
|---|---|---|---|---|
| Vivianne | Renovação Confecção <4h | 11/23 | 9/21 | drift natural (+2/+2) |
| Vivianne | Inadimplência Cobrança <24h | 240/275 | 238/272 | drift natural (+2/+3) |
| Vivianne | Rescisão Loc. Taxas Final | 13/20 | 11/18 | drift natural (+2/+2) |
| Vivianne | BackOffice Concluído <24h | 103/148 | 101/146 | drift natural (+2/+2) |
| Natália | Reparos Pós-venda ≤7d | 14/53 | 15/51 | drift natural (-1/+2) |
| Caio | Tickets SLA | 749/1738 | 706/1686 | drift natural Octadesk (+43/+52) |
| Caio | WhatsApp Avals | 139/154 | 137/152 | drift natural Octadesk (+2/+2) |
| Outros indicadores | — | — | — | dentro de ±1 caso |

Total: **7 indicadores com drift natural aceito**, todos com ratio (%) próximo da baseline.

---

## MUDANÇAS DE MODELO COM IMPACTO INTENCIONAL

| Pessoa | Indicador | Δ | Origem |
|---|---|---|---|
| Marinho | Laudos ≤24h denominador | +10 cards | Regra 11ª (cards parados contam) |
| Vivianne | Bônus Inadimplência N | -63 (124→61) | Regra 11ª (cobrança proativa) |
| Caio | Bônus Comercial N | -1 (4→3) | IM1567 saiu da janela |
| Gardênia | Bônus Cont. ADM N | -1 (5→4 baseline, +1 11ª = 5) | Fix array vazio + drift |

---

## STATUS GERAL

**✓ Pipeline 100% operacional e pronto para Fase 5 (painel HTML)**.

Componentes:
- ✓ `pipeline/extract_pipefy.py` — 12 pipes Pipefy via GraphQL (cache em `dados/raw/`)
- ✓ `pipeline/extract_octadesk.py` — XLSX local de `dados/octadesk/` (Conversas, Tickets, Avaliações)
- ✓ `pipeline/extract_imobiliar.py` — CSVs Imobiliar com parser custom (multi-record)
- ✓ `calculate.py` — 30+ funções calc com regras do manual v4 + ajustes 11ª Ed
- ✓ `pipeline/validate.py` — comparação automática contra `baselines.json`
- ✓ `pipeline/run.py` — orquestrador end-to-end, gera `painel/dados/atual.json`

Configs persistidos para auditoria:
- ✓ `config/bonus_caio.json` (4 IMs 10ª, 3 continuação 11ª, 15 descartados com motivo)
- ✓ `config/bonus_vivianne.json` (N=61, regra R1+R2+R3, drift documentado)
- ✓ `baselines.json` (com `_aviso_drift_modelo` para Marinho)

Limitações conhecidas (não-bloqueantes para Fase 5):
- `painel/dados/atual.json` tem `IMOVEIS={}` e `PROC_RICH={}` vazios — drilldown por imóvel/processo fica para iteração futura.
- 38 cards no pipe Inadimplência sem "Vencimento 1º Boleto:" preenchido — Vivianne pode revisar.
- 8 cards Rescisão Loc. de cada assessora sem nenhum dos campos de chaves preenchidos — usam fallback antigo.

**Aprovado para iniciar Fase 5: criar `painel/index.html` (novo) consumindo `painel/dados/atual.json`, preservando `painel/index_v10_original.html` como referência.**
