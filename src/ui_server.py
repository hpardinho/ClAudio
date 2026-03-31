"""
ui_server.py — Serve a interface HTML em localhost e abre como widget.
Isso é necessário porque a Web Speech API (microfone) não funciona em file://.
"""

import http.server
import logging
import os
import shutil
import subprocess
import threading
import webbrowser
from pathlib import Path

logger = logging.getLogger(__name__)

UI_DIR = Path(__file__).resolve().parent / "ui"
UI_PORT = 8766  # Porta para o servidor HTTP (WebSocket usa 8765)

_server = None
_browser_process = None


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """Handler HTTP que não imprime logs no console."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(UI_DIR), **kwargs)

    def log_message(self, format, *args):
        pass  # Silencia os logs do HTTP server


def start() -> int:
    """Inicia o servidor HTTP em background. Retorna a porta."""
    global _server
    if _server is not None:
        return UI_PORT

    _server = http.server.HTTPServer(("localhost", UI_PORT), _QuietHandler)
    thread = threading.Thread(target=_server.serve_forever, daemon=True)
    thread.start()
    logger.info("UI servida em http://localhost:%d", UI_PORT)
    return UI_PORT


def open_widget(width: int = 420, height: int = 620) -> None:
    """
    Abre a interface como 'widget' (janela sem barra de navegação).
    Tenta Chrome/Edge em modo --app, senão abre no browser padrão.
    """
    url = f"http://localhost:{UI_PORT}/index.html"

    # Procura Chrome ou Edge instalados
    chrome_paths = [
        # Chrome
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        # Edge
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]

    browser_exe = None
    for path in chrome_paths:
        if os.path.isfile(path):
            browser_exe = path
            break

    if browser_exe:
        import tempfile
        temp_dir = os.path.join(tempfile.gettempdir(), "claudio_chrome_profile")
        
        global _browser_process
        # Modo --app: janela limpa sem barra de URL, tipo widget nativo
        # User-data-dir força a engine separar o processo físico do chrome habitual, viabilizando o terminate()
        _browser_process = subprocess.Popen([
            browser_exe,
            f"--app={url}",
            f"--window-size={width},{height}",
            f"--user-data-dir={temp_dir}",
            "--disable-extensions",
            "--disable-infobars",
            "--autoplay-policy=no-user-gesture-required",
        ])
        logger.info("Widget isolado e aberto via %s", Path(browser_exe).name)
    else:
        # Fallback: abre no browser padrão
        webbrowser.open(url)
        logger.info("Aberto no navegador padrão: %s", url)

def close_widget() -> None:
    """Encerra agressivamente o processo atrelado à UI do Chrome Chrome."""
    global _browser_process
    if _browser_process:
        try:
            _browser_process.terminate()
            logger.info("Processo Popen do Chrome GUI desligado.")
        except Exception as e:
            logger.error("Erro ao matar o GUI Chrome: %s", e)
