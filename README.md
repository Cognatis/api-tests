# API Tests Suite

Test suite para APIs Cognatis (DataLead v1, etc.)

## 📁 Estrutura

- `scripts/` — Código de testes (notebooks, módulos Python)
- `docs/` — Documentação, exemplos, resultados

## 🚀 Começar Rápido

### DataLead v1 (Geo-enriquecimento)

```bash
cd scripts
jupyter notebook datalead_interactive.ipynb
```

Kernel: `.venv` (Python 3.12)  
Cell 0: Autenticação  
Cells 1-8: 8 exemplos prontos (CNPJ, endereços, coordenadas, buffers, filtros, etc.)

**Documentação:**
- `docs/README_DATALEAD.md` — Guia completo
- `docs/TECH_ANSWERS.md` — Respostas técnicas
- `docs/TEST_REPORT.md` — Resultados de 15 testes

## 📝 Testes Inclusos

### DataLead v1 / export/summary
- ✅ CNPJ keys (geolevel, buffer)
- ✅ Coordenadas XY (buffer)
- ✅ Endereços CEP+número (buffer, geoLevel em dimension)
- ✅ Dry-run (estimativa)
- ✅ Filtros data.where e expressions.where
- ✅ Agregação PS+EX

**Status:** 40% pass rate  
**Bugs conhecidos:**
- `data.geoLevel + addresses` → 500 NullRef (use `dimension.geoLevel`)

## 🔧 Requisitos

- Python 3.12+
- `requests`, `pandas`, `jupyter`, `ipykernel`
- Token JWT Cognatis (via Passport `/api/Token/login`)

## 📌 Próximos Passos

1. Rodar notebook interativo
2. Adaptar exemplos para seus casos de uso
3. Testar com dados reais
4. Reportar bugs/gaps em Issues

---

**Última atualização:** 2026-05-19
