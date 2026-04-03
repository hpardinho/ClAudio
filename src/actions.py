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


def _type_text_native(texto: str) -> None:
    """
    Digita texto usando a API nativa do Windows SendInput (KEYEVENTF_UNICODE).
    Suporta perfeitamente português (acentos) sem usar clipboard,
    e destrava ativamente qualquer tecla modificadora antes.
    """
    import ctypes
    from ctypes import wintypes
    import time
    
    user32 = ctypes.windll.user32

    # Tenta liberar qualquer tecla modificadora presa (como ALT)
    KEYEVENTF_KEYUP = 0x0002
    for vk in [0x12, 0x11, 0x10, 0x5B, 0x5C]:  # ALT, CTRL, SHIFT, LWIN, RWIN
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.1)

    INPUT_KEYBOARD = 1
    KEYEVENTF_UNICODE = 0x0004

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("ki", KEYBDINPUT),
            ("mi", MOUSEINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("union", INPUT_UNION),
        ]

    for char in texto:
        scan = ord(char)

        # Key down
        down = INPUT()
        down.type = INPUT_KEYBOARD
        down.union.ki.wVk = 0
        down.union.ki.wScan = scan
        down.union.ki.dwFlags = KEYEVENTF_UNICODE

        # Key up
        up = INPUT()
        up.type = INPUT_KEYBOARD
        up.union.ki.wVk = 0
        up.union.ki.wScan = scan
        up.union.ki.dwFlags = KEYEVENTF_UNICODE | KEYEVENTF_KEYUP

        inputs = (INPUT * 2)(down, up)
        user32.SendInput(2, ctypes.byref(inputs), ctypes.sizeof(INPUT))
        time.sleep(0.015)

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
        "fechar janela": ("ACTION:fechar_janela", "Fechando."),
        "feche a janela": ("ACTION:fechar_janela", "Fechando."),
        "fecha a janela": ("ACTION:fechar_janela", "Fechando."),
        "fechar aba": ("ACTION:fechar_janela", "Fechando."),
        "fechar": ("ACTION:fechar_janela", "Fechando."),
        "feche": ("ACTION:fechar_janela", "Fechando."),
        "fecha isso": ("ACTION:fechar_janela", "Fechando."),
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

    # ── Bypass dinâmico: digitação direta (sem LLM) ──────────────
    # Detecta verbos de digitação e extrai o texto real do usuário, preservando capitalização original.
    _TYPING_KEYWORDS = ["digite", "digita", "escreva", "escreve"]
    for kw in _TYPING_KEYWORDS:
        idx = text.find(kw)
        if idx != -1:
            # Extrai o texto ORIGINAL (com capitalização) após a palavra-chave
            # Calcula offset no texto original (user_text) baseado na posição encontrada no texto normalizado
            after_kw = user_text.strip()[idx + len(kw):]
            # Remove lixo de ligação entre a keyword e o conteúdo ("que", "o seguinte", vírgulas etc)
            import re as _re
            after_kw = _re.sub(r'^[\s,:]+', '', after_kw)  # remove pontuação/espaço inicial
            after_kw = _re.sub(r'^(que|o seguinte|isso|o texto|pra mim|para mim)\s*[:;,]?\s*', '', after_kw, flags=_re.IGNORECASE)
            after_kw = after_kw.strip()
            if after_kw:
                return (f"ACTION:digitar:{after_kw}", "Digitando.")
    
    # ── Bypass dinâmico: busca na web ──────────────────────────────
    _SEARCH_KEYWORDS = ["pesquise", "pesquisa", "busque", "busca"]
    for kw in _SEARCH_KEYWORDS:
        idx = text.find(kw)
        if idx != -1:
            after_kw = user_text.strip()[idx + len(kw):]
            import re as _re
            after_kw = _re.sub(r'^[\s,:]+', '', after_kw)
            after_kw = _re.sub(r'^(por|sobre|no google|na web|na internet)\s*[:;,]?\s*', '', after_kw, flags=_re.IGNORECASE)
            after_kw = after_kw.strip()
            if after_kw:
                return (f"ACTION:pesquisar_web:{after_kw}", "Pesquisando.")

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
    Tenta interpretar a resposta como um ou mais comandos ACTION e executá-los em sequência.
    Extração por token ACTION: permitindo resistência a erros de quebra de linha do LLM.
    """
    import time
    
    parts = response.split("ACTION:")
    any_action_executed = False
    just_opened_app = False

    for part in parts[1:]:
        raw_action = part.strip().split("\n")[0].strip() # Pega só a ação até a primeira linha pra evitar lixo
        if not raw_action:
            continue

        any_action_executed = True

        if raw_action.startswith("esperar:"):
            try:
                segundos = float(raw_action.split(":", 1)[1].strip())
                time.sleep(segundos)
                logger.info("Esperando por %s segundos", segundos)
            except ValueError:
                pass

        elif raw_action.startswith("nova_nota:"):
            texto = raw_action.split(":", 1)[1].strip()
            if texto:
                _nova_nota(texto)

        elif raw_action.startswith("abrir_app:"):
            app = raw_action.split(":", 1)[1].strip()
            # Sanitização rigorosa (mitigação contra OS Command Injections)
            import re
            seguro_app = re.sub(r'[&|;<>^\(\)]', '', app).strip()
            # Execução baseada em subprocess de forma isolada do interpretador bash global
            subprocess.Popen(["cmd.exe", "/c", "start", '""', seguro_app], shell=False)
            just_opened_app = True
            logger.info("Aplicativo lançado com segurança: %s", seguro_app)

        elif raw_action.startswith("abrir_app_admin:"):
            app = raw_action.split(":", 1)[1].strip()
            import re
            seguro_app = re.sub(r'[&|;<>^\(\)]', '', app).strip()
            import ctypes
            # ShellExecuteW com o parâmetro 'runas' recruta o sistema UAC Nativo do Windows pra elevação
            ctypes.windll.shell32.ShellExecuteW(None, "runas", seguro_app, "", None, 1)
            just_opened_app = True
            logger.info("Tentativa de abrir aplicativo Nível Administrador: %s", seguro_app)

        elif raw_action.startswith("fechar_janela"):
            from src.window_manager import restore_focus_for_typing
            # Necessário minimizar o ClAudio primeiro, senão ele vai dar ALT+F4 em si mesmo!
            restore_focus_for_typing()
            
            # O PyAutoGUI tentará de forma mais segura injetar as teclas na janela em evidência do OS.
            pyautogui.hotkey('alt', 'f4')
            logger.info("Atalho de fechamento enviado (ALT+F4).")

        elif raw_action.startswith("abrir_pasta:"):
            caminho = raw_action.split(":", 1)[1].strip()
            try:
                safe_caminho = caminho.replace('"', '').strip()
                if safe_caminho == "":
                    subprocess.Popen(["explorer.exe"])
                elif safe_caminho.startswith("steam://"):
                    os.startfile(safe_caminho)
                else:
                    subprocess.Popen(["explorer.exe", safe_caminho])
                just_opened_app = True
                logger.info("Explorador/URI isolado apontado para: %s", safe_caminho)
            except Exception as e:
                logger.error("Falha ao abrir a pasta/protocolo '%s': %s", caminho, e)

        elif raw_action.startswith("pesquisar_web:"):
            termo = raw_action.split(":", 1)[1].strip()
            url = f"https://www.google.com/search?q={urllib.parse.quote(termo)}"
            webbrowser.open(url)
            just_opened_app = True
            logger.info("Aberto nova guia de pesquisa do Google para: %s", termo)

        elif raw_action.startswith("digitar:"):
            texto_para_digitar = raw_action.split(":", 1)[1].strip()
            
            from src.window_manager import restore_focus_for_typing
            restore_focus_for_typing()

            # Se o LLM resolveu abrir algo no mesmo bloco, espera a janela carregar
            if just_opened_app:
                time.sleep(2.0)
                just_opened_app = False
            
            # Digita diretamente via SendInput Unicode (sem clipboard, sem atalhos)
            _type_text_native(texto_para_digitar)
            logger.info("Digitado via SendInput %d caracteres: '%s'", len(texto_para_digitar), texto_para_digitar[:50])

        else:
            # Ações simples sem arg que sobraram (fallback de legado)
            # Retiramos espaços pra match exato (ex: abrir_navegador)
            base_cmd = raw_action.split()[0] if raw_action else ""
            handler = _ACTION_MAP.get(base_cmd)
            if handler:
                handler()
                just_opened_app = True # Comportamentos legado costumam abrir web, spotify, etc
            else:
                logger.warning("ACTION desconhecida ordenando pelo Gemini ignorada: %s", raw_action)

    return any_action_executed
