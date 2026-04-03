// --- Sec-UX (Anti-Inspecionar Global) ---
    document.addEventListener('contextmenu', e => e.preventDefault());
    document.addEventListener('keydown', e => {
      if (e.key === 'F12' || (e.ctrlKey && e.shiftKey && ['i', 'I', 'j', 'J', 'c', 'C'].includes(e.key)) || (e.ctrlKey && ['u', 'U'].includes(e.key))) {
        e.preventDefault(); return false;
      }
    });

    // --- Arraste de Janela Nativo (Drag Fallback) ---
    document.body.addEventListener('mousedown', (e) => {
      if (!e.target.closest('.close-btn') && !e.target.closest('#coreWrap') && !e.target.closest('.msg')) {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'drag_window' }));
        }
      }
    });

    // ── Gestão de Estados e UI Avançada ─────────────────────────────────
    let state = 'idle';
    const badgeEl = document.getElementById('badge');
    const hintEl = document.getElementById('hint');

    function applyState(s) {
      state = s;
      document.body.className = 's-' + s; // Liga o CSS Monocromatico respectivo

      let t = '';
      let active = false;
      if (s === 'idle') { t = 'aguardando'; }
      else if (s === 'listening') { t = 'ouvindo'; active = true; }
      else if (s === 'thinking') { t = 'pensando'; active = true; }
      else if (s === 'speaking') { t = 'respondendo'; active = true; }
      else if (s === 'wake') { t = 'oi!'; active = true; }
      else if (s === 'error') { t = 'erro'; }

      badgeEl.textContent = t;
      badgeEl.className = 'status-badge' + (active ? ' active' : '');
      hintEl.className = s === 'idle' ? 'hint' : 'hint hidden';
    }
    applyState('idle');

    // ── Wake Word + Speech Recognition (LÓGICA BLINDADA DO USUÁRIO) ────────────────────────
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let recognition = null;
    let hasSent = false;
    let listenMode = 'off';
    let silenceTimer = null;

    function normalize(str) {
      return str.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim();
    }

    function containsWakeWord(text) {
      return normalize(text).includes('claudio');
    }

    function extractQuestion(text) {
      const norm = normalize(text);
      const idx = norm.indexOf('claudio');
      if (idx === -1) return text.trim();
      return text.substring(idx + 7).replace(/^[,!?\s]+/, '').trim();
    }

    // Microfone desligado por padrão. Só ativa ao clicar no orb (Push-to-Talk).

    if (!SpeechRecognition) {
      document.getElementById('unsupported').style.display = 'block';
    } else {
      recognition = new SpeechRecognition();
      recognition.lang = 'pt-BR';

      recognition.onstart = () => {
        applyState('listening');
      };

      recognition.onresult = (event) => {
        let interim = '', finalText = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const txt = event.results[i][0].transcript;
          if (event.results[i].isFinal) finalText += txt;
          else interim += txt;
        }
        const currentText = finalText || interim;

        // Modo passivo removido — microfone só liga via clique no orb

        if (listenMode === 'active') {
          showTranscript(currentText);
          if (finalText && !hasSent) {
            const q = extractQuestion(finalText);
            if (q.length <= 2) return;

            hasSent = true; listenMode = 'off';
            recognition.stop();

            const qClean = q.toLowerCase().replace(/[^a-z0-9áéíóúâêîôûãõç]/g, '');
            if (qClean === 'cancelar' || qClean === 'cancela') {
              showTranscript('Solicitação cancelada.');
              applyState('speaking');
              speakText('Solicitação cancelada.');
              return;
            }
            sendToBackend(q);
          }
        }

        if (listenMode === 'active' && !hasSent) {
          if (silenceTimer) clearTimeout(silenceTimer);
          silenceTimer = setTimeout(() => {
            if (listenMode === 'active' && !hasSent) {
              const q = extractQuestion(currentText);
              if (q.length > 2) {
                hasSent = true; listenMode = 'off';
                try { recognition.stop(); } catch(e){}
                const qClean = q.toLowerCase().replace(/[^a-z0-9áéíóúâêîôûãõç]/g, '');
                if (qClean === 'cancelar' || qClean === 'cancela') {
                  showTranscript('Solicitação cancelada.');
                  applyState('speaking');
                  speakText('Solicitação cancelada.');
                  return;
                }
                sendToBackend(q);
              } else {
                 applyState('idle');
              }
            }
          }, 1500);
        }
      };

      recognition.onerror = (event) => {
        if (event.error === 'no-speech' && listenMode === 'active') {
          showTranscript('Não ouvi nada. Clique no orb para tentar novamente.');
        }
        listenMode = 'off';
        applyState('idle');
      };

      recognition.onend = () => {
        if (listenMode === 'active' && !hasSent) {
          applyState('idle');
        }
        // Mic desliga ao terminar — só religa com novo clique no orb
      };
    }

    // ── TTS Otimizado ────────────────────────────────────────────────────
    let bestVoice = null;
    let ttsReady = false;
    let speakTimeout = null;

    function findBestVoice() {
      const voices = speechSynthesis.getVoices();
      if (!voices.length) return null;
      const priorities = [
        v => v.name.includes('Online') && v.lang.startsWith('pt-BR'),
        v => v.name.includes('Natural') && v.lang.startsWith('pt-BR'),
        v => v.name.includes('Online') && v.lang.startsWith('pt'),
        v => v.name.includes('Francisca') || v.name.includes('Antonio'),
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
      applyState('idle');
      // Mic permanece desligado até o próximo clique no orb
    }

    function speakText(text) {
      if (!('speechSynthesis' in window)) { recoverFromSpeech(); return; }

      const now = Date.now();
      const lastSpoke = parseInt(localStorage.getItem('claudio_last_spoke') || '0');
      if (now - lastSpoke < 500) { recoverFromSpeech(); return; }
      localStorage.setItem('claudio_last_spoke', now.toString());

      if (recognition) try { recognition.stop(); } catch (e) { }
      listenMode = 'off';
      speechSynthesis.cancel();

      const u = new SpeechSynthesisUtterance(text);
      u.lang = 'pt-BR'; u.rate = 1.0; u.pitch = 1.0;
      if (bestVoice) u.voice = bestVoice;

      u.onend = () => recoverFromSpeech();
      u.onerror = () => recoverFromSpeech();

      const estimatedMs = Math.max(text.length * 80, 4000) + 4000;
      clearTimeout(speakTimeout);
      speakTimeout = setTimeout(() => {
        speechSynthesis.cancel();
        recoverFromSpeech();
      }, estimatedMs);
      speechSynthesis.speak(u);
    }

    if ('speechSynthesis' in window) {
      const lv = () => { bestVoice = findBestVoice(); warmUpTTS(); };
      speechSynthesis.onvoiceschanged = lv;
      lv();
      setTimeout(warmUpTTS, 1000);
    }

    // ── Clicks & Backend Interop ───────────────────────────────────
    document.getElementById('coreWrap').onclick = () => {
      if (!recognition || state === 'thinking') return;
      if (state === 'speaking') {
        if ('speechSynthesis' in window) speechSynthesis.cancel();
        applyState('idle');
        return;
      }
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        applyState('error'); showTranscript('Servidor não conectado.');
        setTimeout(() => applyState('idle'), 2000); return;
      }
      // Para qualquer escuta anterior antes de iniciar nova
      try { recognition.stop(); } catch (e) { }
      setTimeout(() => {
        listenMode = 'active'; hasSent = false;
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'wake_word' }));
        recognition.continuous = false; recognition.interimResults = true;
        try { recognition.start(); } catch (e) { }
      }, 250);
    };

    function sendToBackend(text) {
      if (!ws || ws.readyState !== WebSocket.OPEN) return;
      applyState('thinking'); showTranscript(text);
      ws.send(JSON.stringify({ type: 'user_message', text: text }));
    }

    function showTranscript(text) {
      const tr = document.getElementById('transcript');
      tr.textContent = text;
      if (text) { tr.classList.add('show'); }
      else { tr.classList.remove('show'); }
    }

    function addHistory(role, text) {
      const div = document.createElement('div');
      div.className = `msg ${role}`;
      div.textContent = text;
      const hist = document.getElementById('history');
      hist.appendChild(div);
      hist.scrollTop = hist.scrollHeight;
      while (hist.children.length > 20) hist.removeChild(hist.firstChild);
    }

    // ── Timer de Reset ───────────────────────────────────
    let resetTimerInterval;
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
        timerEl.textContent = `Reset em: ${h.toString().padStart(2, '0')}h${m.toString().padStart(2, '0')}`;
      }
      updateTimer();
      resetTimerInterval = setInterval(updateTimer, 60000); // 1 minuto update visual
    }

    // ── WebSocket Connect ──────────────────────────────────────────────
    let ws;
    const wsDot = document.getElementById('wsDot');
    const wsLabel = document.getElementById('wsLabel');
    const quotaWrap = document.getElementById('quotaWrap');
    const quotaCount = document.getElementById('quotaCount');

    function connectWS() {
      try {
        ws = new WebSocket('ws://localhost:8765');
        ws.onopen = () => {
          wsDot.className = 'dot connected'; wsLabel.textContent = 'conectado';
          // Mic desligado até o clique no orb (Push-to-Talk)
          startResetTimer();
        };
        ws.onmessage = (e) => {
          const data = JSON.parse(e.data);
          if (data.state) {
            applyState(data.state);
            if (data.state === 'speaking' && data.transcript) speakText(data.transcript);
          }
          if (data.interactions !== undefined) {
            quotaCount.textContent = data.interactions + "/20";
            quotaWrap.style.opacity = '1';
          }
          if (data.transcript && data.state !== 'speaking') showTranscript(data.transcript);
          if (data.message && data.role) addHistory(data.role, data.message); // Updated role assignment
        };
        ws.onclose = () => {
          wsDot.className = 'dot'; wsLabel.textContent = 'desconectado';
          quotaWrap.style.opacity = '0';
          listenMode = 'off';
          if (resetTimerInterval) clearInterval(resetTimerInterval);
          if (recognition) try { recognition.stop(); } catch (e) { }
          setTimeout(connectWS, 3000);
        };
        ws.onerror = () => { wsDot.className = 'dot error'; wsLabel.textContent = 'erro ws'; };
      } catch (err) { setTimeout(connectWS, 3000); }
    }

    connectWS();
