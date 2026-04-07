// ClAudio - Main Frontend Logic (ULTRA STANDBY EDITION)
// ── Estado Global ──────────────────────────────────────────────────
let state = 'idle';
let listenMode = 'off'; // 'off', 'active', 'wake_word'
let hasSent = false;
let ignoreNextResponse = false;
let silenceTimer = null;
let speakTimeout = null;
let recognition = null;
let ws = null;
let bestVoice = null;
let ttsReady = false;

const badgeEl = document.getElementById('badge');
const hintEl = document.getElementById('hint');
const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

// ── Anti-Inspecionar & Drag ─────────────────────────────────────────
document.addEventListener('contextmenu', e => e.preventDefault());
document.addEventListener('keydown', e => {
    if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && ['i', 'I', 'j', 'J', 'c', 'C'].includes(e.key)) || (e.ctrlKey && ['u', 'U'].includes(e.key))) {
        e.preventDefault(); return false;
    }
});

document.body.addEventListener('mousedown', (e) => {
    if (!e.target.closest('.close-btn') && !e.target.closest('#coreWrap') && !e.target.closest('.msg')) {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'drag_window' }));
        }
    }
});

// ── Utilitários ─────────────────────────────────────────────────────
function normalize(str) {
    if (!str) return '';
    return str.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
}

function containsWakeWord(text) {
    const n = normalize(text);
    const words = ['claudio', 'audio', 'claudi', 'claudia', 'claudio', 'claudu'];
    return words.some(w => n.includes(w));
}

function extractQuestion(text) {
    const norm = normalize(text);
    const words = ['claudio', 'audio', 'claudia'];
    let cleanText = text;
    for (const w of words) {
        const idx = normalize(cleanText).indexOf(w);
        if (idx !== -1) {
            cleanText = cleanText.substring(idx + w.length).replace(/^[,!?\s]+/, '').trim();
            break;
        }
    }
    return cleanText;
}

function showTranscript(text) {
    const tr = document.getElementById('transcript');
    if (!tr) return;
    tr.textContent = text;
    if (text) { tr.classList.add('show'); }
    else { tr.classList.remove('show'); }
}

function addHistory(role, text) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.textContent = text;
    const hist = document.getElementById('history');
    if (!hist) return;
    hist.appendChild(div);
    hist.scrollTop = hist.scrollHeight;
    while (hist.children.length > 20) hist.removeChild(hist.firstChild);
}

// ── Gestão de Estados ───────────────────────────────────────────────
function applyState(s) {
    if (state === s && s !== 'idle' && s !== 'listening') return;
    console.log(`[Estado] ${state.toUpperCase()} -> ${s.toUpperCase()}`);
    state = s;
    document.body.className = 's-' + s;

    let t = '';
    let active = false;
    if (s === 'idle') { t = 'standby'; }
    else if (s === 'listening') { t = 'ouvindo'; active = true; }
    else if (s === 'thinking') { t = 'pensando'; active = true; }
    else if (s === 'speaking') { t = 'respondendo'; active = true; }
    else if (s === 'wake') { t = 'oi!'; active = true; }
    else if (s === 'error') { t = 'erro'; }

    if (badgeEl) {
        badgeEl.textContent = t;
        badgeEl.className = 'status-badge' + (active ? ' active' : '');
    }
    if (hintEl) {
        hintEl.className = s === 'idle' ? 'hint' : 'hint hidden';
    }

    ensureWakeWordListener();
}

function ensureWakeWordListener() {
    if (!recognition || listenMode === 'active') return;

    const validStates = ['idle', 'thinking', 'speaking', 'error'];
    if (validStates.includes(state)) {
        if (listenMode !== 'wake_word') {
            console.log(`[Mic] Iniciando Escuta Passiva (Wake Word)...`);
            startPassiveRecognition();
        }
    } else {
        if (listenMode === 'wake_word') {
            listenMode = 'off';
            try { recognition.stop(); } catch (e) { }
        }
    }
}

function startPassiveRecognition() {
    listenMode = 'off';
    try { recognition.stop(); } catch (e) { }
    
    setTimeout(() => {
        if (listenMode !== 'active' && ['idle', 'thinking', 'speaking', 'error'].includes(state)) {
            listenMode = 'wake_word';
            hasSent = false;
            recognition.continuous = true;
            recognition.interimResults = true;
            try { 
                recognition.start(); 
                console.log("[Mic] Standby ATIVO.");
            } catch (e) { 
                console.warn("[Mic] Aguardando permissão/gesto.", e);
                listenMode = 'off'; 
            }
        }
    }, 400);
}

// ── Voz (TTS) ───────────────────────────────────────────────────────
function findBestVoice() {
    const voices = speechSynthesis.getVoices();
    if (!voices.length) return null;
    const priorities = [
        v => v.name.includes('Online') && v.lang.startsWith('pt-BR'),
        v => v.name.includes('Natural') && v.lang.startsWith('pt-BR'),
        v => v.lang === 'pt-BR',
        v => v.lang.startsWith('pt'),
    ];
    for (const test of priorities) {
        const found = voices.find(test);
        if (found) return found;
    }
    return null;
}

function warmUpTTS() {
    if (!('speechSynthesis' in window) || ttsReady) return;
    const warm = new SpeechSynthesisUtterance('');
    warm.volume = 0;
    warm.onend = () => { ttsReady = true; };
    speechSynthesis.speak(warm);
}

function recoverFromSpeech() {
    clearTimeout(speakTimeout);
    speakTimeout = null;
    if (state === 'speaking') applyState('idle');
}

function speakText(text) {
    if (!('speechSynthesis' in window)) { recoverFromSpeech(); return; }
    
    console.log("[TTS] Falando...");
    const now = Date.now();
    const lastSpoke = parseInt(localStorage.getItem('claudio_last_spoke') || '0');
    if (now - lastSpoke < 500) { recoverFromSpeech(); return; }
    localStorage.setItem('claudio_last_spoke', now.toString());

    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'pt-BR'; u.rate = 1.0; u.pitch = 1.0;
    if (bestVoice) u.voice = bestVoice;
    u.onend = () => recoverFromSpeech();
    u.onerror = () => recoverFromSpeech();

    const estimatedMs = Math.max(text.length * 80, 5000) + 5000;
    clearTimeout(speakTimeout);
    speakTimeout = setTimeout(() => {
        speechSynthesis.cancel();
        recoverFromSpeech();
    }, estimatedMs);

    speechSynthesis.speak(u);
    ensureWakeWordListener();
}

// ── Reconhecimento de Voz ───────────────────────────────────────────
if (!SpeechRecognition) {
    const uns = document.getElementById('unsupported');
    if (uns) uns.style.display = 'block';
} else {
    recognition = new SpeechRecognition();
    recognition.lang = 'pt-BR';

    recognition.onstart = () => {
        console.log(`[Mic] Ligado (${listenMode})`);
    };

    recognition.onresult = (event) => {
        let interim = '', finalText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const txt = event.results[i][0].transcript;
            if (event.results[i].isFinal) finalText += txt;
            else interim += txt;
        }
        const currentText = finalText || interim;

        // --- MODO PASSIVO (WAKE WORD) ---
        if (listenMode === 'wake_word') {
            const heard = normalize(currentText);
            if (heard) console.log(`[Standby] Ouvindo: "${heard}"`);

            if (containsWakeWord(heard)) {
                console.log("[Mic] Wake detected!");
                speechSynthesis.cancel();
                if (state === 'thinking') ignoreNextResponse = true;

                listenMode = 'off';
                try { recognition.stop(); } catch (e) { }

                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ type: 'wake_word' }));
                }

                setTimeout(() => {
                    listenMode = 'active'; hasSent = false;
                    recognition.continuous = false; recognition.interimResults = true;
                    applyState('listening');
                    showTranscript('');
                    try { recognition.start(); } catch (e) { }
                }, 350);
            }
            return;
        }

        // --- MODO ATIVO (Ouvindo Comando) ---
        if (listenMode === 'active') {
            showTranscript(currentText);
            
            // Verifica comando "cancelar" em tempo real (interim ou final)
            const n = normalize(currentText).replace(/[^a-z0-9]/g, '');
            if (n.includes('cancelar') || n.includes('cancela')) {
                console.log("[Mic] Comando 'Cancelar' detectado. Voltando para Standby.");
                hasSent = true; 
                listenMode = 'off';
                try { recognition.stop(); } catch (e) { }
                
                showTranscript('Cancelado.');
                speakText('Solicitação cancelada.');
                applyState('idle'); // Isso forçará a volta para Wake Word mode
                return;
            }

            if (finalText && !hasSent) {
                const q = extractQuestion(finalText);
                if (q.length <= 1) return;

                hasSent = true; listenMode = 'off';
                try { recognition.stop(); } catch (e) { }
                sendToBackend(q);
            }
        }

        // Timer de silêncio
        if (listenMode === 'active' && !hasSent) {
            if (silenceTimer) clearTimeout(silenceTimer);
            silenceTimer = setTimeout(() => {
                if (listenMode === 'active' && !hasSent) {
                    const q = extractQuestion(currentText);
                    if (q.length > 2) {
                        hasSent = true; listenMode = 'off';
                        try { recognition.stop(); } catch (e) { }
                        sendToBackend(q);
                    } else {
                        applyState('idle');
                    }
                }
            }, 2100);
        }
    };

    recognition.onerror = (event) => {
        console.error("[Mic] Erro:", event.error);
        if (listenMode === 'active') {
            listenMode = 'off';
            applyState('idle');
        }
    };

    recognition.onend = () => {
        if (listenMode === 'wake_word') {
            setTimeout(() => {
                if (listenMode === 'wake_word') {
                    recognition.continuous = true;
                    recognition.interimResults = true;
                    try { recognition.start(); } catch (e) { }
                }
            }, 400);
        } else if (listenMode === 'active' && !hasSent) {
            applyState('idle');
        }
    };
}

// ── Backend & WebSocket ────────────────────────────────────────────
function connectWS() {
    try {
        ws = new WebSocket('ws://localhost:8765');
        ws.onopen = () => {
            const dot = document.getElementById('wsDot');
            const lab = document.getElementById('wsLabel');
            if (dot) dot.className = 'dot connected';
            if (lab) lab.textContent = 'conectado';
            startResetTimer();
            ensureWakeWordListener();
        };
        ws.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (ignoreNextResponse && data.state === 'speaking') {
                ignoreNextResponse = false;
                console.log("[WS] Resposta ignorada.");
                return;
            }
            if (data.state) {
                applyState(data.state);
                if (data.state === 'speaking' && data.transcript) speakText(data.transcript);
            }
            if (data.interactions !== undefined) {
                const count = document.getElementById('quotaCount');
                const wrap = document.getElementById('quotaWrap');
                if (count) count.textContent = data.interactions + "/20";
                if (wrap) wrap.style.opacity = '1';
            }
            if (data.transcript && data.state !== 'speaking') showTranscript(data.transcript);
            if (data.message && data.role) addHistory(data.role, data.message);
        };
        ws.onclose = () => {
            const dot = document.getElementById('wsDot');
            const lab = document.getElementById('wsLabel');
            if (dot) dot.className = 'dot';
            if (lab) lab.textContent = 'desconectado';
            listenMode = 'off';
            setTimeout(connectWS, 4000);
        };
    } catch (err) { setTimeout(connectWS, 4000); }
}

function sendToBackend(text) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ignoreNextResponse = false;
    applyState('thinking');
    showTranscript(text);
    ws.send(JSON.stringify({ type: 'user_message', text: text }));
}

// ── Inicialização & Loops ──────────────────────────────────────────
function startResetTimer() {
    if (resetTimerInterval) clearInterval(resetTimerInterval);
    const timerEl = document.getElementById('quotaTimer');
    function updateTimer() {
        const now = new Date();
        const target = new Date(now);
        target.setHours(5, 0, 0, 0);
        if (now.getHours() >= 5) target.setDate(target.getDate() + 1);
        const diffMs = target - now;
        const h = Math.floor(diffMs / 3600000);
        const m = Math.floor((diffMs % 3600000) / 60000);
        if (timerEl) timerEl.textContent = `Reset em: ${h.toString().padStart(2, '0')}h${m.toString().padStart(2, '0')}`;
    }
    updateTimer();
    setInterval(updateTimer, 60000);
}

setInterval(() => {
    if (state === 'idle' && listenMode === 'off' && recognition) {
        console.log("[Watchdog] Resetando Standby...");
        ensureWakeWordListener();
    }
}, 6000);

window.addEventListener('load', () => {
    connectWS();
    applyState('idle');
});

document.getElementById('coreWrap').onclick = () => {
    if (!recognition || state === 'thinking') return;
    if (state === 'speaking') {
        speechSynthesis.cancel();
        applyState('idle');
        return;
    }
    listenMode = 'off';
    try { recognition.stop(); } catch (e) { }
    setTimeout(() => {
        listenMode = 'active'; hasSent = false;
        recognition.continuous = false;
        recognition.interimResults = true;
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'wake_word' }));
        applyState('listening');
        try { recognition.start(); } catch (e) { }
    }, 200);
};

document.body.addEventListener('mousedown', () => {
    if (listenMode === 'off' && state === 'idle' && recognition) {
        ensureWakeWordListener();
    }
}, { once: false });

if ('speechSynthesis' in window) {
    const lv = () => { bestVoice = findBestVoice(); warmUpTTS(); };
    speechSynthesis.onvoiceschanged = lv;
    lv();
}
