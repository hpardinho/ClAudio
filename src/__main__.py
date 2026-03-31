"""
__main__.py — Ponto de entrada do ClAudio.
Uso: python -m src
"""

import logging
import sys
import time

from src.brain import ask_gemini
from src.actions import try_execute_action, try_local_bypass
from src import gui_bridge

# ── Logging ─────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("claudio")

# ── Imports opcionais (módulos de voz) ──────────────────────────

try:
    from src.wake_word import listen_for_wake_word
    from src.recorder import record_until_silence
    from src.transcriber import transcribe
    from src.speaker import speak
    _VOICE_AVAILABLE = True
except ImportError:
    _VOICE_AVAILABLE = False


# ── Handler para mensagens do browser ───────────────────────────

def _handle_browser_message(user_text: str) -> None:
    """Processa mensagem recebida do browser via WebSocket."""
    logger.info("Mensagem do browser: %s", user_text[:80])

    gui_bridge.send("thinking", transcript=user_text, message=user_text, role="user")

    # Tenta usar atalhos offline (burlar API para economia e velocidade)
    bypass_result = try_local_bypass(user_text)
    if bypass_result:
        simulated_action, spoken_response = bypass_result
        from src.brain import get_daily_interactions
        current_count = get_daily_interactions()
        gui_bridge.send("speaking", transcript=spoken_response, message=spoken_response, interactions=current_count)
        logger.info("⚡ Bypass Local disparado! Resposta: %s", spoken_response)
        if try_execute_action(simulated_action):
            logger.info("Ação simulada executada com sucesso.")
        return

    # Caso contrário, queima cota do Gemini normalmente
    try:
        response = ask_gemini(user_text)
    except RuntimeError as err:
        logger.error("Erro: %s", err)
        gui_bridge.send("error", transcript="Erro ao processar.")
        return

    from src.brain import get_daily_interactions
    current_count = get_daily_interactions()

    gui_bridge.send("speaking", transcript=response, message=response, interactions=current_count)
    logger.info("Resposta: %s (Interações hoje: %d)", response[:80], current_count)

    if try_execute_action(response):
        logger.info("Ação executada a partir da resposta.")


# ── Foco de Janela Nativo (Windows) ─────────────────────────────

from src.window_manager import bring_assistant_to_front

def _bring_window_to_front() -> None:
    """Intermediário do callback de wake word (aponta pro módulo window_manager)."""
    bring_assistant_to_front()


# ── Modos de operação ──────────────────────────────────────────

def _web_mode() -> None:
    """Modo web: serve a UI em localhost e abre como widget."""
    from src.ui_server import start as start_ui, open_widget

    gui_bridge.start(
        on_user_message=_handle_browser_message,
        on_wake_word=_bring_window_to_front
    )
    start_ui()
    open_widget()

    gui_bridge.send("idle")
    logger.info("Widget aberto. Clique no orb para falar. Ctrl+C para encerrar.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Encerrado pelo usuário.")


def _text_mode() -> None:
    """Fallback interativo por texto quando os módulos de voz não estão disponíveis."""
    logger.info("Rodando em modo texto. Digite 'sair' para encerrar.")
    gui_bridge.start(on_user_message=_handle_browser_message, on_wake_word=_bring_window_to_front)
    gui_bridge.send("idle")

    while True:
        try:
            user_input = input("\n🎤 Você: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nAté logo!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("sair", "exit", "quit"):
            print("Até logo!")
            break

        _handle_browser_message(user_input)


def _voice_mode() -> None:
    """Loop principal com reconhecimento de voz nativo (Python)."""
    gui_bridge.start(on_user_message=_handle_browser_message)
    gui_bridge.send("idle")
    logger.info("Assistente pronto. Diga a palavra de ativação para começar.")

    while True:
        try:
            listen_for_wake_word()
            gui_bridge.send("wake", transcript="oi!")

            speak("Pode falar.")
            audio = record_until_silence()
            gui_bridge.send("listening", transcript="ouvindo...")

            text = transcribe(audio)
            logger.info("Transcrição: %s", text)
            _handle_browser_message(text)

            if not try_execute_action(text):
                speak(text)

        except KeyboardInterrupt:
            logger.info("Encerrado pelo usuário.")
            break
        except RuntimeError as err:
            logger.error("Erro no loop: %s", err)
            gui_bridge.send("error", transcript="Ocorreu um erro.")
            continue


# ── Entrypoint ──────────────────────────────────────────────────

def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else None

    if mode == "web":
        _web_mode()
    elif mode == "text":
        _text_mode()
    elif _VOICE_AVAILABLE:
        _voice_mode()
    else:
        logger.warning(
            "Módulos de voz não encontrados. Use 'python -m src web' para modo web "
            "ou 'python -m src text' para modo texto."
        )
        _web_mode()


if __name__ == "__main__":
    main()
