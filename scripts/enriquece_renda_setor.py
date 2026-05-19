"""Aurel
Enriquecimento por endereço (Fluxo B) na API Cognatis DataLead v1.

Suporta dois sub-fluxos do Fluxo B do `/export/summary`:
  --mode xy        coordenadas lat/long já-geocodificadas (default)
  --mode address   endereços CEP+número (geocodificação server-side)

Fluxo:
  1) POST /passport/api/Token/login  (SEM environmentId)  -> JWT inicial
  2) GET  /passport/api/users/environments/{userId}       -> lista de ambientes
  3) Escolhe ambiente (env_id via flag, env var ou prompt)
  4) POST /passport/api/Token/login  (COM environmentId)  -> JWT escopado
  5) (opcional) POST /export/summary com dryRun=true      -> estimativa
  6) Pergunta confirmação (skipable com --no-dry-run / --yes)
  7) POST /dev/datalead/api/v1/export/summary             -> enriquecimento real

Modos de execução
-----------------

(A) Não-interativo via variáveis de ambiente (recomendado para debug):
    NTP_EMAIL=foo@cognatis.com.br NTP_PASSWORD='senha' NTP_ENV_ID=1 \\
        python enriquece_renda_setor.py

(B) Não-interativo com token JWT pronto (pula passos 1-4):
    NTP_TOKEN='<jwt>' python enriquece_renda_setor.py

(C) Não-interativo via flags:
    python enriquece_renda_setor.py --email foo@... --password 'senha' --env-id 1

(D) Modo dump (não chama API, só mostra o payload do summary):
    python enriquece_renda_setor.py --dump-payload
    python enriquece_renda_setor.py --dump-payload --mode address

(E) Interativo (default — pede credenciais via prompt):
    python enriquece_renda_setor.py

(F) Modo address (testa o GeocodingService do backend):
    NTP_TOKEN='<jwt>' python enriquece_renda_setor.py --mode address
    Aviso: comentário em vue-project/.../GeocodingService indica que em DEV
    esse caminho retornava 500 ("column g.latitude does not exist"). Esse
    modo serve justamente pra reconfirmar/refutar isso empiricamente.

Variáveis de ambiente reconhecidas:
    NTP_EMAIL, NTP_PASSWORD, NTP_ENV_ID, NTP_TOKEN
"""

import argparse
import base64
import getpass
import json
import os
import sys

import requests

# ---- Ambiente -------------------------------------------------------------
# Hosts confirmados em vue-project/config/dev.env.js e .env.development:
#   PASSPORT_URL = <BASE_URL>/passport         (sem prefixo /dev)
#   API DataLead = <BASE_URL>/dev/datalead/... (com prefixo /dev)
#
# Para PRD/HML trocar BASE_URL e DATALEAD_PREFIX:
#   DEV: BASE_URL = "https://dev.nettoolpro.cognatis.com.br"; DATALEAD_PREFIX = "/dev"
#   HML: BASE_URL = "https://hml.nettoolpro.cognatis.com.br"; DATALEAD_PREFIX = "/hml"
#   PRD: BASE_URL = "https://nettoolpro.cognatis.com.br";     DATALEAD_PREFIX = ""
BASE_URL = "https://dev.nettoolpro.cognatis.com.br"
DATALEAD_PREFIX = "/dev"

# Usamos /api/Token/login (o endpoint que o front Vue do NTP usa em prd/hml/dev).
# A doc descreve /api/token/auth como variante "pública" mas no DEV ela está
# retornando 400 — Token/login é o caminho conhecido por funcionar.
AUTH_URL = f"{BASE_URL}/passport/api/Token/login"
ENVIRONMENTS_URL_TEMPLATE = (
    f"{BASE_URL}/passport/api/users/environments/{{user_id}}"
)
SUMMARY_URL = f"{BASE_URL}{DATALEAD_PREFIX}/datalead/api/v1/export/summary"
MODULE_LIST_URL = f"{BASE_URL}{DATALEAD_PREFIX}/datalead/api/v1/module/list"
MODULE_VARS_URL_TEMPLATE = (
    f"{BASE_URL}{DATALEAD_PREFIX}/datalead/api/v1/module/{{module_id}}/list"
)
GEOLEVELS_URL = f"{BASE_URL}{DATALEAD_PREFIX}/datalead/api/v1/module/geolevels"

# ID da expressão "Renda Média do Setor Censitário".
# Trocar pelo ID real do catálogo (GET /datalead/api/v1/module/{moduleId}/{version}/list).
RENDA_MEDIA_EXPRESSION_ID = 23

# Coordenadas X (longitude) / Y (latitude) idênticas ao exemplo
# caso_b2_endereco_latlong_body do Confluence
# (https://cognatis.atlassian.net/wiki/spaces/DDAASC/pages/3483664385).
#
# Usamos XY em vez de addresses porque o GeocodingService do backend está
# quebrado em DEV ("column g.latitude does not exist"). Com XY já-geocodificado
# o backend pula esse serviço.
PONTOS_XY = [
    {"id": "ponto_sp", "x": -46.6333, "y": -23.5505},
    {"id": "ponto_rj", "x": -43.1729, "y": -22.9068},
    {"id": "ponto_bh", "x": -43.9378, "y": -19.9245},
]

# Endereços hardcoded para o modo --mode address.
# Formato {recId, zipCode (int), number (int)} — literal do exemplo Postman
# "Extrair com dimensão e Address Point". A doc Confluence 3483664385 mostra
# formato diferente ({id, addressLine, city, state, country}) mas o backend
# em DEV usa esta forma (confirmado pelo Postman, contradiz a doc).
ENDERECOS = [
    {"recId": "loja_sp", "zipCode": 1310100, "number": 100},
    {"recId": "loja_rj", "zipCode": 22071900, "number": 50},
    {"recId": "loja_bh", "zipCode": 30112000, "number": 200},
]

# Raios de buffer para o modo --mode address. Replica os 4 raios canônicos
# do exemplo Postman "Address Point".
BUFFER_RAIOS = [
    {"distance": 3000, "alias": "3KM"},
    {"distance": 5000, "alias": "5KM"},
    {"distance": 8000, "alias": "8KM"},
    {"distance": 10000, "alias": "10KM"},
]


# ---- Helpers ---------------------------------------------------------------

def b64(texto: str) -> str:
    return base64.b64encode(texto.encode("utf-8")).decode("ascii")


def jwt_claims(token: str) -> dict:
    """Decodifica o payload de um JWT (sem validar assinatura)."""
    try:
        payload = token.split(".")[1]
        padding = "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload + padding))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        print(f"Token inválido — não consegui decodificar claims: {exc}",
              file=sys.stderr)
        sys.exit(3)


# ---- Defaults para evitar interatividade ---------------------------------
# Email e env_id hardcoded como conveniência para reinaldo.gregori. Podem ser
# sobrescritos via flag ou env var.
DEFAULT_EMAIL = "reinaldo.gregori@cognatis.com.br"
DEFAULT_ENV_ID = 1


# ---- Etapa 1: argumentos / credenciais ------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enriquecimento por XY via API Cognatis DataLead v1.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--email", help="E-mail. Default: $NTP_EMAIL.")
    parser.add_argument("--password",
                        help="Senha. Default: $NTP_PASSWORD. Evite passar "
                             "via CLI (fica no histórico do shell) — prefira "
                             "a env var.")
    parser.add_argument("--env-id", type=int,
                        help="environmentId. Default: $NTP_ENV_ID. Se ausente "
                             "e houver TTY, lista ambientes e pergunta.")
    parser.add_argument("--token",
                        help="JWT já-emitido (pula login). Default: $NTP_TOKEN.")
    parser.add_argument("--dump-payload", action="store_true",
                        help="Só monta e imprime o payload do summary, sem "
                             "chamar nenhuma API. Útil para validar formato.")
    parser.add_argument("--mode", choices=("xy", "address", "postman-clone"),
                        default="xy",
                        help="xy: PONTOS_XY com dimension.geoLevel (default). "
                             "address: ENDERECOS com dimension.geoLevel. "
                             "postman-clone: replica byte-a-byte o exemplo "
                             "'Extrair com dimensão e Entry Point' do Postman "
                             "(1 ponto XY + dimension.buffer 4 raios + 30 "
                             "expressions) — baseline pra isolar bugs do payload.")
    parser.add_argument("--no-dry-run", action="store_true",
                        help="Pula a estimativa (dryRun=true) e vai direto pra "
                             "extração real. Default: faz dryRun e pede "
                             "confirmação em TTY.")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Auto-confirma a extração real após o dryRun. "
                             "Útil em scripts/CI. Sem TTY, --yes é assumido.")
    parser.add_argument("--list-modules", action="store_true",
                        help="Chama GET /module/list e GET /module/geolevels. "
                             "Útil pra descobrir IDs reais do env do usuário.")
    parser.add_argument("--list-vars", type=int, metavar="MODULE_ID",
                        help="Chama GET /module/{MODULE_ID}/list, lista todas "
                             "as expressions disponíveis no módulo (IDs + nomes).")
    return parser.parse_args()


def obter_credenciais(args: argparse.Namespace) -> tuple[str, str]:
    email = args.email or os.environ.get("NTP_EMAIL") or DEFAULT_EMAIL
    senha = args.password or os.environ.get("NTP_PASSWORD")

    print(f"E-mail: {email}")

    if not senha:
        if not sys.stdin.isatty():
            print("Senha não fornecida (use --password ou NTP_PASSWORD).",
                  file=sys.stderr)
            sys.exit(1)
        senha = getpass.getpass("Senha (input oculto): ")

    if not email or not senha:
        print("E-mail e/ou senha vazios. Abortando.", file=sys.stderr)
        sys.exit(1)
    return email, senha


def obter_env_id(args: argparse.Namespace) -> int:
    """Resolve env_id de flag → env var → default. Sempre retorna um int."""
    if args.env_id is not None:
        return args.env_id
    env_raw = os.environ.get("NTP_ENV_ID")
    if env_raw:
        try:
            return int(env_raw)
        except ValueError:
            print(f"NTP_ENV_ID inválido: {env_raw!r}", file=sys.stderr)
            sys.exit(1)
    return DEFAULT_ENV_ID


# ---- Etapa 2 e 4: autenticação -------------------------------------------

def _extrair_mensagem(response: requests.Response) -> str:
    """Tenta extrair a mensagem mais útil do corpo da resposta do Passport.

    O Passport às vezes devolve JSON `{message: "..."}` e às vezes string crua
    do tipo 'Response status code does not indicate success: 400 (Bad Request).'
    """
    try:
        body = response.json()
        if isinstance(body, dict):
            return (body.get("message") or body.get("error")
                    or body.get("title") or json.dumps(body, ensure_ascii=False))
    except ValueError:
        pass
    return response.text.strip()


def autenticar(email: str, senha: str, env_id: int | None = None) -> dict:
    """Login via /passport/api/Token/login. Retorna dict com `accessToken`.

    Mesma forma do payload que o front Vue do NTP usa em Login.vue:326-344.
    """
    payload = {
        "username": b64(email),
        "password": b64(senha),
        "loginAttempts": 1,
    }
    if env_id is not None:
        payload["environmentId"] = env_id

    headers = {"Content-Type": "application/json"}
    label = f"com env={env_id}" if env_id else "sem env"
    print(f"\nPOST {AUTH_URL}  ({label})")

    try:
        response = requests.post(AUTH_URL, headers=headers, json=payload,
                                 timeout=30)
    except requests.RequestException as exc:
        print(f"Falha de rede no login: {exc}", file=sys.stderr)
        sys.exit(2)

    mensagem = _extrair_mensagem(response)
    msg_lower = mensagem.lower()

    # 200 com authenticated=false (Passport sinaliza credencial inválida assim).
    if response.status_code == 200:
        data = response.json()
        if data.get("authenticated") is False:
            print(
                "Login recusado pelo Passport — provavelmente senha errada "
                "para esse e-mail.",
                file=sys.stderr,
            )
            print(f"  detalhe do servidor: {data.get('message') or mensagem}",
                  file=sys.stderr)
            if data.get("lockedByManyAttempts"):
                print("  ATENÇÃO: conta bloqueada por excesso de tentativas.",
                      file=sys.stderr)
            sys.exit(3)

        raw = data.get("accessToken") or data.get("token")
        if not raw:
            print("Resposta 200 sem accessToken/token. Body:", file=sys.stderr)
            print(json.dumps(data, indent=2, ensure_ascii=False),
                  file=sys.stderr)
            sys.exit(3)
        # O Passport devolve accessToken JÁ com prefixo "Bearer " no valor
        # (confirmado em vue-project/src/components/authentication/Login.vue:511
        # onde o front faz accessToken.replace('Bearer ', '')). Normalizamos
        # aqui pra guardar só o JWT cru.
        token = raw[7:].strip() if raw.lower().startswith("bearer ") else raw
        data["token"] = token
        # Debug: mostra estrutura da resposta (sem o token).
        keys = sorted(k for k in data.keys() if k not in ("token", "accessToken", "id_token"))
        print(f"  -> autenticado. Campos retornados: {keys}")
        if "environments" in data:
            print(f"     environments (count?): {data['environments']}")
        return data

    # Erros HTTP — diagnóstico orientado à causa provável.
    if response.status_code == 400:
        # 400 com mensagens típicas de credencial Base64 inválida ou usuário
        # sem senha local (caso comum de quem só loga via Google SSO).
        if "password" in msg_lower or "credential" in msg_lower:
            print("400 Bad Request — credenciais inválidas ou mal formatadas.",
                  file=sys.stderr)
        elif "sso" in msg_lower or "google" in msg_lower or "identity" in msg_lower:
            print(
                "400 Bad Request — esse usuário parece autenticar via Google "
                "SSO e não tem senha local no Passport. Peça à Cognatis para "
                "criar uma senha de serviço ou use o cookie ssoSessionKey.",
                file=sys.stderr,
            )
        else:
            print(
                "400 Bad Request — payload rejeitado pelo Passport. Causas "
                "típicas: (a) e-mail/senha errados; (b) usuário só tem login "
                "Google SSO, sem senha local; (c) campos faltando.",
                file=sys.stderr,
            )
        print(f"  detalhe do servidor: {mensagem}", file=sys.stderr)
        sys.exit(3)

    if response.status_code == 401:
        print("401 — credenciais inválidas (e-mail e/ou senha errados).",
              file=sys.stderr)
        print(f"  detalhe do servidor: {mensagem}", file=sys.stderr)
        sys.exit(3)

    if response.status_code == 404:
        print("404 — usuário não encontrado nesse ambiente do Passport.",
              file=sys.stderr)
        print(f"  detalhe do servidor: {mensagem}", file=sys.stderr)
        sys.exit(3)

    if response.status_code == 423:
        print("423 Locked — conta bloqueada (excesso de tentativas?).",
              file=sys.stderr)
        print(f"  detalhe do servidor: {mensagem}", file=sys.stderr)
        sys.exit(3)

    print(f"Falha no login (status HTTP {response.status_code}):",
          file=sys.stderr)
    print(f"  detalhe do servidor: {mensagem}", file=sys.stderr)
    sys.exit(3)


# ---- Etapa 3: listar ambientes e escolher --------------------------------

def listar_ambientes(token: str) -> list[dict]:
    claims = jwt_claims(token)
    user_id = (
        claims.get("UserId") or claims.get("userId") or claims.get("sub")
    )
    if not user_id:
        print("Não achei UserId no JWT. Claims disponíveis:",
              list(claims.keys()), file=sys.stderr)
        sys.exit(3)

    # Debug: mostra claims relevantes (sem dados sensíveis).
    interessantes = {
        k: claims.get(k) for k in
        ("UserId", "userId", "sub", "EnvironmentId", "environmentId",
         "cClient", "exp", "iss", "aud", "Email", "email")
        if k in claims
    }
    print(f"  JWT claims: {interessantes}")

    url = ENVIRONMENTS_URL_TEMPLATE.format(user_id=user_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    print(f"\nGET  {url}")

    try:
        response = requests.get(url, headers=headers, timeout=30)
    except requests.RequestException as exc:
        print(f"Falha de rede ao listar ambientes: {exc}", file=sys.stderr)
        sys.exit(4)

    if response.status_code != 200:
        print(f"Falha ao listar ambientes (status {response.status_code}):",
              file=sys.stderr)
        print(f"  body: {response.text!r}", file=sys.stderr)
        print(f"  response headers: {dict(response.headers)}", file=sys.stderr)
        sys.exit(4)

    ambientes = response.json()
    if not ambientes:
        print("Nenhum ambiente disponível para esse usuário.", file=sys.stderr)
        sys.exit(4)
    return ambientes


def escolher_ambiente(ambientes: list[dict],
                      env_id_preset: int | None = None) -> int:
    """Resolve o environmentId a usar.

    Se env_id_preset foi passado (via flag ou env var) e existe na lista,
    retorna direto. Senão, em TTY pergunta; sem TTY usa o default (ou aborta).
    """
    by_id = {env.get("id"): env for env in ambientes}

    if env_id_preset is not None:
        if env_id_preset not in by_id:
            print(f"env_id={env_id_preset} não está na lista de ambientes "
                  f"disponíveis para esse usuário. IDs válidos: "
                  f"{sorted(by_id.keys())[:10]}...", file=sys.stderr)
            sys.exit(4)
        nome = (by_id[env_id_preset].get("fullName")
                or by_id[env_id_preset].get("shortName"))
        print(f"  -> usando env_id={env_id_preset} ({nome})")
        return env_id_preset

    print(f"\nAmbientes disponíveis ({len(ambientes)}):")
    default_idx = None
    for idx, env in enumerate(ambientes, start=1):
        nome = env.get("fullName") or env.get("shortName") or f"env {env.get('id')}"
        marca_default = "  (padrão)" if env.get("isDefault") else ""
        print(f"  [{idx}] {nome}  — id={env.get('id')}{marca_default}")
        if env.get("isDefault"):
            default_idx = idx

    if not sys.stdin.isatty():
        if default_idx is not None:
            chosen = ambientes[default_idx - 1]["id"]
            print(f"  -> sem TTY, usando default env_id={chosen}")
            return chosen
        print("Sem TTY e sem ambiente default. Use --env-id ou NTP_ENV_ID.",
              file=sys.stderr)
        sys.exit(4)

    while True:
        prompt = "Escolha o número do ambiente"
        if default_idx is not None:
            prompt += f" [ENTER = {default_idx}]"
        escolha = input(f"{prompt}: ").strip()
        if not escolha and default_idx is not None:
            return ambientes[default_idx - 1]["id"]
        if escolha.isdigit():
            n = int(escolha)
            if 1 <= n <= len(ambientes):
                return ambientes[n - 1]["id"]
        print("  inválido — digite um número da lista.")


# ---- Etapa 5: enriquecimento ---------------------------------------------

def validar_xy() -> None:
    invalidos = [
        p["id"] for p in PONTOS_XY
        if not isinstance(p.get("x"), (int, float))
        or not isinstance(p.get("y"), (int, float))
    ]
    if invalidos:
        print("Ponto XY inválido — x e y precisam ser numéricos: "
              + ", ".join(invalidos), file=sys.stderr)
        sys.exit(1)


def montar_payload_postman_clone(dry_run: bool = False) -> dict:
    """Replica exato do exemplo 'Extrair com dimensão e Entry Point' do Postman.

    Usado como baseline: se este payload retornar 500, o problema é o
    endpoint /export/summary em DEV, não nosso payload customizado.
    """
    return {
        "compact": False,
        "dryRun": dry_run,
        "delimiter": "|",
        "formatType": "csv",
        "dimension": {
            "buffer": {
                "values": [
                    {"distance": 3000, "alias": "3KM"},
                    {"distance": 5000, "alias": "5KM"},
                    {"distance": 8000, "alias": "8KM"},
                    {"distance": 10000, "alias": "10KM"},
                ],
            },
        },
        "expressions": {
            "major": None,
            "moduleId": None,
            "subModule": None,
            "select": [{"id": i} for i in [
                298, 300, 330, 331, 352, 361, 369, 371, 372, 373,
                374, 375, 407, 408, 449, 450, 469, 476, 478, 518,
                522, 526, 529, 530, 531, 532, 533, 534, 535, 536,
            ]],
            "where": [],
            "groupBy": [],
            "having": [],
            "orderBy": [],
            "pageOptions": None,
        },
        "data": {
            "values": [
                {"id": "000013880002", "x": -47.88745117, "y": -15.7788105},
            ],
            "select": [],
            "where": [],
            "orderBy": [],
            "pageOptions": None,
        },
    }


def montar_payload_enriquecimento(mode: str = "xy",
                                  dry_run: bool = False) -> dict:
    """Payload do POST /export/summary para Fluxo B (enriquecimento).

    mode="xy"      → data.values com lista de {id, x, y}.
                     Formato confirmado na página Confluence "Payload"
                     (2645655553) e usado pelo backend atual.
    mode="address" → data.addresses com lista de {id, addressLine, city,
                     state, country}. Formato da doc oficial 3483664385
                     (12/05/2026). Em DEV pode falhar se o GeocodingService
                     estiver quebrado.
    """
    # Cada sub-modo replica um exemplo Postman específico:
    #
    # mode=address → "Extrair com dimensão e Address Point" (literal):
    #   dimension.buffer com 4 raios (3/5/8/10KM) + addresses [{recId,zipCode,number}].
    #   Sem data.geoLevel. Cada saída é uma linha por (endereço × raio).
    #
    # mode=xy → tentativa de "enriquecer no setor onde o ponto cai":
    #   sem dimension + data.geoLevel:49 + values [{id,x,y}].
    #   Esse caminho ESTOURA em DEV (BuilderService.CreateMetadataObjects
    #   linha 905) — sem precedente no Postman para data.values puro sem
    #   dimension. Mantemos para reportar o bug.
    #
    # Expressions: 449 e 298 são as mais usadas em exemplos de setor 49 (EX,
    # sem agg). Para misturar com PS de PJ (Geopop Supply), incluir agg.
    expressions = {
        "major": None,
        "moduleId": None,
        "subModule": None,
        "select": [
            {"id": 449},
            {"id": 298},
        ],
        "where": [],
        "groupBy": [],
        "having": [],
        "orderBy": [],
        "pageOptions": None,
    }

    if mode == "address":
        return {
            "compact": False,
            "verbose": False,
            "dryRun": dry_run,
            "delimiter": "|",
            "formatType": "csv",
            "dimension": {"buffer": {"values": BUFFER_RAIOS}},
            "expressions": expressions,
            "data": {
                "addresses": ENDERECOS,
                "select": [],
                "where": [],
                "orderBy": [],
                "pageOptions": None,
            },
        }

    if mode == "xy":
        return {
            "compact": False,
            "dryRun": dry_run,
            "delimiter": "|",
            "formatType": "csv",
            "expressions": expressions,
            "data": {
                "geoLevel": 49,
                "values": PONTOS_XY,
                "select": [],
                "where": [],
                "orderBy": [],
                "pageOptions": None,
            },
        }

    raise ValueError(f"mode desconhecido: {mode!r}")


def _executar_summary(token: str, payload: dict, label: str) -> requests.Response:
    """POST no summary com tratamento padrão. Retorna a Response em caso de 200.
    Em erro != 200, imprime diagnóstico completo e encerra (sys.exit)."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    print(f"\nPOST {SUMMARY_URL}  ({label})")

    try:
        response = requests.post(SUMMARY_URL, headers=headers, json=payload,
                                 timeout=120)
    except requests.RequestException as exc:
        print(f"Falha de rede no enriquecimento: {exc}", file=sys.stderr)
        sys.exit(5)

    print(f"  status: {response.status_code}")

    if response.status_code != 200:
        mensagens = {
            400: "Payload inválido (mistura PS/EX sem agg, formato, limites).",
            401: "Não autenticado — token inválido ou expirado.",
            403: "Sem permissão para essa expressão/ambiente.",
            404: "Chave sem match ou endereço não geocodificado.",
            422: "Expressão inexistente ou filtro incompatível.",
            429: "Rate limit excedido.",
            500: "Erro interno do servidor — geocoder, SQLCog ou similar.",
        }
        if response.status_code in mensagens:
            print(mensagens[response.status_code])
        try:
            body_json = response.json()
            print("Body:")
            print(json.dumps(body_json, indent=2, ensure_ascii=False))
        except ValueError:
            print(f"Body (texto, {len(response.text)} chars):")
            print(response.text)
        sys.exit(6)

    return response


def _imprimir_resposta(response: requests.Response, titulo: str) -> None:
    content_type = response.headers.get("Content-Type", "")
    print(f"\n{titulo} ({content_type}):")
    if "json" in content_type:
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
    else:
        print(response.text)


def _build_payload(mode: str, dry_run: bool) -> dict:
    if mode == "postman-clone":
        return montar_payload_postman_clone(dry_run=dry_run)
    return montar_payload_enriquecimento(mode=mode, dry_run=dry_run)


def extrair(token: str, mode: str, do_dry_run: bool, auto_yes: bool) -> None:
    if mode == "xy":
        print(f"  pontos XY: {len(PONTOS_XY)} | dimension.geoLevel=49")
    elif mode == "address":
        print(f"  endereços: {len(ENDERECOS)} | dimension.geoLevel=49")
    else:
        print(f"  postman-clone: 1 ponto XY | dimension.buffer 4 raios | 30 vars")
    print(f"  modo: {mode}")

    if do_dry_run:
        payload_dry = _build_payload(mode=mode, dry_run=True)
        resp_dry = _executar_summary(token, payload_dry, label="dryRun=true")
        _imprimir_resposta(resp_dry, "Estimativa (dryRun)")

        if not auto_yes and sys.stdin.isatty():
            confirm = input("\nConfirmar extração real? [y/N]: ").strip().lower()
            if confirm != "y":
                print("Extração cancelada pelo usuário.")
                return
        elif not auto_yes and not sys.stdin.isatty():
            print("\nSem TTY e sem --yes — pulando extração real.")
            return

    payload_real = _build_payload(mode=mode, dry_run=False)
    resp = _executar_summary(token, payload_real, label="extração real")
    _imprimir_resposta(resp, "Resposta")


# ---- Catálogo (diagnóstico) ----------------------------------------------

def _get_json(token: str, url: str, label: str) -> object:
    headers = {"Authorization": f"Bearer {token}"}
    print(f"\nGET  {url}  ({label})")
    try:
        response = requests.get(url, headers=headers, timeout=60)
    except requests.RequestException as exc:
        print(f"Falha de rede: {exc}", file=sys.stderr)
        sys.exit(7)
    print(f"  status: {response.status_code}")
    if response.status_code != 200:
        print(f"  body: {response.text[:1000]}", file=sys.stderr)
        sys.exit(7)
    return response.json()


def listar_modulos(token: str) -> None:
    geolevels = _get_json(token, GEOLEVELS_URL, "geolevels disponíveis")
    print("\nGeolevels disponíveis:")
    if isinstance(geolevels, list):
        for gl in geolevels:
            if isinstance(gl, dict):
                print(f"  id={gl.get('id'):>4}  {gl.get('name') or gl.get('description')}")
    else:
        print(json.dumps(geolevels, indent=2, ensure_ascii=False))

    modulos = _get_json(token, MODULE_LIST_URL, "módulos contratados")
    print("\nMódulos contratados no env:")
    if isinstance(modulos, list):
        for m in modulos:
            if isinstance(m, dict):
                versions = m.get('versions') or []
                version_str = ', '.join(
                    str(v.get('major')) for v in versions if isinstance(v, dict)
                ) if versions else '?'
                print(f"  id={m.get('objectId') or m.get('id'):>4}  "
                      f"{m.get('name'):<30}  versions=[{version_str}]")
    else:
        print(json.dumps(modulos, indent=2, ensure_ascii=False))


def listar_variaveis(token: str, module_id: int) -> None:
    url = MODULE_VARS_URL_TEMPLATE.format(module_id=module_id)
    payload = _get_json(token, url, f"expressions do módulo {module_id}")
    print(f"\nExpressions do módulo {module_id}:")
    if isinstance(payload, list):
        for e in payload:
            if isinstance(e, dict):
                eid = e.get('id') or e.get('objectId')
                name = e.get('name') or e.get('alias') or e.get('description', '')
                ftype = e.get('fieldType') or e.get('type')
                col = e.get('columnName', '')
                print(f"  id={eid:>6}  ftype={ftype}  {name}  (col={col})")
    elif isinstance(payload, dict):
        # Pode vir como {expressions:[...], ...}
        exprs = payload.get('expressions') or payload.get('items') or []
        for e in exprs:
            if isinstance(e, dict):
                eid = e.get('id') or e.get('objectId')
                name = e.get('name') or e.get('alias') or e.get('description', '')
                ftype = e.get('fieldType') or e.get('type')
                print(f"  id={eid:>6}  ftype={ftype}  {name}")
        if not exprs:
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])


# ---- Main ------------------------------------------------------------------

def _resolver_token(args: argparse.Namespace) -> str:
    """Resolve um Bearer token: usa NTP_TOKEN/--token se houver, senão faz
    login interativo (sequência de 2 logins + lista ambientes)."""
    token_pronto = args.token or os.environ.get("NTP_TOKEN")
    if token_pronto:
        if token_pronto.lower().startswith("bearer "):
            token_pronto = token_pronto[7:].strip()
        print("Usando JWT pré-fornecido (sem chamar Passport).")
        return token_pronto

    email, senha = obter_credenciais(args)
    env_id_preset = obter_env_id(args)
    auth1 = autenticar(email, senha, env_id=None)
    ambientes = listar_ambientes(auth1["token"])
    env_id = escolher_ambiente(ambientes, env_id_preset=env_id_preset)
    auth2 = autenticar(email, senha, env_id=env_id)
    return auth2["token"]


def main() -> None:
    args = parse_args()

    # Modo (D): só dump do payload, sem chamar API.
    if args.dump_payload:
        if args.mode == "xy":
            validar_xy()
        do_dry_run = not args.no_dry_run
        print(f"Payload do POST /export/summary (mode={args.mode}, "
              f"dryRun={'true (mostra primeiro)' if do_dry_run else 'false'}):")
        payload = montar_payload_enriquecimento(mode=args.mode,
                                                dry_run=do_dry_run)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    # Modos diagnósticos: precisam só de token, não extraem nada.
    if args.list_modules:
        token = _resolver_token(args)
        listar_modulos(token)
        return

    if args.list_vars is not None:
        token = _resolver_token(args)
        listar_variaveis(token, args.list_vars)
        return

    # Modo principal: enriquecimento.
    if args.mode == "xy":
        validar_xy()
    do_dry_run = not args.no_dry_run
    token = _resolver_token(args)
    extrair(token, mode=args.mode, do_dry_run=do_dry_run, auto_yes=args.yes)


if __name__ == "__main__":
    main()
