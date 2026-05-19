# DataLead v1 API — Suite de Testes Modular

**Status:** ✅ Pronto para usar  
**Data:** 2026-05-19

---

## 📋 Arquivos Criados

### 1. test_datalead_modular.py
Script Python modular com funções reutilizáveis.

**Funções principais:**
- `load_auth()` — autentica, obtém TOKEN
- `call_summary(payload, label)` — chama API, retorna DataFrame
- `build_summary_payload()` — constrói payload
- `build_buffer_dimension()` — cria dimension.buffer
- `uso_01_*` até `uso_04_*` — casos de uso exemplos

**Usar:**
```python
from test_datalead_modular import load_auth, call_summary

TOKEN = load_auth()
df = call_summary(payload, label="Meu teste")
print(df)
```

### 2. datalead_usecases_exemplos.ipynb
Notebook Jupyter com 8 exemplos prontos.

**Exemplos:**
1. CNPJ geolevel=1
2. CNPJ + buffer
3. Coordenadas + buffer
4. Endereços + buffer
5. DRY RUN
6. **data.where** (filtro INPUT)
7. **expressions.where** (filtro AGREGAÇÃO)
8. PS + EX (agregação)

### 3. TECH_ANSWERS.md
Respostas técnicas com exemplos JSON.

### 4. Senhas Atualizadas
- enriquece_renda_setor.py → Cog2222
- test_all_usecases.py → Cog2222

---

## 🚀 Começar

### Opção A: Jupyter Interativo ⭐

```bash
# VSCode
code scripts/datalead_usecases_exemplos.ipynb

# Kernel: NTP (.venv) (canto superior direito)
# Cell 0: load_auth()
# Cell N: exemplo que quer testar
```

### Opção B: Script Puro

```bash
cd scripts
python3 test_datalead_modular.py
```

### Opção C: Seu Código

```python
from test_datalead_modular import load_auth, build_summary_payload, call_summary

TOKEN = load_auth()
payload = build_summary_payload(...)
df = call_summary(payload, label="teste")
```

---

## 📊 Estruturas JSON

### CNPJ (geolevel=1)
```json
{
  "data": {
    "keys": [33461874000103],
    "geoLevel": 1
  }
}
```

### Coordenadas + Buffer
```json
{
  "dimension": {
    "buffer": {
      "values": [
        {"distance": 3000, "alias": "3KM"},
        {"distance": 5000, "alias": "5KM"}
      ]
    }
  },
  "data": {
    "values": [
      {"id": "pt1", "x": -46.6333, "y": -23.5505}
    ]
  }
}
```

### PS + EX (agregação)
```json
{
  "expressions": {
    "select": [
      {"id": 449},              // EX
      {"id": 999, "function": "avg"}  // PS com function
    ]
  }
}
```

### data.where (filtro INPUT)
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
  }
}
```

### expressions.where (filtro AGREGAÇÃO)
```json
{
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

---

## 🎯 Próximas Ações

1. **Descobrir MODULE_PJ_ID**
```bash
curl -H "Authorization: Bearer <TOKEN>" \
  "https://dev.nettoolpro.cognatis.com.br/dev/datalead/api/v1/module/list"
```

2. **Testar notebook** — abrir em VSCode, executar Cell 0

3. **Ajustar IDs** — substituir 999 por IDs reais de PS

4. **Validar filtros** — confirmar campos com DBA

---

## 📚 Referência

- **TECH_ANSWERS.md** — respostas técnicas
- **TEST_REPORT.md** — resultados de 15 testes
- **jsonrule-querybuilder.md** — estrutura JsonRule (memória)
