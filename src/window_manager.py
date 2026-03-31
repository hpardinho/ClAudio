"""
window_manager.py — Isola e abstrai as APIs nativas do Sistema Operacional (Windows).
Impede o acoplamento excessivo de chamadas de kernel (ctypes) nas raízes de rotina de IA.
"""

import sys
import time
import logging

logger = logging.getLogger(__name__)

def is_windows() -> bool:
    return sys.platform == "win32"

def _find_claudio_hwnd():
    """Varre ativamente todas as janelas do Windows e retorna a do ClAudio ignorando sufixos como '- Google Chrome'."""
    if not is_windows(): return None
    import ctypes
    from ctypes import wintypes
    
    user32 = ctypes.windll.user32
    target_hwnd = None
    
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    
    def enum_cb(hwnd, lparam):
        nonlocal target_hwnd
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                # Corta a busca pela raiz para evitar falhas com Em-Dash HTML, Hífen e injecões de lentidão do Chrome
                if "ClAudio" in buff.value:
                    target_hwnd = hwnd
                    return False  # Achou, para o loop C++
        return True
        
    user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
    return target_hwnd

def bring_assistant_to_front() -> None:
    """Procura pelo título exato da janela do ClAudio e a traz para a frente (des-minimiza)."""
    if not is_windows():
        return
        
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = _find_claudio_hwnd()
        
        if hwnd:
            # 9 = SW_RESTORE
            user32.ShowWindow(hwnd, 9)
            
            # Hack de teclado fantasma ALT para simular interesse físico do usuário na janela,
            # forçando o Foco Ativo do Windows Bypassing o Anti-Spam Popup.
            user32.keybd_event(0x12, 0, 0, 0) # Pressiona ALT (VK_MENU)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            user32.keybd_event(0x12, 0, 2, 0) # Solta ALT
            
            logger.info("Widget resgatado pro centro da tela com sucesso!")
        else:
            logger.debug("Janela não encontrada pelo nome exato: '%s'", title)
    except Exception as e:
        logger.error("Falha na API do Windows: %s", e)

def restore_focus_for_typing() -> None:
    """
    Minimiza ou joga o ClAudio para trás rapidamente para devolver o foco 
    ativo para o programa anterior do usuário (necessário para o pyautogui escrever no app base).
    """
    if not is_windows():
        return
        
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = _find_claudio_hwnd()
        if hwnd:
            # 6 = SW_MINIMIZE (Minimiza, transferindo o foco nativamente)
            user32.ShowWindow(hwnd, 6)
            time.sleep(0.3)
    except Exception as e:
        logger.error("Falha ao restaurar o foco para a digitação remota: %s", e)

def remove_window_frame() -> None:
    """Arranca as bordas do Windows (inclui botões minimizar/maximizar e fechar),
       tornando-a uma janela de quiosque/exclusiva (frameless)."""
    if not is_windows():
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = _find_claudio_hwnd()
        if hwnd:
            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            
            # Anula operações binárias nos bits do título e de engorda da borda
            user32.SetWindowLongW(hwnd, GWL_STYLE, style & ~WS_CAPTION & ~WS_THICKFRAME)
            
            SWP_FRAMECHANGED = 0x0020
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOZORDER = 0x0004
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
            logger.info("Janela convertida para Native Frameless (sem bordas) com sucesso.")
    except Exception as e:
        logger.error("Falha ao remover barras superior da janela: %s", e)

def start_drag() -> None:
    """Simula um clique na 'Antiga Titlebar' e libera a captura de cursos, 
       permitindo que o Windows mova a janela do Chrome mesmo que ela não possua bordas."""
    if not is_windows():
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = _find_claudio_hwnd()
        if hwnd:
            user32.ReleaseCapture()
            WM_NCLBUTTONDOWN = 0x00A1
            HTCAPTION = 2
            user32.SendMessageW(hwnd, WM_NCLBUTTONDOWN, HTCAPTION, 0)
    except Exception as e:
        pass
