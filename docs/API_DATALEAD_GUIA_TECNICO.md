# DataLead API v1 — Guia Técnico de Integração

**Endpoint:** `POST /datalead/api/v1/export/summary`

---

## Visão Geral

A API DataLead realiza **enriquecimento geográfico e demográfico** de um conjunto de pontos de referência (empresas, endereços, coordenadas ou filtros dinâmicos). O cliente envia os dados de entrada e especifica quais variáveis deseja obter; a API retorna um arquivo CSV com os valores enriquecidos.

O payload é um JSON com quatro seções principais:

| Seção | Responsabilidade |
|---|---|
| `dryRun` / `formatType` / `delimiter` | Configurações gerais da extração |
| `dimension` | Unidade geográfica de agregação da saída |
| `expressions` | Variáveis a serem retornadas |
| `data` | Dado de entrada (referência para o enriquecimento) |

---

## Como montar o payload — Fluxo de decisão

Antes de construir o payload, responda estas três perguntas em ordem:

**1. Qual é minha entrada?**
→ Escolhe a tag em `data`: `keys` (CNPJs), `addresses` (endereços), `values` (coordenadas XY), `where` (filtro dinâmico) ou `file` (arquivo).

**2. Quais variáveis quero retornar?**
→ Identifique o **nível geográfico nativo** de cada variável (empresa, setor, etc.).

**3. As variáveis são todas do mesmo nível geográfico?**

- **Sim, mesmo nível** → `dimension` pode ser `null` (retorno no nível do input) ou uma dimensão para re-agregar.
- **Não, níveis diferentes** → `dimension` é **obrigatória**. Escolha `buffer` ou `geoLevel`. Variáveis mais granulares que a dimensão de saída precisam de `agg`.

---

## 1. Configurações Gerais

```json
{
  "dryRun": false,
  "formatType": "csv",
  "delimiter": "|"
}
```

### `dryRun`

| Valor | Comportamento |
|---|---|
| `true` | Retorna estimativa de custo e linhas. **Não consome cota.** |
| `false` | Executa a extração e consome cota. |

> **Boa prática:** sempre execute `dryRun: true` antes de extrações grandes para estimar o consumo antes de confirmar.

### `formatType`
Formato do arquivo de retorno. Valor suportado: `"csv"`.

### `delimiter`
Separador de colunas no CSV de retorno. Recomendado: `"|"` (pipe).

---

## 2. Dimension — Unidade Geográfica de Saída

A seção `dimension` define **como os dados de saída serão agregados geograficamente**.

### Quando usar `null`

`dimension: null` é válido **somente quando todas as variáveis do `select` são do mesmo nível geográfico** do dado de entrada. Nesse caso, cada linha do retorno corresponde a um registro de entrada.

| Entrada | Variáveis do select | Dimensão nula válida? | Saída |
|---|---|---|---|
| CNPJ | Só vars de empresa | Sim | 1 linha por CNPJ |
| CNPJ | Só vars de setor | Sim | 1 linha por CNPJ (dados do setor onde está) |
| CNPJ | Vars empresa + setor | **Não** — obrigatório declarar dimensão | — |
| Endereço / XY | Só vars de setor | Sim | 1 linha por ponto (setor onde está alocado) |
| Endereço / XY | Vars setor + empresa | **Não** — obrigatório declarar dimensão | — |
| `where` (filtro) | Só vars de setor | Sim | 1 linha por empresa filtrada |
| `where` (filtro) | Vars setor + empresa | **Não** — obrigatório declarar dimensão | — |

```json
"dimension": null
```

---

### 2.1 Buffer

Agrega os dados em anéis concêntricos ao redor de cada ponto de entrada.

```json
"dimension": {
  "buffer": {
    "values": [
      { "distance": 1000, "alias": "1KM" },
      { "distance": 3000, "alias": "3KM" },
      { "distance": 5000, "alias": "5KM" }
    ]
  }
}
```

**Regras:**
- Máximo de **5 raios** por requisição.
- `distance` em metros (inteiro), `alias` é o nome da coluna no CSV de saída.
- Os raios são **incrementais**: cada anel representa a faixa entre o raio anterior e o atual.

**Quando usar:** análise de área de influência, catchment area, estudo de mercado ao redor de pontos.

---

### 2.2 GeoLevel

Agrega os dados por uma unidade geográfica (setor censitário, bairro, município, etc.).

```json
"dimension": {
  "geoLevel": {
    "values": [
      { "id": 49, "alias": "Setor" }
    ]
  }
}
```

> Consulte `GET /datalead/api/v1/module/geolevels` para os IDs disponíveis na sua conta.

**Quando usar:** agrupamento por unidade administrativa, comparativos regionais, mix de variáveis de níveis diferentes.

---

## 3. Expressions — Variáveis de Saída

```json
"expressions": {
  "major": null,
  "moduleId": null,
  "subModule": null,
  "select": [ ... ]
}
```

| Campo | Descrição |
|---|---|
| `major` | Versão do dado. `null` retorna a mais recente. |
| `moduleId` | Solicita todas as variáveis de um módulo. Quando usado, `select` pode ser omitido. |
| `subModule` | Restringe a um submódulo. Complementa `moduleId`. |

### 3.1 Select — Variáveis individuais

```json
"select": [
  { "id": 449 },
  { "id": 6547 }
]
```

> IDs de expressão disponíveis via `GET /datalead/api/v1/module/{moduleId}/list`.

---

### 3.2 Função de Agregação (`agg`)

`agg` é obrigatório quando a variável é **mais granular** que a dimensão de saída.

**Regra:**
- Variável no **mesmo nível** que a saída → sem `agg`
- Variável **mais granular** que a saída → `agg` obrigatório
- Variável **mais agregada** que a saída → sem `agg` (o valor é herdado)

**Exemplo — saída por Setor Censitário:**

```json
"select": [
  { "id": 449 },              // var de setor → mesmo nível da saída → sem agg
  { "id": 40, "agg": "count" } // var de empresa → mais granular → agg obrigatório
]
```

> ❌ **Não adicione `agg` em variáveis já no nível da saída** — a API retornará erro 400.

**Funções disponíveis:**

| Função | Descrição |
|---|---|
| `"sum"` | Soma |
| `"avg"` | Média |
| `"min"` | Mínimo |
| `"max"` | Máximo |
| `"count"` | Contagem de registros |

---

## 4. Data — Dado de Entrada

Apenas **uma** das opções abaixo deve ser usada por requisição: `keys`, `addresses`, `values`, `where` ou `file`.

---

### 4.1 Keys — CNPJs no corpo da requisição

```json
"data": {
  "geoLevel": 1,
  "keys": [33461874000103, 5951509000133]
}
```

- Valores como **inteiros** (sem pontos, barras ou formatação).
- `geoLevel: 1` identifica o nível empresa.
- Para volumes grandes, use `file`.

---

### 4.2 Addresses — Endereços (CEP + número)

```json
"data": {
  "addresses": [
    { "recId": "loja_sp", "zipCode": 4530030,  "number": 140 },
    { "recId": "loja_rj", "zipCode": 22071900, "number": 50  }
  ]
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `recId` | string | Identificador do registro (aparece no CSV de saída) |
| `zipCode` | inteiro | CEP sem hífen |
| `number` | inteiro | Número do logradouro |

---

### 4.3 Values — Coordenadas XY (longitude/latitude)

```json
"data": {
  "values": [
    { "id": "ponto_sp", "x": -46.6333, "y": -23.5505 },
    { "id": "ponto_rj", "x": -43.1729, "y": -22.9068 }
  ]
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | string | Identificador do ponto (aparece no CSV de saída) |
| `x` | decimal | Longitude |
| `y` | decimal | Latitude |

> Use XY quando os pontos já estiverem geocodificados. É mais eficiente que `addresses` pois não aciona o serviço de geocodificação.

---

### 4.4 Where — Filtro dinâmico de empresas da base Cognatis

Use para selecionar empresas da base Cognatis aplicando filtros, sem informar CNPJs manualmente.

```json
"data": {
  "where": [
    {
      "rules": [
        {
          "id": 35,
          "value": ["BRADESCO"],
          "operator": "in",
          "geoLevelId": 1
        }
      ]
    },
    {
      "rules": [
        {
          "id": 449,
          "value": "10000000",
          "operator": "greater",
          "condition": "OR",
          "geoLevelId": 5
        }
      ]
    }
  ]
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | inteiro | ID da variável usada como critério de filtro |
| `value` | string ou lista | Valor(es). Lista para `in`/`not_in`, string para os demais |
| `operator` | string | Operador de comparação (ver tabela abaixo) |
| `geoLevelId` | inteiro | Nível geográfico da variável de filtro |
| `condition` | string | Conector entre grupos: `"AND"` (padrão) ou `"OR"` |

**Operadores:**

| Operador | Descrição |
|---|---|
| `"in"` | Valor está na lista |
| `"not_in"` | Valor não está na lista |
| `"eq"` | Igual |
| `"greater"` | Maior que |
| `"less"` | Menor que |
| `"between"` | Entre dois valores (lista com 2 elementos) |

**Lógica de combinação:**
- Múltiplas `rules` no mesmo objeto → **AND**
- Múltiplos objetos no array → **AND** por padrão; use `"condition": "OR"` no primeiro `rule` do grupo para mudar para **OR**

> `data.geoLevel` não é necessário quando `where` é utilizado — o nível é inferido pelo `geoLevelId` das regras.

---

### 4.5 File — Chaves ou Endereços via Arquivo

Para volumes grandes. O arquivo deve ser enviado previamente via endpoint de upload.

```json
"data": {
  "geoLevel": 1,
  "file": {
    "url": "cliente/uploads/798ead29b4694ebdb097931fcd4c38bd.csv",
    "provider": "GoogleCloudBucket",
    "contentType": "Keys",
    "delimiter": ";",
    "fields": { "id": "cnpj" }
  }
}
```

| Campo | Descrição |
|---|---|
| `url` | Caminho do arquivo retornado pelo endpoint de upload |
| `provider` | Provedor de storage. Valor fixo: `"GoogleCloudBucket"` |
| `contentType` | `"Keys"` (CNPJs) ou `"Addresses"` (endereços) |
| `delimiter` | Separador de colunas do arquivo enviado |
| `fields.id` | Nome da coluna do arquivo que contém as chaves de match |

---

## 5. O que não fazer

### ❌ Misturar níveis de variáveis sem declarar dimensão

Quando `select` contém variáveis de níveis geográficos diferentes (ex: empresa + setor), a `dimension` é **obrigatória**.

```json
// ERRADO — mix de níveis sem dimension
"dimension": null,
"expressions": {
  "select": [
    { "id": 449 },           // setor
    { "id": 40, "agg": "count" } // empresa
  ]
}
```

```json
// CORRETO — dimension declarada
"dimension": { "geoLevel": { "values": [{ "id": 49, "alias": "Setor" }] } },
"expressions": {
  "select": [
    { "id": 449 },
    { "id": 40, "agg": "count" }
  ]
}
```

---

### ❌ Adicionar `agg` em variáveis já no nível de saída

Variáveis que já estão no mesmo nível geográfico da dimensão de saída **não aceitam** `agg` — a API retorna erro 400.

```json
// ERRADO — var de setor com agg quando saída é setor
"dimension": { "geoLevel": { "values": [{ "id": 49, "alias": "Setor" }] } },
"select": [
  { "id": 449, "agg": "sum" }  // ❌ 449 já é de setor — sem agg
]
```

```json
// CORRETO
"select": [
  { "id": 449 },               // setor → setor: sem agg
  { "id": 40, "agg": "count" } // empresa → setor: agg obrigatório
]
```

---

### ❌ Usar mais de uma opção de entrada em `data`

`keys`, `addresses`, `values`, `where` e `file` são **mutuamente exclusivos**.

---

## 6. Exemplos Completos

### Exemplo A — CNPJ + sem dimensão + variáveis demográficas

Retorno por empresa (1 linha por CNPJ), com dados do setor onde cada empresa está alocada.

```json
{
  "dryRun": false,
  "formatType": "csv",
  "delimiter": "|",
  "dimension": null,
  "expressions": {
    "major": null,
    "select": [
      { "id": 449 },
      { "id": 6547 }
    ]
  },
  "data": {
    "geoLevel": 1,
    "keys": [33461874000103]
  }
}
```

---

### Exemplo B — CNPJ + buffer + variáveis demográficas

Retorno por empresa × raio de buffer, com dados demográficos dentro de cada anel.

```json
{
  "dryRun": false,
  "formatType": "csv",
  "delimiter": "|",
  "dimension": {
    "buffer": {
      "values": [
        { "distance": 1000, "alias": "1KM" },
        { "distance": 3000, "alias": "3KM" },
        { "distance": 5000, "alias": "5KM" }
      ]
    }
  },
  "expressions": {
    "major": null,
    "select": [
      { "id": 449 },
      { "id": 6547 }
    ]
  },
  "data": {
    "keys": [33461874000103, 5951509000133]
  }
}
```

---

### Exemplo C — CNPJ + geoLevel + mix empresa e demográfico

Saída por setor censitário. Variável de empresa (`id: 40`) é mais granular que setor → precisa de `agg`. Variável de setor (`id: 449`) já está no nível de saída → sem `agg`.

```json
{
  "dryRun": false,
  "formatType": "csv",
  "delimiter": "|",
  "dimension": {
    "geoLevel": {
      "values": [{ "id": 49, "alias": "Setor" }]
    }
  },
  "expressions": {
    "major": null,
    "select": [
      { "id": 449 },
      { "id": 6547 },
      { "id": 40, "agg": "count" }
    ]
  },
  "data": {
    "geoLevel": 1,
    "keys": [33461874000103]
  }
}
```

---

### Exemplo D — Coordenadas XY + buffer + mix empresa e demográfico

```json
{
  "dryRun": false,
  "formatType": "csv",
  "delimiter": "|",
  "dimension": {
    "buffer": {
      "values": [
        { "distance": 1000, "alias": "1KM" },
        { "distance": 3000, "alias": "3KM" },
        { "distance": 5000, "alias": "5KM" }
      ]
    }
  },
  "expressions": {
    "major": null,
    "select": [
      { "id": 449 },
      { "id": 6547 },
      { "id": 40, "agg": "count" }
    ]
  },
  "data": {
    "values": [
      { "id": "ponto_sp", "x": -46.6333, "y": -23.5505 },
      { "id": "ponto_rj", "x": -43.1729, "y": -22.9068 }
    ]
  }
}
```

---

### Exemplo E — Filtro de empresas (where) + geoLevel + mix empresa e demográfico

Seleção de agências Bradesco em grandes municípios, com variáveis de setor e contagem de empresas por setor censitário.

- Variável `id: 449` (setor) → mesmo nível da saída → sem `agg`
- Variável `id: 40` (empresa) → mais granular → `agg: "count"`
- Grupo 1 filtra por razão social; Grupo 2 (OR) filtra por população do município

```json
{
  "dryRun": false,
  "formatType": "csv",
  "delimiter": "|",
  "dimension": {
    "geoLevel": {
      "values": [{ "id": 49, "alias": "Setor" }]
    }
  },
  "expressions": {
    "major": null,
    "select": [
      { "id": 449 },
      { "id": 6547 },
      { "id": 40, "agg": "count" }
    ]
  },
  "data": {
    "where": [
      {
        "rules": [
          { "id": 35, "value": ["BRADESCO"], "operator": "in", "geoLevelId": 1 }
        ]
      },
      {
        "rules": [
          { "id": 449, "value": "10000000", "operator": "greater", "condition": "OR", "geoLevelId": 5 }
        ]
      }
    ]
  }
}
```

---

### Exemplo F — Chaves via arquivo + buffer (estimativa antes de extrair)

```json
{
  "dryRun": true,
  "formatType": "csv",
  "delimiter": "|",
  "dimension": {
    "buffer": {
      "values": [
        { "distance": 500,  "alias": "500M" },
        { "distance": 1000, "alias": "1KM" }
      ]
    }
  },
  "expressions": {
    "major": null,
    "select": [
      { "id": 449 },
      { "id": 6547 }
    ]
  },
  "data": {
    "geoLevel": 1,
    "file": {
      "url": "cliente/uploads/798ead29b4694ebdb097931fcd4c38bd.csv",
      "provider": "GoogleCloudBucket",
      "contentType": "Keys",
      "delimiter": ";",
      "fields": { "id": "cnpj" }
    }
  }
}
```

---

## 7. Referência Rápida

### Combinações de entrada × dimensão × `agg`

| Entrada | Variáveis | Dimension | `agg` necessário? |
|---|---|---|---|
| `keys` / `where` / `file` | Mesmo nível | `null` | Não |
| `keys` / `where` / `file` | Mesmo nível | `buffer` | Não |
| `keys` / `where` / `file` | Mesmo nível | `geoLevel` | Somente se mais granular que a saída |
| `keys` / `where` / `file` | **Mix de níveis** | `null` | ❌ **Inválido** — dimension obrigatória |
| `keys` / `where` / `file` | **Mix de níveis** | `buffer` | Sim, para vars mais granulares que a saída |
| `keys` / `where` / `file` | **Mix de níveis** | `geoLevel` | Sim, para vars mais granulares que a saída |
| `addresses` / `values` | Mesmo nível | `null` | Não |
| `addresses` / `values` | Mesmo nível | `buffer` | Não |
| `addresses` / `values` | Mesmo nível | `geoLevel` | Somente se mais granular que a saída |
| `addresses` / `values` | **Mix de níveis** | `null` | ❌ **Inválido** — dimension obrigatória |
| `addresses` / `values` | **Mix de níveis** | `buffer` | Sim, para vars mais granulares que a saída |
| `addresses` / `values` | **Mix de níveis** | `geoLevel` | Sim, para vars mais granulares que a saída |

### `agg` por nível de variável vs. dimensão de saída

| Variável | Nível nativo | Saída = Setor (49) | Saída = buffer |
|---|---|---|---|
| Demográfico / geopop | Setor (49) | Sem `agg` | Sem `agg` |
| Contagem / atributo de empresa | Empresa (1) | `agg` obrigatório | `agg` obrigatório |
