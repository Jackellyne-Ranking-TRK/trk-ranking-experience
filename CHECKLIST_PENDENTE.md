# CHECKLIST PENDENTE — TRK Ranking Experience

Última atualização: 14/05/2026 (após Fase 5 completa)

## Pendências da 11ª Edição

### Alta prioridade
- [ ] **Atualizar Manual v4 → v5** com as 5 mudanças metodológicas decididas em 14/05/2026:
  1. Marinho Vistorias — cards parados em "Em produção" contam como atraso (educativo)
  2. Vivianne Inadimplência — regra estrita R1 (multa ≤15%) + R2 (card.criado ≤ data_pag) + R3 (data_pag < data_repasse). N=124 → N=61 INTENCIONAL.
  3. Caio Comercial — bônus N=3 (continuação 10ª: IM39, IM123, IM135). 15 candidatos novos descartados pela gestora (11 com publicação anterior, 4 entrada direta em ADM).
  4. Gardênia Cont.ADM — fix de array vazio '[]' em "Criar Card de Vistoria Técnica"
  5. Rescisão ADM (Assessoras) — início = "Última vez que saiu da fase Caixa de entrada" (não mais "Criado em")
  + Rescisão Loc. — campo "Data do recebimento das chaves:" como prioridade 1 (refinamento documentado)

### Média prioridade
- [x] **Ativar GitHub Pages** — CONCLUÍDO em 15/05/2026. Pasta renomeada painel/ → docs/ via `git mv`. Repo migrado para org TRK-Imoveis. Pendente apenas: ativar manualmente em Settings → Pages → Folder: /docs.
- [ ] **Configurar routines automáticas** na nuvem Anthropic (~30 min):
  - Snapshot diário 02h
  - Resumo semanal segunda 08h
  - Fechamento mensal dia 1 06h
  - Recalcular sob demanda (API)
  - Validação semanal sexta

### Baixa prioridade
- [ ] **Comunicar Marinho** sobre regra de cards parados em "Em produção" antes da 12ª Edição (não-técnico)
- [ ] **Refazer aba "Resumo Executivo"** com análises melhores quando quiser (escondida na 11ª)
- [ ] **Renomear BASELINE_9 → BASELINE_EDICAO_ANTERIOR** no código (cosmético, sem urgência)

## Pendências técnicas de qualidade

- [ ] **Investigar 7 boletos "passaram batido"** na Vivianne (cobrados antes do repasse, sem card aberto). Informação operacional útil — pode ser oportunidade perdida ou cliente que paga sem cobrança.
- [ ] **Reativar Produtividade m²/h do Marinho** quando metas forem recalibradas em conjunto com ele.

## Para a próxima edição (12ª)

- [ ] **Atualizar pasta dados/octadesk/** com XLSX recentes (Conversas, Tickets, Avaliações)
- [ ] **Atualizar pasta dados/csv/** com 3 CSVs recentes do Imobiliar (Boletos, Proprietários, Imóveis)
- [ ] **Rodar python pipeline/run.py** (apenas comando)
- [ ] **Validar painel localmente** antes de commit
- [ ] **Validar candidatos a bônus Caio** (se houver novos IMs na lista pendente)
- [ ] **Commit + push** com mensagem da edição

---

**Como retomar:** abrir Claude Code com `claude --resume afc237db-430c-43c3-9826-f7e7ba90eac1` ou começar nova sessão e ler este arquivo.
