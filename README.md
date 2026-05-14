# TRK Experience — Setup do Pipeline Automatizado

Sistema que substitui o processo manual atual (baixar XLSX, calcular, atualizar HTML) por um pipeline automatizado que roda diariamente, puxa dados das APIs do Pipefy e Octadesk, aplica as regras do manual v4 e mantém o painel sempre atualizado.

---

## Arquitetura final

```
Pipefy API ─┐
            ├─→ Pipeline Python ─→ dados/atual.json ─→ Painel HTML (GitHub Pages)
Octadesk ──┘         ↑
                     │
            Claude Code Routines
            (rodando na nuvem da Anthropic)
            ─ Diária 02h: snapshot completo
            ─ Segunda 08h: resumo semanal por email
            ─ Dia 1 06h: fechamento mensal (edição oficial)
            ─ API: recalcular sob demanda
            ─ Sexta: validação manual vs código
```

**O que isso significa na prática:** após o setup, você nunca mais baixa um XLSX. O painel atualiza sozinho todo dia 02h. No dia 1 de cada mês, você recebe um email com o relatório oficial da edição.

---

## Pré-requisitos

- [ ] Conta Claude **plano Max** (você já tem)
- [ ] Tokens do Pipefy e Octadesk (você já tem)
- [ ] Computador com Windows (10 ou superior)
- [ ] Conta GitHub (vamos criar no passo 1)
- [ ] ~1 semana de trabalho distribuído (umas 6-8h totais suas)

---

## Setup passo a passo

### 1. Criar conta GitHub (5 min)

GitHub é onde o código vai morar. **É grátis** para o seu uso.

1. Vá em https://github.com/signup
2. Crie a conta com email pessoal ou de trabalho
3. Escolha plano **Free** (suficiente)
4. Confirme o email

### 2. Instalar Claude Code no Windows (10 min)

Claude Code é a CLI da Anthropic que vai escrever todo o código por você. Roda no terminal do Windows.

1. Abra o **PowerShell como Administrador** (botão direito no menu Iniciar → Terminal Admin)
2. Cole e rode:
   ```powershell
   irm https://claude.ai/install.ps1 | iex
   ```
3. Depois de instalado, rode:
   ```powershell
   claude
   ```
4. Faça login com sua conta Max
5. Pronto. Você vai usar esse mesmo comando `claude` daqui em diante.

### 3. Instalar Python no Windows (5 min)

Necessário para rodar o pipeline localmente em testes (a versão final roda na nuvem da Anthropic via routine).

1. Baixe Python 3.11+ em https://www.python.org/downloads/
2. **Importante:** marque a caixa "Add Python to PATH" antes de clicar em Install
3. Confirme abrindo PowerShell e digitando `python --version` — deve aparecer algo como `Python 3.11.x`

### 4. Criar o repositório do projeto (5 min)

1. No GitHub, clique no `+` no canto superior direito → **New repository**
2. Nome: `trk-ranking-experience`
3. Descrição: "Pipeline automatizado de ranking de performance TRK Imóveis"
4. Visibilidade: **Public** (necessário para GitHub Pages grátis)
5. Marque: "Add a README file"
6. **NÃO** adicione .gitignore nem licença ainda
7. Clique em **Create repository**

### 5. Clonar o repo na sua máquina (3 min)

```powershell
cd $HOME\Documents
git clone https://github.com/SEU-USUARIO/trk-ranking-experience.git
cd trk-ranking-experience
```

Substitua `SEU-USUARIO` pelo seu nome de usuário GitHub.

### 6. Adicionar os arquivos deste kit (5 min)

Copie estes 4 arquivos para dentro da pasta `trk-ranking-experience`:

- `README.md` (este arquivo) — sobrescreve o do GitHub
- `prompt_inicial.md` — briefing para o Claude Code
- `calculate.py` — esqueleto do pipeline
- `baselines.json` — teste de regressão (10ª Edição)
- `manual_v4.md` — o manual técnico que você já tem

### 7. Guardar os tokens com segurança (10 min)

**Nunca** commite tokens no GitHub. Crie um arquivo `.env` local (que o Git ignora):

1. Na pasta do projeto, crie um arquivo chamado `.env.example`:
   ```
   PIPEFY_TOKEN=cole_seu_token_aqui
   OCTADESK_TOKEN=cole_seu_token_aqui
   ```

2. Copie ele para `.env` e preencha com os tokens reais:
   ```powershell
   copy .env.example .env
   notepad .env
   ```

3. Crie um arquivo `.gitignore` na pasta do projeto com este conteúdo:
   ```
   .env
   __pycache__/
   *.pyc
   .vscode/
   dados/raw/
   ```

4. Commit inicial:
   ```powershell
   git add .
   git commit -m "Setup inicial: kit de arquivos"
   git push
   ```

   Se pedir login, use o GitHub CLI ou Personal Access Token (siga as instruções na tela).

### 8. Primeira execução do Claude Code (30 min)

Esta é a parte importante. Você vai abrir o Claude Code dentro da pasta do projeto e mandar ele ler o `prompt_inicial.md`.

```powershell
cd $HOME\Documents\trk-ranking-experience
claude
```

Quando o Claude Code abrir, cole esta primeira mensagem:

> Olá. Leia o arquivo `prompt_inicial.md` e me mostre que entendeu o projeto.
> Depois, espere meu OK para começar a Fase 1 (mapeamento de pipes e fields).

Ele vai ler tudo, te dar um resumo, e perguntar se pode começar.

### 9. Fase 1 — Mapeamento de pipes e fields (1-2h)

Claude Code vai:
- Listar todos os 12 pipes do seu Pipefy via API
- Para cada pipe, descobrir o `field_id` de cada campo que o manual usa
- Salvar tudo em `config/pipes.json` e `config/fields_map.json`

Você só vai precisar **confirmar** quando ele perguntar coisas tipo "achei 14 pipes, esses 12 são os do ranking? confirme cada um".

### 10. Fase 2 — Pipeline de extração e cálculo (3-4h)

Claude Code vai escrever:
- `pipeline/extract_pipefy.py` — puxa cards de cada pipe com paginação
- `pipeline/extract_octadesk.py` — puxa conversas, tickets, avaliações
- `pipeline/calculate.py` — aplica as 30+ regras do manual
- `pipeline/validate.py` — compara resultado com `baselines.json`
- `pipeline/run.py` — orquestra tudo

### 11. Fase 3 — Validação contra 10ª Edição (1h)

Rode local:
```powershell
python pipeline/run.py --modo teste
```

O script vai puxar dados, calcular, e comparar com `baselines.json`. Se as notas finais baterem com tolerância ±0,05, está correto:
- Caio 5,48 ± 0,05
- Vivianne 5,22 ± 0,05
- Marinho 4,76 ± 0,05
- Natália 3,98 ± 0,05
- Gardênia 3,97 ± 0,05

Se não bater, Claude Code vai investigar qual indicador divergiu.

### 12. Fase 4 — Adaptar o painel HTML (30 min)

Hoje seu `index.html` tem dados hardcoded. Vamos trocar por leitura dinâmica.

Claude Code vai pegar seu HTML atual da 10ª Edição, fazer uma mudança mínima no JS:

```javascript
// Antes:
const PESSOAS = [{id:"caio", nota:5.48, ...}];

// Depois:
const dados = await fetch('./dados/atual.json').then(r => r.json());
const PESSOAS = dados.PESSOAS;
const IMOVEIS = dados.IMOVEIS;
const PROC_RICH = dados.PROC_RICH;
```

E vai criar a estrutura `painel/index.html` + `painel/dados/atual.json` no repo.

### 13. Fase 5 — Publicar no GitHub Pages (10 min)

1. No GitHub, vá no repositório → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main` · Folder: `/painel`
4. Salve.
5. Em ~2 min, o painel vai estar em `https://SEU-USUARIO.github.io/trk-ranking-experience/`

Compartilhe essa URL com a equipe TRK.

### 14. Fase 6 — Configurar as 5 routines (30 min)

Acesse https://claude.ai/code → **Routines** → **New routine**.

Configure cada uma:

#### Routine 1 — Snapshot diário
- **Tipo:** Scheduled
- **Cadência:** Daily 02:00
- **Repo:** `trk-ranking-experience`
- **Prompt:** Veja `routines/snapshot_diario.md` no repo

#### Routine 2 — Resumo semanal
- **Tipo:** Scheduled
- **Cadência:** Monday 08:00
- **Prompt:** Veja `routines/resumo_semanal.md`

#### Routine 3 — Fechamento mensal
- **Tipo:** Scheduled
- **Cadência:** Monthly day 1, 06:00
- **Prompt:** Veja `routines/fechamento_mensal.md`

#### Routine 4 — Recalcular sob demanda
- **Tipo:** API
- **Prompt:** Veja `routines/recalcular.md`
- Anote o endpoint URL e o token — você vai usar para criar o botão "Atualizar" no painel.

#### Routine 5 — Validação manual vs código
- **Tipo:** Scheduled
- **Cadência:** Friday 17:00
- **Prompt:** Veja `routines/validacao_semanal.md`

---

## Rotina mensal — Atualizar arquivos externos

Antes de rodar a edição mensal (ou sempre que quiser um snapshot novo do painel), baixar manualmente os arquivos do Octadesk e do sistema Imobiliar para as pastas locais. O pipeline lê esses arquivos diretamente — não consulta API.

### Octadesk → pasta `dados/octadesk/`

Baixar os 3 relatórios mais recentes do dashboard Octadesk e salvar com nomes em formato `Nome-AAAAMMDD-HHMM.xlsx` (o pipeline pega sempre o mais recente em ordem alfabética):

| Arquivo | Origem no Octadesk |
|---|---|
| `Total_de_conversas-AAAAMMDD-HHMM.xlsx` | Relatórios → Conversas WhatsApp |
| `Tickets_totais-AAAAMMDD-HHMM.xlsx` | Relatórios → Tickets |
| `Avaliacoes-TICKET-AAAAMMDD-HHMM.xlsx` | Relatórios → Avaliações de Ticket |

Se a pasta estiver vazia, o pipeline ignora WhatsApp/Tickets (indicadores ficam zerados, mas o painel continua funcionando).

### Imobiliar → pasta `dados/csv/`

Exportar os 3 relatórios do sistema Imobiliar (encoding latin-1, separador `;`):

| Arquivo | Uso |
|---|---|
| `Relatorio_de_Boletos_Quitados.csv` | Bônus Inadimplência (Vivianne) |
| `Relatorio_De_proprietarios.csv` | Cruzamento por proprietário |
| `Relatorio_de_Imoveis.csv` | Cruzamento por IM |

Se faltar qualquer um dos 3, o bônus Inadimplência sai como N=0.

### Segurança

Ambas as pastas são **gitignored** — nunca commitar dados de cliente/financeiro.

### Quando a API entrar

Cada um dos `pipeline/extract_octadesk.py` e `pipeline/extract_imobiliar.py` pode ser substituído por um leitor de API sem mexer em mais nenhum arquivo do pipeline. A interface (dict de DataFrames) permanece a mesma.

---

## Configurações de email

Para receber os emails:

1. No Claude Code on the web, vá em **Settings** → **Notifications**
2. Confirme o email cadastrado
3. Em cada routine, defina **Notify on completion: email**

---

## Como rodar manualmente quando quiser

Local (na sua máquina, para testes):
```powershell
cd $HOME\Documents\trk-ranking-experience
python pipeline\run.py
```

Via routine API (de qualquer lugar):
```powershell
curl -X POST https://api.claude.com/routines/SEU_ID/run `
     -H "Authorization: Bearer SEU_TOKEN_ROUTINE"
```

---

## O que esperar de prazo

| Etapa | Prazo realista |
|---|---|
| Passos 1-7 (setup básico) | 1 dia, ~1h |
| Passos 8-9 (mapeamento) | 1 dia, ~2h |
| Passo 10 (pipeline) | 2-3 dias, ~4h |
| Passos 11-12 (validação + painel) | 1 dia, ~2h |
| Passos 13-14 (deploy + routines) | 1 dia, ~1h |
| **Total** | **~1 semana, ~10h sua** |

Resto do tempo o Claude Code está escrevendo código sozinho. Você só revisa e confirma.

---

## Suporte

Se algo der errado no setup, abra o Claude Code dentro da pasta do projeto e descreva o problema. Ele tem acesso a todos os arquivos, ao manual, ao baselines, e vai te ajudar a debugar.

Para dúvidas sobre as regras de cálculo: o `manual_v4.md` é a fonte da verdade.

Para dúvidas sobre arquitetura: este README é a fonte da verdade.

---

## Decisões já tomadas (não revisitar)

- **Cadência:** snapshot diário, edições mensais (dia 1)
- **Hospedagem painel:** GitHub Pages público
- **Linguagem:** Python 3.11+
- **Onde tokens ficam:** secrets do Claude Code routines + `.env` local
- **Marinho Produtividade m²/h:** código implementa mas com flag `ativo=False` (decisão temporária, pode religar a qualquer momento)
- **DIRF/DARF cutoff:** 29/mai/2026 (prorrogação oficial)
- **Email destino:** o configurado em Claude Code settings
