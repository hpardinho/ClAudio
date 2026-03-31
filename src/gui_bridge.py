"""
gui_bridge.py — Conecta o assistente Python à interface HTML via WebSocket.
Suporta comunicação bidirecional: recebe texto do browser e envia respostas.
Requer: pip install websockets
"""

import asyncio
import json
import logging
import threading
from typing import Callable, Optional

import websockets

logger = logging.getLogger(__name__)

# ── Estado interno ──────────────────────────────────────────────

_clients: set = set()
_loop: Optional[asyncio.AbstractEventLoop] = None
_on_user_message: Optional[Callable[[str], None]] = None
_on_wake_word: Optional[Callable[[], None]] = None


async def _handler(websocket) -> None:
    """Gerencia a conexão de cada cliente WebSocket."""
    _clients.add(websocket)
    logger.info("Cliente conectado. Total: %d", len(_clients))
    
    try:
        from src.brain import get_daily_interactions
        initial_count = get_daily_interactions()
        await websocket.send(json.dumps({"state": "idle", "interactions": initial_count}))
        
        # Muta a tela para Frameless nativo assim que o HTML dá sinal de vida
        # Injetamos 1.5s de delay porque o Chrome não injeta a tag <title> de imediato quando a aba é carregada.
        def _delayed_frame_removal():
            import time
            time.sleep(1.5)
            from src.window_manager import remove_window_frame
            remove_window_frame()
        import threading
        threading.Thread(target=_delayed_frame_removal, daemon=True).start()
        
    except Exception as e:
        logger.error("Erro ao configurar setup inicial: %s", e)
        
    try:
        async for raw in websocket:
            try:
                data = json.loads(raw)
                msg_type = data.get("type")
                if msg_type == "user_message" and _on_user_message:
                    user_text = data.get("text", "").strip()
                    if user_text:
                        logger.info("Recebido do browser: %s", user_text[:80])
                        # Processa em thread separada para não bloquear o event loop
                        threading.Thread(
                            target=_on_user_message,
                            args=(user_text,),
                            daemon=True,
                        ).start()
                elif msg_type == "wake_word" and _on_wake_word:
                    logger.info("Wake word detectada! Chamando focus_window...")
                    threading.Thread(target=_on_wake_word, daemon=True).start()
                elif msg_type == "drag_window":
                    from src.window_manager import start_drag
                    start_drag()
                elif msg_type == "close_widget":
                    logger.info("Botão Fechar Acionado via UI. Encerrando Core do ClAudio...")
                    from src import ui_server
                    ui_server.close_widget()
                    import os
                    os._exit(0)
                    
            except json.JSONDecodeError:
                logger.warning("Mensagem inválida recebida: %s", raw[:100])
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        _clients.discard(websocket)
        logger.info("Cliente desconectado. Total: %d", len(_clients))


async def _broadcast(data: dict) -> None:
    """Envia dados JSON para todos os clientes conectados."""
    if not _clients:
        return
    msg = json.dumps(data, ensure_ascii=False)
    await asyncio.gather(
        *[client.send(msg) for client in _clients],
        return_exceptions=True,
    )


async def _serve() -> None:
    """Inicia o servidor WebSocket."""
    async with websockets.serve(_handler, "localhost", 8765):
        logger.info("WebSocket rodando em ws://localhost:8765")
        await asyncio.Future()  # Roda para sempre


def _run_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Executa o event loop em uma thread separada."""
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_serve())


# ── API pública ─────────────────────────────────────────────────

def start(
    on_user_message: Optional[Callable[[str], None]] = None,
    on_wake_word: Optional[Callable[[], None]] = None
) -> None:
    """
    Inicia o servidor WebSocket em uma thread daemon separada.

    Args:
        on_user_message: Callback chamado quando o browser envia uma mensagem.
                         Recebe o texto do usuário como argumento.
        on_wake_word: Callback acionado quando a wake-word 'Cláudio' é falada no frontend.
    """
    global _loop, _on_user_message, _on_wake_word
    if _loop is not None:
        logger.warning("Servidor WebSocket já está rodando.")
        return

    _on_user_message = on_user_message
    _on_wake_word = on_wake_word
    _loop = asyncio.new_event_loop()
    thread = threading.Thread(target=_run_loop, args=(_loop,), daemon=True)
    thread.start()


def send(
    state: str,
    transcript: str = "",
    message: str = "",
    role: str = "assistant",
    interactions: Optional[int] = None,
) -> None:
    """
    Envia atualização de estado para a interface web.

    Args:
        state: Um de 'idle', 'listening', 'thinking', 'speaking', 'wake', 'error'.
        transcript: Texto sendo ouvido ou falado (exibido na tela).
        message: Mensagem para o painel de histórico.
        role: 'user' ou 'assistant' (para estilização do histórico).
        interactions: Número de interações atuais para exibir limite.
    """
    if _loop is None:
        return

    data: dict = {"state": state}
    if transcript:
        data["transcript"] = transcript
    if message:
        data["message"] = message
        data["role"] = role
    if interactions is not None:
        data["interactions"] = interactions

    asyncio.run_coroutine_threadsafe(_broadcast(data), _loop)
