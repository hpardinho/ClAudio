"""
window_manager.py — Isola e abstrai as APIs nativas do Sistema Operacional (Windows).
Impede o acoplamento excessivo de chamadas de kernel (ctypes) nas raízes de rotina de IA.
"""

import sys
import time
import logging
import threading

logger = logging.getLogger(__name__)

# Armazena o HWND da janela que o usuário estava usando ANTES do ClAudio roubar o foco.
# Isso garante que ao digitar, o foco volte pra janela correta (Word, Chrome, VS Code etc).
_last_user_hwnd = None

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

def save_user_window() -> None:
    """Salva o HWND da janela que está em primeiro plano AGORA (antes do ClAudio roubar o foco)."""
    global _last_user_hwnd
    if not is_windows():
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        fg = user32.GetForegroundWindow()
        claudio_hwnd = _find_claudio_hwnd()
        # Só salva se NÃO for a própria janela do ClAudio
        if fg and fg != claudio_hwnd:
            _last_user_hwnd = fg
            # Log do título para debug
            length = user32.GetWindowTextLengthW(fg)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(fg, buff, length + 1)
                logger.info("Janela do usuário memorizada: '%s' (hwnd=%s)", buff.value[:60], fg)
    except Exception as e:
        logger.error("Falha ao salvar janela do usuário: %s", e)

def bring_assistant_to_front() -> None:
    """Procura pelo título exato da janela do ClAudio e a traz para a frente (des-minimiza)."""
    def _bring_to_front_thread():
        # Aguarda uns milissegundos para o Eel/Chrome criar efetivamente a janela
        time.sleep(0.3)
        hwnd = _find_claudio_hwnd()
        if not hwnd:
            logger.warning("Não foi possível achar a janela do ClAudio para forçar o foco.")
            return

        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            # Se a janela estiver minimizada, restaura
            user32.ShowWindow(hwnd, 9)

            # Método oficial do Windows: AttachThreadInput no lugar do Hack do ALT
            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd and fg_hwnd != hwnd:
                fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
                my_thread = kernel32.GetCurrentThreadId()
                
                if fg_thread != my_thread and fg_thread != 0:
                    user32.AttachThreadInput(my_thread, fg_thread, True)
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                    user32.AttachThreadInput(my_thread, fg_thread, False)
                else:
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
            else:
                user32.SetForegroundWindow(hwnd)
                user32.BringWindowToTop(hwnd)
            
            logger.info("Widget resgatado pro centro da tela com sucesso!")
        except Exception as e:
            logger.error("Falha detalhada ao forçar o ClAudio para a frente: %s", e)

    if not is_windows():
        return
        
    # ANTES de trazer o ClAudio, salva a janela atual do usuário
    save_user_window()
    
    # Executa em thread separada para não travar o loop principal do servidor
    threading.Thread(target=_bring_to_front_thread, daemon=True).start()

def restore_focus_for_typing() -> None:
    """
    Restaura o foco para a janela EXATA que o usuário estava usando antes de chamar o ClAudio.
    Isso é crítico para que o pyautogui.write() envie as teclas para o app correto (Word, Chrome, etc).
    """
    global _last_user_hwnd
    if not is_windows():
        return
        
    try:
        import ctypes
        user32 = ctypes.windll.user32
        
        # 1. Minimiza o ClAudio para ele sair do caminho
        claudio_hwnd = _find_claudio_hwnd()
        if claudio_hwnd:
            user32.ShowWindow(claudio_hwnd, 6)  # SW_MINIMIZE
            time.sleep(0.15)
        
        # 2. Restaura o foco para a janela EXATA que o usuário estava
        if _last_user_hwnd and user32.IsWindow(_last_user_hwnd):
            user32.ShowWindow(_last_user_hwnd, 9)  # SW_RESTORE
            
            # REMOVIDO HACK DO ALT! (Ele travava o teclado do usuário)
            # Método oficial do Windows: Anexar a thread de input para permitir a troca de foco
            kernel32 = ctypes.windll.kernel32
            fg_hwnd = user32.GetForegroundWindow()
            if fg_hwnd and fg_hwnd != _last_user_hwnd:
                fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None)
                my_thread = kernel32.GetCurrentThreadId()
                
                if fg_thread != my_thread and fg_thread != 0:
                    user32.AttachThreadInput(my_thread, fg_thread, True)
                    user32.SetForegroundWindow(_last_user_hwnd)
                    user32.BringWindowToTop(_last_user_hwnd)
                    user32.AttachThreadInput(my_thread, fg_thread, False)
                else:
                    user32.SetForegroundWindow(_last_user_hwnd)
                    user32.BringWindowToTop(_last_user_hwnd)
            else:
                user32.SetForegroundWindow(_last_user_hwnd)
                user32.BringWindowToTop(_last_user_hwnd)
            
            time.sleep(0.3)
            logger.warning("Sem janela memorizada. Foco delegado ao Windows.")
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
