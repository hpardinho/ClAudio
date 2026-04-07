"""
brain.py — Módulo de inteligência do ClAudio.
Gerencia conversas com a API do Google Gemini e persiste o histórico em SQLite.
"""

import logging
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

# ── Configuração ────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# Silencia logs verbosos de dependências
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("google_genai").setLevel(logging.WARNING)
logging.getLogger("google_genai.models").setLevel(logging.WARNING)

import sys
if getattr(sys, 'frozen', False):
    _base_dir = Path(sys.executable).parent
else:
    _base_dir = Path(__file__).resolve().parent.parent

_ENV_PATH = _base_dir / ".env"
load_dotenv(_ENV_PATH)

_api_key = os.environ.get("GEMINI_API_KEY")
if not _api_key:
    raise EnvironmentError(
        f"Variável de ambiente GEMINI_API_KEY não encontrada.\n"
        f"Crie um arquivo .env na mesma pasta do executável: {_ENV_PATH}"
    )

_client = genai.Client(api_key=_api_key)

MODELS = [
    "gemini-2.5-flash", 
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite"
]

SYSTEM_PROMPT = (
    "Você é ClAudio, um assistente pessoal virtual ágil para Windows. "
    "REGRAS DE CONTEXTO: \n"
    "1. Se o usuário pedir para 'escrever', 'digitar' ou 'mandar' uma mensagem/texto, VOCÊ DEVE OBRIGATORIAMENTE usar ACTION:digitar.\n"
    "2. Se o usuário pedir para 'fechar' algo que está aberto na tela, use ACTION:fechar_janela.\n"
    "Para executar ações autônomas no sistema, responda APENAS com um ou mais dos comandos exatos abaixo (um por linha):\n"
    "  ACTION:abrir_navegador\n"
    "  ACTION:abrir_spotify\n"
    "  ACTION:abrir_app:<nome executável (ex: calc, notepad, chrome, winword)>\n"
    "  ACTION:abrir_pasta:<caminho absoluto no PC, ex: C:/>\n"
    "  ACTION:pesquisar_web:<pesquisa exata a ser feita>\n"
    "  ACTION:digitar:<texto exato que deve ser escrito no foco atual>\n"
    "  ACTION:fechar_janela\n"
    "  ACTION:nova_nota:<texto da nota para lembrar offline>\n"
    "  ACTION:esperar:<tempo em segundos (ex: 1, 2)>"
)

# ── Banco de dados (histórico) ──────────────────────────────────

_APPDATA = Path(os.getenv("APPDATA", _base_dir))
_DATA_DIR = _APPDATA / "ClAudio" / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = _DATA_DIR / "history.db"


def _get_connection() -> sqlite3.Connection:
    """Retorna uma conexão ao banco, criando diretório e tabela se necessário."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """CREATE TABLE IF NOT EXISTS history (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            role    TEXT    NOT NULL,
            content TEXT    NOT NULL,
            ts      TEXT    NOT NULL
        )"""
    )
    conn.commit()
    return conn


def _load_history(conn: sqlite3.Connection, limit: int = 10) -> list[types.Content]:
    """Carrega as últimas `limit` mensagens no formato esperado pelo Gemini."""
    rows = conn.execute(
        "SELECT role, content FROM history ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [
        types.Content(role=role, parts=[types.Part(text=content)])
        for role, content in reversed(rows)
    ]


def get_daily_interactions() -> int:
    """Retorna o total de interações do usuário no ciclo atual (reinicia às 05h da manhã BRT)."""
    conn = _get_connection()
    try:
        now = datetime.now()
        # Se for antes das 5h da manhã, a cota ainda pertence ao dia anterior
        if now.hour < 5:
            start_date = (now - timedelta(days=1)).replace(hour=5, minute=0, second=0, microsecond=0)
        else:
            start_date = now.replace(hour=5, minute=0, second=0, microsecond=0)
            
        start_iso = start_date.isoformat()
        
        count = conn.execute(
            "SELECT COUNT(*) FROM history WHERE role = 'user' AND ts >= ?", 
            (start_iso,)
        ).fetchone()[0]
        return count
    except Exception:
        return 0
    finally:
        conn.close()


# ── API pública ─────────────────────────────────────────────────

def ask_gemini(user_text: str) -> str:
    """
    Envia a mensagem do usuário ao Gemini, mantendo contexto do histórico.
    Em caso de erro de cota, tenta modelos secundários.

    Args:
        user_text: Texto transcrito do usuário.

    Returns:
        Resposta do modelo como string.

    Raises:
        RuntimeError: Se a API retornar um erro inesperado e esgotar os modelos.
    """
    conn = _get_connection()

    try:
        history = _load_history(conn)
        reply = None

        # Tenta os modelos em cascata (fallback automático)
        for model in MODELS:
            try:
                chat = _client.chats.create(
                    model=model,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=512,
                    ),
                    history=history,
                )

                response = chat.send_message(user_text)
                reply = response.text.strip()
                logger.info("Modelo %s usado com sucesso.", model)
                break  # Deu certo, para o loop
                
            except Exception as e:
                # Qualquer falha com este modelo (cota, 404, 503) -> tenta o próximo
                logger.warning("Erro no modelo %s: %s. Tentando próximo...", model, str(e)[:100])
                continue

        if not reply:
            raise RuntimeError("Todos os modelos de IA falharam por falta de cota ou erro.")

        # Persiste no histórico
        ts = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO history (role, content, ts) VALUES (?, ?, ?)",
            ("user", user_text, ts),
        )
        conn.execute(
            "INSERT INTO history (role, content, ts) VALUES (?, ?, ?)",
            ("model", reply, ts),
        )
        conn.commit()

        logger.info("Gemini respondeu: %s", reply[:80])
        return reply

    except Exception:
        logger.exception("Erro ao chamar a API do Gemini")
        raise RuntimeError("Não foi possível processar. Tente novamente mais tarde.") from None

    finally:
        conn.close()
