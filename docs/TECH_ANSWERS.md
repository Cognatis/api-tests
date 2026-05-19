# Respostas às 3 Perguntas Técnicas — API DataLead v1

**Data:** 2026-05-19  
**Status:** Baseado em exemplos Postman + JsonRule + test_results.json  

---

## 1️⃣ Qual módulo ID para expressões PJ (business)?

**Resposta Curta:** Não achei na doc Confluence. Execute:

```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "https://dev.nettoolpro.cognatis.com.br/dev/datalead/api/v1/module/list"
```

Procure no JSON por "faturamento", "bandeira", etc.

---

## 2️⃣ Sintaxe exata para aggregation function (PS)?

**Resposta:** Adicione `function` em cada PS:

```json
{
  "expressions": {
    "select": [
      {"id": 449},                    // EX — sem function
      {"id": 999, "function": "avg"}  // PS — OBRIGATÓRIO function
    ]
  }
}
```

Funções suportadas: `"sum"`, `"avg"`, `"min"`, `"max"`, `"count"`

---

## 3️⃣ Estrutura de `data.where` e `expressions.where`?

**Resposta:** JsonRule — {field, operator, value}

```json
{
  "data": {
    "where": [
      {
        "rules": [
          {
            "field": "segmento",
            "operator": "equal",
            "value": "FARMACIA"
          }
        ],
        "condition": "and"
      }
    ]
  },
  "expressions": {
    "where": [
      {
        "rules": [
          {
            "field": "segmento_pj",
            "operator": "equal",
            "value": "FARMACIA"
          }
        ],
        "condition": "and"
      }
    ]
  }
}
```

**Diferença:**
- `data.where` → filtro na ENTRADA
- `expressions.where` → filtro na AGREGAÇÃO

---

Ver README_DATALEAD.md para exemplos completos.
