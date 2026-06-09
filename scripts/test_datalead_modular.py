"""DataLead v1 API — Interactive Test Suite (Modular)

Estrutura modular para Jupyter interativo.

Uso no Jupyter:
  1. load_auth()
  2. call_summary(payload)
  3. DataFrame resultado
"""

import json, sys, base64
from typing import Dict, List, Optional, Any
from io import StringIO
import requests
import pandas as pd

# CONFIG
BASE_URL = "https://dev.nettoolpro.cognatis.com.br"
DATALEAD_PREFIX = "/dev"
AUTH_URL = f"{BASE_URL}/passport/api/Token/login"
SUMMARY_URL = f"{BASE_URL}{DATALEAD_PREFIX}/datalead/api/v1/export/summary"

EMAIL = "daniel.costa@cognatis.com.br"
PASSWORD = "Cog@2023"
ENV_ID = 1

# Expressões
EXPR_POP_RESID = 449
EXPR_RENDA_MEDIA = 6547
MODULE_PJ_ID = None

# Dados de teste
COORDS_SP = {"id": "pt_sp", "x": -46.6333, "y": -23.5505}
COORDS_RJ = {"id": "pt_rj", "x": -43.1729, "y": -22.9068}
ADDR_SP = {"id": "sp_01", "zipCode": 1310100, "number": 100}
CNPJ_COGNATIS = 33461874000103

TOKEN = None
HEADERS = None

# ============================================================================
# AUTH
# ============================================================================

def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")

def load_auth():
    global TOKEN, HEADERS
    print(f"\n{'='*60}\n[AUTH]\n{'='*60}")

    payload = {
        "username": b64(EMAIL),
        "password": b64(PASSWORD),
        "loginAttempts": 1,
        "environmentId": ENV_ID,
    }

    r = requests.post(AUTH_URL, json=payload, timeout=15)

    if r.status_code != 200:
        print(f"ERRO {r.status_code}: {r.text}")
        sys.exit(1)

    data = r.json()
    if not data.get("authenticated"):
        print(f"Login recusado: {data.get('message', r.text)}")
        sys.exit(1)

    access = data.get("accessToken", "")
    TOKEN = access.replace("Bearer ", "").strip()
    HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    print(f"OK Token: {TOKEN[:40]}...")
    return TOKEN

# ============================================================================
# BUILDERS
# ============================================================================

def build_summary_payload(
    dimension: Optional[Dict] = None,
    expressions_select: List[Dict] = None,
    data_input: Dict = None,
    data_where: Optional[List[Dict]] = None,
    dry_run: bool = False
) -> Dict:

    if expressions_select is None:
        expressions_select = [{"id": EXPR_POP_RESID}, {"id": EXPR_RENDA_MEDIA}]
    if data_input is None:
        data_input = {"keys": [CNPJ_COGNATIS], "geoLevel": 1}

    data = {**data_input}
    if data_where:
        data["where"] = data_where

    return {
        "dryRun": dry_run,
        "delimiter": "|",
        "formatType": "csv",
        "dimension": dimension,
        "expressions": {
            "major": None,
            "select": expressions_select,
        },
        "data": data
    }

def build_buffer_dimension(raios: List[int]) -> Dict:
    return {
        "buffer": {
            "values": [
                {"distance": d, "alias": f"{d//1000}KM" if d >= 1000 else f"{d}M"}
                for d in raios
            ]
        }
    }

# ============================================================================
# CALL
# ============================================================================

def call_summary(
    payload: Dict,
    label: str = "",
    show_payload: bool = True
) -> Optional[pd.DataFrame]:

    print(f"\n{'='*70}")
    if label:
        print(f"📋 {label}")
    print(f"{'='*70}")

    if show_payload:
        print("Payload:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    r = requests.post(SUMMARY_URL, headers=HEADERS, json=payload, timeout=120)
    print(f"Status: HTTP {r.status_code}")

    if r.status_code != 200:
        print(f"❌ ERRO: {r.text[:500]}")
        return None

    try:
        text = r.content.decode("utf-8-sig")  # decodifica removendo BOM
        df = pd.read_csv(StringIO(text), sep=None, engine="python")
        df.columns = [c.strip('"') for c in df.columns]  # remove aspas dos headers
        print(f"✓ {len(df)} linhas × {len(df.columns)} colunas")
        print(df.columns.tolist())
        return df
    except Exception as e:
        print(f"❌ Erro ao parsear: {e}")
        return None

# ============================================================================
# CASOS DE USO
# ============================================================================

def uso_01_cnpj_geolevel_1_inline():
    payload = build_summary_payload(
        dimension=None,
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA}
        ],
        data_input={
            "keys": [CNPJ_COGNATIS],
            "geoLevel": 1
        }
    )
    return call_summary(payload, label="USO 01 — CNPJ geolevel=1 inline (sem buffer)")

def uso_02_cnpj_buffer_inline():
    payload = build_summary_payload(
        dimension=build_buffer_dimension([500, 1000, 1500]),
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA}
        ],
        data_input={
            "keys": [CNPJ_COGNATIS]
        }
    )
    return call_summary(payload, label="USO 02 — CNPJ + buffer 500m/1km/1.5km")

def uso_03_coords_buffer_inline():
    payload = build_summary_payload(
        dimension=build_buffer_dimension([3000, 5000, 8000]),
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA}
        ],
        data_input={
            "values": [COORDS_SP, COORDS_RJ]
        }
    )
    return call_summary(payload, label="USO 03 — Coordenadas XY + buffer 3km/5km/8km")

def uso_04_addresses_buffer_inline():
    payload = build_summary_payload(
        dimension=build_buffer_dimension([500, 1000]),
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA}
        ],
        data_input={
            "addresses": [ADDR_SP]
        }
    )
    return call_summary(payload, label="USO 04 — Endereços + buffer 500m/1km")

def uso_05_bradesco_brooklin_setor():
    # Filtro de empresas via where:
    #   Grupo 1 (AND): razão social contém "BRADESCO"
    #   Grupo 2 (OR):  população do município > 10.000.000 (restringe a grandes centros)
    # Dimensão de saída: setor censitário (geoLevel 49)
    # Expressões: geopop (variáveis de setor) + contagem de empresas (id 40, agg=count)
    payload = {
        "compact": False,
        "verbose": False,
        "dryRun": False,
        "delimiter": "|",
        "formatType": "csv",
        "dimension": {
            "geoLevel": {
                "values": [
                    {"id": 49, "alias": "Setor"}
                ]
            }
        },
        "expressions": {
            "major": None,
            "select": [
                {"id": 298},
                {"id": 40, "agg": "count"},
                {"id": 300},
                {"id": 330},
                {"id": 331},
                {"id": 352},
                {"id": 361},
                {"id": 369},
                {"id": 371},
                {"id": 372},
                {"id": 373},
                {"id": 374},
                {"id": 375},
                {"id": 407},
                {"id": 408},
                {"id": 449},
                {"id": 450},
                {"id": 469},
                {"id": 476},
                {"id": 478},
                {"id": 518},
                {"id": 522},
                {"id": 526},
                {"id": 529},
                {"id": 530},
                {"id": 531},
                {"id": 532},
                {"id": 533},
                {"id": 534},
                {"id": 535},
                {"id": 536},
            ],
        },
        "data": {
            "where": [
                {
                    "rules": [
                        {
                            "id": 35,
                            "value": ["BRADESCO"],
                            "operator": "in",
                            "geoLevelId": 1,
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
                            "geoLevelId": 5,
                        }
                    ]
                },
            ],
        },
    }
    return call_summary(payload, label="USO 05 — Bradesco (where) + geopop/empresas agregado por Setor")

# --- Cenário 1: CNPJ ----------------------------------------------------------

def uso_06_cnpj_sem_dimensao_mix_empresa_demografico():
    # CNPJ + sem dimensão: output por empresa (1 linha por CNPJ)
    # TODO: substituir EXPR_EMPRESA_VAR pelo ID correto de variável empresa (ex: faturamento médio)
    EXPR_EMPRESA_VAR = None  # ID pendente — confirmar com equipe de dados
    select = [{"id": EXPR_POP_RESID}, {"id": EXPR_RENDA_MEDIA}]
    if EXPR_EMPRESA_VAR:
        select.append({"id": EXPR_EMPRESA_VAR})
    payload = build_summary_payload(
        dimension=None,
        expressions_select=select,
        data_input={"keys": [CNPJ_COGNATIS], "geoLevel": 1}
    )
    return call_summary(payload, label="USO 06 — CNPJ + sem dimensão + mix empresa+demográfico")

def uso_07_cnpj_buffer_mix_empresa_demografico():
    # CNPJ + buffer: output por empresa × raio
    # TODO: substituir EXPR_EMPRESA_VAR pelo ID correto de variável empresa com agg
    EXPR_EMPRESA_VAR = None
    select = [{"id": EXPR_POP_RESID}, {"id": EXPR_RENDA_MEDIA}]
    if EXPR_EMPRESA_VAR:
        select.append({"id": EXPR_EMPRESA_VAR, "agg": "count"})
    payload = build_summary_payload(
        dimension=build_buffer_dimension([1000, 3000, 5000]),
        expressions_select=select,
        data_input={"keys": [CNPJ_COGNATIS]}
    )
    return call_summary(payload, label="USO 07 — CNPJ + buffer 1km/3km/5km + mix empresa(agg)+demográfico")

def uso_08_cnpj_geolevel_mix_empresa_demografico():
    # CNPJ + geoLevel setor: output por setor censitário
    # Empresa (id=40) é de nível mais granular que setor → obrigatório agg
    payload = build_summary_payload(
        dimension={"geoLevel": {"values": [{"id": 49, "alias": "Setor"}]}},
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA},
            {"id": 40, "agg": "count"},
        ],
        data_input={"keys": [CNPJ_COGNATIS], "geoLevel": 1}
    )
    return call_summary(payload, label="USO 08 — CNPJ + geoLevel setor + mix empresa(agg)+demográfico")

# --- Cenário 2: Address / XY --------------------------------------------------

def uso_09_address_sem_dimensao():
    # Endereço + sem dimensão: output por setor censitário onde o ponto está alocado
    # Sem dimensão explícita, endereço agrega por setor → empresa precisa de agg
    payload = build_summary_payload(
        dimension=None,
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA},
            {"id": 40, "agg": "count"},
        ],
        data_input={"addresses": [ADDR_SP]}
    )
    return call_summary(payload, label="USO 09 — Endereço + sem dimensão + mix empresa(agg)+demográfico")

def uso_10_xy_buffer_mix_empresa_demografico():
    # XY + buffer + mix demográfico (+ empresa var quando ID disponível)
    EXPR_EMPRESA_VAR = None
    select = [{"id": EXPR_POP_RESID}, {"id": EXPR_RENDA_MEDIA}]
    if EXPR_EMPRESA_VAR:
        select.append({"id": EXPR_EMPRESA_VAR, "agg": "count"})
    payload = build_summary_payload(
        dimension=build_buffer_dimension([1000, 3000, 5000]),
        expressions_select=select,
        data_input={"values": [COORDS_SP, COORDS_RJ]}
    )
    return call_summary(payload, label="USO 10 — XY + buffer 1km/3km/5km + mix empresa(agg)+demográfico")

def uso_11_address_geolevel_mix_empresa_demografico():
    # Endereço + geoLevel setor
    # BUG BACKEND: retorna HTTP 500 "Sequence contains no elements" — aguardando correção
    payload = build_summary_payload(
        dimension={"geoLevel": {"values": [{"id": 49, "alias": "Setor"}]}},
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA},
        ],
        data_input={"addresses": [ADDR_SP]}
    )
    return call_summary(payload, label="USO 11 — Endereço + geoLevel setor [BUG BACKEND]")

# --- Cenário 3: Filtro where --------------------------------------------------

BRADESCO_WHERE = [
    {"rules": [{"id": 35, "value": ["BRADESCO"], "operator": "in", "geoLevelId": 1}]},
    {"rules": [{"id": 449, "value": "10000000", "operator": "greater", "condition": "OR", "geoLevelId": 5}]},
]

def uso_12_where_buffer_demografico():
    # Where (filtro) + buffer + só variáveis demográficas (mesmo nível — sem mix)
    # Todas as variáveis são de setor: sem agg necessária dentro do buffer
    payload = build_summary_payload(
        dimension=build_buffer_dimension([1000, 3000]),
        expressions_select=[
            {"id": EXPR_POP_RESID},
            {"id": EXPR_RENDA_MEDIA},
        ],
        data_input={},
        data_where=BRADESCO_WHERE
    )
    return call_summary(payload, label="USO 12 — Where (Bradesco) + buffer 1km/3km + demográfico")

def uso_13_where_geolevel_setor_mix_empresa_demografico():
    # Where (filtro) + geoLevel Setor + mix demográfico(setor, sem agg) + empresa(agg)
    # Saída por setor: vars de setor já estão no nível correto (sem agg).
    # Var empresa (nível mais granular) precisa de agg para subir ao nível setor.
    payload = build_summary_payload(
        dimension={"geoLevel": {"values": [{"id": 49, "alias": "Setor"}]}},
        expressions_select=[
            {"id": EXPR_POP_RESID},            # setor → setor: sem agg
            {"id": EXPR_RENDA_MEDIA},           # setor → setor: sem agg
            {"id": 40, "agg": "count"},         # empresa → setor: precisa agg
        ],
        data_input={},
        data_where=BRADESCO_WHERE
    )
    return call_summary(payload, label="USO 13 — Where (Bradesco) + geoLevel Setor + mix empresa(agg)+demográfico")

if __name__ == "__main__":
    load_auth()

    print("\n" + "="*70)
    print("RESUMO DOS TESTES")
    print("="*70)

    tests = [
        # Cenário 1 — CNPJ
        ("USO 01", lambda: uso_01_cnpj_geolevel_1_inline()),
        ("USO 02", lambda: uso_02_cnpj_buffer_inline()),
        ("USO 06", lambda: uso_06_cnpj_sem_dimensao_mix_empresa_demografico()),
        ("USO 07", lambda: uso_07_cnpj_buffer_mix_empresa_demografico()),
        ("USO 08", lambda: uso_08_cnpj_geolevel_mix_empresa_demografico()),
        # Cenário 2 — Address / XY
        ("USO 03", lambda: uso_03_coords_buffer_inline()),
        ("USO 04", lambda: uso_04_addresses_buffer_inline()),
        ("USO 09", lambda: uso_09_address_sem_dimensao()),
        ("USO 10", lambda: uso_10_xy_buffer_mix_empresa_demografico()),
        ("USO 11", lambda: uso_11_address_geolevel_mix_empresa_demografico()),
        # Cenário 3 — Where (filtro)
        ("USO 05", lambda: uso_05_bradesco_brooklin_setor()),
        ("USO 12", lambda: uso_12_where_buffer_demografico()),
        ("USO 13", lambda: uso_13_where_geolevel_setor_mix_empresa_demografico()),
    ]

    results = {}
    for name, fn in tests:
        try:
            df = fn()
            results[name] = "✓ PASS" if df is not None else "✗ FAIL"
        except Exception as e:
            results[name] = f"✗ ERROR"

    print("\n" + "="*70)
    for name, result in results.items():
        print(f"  {name}: {result}")
