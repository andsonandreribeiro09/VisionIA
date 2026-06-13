import json
import os
import platform
import time
import urllib.error
import urllib.request
from datetime import datetime


def _truthy(valor):
    return str(valor or "").strip().lower() in {"1", "true", "sim", "yes", "on"}


def licenca_obrigatoria():
    return _truthy(os.getenv("VISIONAI_REQUIRE_LICENSE", "0"))


def licenca_configurada():
    return all([
        os.getenv("VISIONAI_LICENSE_SERVER", "").strip(),
        os.getenv("VISIONAI_STORE_ID", "").strip(),
        os.getenv("VISIONAI_LICENSE_KEY", "").strip(),
    ])


def _cache_path():
    return os.getenv("VISIONAI_LICENSE_CACHE_PATH", "data/license_cache.json")


def _api_url():
    servidor = os.getenv("VISIONAI_LICENSE_SERVER", "").strip().rstrip("/")
    if servidor.endswith("/admin"):
        servidor = servidor[:-6]
    return f"{servidor}/api/licenca/verificar"


def _machine_id():
    return os.getenv("VISIONAI_MACHINE_ID", "").strip() or platform.node() or "PC-LOJA"


def _ler_cache():
    caminho = _cache_path()
    try:
        with open(caminho, "r", encoding="utf-8") as arquivo:
            return json.load(arquivo)
    except (OSError, ValueError, TypeError):
        return None


def _salvar_cache(resultado):
    caminho = _cache_path()
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)

    pacote = {
        "salvo_em": time.time(),
        "resultado": resultado,
    }
    with open(caminho, "w", encoding="utf-8") as arquivo:
        json.dump(pacote, arquivo, ensure_ascii=False, indent=2)


def _resultado_local(mensagem, status="local", liberada=True):
    return {
        "status": status,
        "captura_liberada": liberada,
        "tablet_autorizado": liberada,
        "mensagem": mensagem,
        "modo": "local",
        "verificado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _resultado_cache_se_valido(mensagem_fallback):
    cache = _ler_cache()
    if not cache:
        return None

    idade_segundos = time.time() - float(cache.get("salvo_em") or 0)
    limite_horas = float(os.getenv("VISIONAI_LICENSE_GRACE_HOURS", "24") or 24)
    if idade_segundos > limite_horas * 3600:
        return None

    resultado = dict(cache.get("resultado") or {})
    if not resultado.get("captura_liberada"):
        return None

    resultado["offline_grace"] = True
    resultado["mensagem"] = f"{mensagem_fallback} Usando liberacao em cache por ate {int(limite_horas)}h."
    return resultado


def verificar_licenca(tablet_id=None, tablet_label=None, medicoes_hoje=0, banco_status=""):
    if not licenca_configurada():
        if licenca_obrigatoria():
            return _resultado_local(
                "Licenca nao configurada neste computador. Informe servidor, loja e chave da licenca.",
                status="nao_configurada",
                liberada=False,
            )
        return _resultado_local("Licenca local nao configurada. Captura liberada para validacao.")

    payload = {
        "store_id": os.getenv("VISIONAI_STORE_ID", "").strip(),
        "license_key": os.getenv("VISIONAI_LICENSE_KEY", "").strip(),
        "machine_id": _machine_id(),
        "tablet_id": (tablet_id or "").strip(),
        "tablet_label": (tablet_label or "").strip()[:180],
        "app_version": os.getenv("VISIONAI_APP_VERSION", "1.0.0").strip(),
        "medicoes_hoje": int(medicoes_hoje or 0),
        "banco_status": banco_status or "",
    }

    dados = json.dumps(payload).encode("utf-8")
    requisicao = urllib.request.Request(
        _api_url(),
        data=dados,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        timeout = float(os.getenv("VISIONAI_LICENSE_TIMEOUT", "5") or 5)
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
            corpo = resposta.read().decode("utf-8")
            resultado = json.loads(corpo)
    except urllib.error.HTTPError as exc:
        try:
            corpo = exc.read().decode("utf-8")
            resultado = json.loads(corpo)
        except Exception:
            resultado = {
                "status": "erro_http",
                "captura_liberada": False,
                "tablet_autorizado": False,
                "mensagem": f"Falha ao validar a licenca ({exc.code}).",
            }
    except Exception:
        cache = _resultado_cache_se_valido("Admin de licenca indisponivel.")
        if cache:
            return cache
        return {
            "status": "sem_conexao",
            "captura_liberada": False,
            "tablet_autorizado": False,
            "mensagem": "Nao foi possivel validar a licenca. Verifique internet ou admin central.",
        }

    if resultado.get("captura_liberada"):
        try:
            _salvar_cache(resultado)
        except OSError:
            pass

    return resultado
