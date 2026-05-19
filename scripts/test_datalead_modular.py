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

EMAIL = "reinaldo.gregori@cognatis.com.br"
PASSWORD = "Cog2222"
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
    print(f"\n{'='*60}\n🔐 AUTENTICAÇÃO\n{'='*60}")

    creds = f"{EMAIL}:{PASSWORD}"
    auth_header = f"Basic {b64(creds)}"

    r = requests.post(
        AUTH_URL,
        headers={"Authorization": auth_header},
        json={"environmentId": ENV_ID},
        timeout=10
    )

    if r.status_code != 200:
        print(f"❌ ERRO {r.status_code}: {r.text}")
        sys.exit(1)

    TOKEN = r.json().get("token")
    HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

    print(f"✓ Token: {TOKEN[:30]}...")
    return TOKEN

# ============================================================================
# BUILDERS
# ============================================================================

def build_summary_payload(
    dimension: Optional[Dict] = None,
    expressions_select: List[Dict] = None,
    data_input: Dict = None,
    data_where: Optional[List[Dict]] = None,
    expressions_where: Optional[List[Dict]] = None,
    dry_run: bool = False
) -> Dict:

    if expressions_select is None:
        expressions_select = [{"id": EXPR_POP_RESID}, {"id": EXPR_RENDA_MEDIA}]
    if data_input is None:
        data_input = {"keys": [CNPJ_COGNATIS], "geoLevel": 1}

    return {
        "compact": False,
        "verbose": False,
        "dryRun": dry_run,
        "delimiter": "|",
        "formatType": "csv",
        "dimension": dimension,
        "expressions": {
            "major": None,
            "moduleId": None,
            "subModule": None,
            "select": expressions_select,
            "where": expressions_where or [],
            "groupBy": [],
            "having": [],
            "orderBy": [],
            "pageOptions": None
        },
        "data": {
            **data_input,
            "select": [],
            "where": data_where or [],
            "orderBy": [],
            "pageOptions": None
        }
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
        df = pd.read_csv(StringIO(r.text), sep="|")
        print(f"✓ {len(df)} linhas × {len(df.columns)} colunas")
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

if __name__ == "__main__":
    load_auth()

    print("\n" + "="*70)
    print("RESUMO DOS TESTES")
    print("="*70)

    tests = [
        ("USO 01", lambda: uso_01_cnpj_geolevel_1_inline()),
        ("USO 02", lambda: uso_02_cnpj_buffer_inline()),
        ("USO 03", lambda: uso_03_coords_buffer_inline()),
        ("USO 04", lambda: uso_04_addresses_buffer_inline()),
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
