# Taxa 120 — RPA de Lançamento de Taxas de Condomínio

Sistema de automação que lê boletos de condomínio recebidos por e-mail, extrai os dados via PDF, mapeia cada imóvel no sistema Imobiliar e lança as taxas automaticamente — eliminando o processo manual de digitação. Suporta múltiplas imobiliárias com lógica de extração e similaridade isolada por administradora.

---

## Sumário

- [Como funciona](#como-funciona)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Endpoints](#endpoints)
- [Refatoração](#refatoração)

---

## Como funciona

O fluxo completo é disparado via API e segue cinco etapas:

```
POST /taxa-120/imobiliaria/<cnpj>
        │
        ▼
1. Infraestrutura    → abre túnel Cloudflare, lê inbox de e-mail, separa PDFs
        │
        ▼
2. DE-PARA / LANÇAR TAXAS          → extrai cada boleto, calcula similaridade e mapeia imóvel
        │
        ▼
3. Banco             → carrega tabela de taxas e id da administradora
        │
        ▼
4. Imobiliar         → login → lança taxas por boleto → logout
        │
        ▼
5. Relatório         → gera Excel operacional e envia por e-mail
```

---

## Estrutura do projeto

```
app/
├── classes/
│   ├── boleto.py              # Modelo de dados do boleto extraído do PDF
│   └── log.py                 # Modelo de dados de um evento de log
│
├── core/
│   └── logger_service.py      # Serviço de log: expõe .sucesso(), .erro(), .alerta()
│
├── imobiliarias/
│   ├── registry.py            # Mapeia CNPJ → {config, extrator, matcher} da imobiliária
│   │
│   ├── barcellos/
│   │   ├── config.py          # Parâmetros fixos: nome, caminhos, limiares de similaridade
│   │   ├── extrator.py        # Lê o PDF e retorna objeto boleto estruturado
│   │   ├── fatura.py          # Modelo de dados da fatura/boleto da Barcellos
│   │   ├── matcher.py         # Calcula similaridade entre boleto e imóveis do Imobiliar
│   │   ├── normalizar_taxas.py# Padroniza nomes e valores de taxas
│   │   └── recibo.py          # Modelo de dados do recibo
│   │
│   └── fontenova/
│       ├── config.py #  Parâmetros fixos: nome, caminhos, limiares de similaridade
│       ├── extrator.py # Lê o PDF e retorna objeto boleto estruturado
│       ├── matcher.py # Calcula similaridade entre boleto e imóveis do Imobiliar
│       ├── normalizar_taxas.py # Padroniza nomes e valores de taxas
│       ├── recibo_pagador.py # Modelo de dados da recibo/boleto da Fonte Nova
│       └── virtualimobi.py   # Modelo de dados boleto da Fonte Nova
│
├── repositories/
│   ├── conexao.py             # Fábrica de conexão psycopg2 (único lugar com credenciais)
│   ├── consultas.py           # Todas as queries SQL das tabelas taxa_120_* centralizadas
│   └── db_logger.py           # Persiste eventos de execução na tabela de logs do banco
│
├── routes/
│   ├── ping_routes.py         # Rota de healthcheck
│   └── taxa_120_routes.py     # Endpoints do fluxo principal (POST /taxa-120/imobiliaria/<cnpj>)
│
├── service/
│   ├── de_para.py             # Extrai boletos dos PDFs e mapeia imóveis via matcher + banco
│   ├── imobiliar.py           # Integração com a API do Imobiliar: login, contratos, taxas
│   ├── infraestrutura.py      # Túnel Cloudflare + leitura do inbox + separação de PDFs
│   ├── lancar_taxas.py        # Orquestrador: coordena as etapas na ordem correta
│   └── processador_boleto.py  # Lógica completa de lançamento de um único boleto
│
└── utils/
    ├── dispararEmail.py       # Envia o relatório operacional por e-mail
    ├── formatarCodigoBarras.py# Formata código de barras para padrão do Imobiliar
    ├── normalizacao.py        # Funções de normalização de datas, valores e competências
    ├── relatorio.py           # Gera o relatório operacional em Excel
    ├── separarPdfs.py         # Divide PDFs de múltiplas páginas em arquivos individuais
    └── tunel.py               # Abre e retorna o processo do túnel Cloudflare
```

---

| Método | Rota | Descrição |
|--------|------|-----------|
| `POST` | `/taxa-120/imobiliaria/<cnpj>` | Dispara o fluxo completo para a imobiliária do CNPJ |
| `GET`  | `/taxa-120/arquivo/<nome_arquivo>` | Serve um arquivo da pasta de processados |
| `GET`  | `/ping` | Healthcheck |

---

## Refatoração

Esta versão é uma refatoração do código original. As mudanças foram feitas para separar responsabilidades, centralizar o acesso ao banco e corrigir bugs silenciosos.

### Arquivos criados

| Arquivo | O que foi extraído |
|---|---|
| `app/service/infraestrutura.py` | Bloco de túnel + inbox + PDFs que estava inline em `lancar_taxas.py` |
| `app/service/processador_boleto.py` | Função `_processar_boleto` e suas constantes |
| `app/repositories/conexao.py` | `psycopg2.connect()` que se repetia em 3 arquivos diferentes |
| `app/repositories/consultas.py` | Todas as queries SQL que estavam inline nos serviços |

### Mudanças em arquivos existentes

**`lancar_taxas.py`** — reduzido a orquestrador puro. O corpo de `lancar_taxas_imobiliar` lê como um índice do fluxo, sem SQL, sem lógica de negócio.

**`de_para.py`** — funções privadas `_buscar_id_administradora`, `_inserir_boleto` e `_upsert_imovel` removidas. Equivalentes centralizadas em `consultas.py`.

**`consultas.py`** — criado do zero com duas funções de busca distintas para cada contexto de uso, evitando o mismatch de tipos de retorno (tupla vs escalar) que gerava bugs.
