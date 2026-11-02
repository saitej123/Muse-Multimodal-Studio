/**
 * C.H.I.T.T.I. — Cognitive Heuristic Interface Trained for Task Integration
 *
 * Voice path: Muse Voice Transcribe in, Muse Wonder reply, studio voice out.
 * Fallback: browser SpeechRecognition when Live is unavailable.
 */
(function (global) {
  const NAME = "C.H.I.T.T.I.";
  const EXPAND =
    "Cognitive Heuristic Interface Trained for Task Integration";
  const MARK = "/static/chitti.svg";

  const state = {
    open: false,
    listening: false,
    speaking: false,
    rec: null,
    utterance: null,
    closeTimer: null,
    product: "multimodal",
    onCommand: null,
    onPickFile: null,
    busyGate: null,
    sessionId: null,
    getSessionId: null,
    pickingFile: false,
    liveWs: null,
    micStream: null,
    audioCtx: null,
    processor: null,
    playCtx: null,
    playTime: 0,
    model: "",
    lastHeard: "",
    lastReply: "",
    useLive: true,
  };

  function $(id) {
    return document.getElementById(id);
  }

  function mergeChittiText(prev, next) {
    const a = String(prev || "").trim();
    const b = String(next || "").trim();
    if (!b) return a;
    if (!a) return b;
    if (b.startsWith(a)) return b;
    if (a.startsWith(b) && a.length > b.length) return a;
    if (a.endsWith(b)) return a;
    const max = Math.min(a.length, b.length, 64);
    for (let i = max; i >= 1; i--) {
      if (a.endsWith(b.slice(0, i))) return a + b.slice(i);
    }
    const glue = /[A-Za-z0-9]$/.test(a) && /^[A-Za-z0-9]/.test(b) ? " " : "";
    return a + glue + b;
  }

  function ensureDom() {
    if ($("chitti-root")) return;
    const root = document.createElement("div");
    root.id = "chitti-root";
    root.innerHTML = `
      <button type="button" class="chitti-fab" id="chitti-fab" title="${NAME}" aria-label="Open ${NAME}">
        <img src="${MARK}" alt="" width="34" height="34" />
      </button>
      <aside class="chitti-panel" id="chitti-panel" hidden role="dialog" aria-label="${NAME}">
        <div class="chitti-panel-head">
          <div class="chitti-panel-mark"><img src="${MARK}" alt="" /></div>
          <div class="chitti-panel-copy">
            <div class="chitti-panel-kicker">${NAME}</div>
            <div class="chitti-panel-title">Ready when you are</div>
            <div class="chitti-panel-sub">${EXPAND}</div>
          </div>
          <button type="button" class="chitti-panel-close" id="chitti-close" aria-label="Close">×</button>
        </div>
        <div class="chitti-bubble" id="chitti-bubble" data-tone="idle">Type or tap Respond. Try “create a video” or “upload a document”.</div>
        <div class="chitti-meta" id="chitti-meta" hidden></div>
        <form class="chitti-compose" id="chitti-compose">
          <input type="file" id="chitti-file" class="chitti-file" accept=".pdf,.doc,.docx,.ppt,.pptx,.txt,.md,.markdown,image/*" />
          <input type="text" id="chitti-input" autocomplete="off" maxlength="500"
            placeholder="Create a video, upload a document…" />
          <button type="button" id="chitti-attach" title="Upload a document">File</button>
          <button type="submit" id="chitti-send">Send</button>
        </form>
        <div class="chitti-actions">
          <button type="button" class="chitti-primary" id="chitti-respond"><span aria-hidden="true">🎙</span> Respond</button>
          <button type="button" id="chitti-stop" disabled>Stop</button>
          <button type="button" id="chitti-mute">Mute</button>
        </div>
        <div class="chitti-hints" id="chitti-hints"></div>
      </aside>`;
    document.body.appendChild(root);

    $("chitti-fab")?.addEventListener("click", () => {
      if (state.open) close({ force: true });
      else open();
    });
    $("chitti-close")?.addEventListener("click", () => close({ force: true }));
    $("chitti-respond")?.addEventListener("click", () => startListen());
    $("chitti-stop")?.addEventListener("click", () => stopListen({ say: "Mic off." }));
    $("chitti-mute")?.addEventListener("click", () => {
      cancelOwnSpeech(true);
      try { state.playTime = 0; } catch (e) {}
      setFabState(state.listening ? "listening" : "idle");
    });
    $("chitti-compose")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = $("chitti-input");
      const text = (input?.value || "").trim();
      if (!text) return;
      if (input) input.value = "";
      dispatchCommand(text, { fromLive: false });
    });
    $("chitti-attach")?.addEventListener("click", () => pickDocument());
    $("chitti-file")?.addEventListener("change", (e) => {
      const file = e.target.files && e.target.files[0];
      e.target.value = "";
      state.pickingFile = false;
      if (!file) return;
      if (typeof state.onPickFile === "function") {
        try { state.onPickFile(file); } catch (err) {}
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && state.open) close({ force: true });
    });
    document.addEventListener("pointerdown", (e) => {
      if (!state.open) return;
      if (state.pickingFile) return;
      const panel = $("chitti-panel");
      const fab = $("chitti-fab");
      if (panel?.contains(e.target) || fab?.contains(e.target)) return;
      if (!state.listening && !state.speaking) close({ soft: true });
    });
  }

  function setHints(product) {
    const el = $("chitti-hints");
    if (!el) return;
    if (product === "multimodal") {
      el.textContent =
        "Type or speak. Try: “create a video”, “upload a document”, “status”, “history”, “help”.";
    } else {
      el.textContent =
        "Live voice via Muse. Try: “check profile”, “score matches”, “apply matches”, “open prep”, “help”.";
    }
  }

  function setFabState(mode) {
    const fab = $("chitti-fab");
    if (fab) fab.dataset.state = mode || "idle";
  }

  function setMeta(text) {
    const el = $("chitti-meta");
    if (!el) return;
    if (!text) {
      el.hidden = true;
      el.textContent = "";
      return;
    }
    el.hidden = false;
    el.textContent = text;
  }

  function open() {
    ensureDom();
    clearCloseTimer();
    state.open = true;
    const panel = $("chitti-panel");
    if (panel) panel.hidden = false;
    const input = $("chitti-input");
    if (input) setTimeout(() => input.focus(), 40);
  }

  function clearCloseTimer() {
    if (state.closeTimer) {
      clearTimeout(state.closeTimer);
      state.closeTimer = null;
    }
  }

  function cancelOwnSpeech(forceCancel) {
    try {
      if (state.utterance) state.utterance.__chittiIgnore = true;
      if (forceCancel && state.speaking && global.speechSynthesis) {
        global.speechSynthesis.cancel();
      }
    } catch (e) {}
    state.utterance = null;
    state.speaking = false;
  }

  function close(opts = {}) {
    if (state.listening && !opts.force) return;
    clearCloseTimer();
    if (opts.soft) {
      state.closeTimer = setTimeout(() => close({ force: true }), 420);
      return;
    }
    stopListen({ silent: true });
    if (opts.force) cancelOwnSpeech(true);
    state.open = false;
    const panel = $("chitti-panel");
    if (panel) panel.hidden = true;
    setFabState("idle");
  }

  function scheduleSmartClose(ms) {
    clearCloseTimer();
    const wait = typeof ms === "number" ? ms : 5200;
    state.closeTimer = setTimeout(() => {
      if (!state.listening && !state.speaking) close({ force: true });
    }, wait);
  }

  function say(text, opts = {}) {
    ensureDom();
    open();
    const bubble = $("chitti-bubble");
    const msg = String(text || "").trim();
    if (bubble) {
      bubble.textContent = msg || "…";
      bubble.dataset.tone = opts.tone || "ok";
    }
    const title = document.querySelector("#chitti-panel .chitti-panel-title");
    if (title) title.textContent = opts.title || NAME;

    // Prefer Live audio replies; browser TTS only when Live is idle and speak≠false.
    if (opts.speak !== false && msg && !state.liveWs && global.speechSynthesis) {
      try {
        if (state.speaking) cancelOwnSpeech(true);
        const u = new SpeechSynthesisUtterance(msg);
        u.rate = 1.02;
        state.utterance = u;
        state.speaking = true;
        setFabState("speaking");
        u.onend = () => {
          if (u.__chittiIgnore) return;
          state.speaking = false;
          state.utterance = null;
          setFabState(state.listening ? "listening" : "idle");
          if (opts.autoClose !== false) scheduleSmartClose(opts.closeAfter ?? 2800);
        };
        u.onerror = () => {
          if (u.__chittiIgnore) return;
          state.speaking = false;
          state.utterance = null;
          setFabState(state.listening ? "listening" : "idle");
          if (opts.autoClose !== false) scheduleSmartClose(opts.closeAfter ?? 3500);
        };
        global.speechSynthesis.speak(u);
      } catch (e) {
        state.speaking = false;
        if (opts.autoClose !== false) scheduleSmartClose(opts.closeAfter ?? 4000);
      }
    } else if (opts.autoClose !== false && !state.liveWs) {
      scheduleSmartClose(opts.closeAfter ?? 4500);
    }
  }

  function pickDocument() {
    const input = $("chitti-file");
    if (!input) return;
    state.pickingFile = true;
    try {
      input.click();
    } catch (e) {
      state.pickingFile = false;
    }
    setTimeout(() => { state.pickingFile = false; }, 120000);
  }

  function isStandDown(t) {
    const s = String(t || "")
      .toLowerCase()
      .replace(/[^\w\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    return /^(stop|cancel|quiet|silence|close|stand down|never ?mind)( please)?$/.test(s);
  }

  async function dispatchCommand(raw, meta = {}) {
    const t = String(raw || "").trim();
    if (!t) return;
    state.lastHeard = t;
    const fromLive = !!meta.fromLive;
    const bubble = $("chitti-bubble");
    if (bubble && !state.speaking && !fromLive) {
      bubble.textContent = `Heard: ${t}`;
      bubble.dataset.tone = "listen";
    }

    if (isStandDown(t)) {
      say("Standing down.", { tone: "idle", speak: false, closeAfter: 1600 });
      setTimeout(() => close({ force: true }), 900);
      return;
    }

    if (typeof state.onCommand === "function") {
      try {
        const handled = await state.onCommand(t, {
          product: state.product,
          fromLive,
          file: meta.file || null,
          pickDocument,
        });
        if (handled) return;
      } catch (e) {
        say(e.message || "Something went wrong.", { tone: "err", speak: false });
        return;
      }
    }

    const low = t.toLowerCase();
    if (!fromLive && (/\bhelp\b|\bwho are you\b|\bwhat are you\b/.test(low))) {
      say(
        `${NAME}: ${EXPAND}. I listen with Muse and act on your workspace.`,
        { tone: "ok", speak: false }
      );
    }
  }

  function micBlockedReason() {
    if (typeof state.busyGate === "function") {
      try {
        return state.busyGate() || "";
      } catch (e) {
        return "";
      }
    }
    return "";
  }

  function floatTo16BitPCM(float32Array) {
    const buf = new ArrayBuffer(float32Array.length * 2);
    const view = new DataView(buf);
    for (let i = 0; i < float32Array.length; i++) {
      let s = Math.max(-1, Math.min(1, float32Array[i]));
      view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return new Uint8Array(buf);
  }

  function downsampleTo16k(float32Array, inputRate) {
    if (inputRate === 16000) return float32Array;
    const ratio = inputRate / 16000;
    const newLen = Math.floor(float32Array.length / ratio);
    const result = new Float32Array(newLen);
    for (let i = 0; i < newLen; i++) result[i] = float32Array[Math.floor(i * ratio)];
    return result;
  }

  function stopMediaStream(stream) {
    try {
      stream?.getTracks?.().forEach((t) => {
        try { t.stop(); } catch (e) {}
      });
    } catch (e) {}
  }

  function playPcm24k(bytes) {
    try {
      if (!state.playCtx) {
        state.playCtx = new (global.AudioContext || global.webkitAudioContext)({
          sampleRate: 24000,
        });
        state.playTime = 0;
      }
      const samples = bytes.length / 2;
      const buf = state.playCtx.createBuffer(1, samples, 24000);
      const ch = buf.getChannelData(0);
      const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
      for (let i = 0; i < samples; i++) {
        ch[i] = view.getInt16(i * 2, true) / 0x8000;
      }
      state.speaking = true;
      setFabState("speaking");
      const src = state.playCtx.createBufferSource();
      src.buffer = buf;
      src.connect(state.playCtx.destination);
      const now = state.playCtx.currentTime;
      if (state.playTime < now) state.playTime = now;
      src.start(state.playTime);
      state.playTime += buf.duration;
      src.onended = () => {
        if (state.playCtx && state.playTime <= state.playCtx.currentTime + 0.05) {
          state.speaking = false;
          setFabState(state.listening ? "listening" : "idle");
        }
      };
    } catch (e) {}
  }

  function cleanupLiveMic() {
    try { state.processor?.disconnect(); } catch (e) {}
    try { state.audioCtx?.close(); } catch (e) {}
    stopMediaStream(state.micStream);
    state.micStream = null;
    state.processor = null;
    state.audioCtx = null;
  }

  function cleanupLivePlay() {
    try { state.playCtx?.close(); } catch (e) {}
    state.playCtx = null;
    state.playTime = 0;
  }

  function stopLiveSession() {
    const ws = state.liveWs;
    state.liveWs = null;
    try { ws?.send(JSON.stringify({ end: true })); } catch (e) {}
    try { ws?.close(); } catch (e) {}
    cleanupLiveMic();
  }

  async function startLiveMic(ws) {
    stopMediaStream(state.micStream);
    state.micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    state.audioCtx = new (global.AudioContext || global.webkitAudioContext)({
      sampleRate: 48000,
    });
    const src = state.audioCtx.createMediaStreamSource(state.micStream);
    state.processor = state.audioCtx.createScriptProcessor(4096, 1, 1);
    state.processor.onaudioprocess = (e) => {
      if (!state.liveWs || state.liveWs.readyState !== 1) return;
      const input = e.inputBuffer.getChannelData(0);
      const down = downsampleTo16k(input, state.audioCtx.sampleRate);
      try {
        state.liveWs.send(floatTo16BitPCM(down));
      } catch (err) {}
    };
    src.connect(state.processor);
    state.processor.connect(state.audioCtx.destination);
  }

  function resolveSessionId() {
    try {
      if (typeof state.getSessionId === "function") {
        const sid = state.getSessionId();
        if (sid) return String(sid);
      }
    } catch (e) {}
    return state.sessionId || "";
  }

  function liveWsUrl() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const qs = new URLSearchParams();
    qs.set("product", state.product || "multimodal");
    const sid = resolveSessionId();
    if (sid) qs.set("session_id", sid);
    return `${proto}://${location.host}/ws/chitti/live?${qs}`;
  }

  async function startLiveListen() {
    return new Promise((resolve, reject) => {
      let settled = false;
      const ws = new WebSocket(liveWsUrl());
      state.liveWs = ws;
      ws.binaryType = "arraybuffer";
      ws.onmessage = async (ev) => {
        if (typeof ev.data !== "string") {
          playPcm24k(new Uint8Array(ev.data));
          return;
        }
        let msg;
        try {
          msg = JSON.parse(ev.data);
        } catch (e) {
          return;
        }
        if (msg.error) {
          if (!settled) {
            settled = true;
            reject(new Error(msg.error));
          } else {
            say(msg.error, { tone: "err", speak: false });
          }
          stopLiveSession();
          return;
        }
        if (msg.ready) {
          state.model = msg.model || "";
          state.lastHeard = "";
          state.lastReply = "";
          setMeta(state.model ? `Live · ${msg.voice || "Aoede"} · ${state.model}` : "Live · Muse");
          const title = document.querySelector("#chitti-panel .chitti-panel-title");
          if (title) title.textContent = "Listening…";
          const bubble = $("chitti-bubble");
          if (bubble) {
            bubble.textContent = "Listening via Muse…";
            bubble.dataset.tone = "listen";
          }
          try {
            await startLiveMic(ws);
            state.listening = true;
            setFabState("listening");
            const respond = $("chitti-respond");
            const stop = $("chitti-stop");
            if (respond) respond.disabled = true;
            if (stop) stop.disabled = false;
            if (!settled) {
              settled = true;
              resolve(true);
            }
          } catch (micErr) {
            if (!settled) {
              settled = true;
              reject(micErr);
            }
            stopLiveSession();
          }
          return;
        }
        if (msg.type === "transcript") {
          const role = msg.role || "";
          const chunk = (msg.full || msg.text || "").trim();
          if (!chunk) return;
          const bubble = $("chitti-bubble");
          if (role === "you") {
            state.lastHeard = chunk.startsWith(state.lastHeard)
              ? chunk
              : mergeChittiText(state.lastHeard, chunk);
            if (bubble) {
              bubble.textContent = `You: ${state.lastHeard}`;
              bubble.dataset.tone = "listen";
            }
          } else {
            state.lastReply = chunk.startsWith(state.lastReply)
              ? chunk
              : mergeChittiText(state.lastReply, chunk);
            if (bubble) {
              bubble.textContent = state.lastReply;
              bubble.dataset.tone = "ok";
            }
            const title = document.querySelector("#chitti-panel .chitti-panel-title");
            if (title) title.textContent = NAME;
          }
          return;
        }
        if (msg.text && !msg.type) {
          const bubble = $("chitti-bubble");
          const chunk = String(msg.full || msg.text || "").trim();
          if (chunk) {
            state.lastReply = chunk.startsWith(state.lastReply)
              ? chunk
              : mergeChittiText(state.lastReply, chunk);
            if (bubble) {
              bubble.textContent = state.lastReply;
              bubble.dataset.tone = "ok";
            }
          }
          return;
        }
        if (msg.turn_complete) {
          state.speaking = false;
          setFabState(state.listening ? "listening" : "idle");
          const heard = (msg.heard || state.lastHeard || "").trim();
          if (heard) {
            // Side-effects only — Live already spoke the reply (speak:false).
            dispatchCommand(heard, { fromLive: true });
          }
          scheduleSmartClose(7200);
          return;
        }
        if (msg.type === "usage") {
          setMeta(
            `Live · ${msg.model || state.model || "Muse"} · session billed to admin costs`
          );
        }
      };
      ws.onerror = () => {
        if (!settled) {
          settled = true;
          reject(new Error("Live connection error"));
        }
      };
      ws.onclose = () => {
        if (state.liveWs === ws) state.liveWs = null;
        cleanupLiveMic();
        state.listening = false;
        const respond = $("chitti-respond");
        const stop = $("chitti-stop");
        if (respond) respond.disabled = false;
        if (stop) stop.disabled = true;
        setFabState(state.speaking ? "speaking" : "idle");
        if (!settled) {
          settled = true;
          reject(new Error("Live closed before ready"));
        }
      };
    });
  }

  function stopListen(opts = {}) {
    const rec = state.rec;
    state.listening = false;
    state.rec = null;
    if (rec) {
      try {
        rec.onresult = null;
        rec.onerror = null;
        rec.onend = null;
        rec.abort?.();
      } catch (e) {
        try { rec.stop(); } catch (e2) {}
      }
    }
    stopLiveSession();
    const respond = $("chitti-respond");
    const stop = $("chitti-stop");
    if (respond) respond.disabled = false;
    if (stop) stop.disabled = true;
    setFabState(state.speaking ? "speaking" : "idle");
    if (opts.say) say(opts.say, { tone: "idle", autoClose: true, closeAfter: 2200, speak: false });
  }

  function startBrowserListen() {
    const SR = global.SpeechRecognition || global.webkitSpeechRecognition;
    if (!SR) {
      say("Voice isn’t available here — type a message below, or use File to upload a document.", { tone: "err" });
      return;
    }
    stopListen({ silent: true });
    const rec = new SR();
    state.rec = rec;
    rec.continuous = false;
    rec.interimResults = false;
    rec.lang = "en-US";
    rec.onresult = (ev) => {
      const last = ev.results?.[ev.results.length - 1];
      if (last && last.isFinal) {
        const transcript = last[0]?.transcript || "";
        stopListen({ silent: true });
        dispatchCommand(transcript);
      }
    };
    rec.onerror = (ev) => {
      const err = ev?.error || "";
      stopListen({ silent: true });
      if (err && err !== "aborted" && err !== "no-speech") {
        say(
          err === "not-allowed"
            ? "Microphone permission is blocked for this tab."
            : `Mic error: ${err}`,
          { tone: "err", speak: false }
        );
      }
    };
    rec.onend = () => {
      if (state.rec === rec && state.listening) stopListen({ silent: true });
    };
    try {
      rec.start();
    } catch (e) {
      stopListen({ silent: true });
      say("Could not start the mic.", { tone: "err", speak: false });
      return;
    }
    state.listening = true;
    setFabState("listening");
    setMeta("Browser speech (Live unavailable)");
    const respond = $("chitti-respond");
    const stop = $("chitti-stop");
    if (respond) respond.disabled = true;
    if (stop) stop.disabled = false;
    const bubble = $("chitti-bubble");
    if (bubble) {
      bubble.textContent = "Listening…";
      bubble.dataset.tone = "listen";
    }
  }

  async function startListen() {
    ensureDom();
    open();
    clearCloseTimer();

    const blocked = micBlockedReason();
    if (blocked) {
      say(blocked, { tone: "err", speak: false, autoClose: true, closeAfter: 4500 });
      return;
    }

    if (state.useLive) {
      try {
        await startLiveListen();
        return;
      } catch (e) {
        setMeta("");
        say(
          `Live voice unavailable (${e.message || "error"}). Falling back to browser speech.`,
          { tone: "err", speak: false, autoClose: false }
        );
      }
    }
    startBrowserListen();
  }

  function init(opts = {}) {
    state.product = opts.product || "multimodal";
    state.onCommand = typeof opts.onCommand === "function" ? opts.onCommand : null;
    state.onPickFile = typeof opts.onPickFile === "function" ? opts.onPickFile : null;
    state.busyGate = typeof opts.busyGate === "function" ? opts.busyGate : null;
    state.sessionId = opts.sessionId || null;
    state.getSessionId = typeof opts.getSessionId === "function" ? opts.getSessionId : null;
    if (typeof opts.useLive === "boolean") state.useLive = opts.useLive;
    ensureDom();
    setHints(state.product);
    return api;
  }

  const api = {
    NAME,
    EXPAND,
    init,
    open,
    close,
    say,
    listen: startListen,
    stop: () => stopListen({ silent: true }),
    pickDocument,
    isListening: () => !!state.listening,
    setSessionId: (id) => {
      state.sessionId = id || null;
    },
  };

  global.CHITTI = api;
})(typeof window !== "undefined" ? window : globalThis);
