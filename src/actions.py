"""
actions.py — Executa ações no sistema operacional a partir de comandos do modelo.
"""

import logging
import subprocess
import webbrowser
import os
import urllib.parse
from pathlib import Path
import pyautogui

logger = logging.getLogger(__name__)

# Diretório seguro para salvar notas
_NOTES_DIR = Path(__file__).resolve().parent.parent / "data"

# ── Mapa de ações permitidas ────────────────────────────────────

_ALLOWED_ACTIONS: dict[str, str] = {
    "abrir_navegador": "Abre o navegador padrão",
    "abrir_spotify":   "Abre o Spotify",
}


def _abrir_navegador() -> None:
    webbrowser.open("https://google.com")
    logger.info("Navegador aberto.")


def _abrir_spotify() -> None:
    subprocess.Popen(["start", "spotify"], shell=True)
    logger.info("Spotify iniciado.")


def _nova_nota(texto: str) -> None:
    """Salva uma nota em arquivo de texto no diretório data/."""
    _NOTES_DIR.mkdir(parents=True, exist_ok=True)
    filepath = _NOTES_DIR / "notas.txt"
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(f"{texto}\n")
    logger.info("Nota salva: %s", texto[:50])


# ── Dispatcher e Interceptador Local Bypasses ──────────────────

def try_local_bypass(user_text: str) -> tuple[str, str] | None:
    """
    Inspeciona a fala do usuário e devolve o comando nativo e a fala de resposta, abortando o LLM.
    """
    if not user_text:
        return None

    import re
    text = user_text.lower().strip()
    # Remove pontuações simples
    text = re.sub(r'[^a-z0-9áéíóúâêîôûãõç\s]', '', text).strip()

    bypass_map = {
        "calculadora": ("ACTION:abrir_app:calc", "Abrindo a calculadora."),
        "arquivos": ("ACTION:abrir_pasta:", "Abrindo o explorador de arquivos."),
        "explorador de arquivos": ("ACTION:abrir_pasta:", "Abrindo o explorador de arquivos."),
        "photoshop": ("ACTION:abrir_app:photoshop", "Abrindo o Adobe Photoshop."),
        "after effects": ("ACTION:abrir_app:afterfx", "Iniciando o After Effects."),
        "media encoder": ("ACTION:abrir_app:\"adobe media encoder\"", "Abrindo o Media Encoder."),
        "steam": ("ACTION:abrir_pasta:steam://open/main", "Iniciando a Steam."),
        "valorant": ("ACTION:abrir_app_admin:\"C:\\Riot Games\\Riot Client\\RiotClientServices.exe\" --launch-product=valorant --launch-patchline=live", "Iniciando o Riot Client para Valorant."),
        "navegador": ("ACTION:abrir_navegador", "Abrindo o navegador padrão."),
        "spotify": ("ACTION:abrir_spotify", "Iniciando o Spotify."),
        "bloco de notas": ("ACTION:abrir_app:notepad", "Abrindo o bloco de notas."),
        "cmd como administrador": ("ACTION:abrir_app_admin:cmd.exe", "Iniciando Prompt de Comando como Administrador."),
        "cmd como admin": ("ACTION:abrir_app_admin:cmd.exe", "Iniciando Prompt de Comando como Administrador."),
        "cmd": ("ACTION:abrir_app:cmd.exe", "Iniciando Prompt de Comando."),
        "powershell como administrador": ("ACTION:abrir_app_admin:powershell.exe", "Iniciando PowerShell como Administrador."),
        "powershell como admin": ("ACTION:abrir_app_admin:powershell.exe", "Iniciando PowerShell como Administrador."),
        "powershell": ("ACTION:abrir_app:powershell.exe", "Iniciando PowerShell.")
    }

    # Match direto
    if text in bypass_map:
        return bypass_map[text]

    # Busca relaxada para capturar 'abra o photoshop' ou 'abre a steam'
    for keyword, data in bypass_map.items():
        if keyword in text and len(text) <= len(keyword) + 12:
            return data

    return None

_ACTION_MAP = {
    "abrir_navegador": _abrir_navegador,
    "abrir_spotify":   _abrir_spotify,
}


def try_execute_action(response: str) -> bool:
    """
    Tenta interpretar a resposta como um comando ACTION e executá-lo.
    """
    if not response.startswith("ACTION:"):
        return False

    raw_action = response[len("ACTION:"):].strip()

    if raw_action.startswith("nova_nota:"):
        texto = raw_action.split(":", 1)[1].strip()
        if texto:
            _nova_nota(texto)
        return True

    elif raw_action.startswith("abrir_app:"):
        app = raw_action.split(":", 1)[1].strip()
        # Sanitização rigorosa (mitigação contra OS Command Injections)
        import re
        seguro_app = re.sub(r'[&|;<>^\(\)]', '', app).strip()
        # Execução baseada em subprocess de forma isolada do interpretador bash global
        subprocess.Popen(["cmd.exe", "/c", "start", '""', seguro_app], shell=False)
        logger.info("Aplicativo lançado com segurança: %s", seguro_app)
        return True

    elif raw_action.startswith("abrir_app_admin:"):
        app = raw_action.split(":", 1)[1].strip()
        import re
        seguro_app = re.sub(r'[&|;<>^\(\)]', '', app).strip()
        import ctypes
        # ShellExecuteW com o parâmetro 'runas' recruta o sistema UAC Nativo do Windows pra elevação
        ctypes.windll.shell32.ShellExecuteW(None, "runas", seguro_app, "", None, 1)
        logger.info("Tentativa de abrir aplicativo Nível Administrador: %s", seguro_app)
        return True

    elif raw_action.startswith("abrir_pasta:"):
        caminho = raw_action.split(":", 1)[1].strip()
        try:
            safe_caminho = caminho.replace('"', '').strip()
            # Se vier vazio (como o comando "arquivos" isolado), mandamos abrir só o meu computador.
            # Se for link URI como steam:// também passa por aqui com segurança.
            if safe_caminho == "":
                subprocess.Popen(["explorer.exe"])
            elif safe_caminho.startswith("steam://"):
                # Abre links URI registrados no proprio OS usando o startfile limpo
                os.startfile(safe_caminho)
            else:
                subprocess.Popen(["explorer.exe", safe_caminho])
            logger.info("Explorador/URI isolado apontado para: %s", safe_caminho)
        except Exception as e:
            logger.error("Falha ao abrir a pasta/protocolo '%s': %s", caminho, e)
        return True

    elif raw_action.startswith("pesquisar_web:"):
        termo = raw_action.split(":", 1)[1].strip()
        url = f"https://www.google.com/search?q={urllib.parse.quote(termo)}"
        webbrowser.open(url)
        logger.info("Aberto nova guia de pesquisa do Google para: %s", termo)
        return True

    elif raw_action.startswith("digitar:"):
        texto = raw_action.split(":", 1)[1].strip()
        
        # Centralizando a abstração da DLL do Windows para não poluir esse módulo e manter open-source escalável.
        from src.window_manager import restore_focus_for_typing
        restore_focus_for_typing()
            
        pyautogui.write(texto, interval=0.015)
        logger.info("Digitado remotamente %d letras no foco ativo", len(texto))
        return True

    # Ações simples sem arg que sobraram (fallback de legado)
    handler = _ACTION_MAP.get(raw_action)
    if handler:
        handler()
        return True

    logger.warning("ACTION desconhecida ordenando pelo Gemini ignorada: %s", raw_action)
    return True
