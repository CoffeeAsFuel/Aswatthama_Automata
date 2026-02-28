import * as vscode from 'vscode';
import * as crypto from 'crypto';
import * as http from 'http';

// ─────────────────────────────────────────────────────────────────────────────
// FIX: `fetch` is NOT available in VS Code extension host on Node 16 (VS Code
// ≤1.85). We replace all fetch() calls with a tiny http.request() helper that
// works on every Node version and respects the 120-second agent timeout.
// ─────────────────────────────────────────────────────────────────────────────
function httpPost(path: string, body: object): Promise<any> {
  return new Promise((resolve, reject) => {
    const bodyStr = JSON.stringify(body);
    const options: http.RequestOptions = {
      hostname: '127.0.0.1',
      port: 8000,
      path,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(bodyStr),
      },
    };
    const req = http.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => (data += chunk));
      res.on('end', () => {
        if (res.statusCode && res.statusCode >= 400) {
          reject(new Error(`Server error ${res.statusCode}: ${res.statusMessage}`));
          return;
        }
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(new Error('Backend returned invalid JSON: ' + data.slice(0, 200)));
        }
      });
    });
    req.on('error', reject);
    // 120 s timeout — Whisper load + agent can be slow on first run
    req.setTimeout(120_000, () => req.destroy(new Error('Request timed out (120s). Is the backend running?')));
    req.write(bodyStr);
    req.end();
  });
}

export function activate(context: vscode.ExtensionContext) {
  const provider = new MedhavinViewProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('medhavinSidebar', provider)
  );
}

class MedhavinViewProvider implements vscode.WebviewViewProvider {
  constructor(private readonly extensionUri: vscode.Uri) {}

  resolveWebviewView(webviewView: vscode.WebviewView) {
    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri]
    };

    webviewView.webview.html = this.getHtml(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (message) => {
      switch (message.command) {

        case 'processCommand':
          await this.handleTextCommand(message.text, webviewView);
          break;

        case 'startRecording':
          await this.handleBackendRecording(message.duration ?? 7, webviewView);
          break;

        case 'applyCode':
          await this.applyCodeToEditor(message.code);
          break;
      }
    });
  }

  // ─────────────────────────────────────────────────────────────────────
  // TEXT COMMAND → POST /ask
  // ─────────────────────────────────────────────────────────────────────
  private async handleTextCommand(text: string, webviewView: vscode.WebviewView) {
    webviewView.webview.postMessage({ command: 'log', text: '⏳ Processing: ' + text });

    try {
      // FIX: use httpPost instead of fetch (works on all Node versions)
      const data: any = await httpPost('/ask', { prompt: text });

      if (data.status === 'error') {
        throw new Error(data.message || 'Unknown error from backend.');
      }

      const replyText = this.extractReply(data);
      webviewView.webview.postMessage({ command: 'typeCode', code: replyText });
      webviewView.webview.postMessage({ command: 'log', text: '✅ Done.' });

    } catch (error: any) {
      const msg = this.formatError(error.message);
      webviewView.webview.postMessage({ command: 'error', text: msg });
    }
  }

  // ─────────────────────────────────────────────────────────────────────
  // BACKEND RECORDING → POST /record
  // ─────────────────────────────────────────────────────────────────────
  private async handleBackendRecording(duration: number, webviewView: vscode.WebviewView) {
    webviewView.webview.postMessage({ command: 'recordingStarted', duration });
    webviewView.webview.postMessage({
      command: 'log',
      text: `🎙️ Recording ${duration}s from your microphone…`
    });

    try {
      // FIX: use httpPost instead of fetch
      const data: any = await httpPost('/record', { duration });

      if (data.status === 'error') {
        throw new Error(data.message || 'Recording failed on server.');
      }

      const transcript = data.transcript || '';
      webviewView.webview.postMessage({
        command: 'log',
        text: `🗣️ You said: "${transcript}"`
      });

      const replyText = this.extractReply(data);
      webviewView.webview.postMessage({ command: 'typeCode', code: replyText });
      webviewView.webview.postMessage({ command: 'log', text: '✅ Done.' });
      webviewView.webview.postMessage({ command: 'recordingStopped' });

    } catch (error: any) {
      const msg = this.formatError(error.message);
      webviewView.webview.postMessage({ command: 'error', text: msg });
      webviewView.webview.postMessage({ command: 'recordingStopped' });
    }
  }

  // ─────────────────────────────────────────────────────────────────────
  // EXTRACT TEXT REPLY from nested backend response
  // ─────────────────────────────────────────────────────────────────────
  private extractReply(data: any): string {
    if (!data) { return 'No response received.'; }
    const inner = data.data || data.agent || data;
    if (typeof inner === 'string') { return inner; }
    if (inner.output)  { return String(inner.output); }
    if (inner.message) { return String(inner.message); }
    return JSON.stringify(inner, null, 2);
  }

  private formatError(message: string): string {
    const lower = (message || '').toLowerCase();
    if (lower.includes('connect') || lower.includes('econnrefused') || lower.includes('econnreset')) {
      return '❌ Backend offline. Run: uvicorn medhavin_server:app --port 8000';
    }
    if (lower.includes('timed out')) {
      return '❌ ' + message + '\nTip: Backend may still be loading Whisper — retry in 30s.';
    }
    if (lower.includes('sounddevice') || lower.includes('scipy')) {
      return '❌ Install recording libs: pip install sounddevice scipy';
    }
    return '❌ ' + message;
  }

  // ─────────────────────────────────────────────────────────────────────
  // APPLY CODE to the active editor
  // ─────────────────────────────────────────────────────────────────────
  private async applyCodeToEditor(code: string) {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage('Medhavin: No active editor — open a file first.');
      return;
    }
    const fullRange = new vscode.Range(
      editor.document.positionAt(0),
      editor.document.positionAt(editor.document.getText().length)
    );
    await editor.edit(edit => edit.replace(fullRange, code));
    vscode.window.showInformationMessage('✅ Medhavin: Code injected!');
  }

  // ─────────────────────────────────────────────────────────────────────
  // WEBVIEW HTML
  // ─────────────────────────────────────────────────────────────────────
  private getHtml(webview: vscode.Webview): string {
    const nonce = crypto.randomBytes(16).toString('hex');

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="Content-Security-Policy"
    content="default-src 'none';
             script-src 'nonce-${nonce}';
             style-src 'unsafe-inline';
             img-src data: vscode-resource:;">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Medhavin AI</title>

  <style>
    :root {
      --neon: #00f2fe;
      --spectral-1: #4285F4;
      --spectral-2: #9B72CB;
      --spectral-3: #D96570;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: #050510;
      color: #fff;
      font-family: 'Inter', 'Segoe UI', sans-serif;
      height: 100vh;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }

    .bg { position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none; }
    .bg-orb {
      position: absolute; border-radius: 50%;
      filter: blur(80px); opacity: 0.15;
      animation: drift 12s ease-in-out infinite alternate;
    }
    .bg-orb:nth-child(1) { width:350px; height:350px; top:-100px; left:-80px; background:var(--spectral-1); animation-duration:11s; }
    .bg-orb:nth-child(2) { width:300px; height:300px; bottom:-80px; right:-60px; background:var(--spectral-2); animation-duration:14s; animation-delay:-4s; }
    .bg-orb:nth-child(3) { width:200px; height:200px; top:40%; left:50%; background:var(--spectral-3); animation-duration:9s; animation-delay:-7s; }
    @keyframes drift { from{transform:translate(0,0) scale(1);} to{transform:translate(30px,20px) scale(1.1);} }
    .grid-lines {
      position: fixed; inset: 0; z-index: 0; pointer-events: none;
      background-image: linear-gradient(rgba(66,133,244,0.04) 1px,transparent 1px), linear-gradient(90deg,rgba(66,133,244,0.04) 1px,transparent 1px);
      background-size: 40px 40px;
    }

    .shell { position:relative; z-index:10; display:flex; flex-direction:column; height:100vh; padding:20px 16px 16px; gap:12px; }

    .header { flex-shrink: 0; }
    .title {
      font-size:28px; font-weight:900; letter-spacing:-1.5px; line-height:1;
      background: linear-gradient(90deg, var(--spectral-1), var(--spectral-2), var(--spectral-3));
      -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
    }
    .subtitle { font-size:9px; letter-spacing:3px; text-transform:uppercase; color:var(--neon); opacity:0.5; margin-top:3px; }

    .output-box {
      flex:1; min-height:0;
      background:rgba(255,255,255,0.025);
      border:1px solid rgba(255,255,255,0.08);
      border-radius:16px; padding:16px;
      overflow-y:auto; display:flex; flex-direction:column; gap:8px;
    }
    .log-area {
      font-family:'Fira Code','Consolas',monospace;
      font-size:10px; color:var(--neon); opacity:0.6;
      border-bottom:1px solid rgba(255,255,255,0.06);
      padding-bottom:8px; margin-bottom:4px;
      max-height:80px; overflow-y:auto;
    }
    .log-area:empty { display:none; }
    .log-line { line-height:1.6; }
    .log-line.error { color:#ff6b6b; opacity:1; }

    .output-pre {
      font-family:'Fira Code','Consolas',monospace;
      font-size:12px; line-height:1.7; color:#e8e8f0;
      white-space:pre-wrap; word-break:break-word; flex:1;
    }
    .placeholder { color:rgba(255,255,255,0.2); font-style:italic; }

    .controls { flex-shrink:0; display:flex; flex-direction:column; gap:8px; }

    .input-row {
      display:flex; align-items:center; gap:8px;
      background:rgba(255,255,255,0.05);
      border:1px solid rgba(255,255,255,0.1);
      border-radius:14px; padding:4px 4px 4px 16px;
      transition:border-color 0.2s;
    }
    .input-row:focus-within {
      border-color:rgba(66,133,244,0.5);
      box-shadow:0 0 0 2px rgba(66,133,244,0.1);
    }
    #prompt-input {
      flex:1; background:transparent; border:none;
      color:#fff; font-size:14px; outline:none; padding:10px 0;
    }
    #prompt-input::placeholder { color:rgba(255,255,255,0.3); }

    #send-btn {
      width:40px; height:40px; border-radius:10px; border:none; cursor:pointer;
      font-size:16px;
      background:linear-gradient(135deg, var(--spectral-1), var(--spectral-2));
      transition:all 0.2s; flex-shrink:0;
      display:flex; align-items:center; justify-content:center; opacity:0.85;
    }
    #send-btn:hover { opacity:1; transform:scale(1.05); }

    #mic-btn {
      width:40px; height:40px; border-radius:10px; border:none; cursor:pointer;
      font-size:18px; background:rgba(255,255,255,0.07);
      transition:all 0.2s; flex-shrink:0;
      display:flex; align-items:center; justify-content:center;
    }
    #mic-btn:hover { background:rgba(255,255,255,0.12); }
    #mic-btn:disabled { opacity:0.35; cursor:not-allowed; }

    #mic-btn.recording {
      background:rgba(255,60,60,0.25);
      animation:mic-pulse 1s ease-out infinite;
    }
    @keyframes mic-pulse {
      0%   { box-shadow:0 0 0 0 rgba(255,60,60,0.5); }
      70%  { box-shadow:0 0 0 8px rgba(255,60,60,0); }
      100% { box-shadow:0 0 0 0 rgba(255,60,60,0); }
    }

    .duration-row {
      display:flex; align-items:center; gap:8px;
      padding:0 4px;
    }
    .duration-label { font-size:10px; color:rgba(255,255,255,0.4); }
    .dur-btn {
      padding:3px 10px; border-radius:8px; border:1px solid rgba(255,255,255,0.12);
      background:rgba(255,255,255,0.05); color:rgba(255,255,255,0.55);
      font-size:11px; cursor:pointer; transition:all 0.15s;
    }
    .dur-btn:hover { background:rgba(255,255,255,0.1); color:#fff; }
    .dur-btn.active {
      background:rgba(66,133,244,0.25);
      border-color:rgba(66,133,244,0.5);
      color:#fff;
    }

    #countdown-wrap {
      display:none; height:3px; border-radius:2px;
      background:rgba(255,255,255,0.08); overflow:hidden;
    }
    #countdown-bar {
      height:100%; width:100%;
      background:linear-gradient(90deg, var(--spectral-1), var(--spectral-3));
      transform-origin:left;
      transition:transform linear;
    }

    #status-bar {
      font-size:10px; min-height:14px; padding:0 4px;
      color:var(--neon); opacity:0.7;
      text-align:center; transition:color 0.2s;
    }
    #status-bar.error-text { color:#ff6b6b; opacity:1; }

    #inject-btn {
      display:none; width:100%; padding:14px; border-radius:12px; border:none;
      background:linear-gradient(90deg, var(--spectral-1), var(--spectral-2));
      color:#fff; font-weight:800; font-size:13px; letter-spacing:0.5px;
      cursor:pointer; text-transform:uppercase;
      box-shadow:0 8px 24px rgba(66,133,244,0.25);
      transition:opacity 0.2s, transform 0.1s;
    }
    #inject-btn:hover  { opacity:0.9; transform:translateY(-1px); }
    #inject-btn:active { transform:translateY(0); }
  </style>
</head>
<body>

  <div class="bg">
    <div class="bg-orb"></div><div class="bg-orb"></div><div class="bg-orb"></div>
  </div>
  <div class="grid-lines"></div>

  <div class="shell">

    <div class="header">
      <div class="title">MEDHAVIN</div>
      <div class="subtitle">Autonomous Coding Agent · v3.0</div>
    </div>

    <div class="output-box" id="output-box">
      <div class="log-area" id="log-area"></div>
      <pre class="output-pre" id="output-pre"><span class="placeholder">// Awaiting your command…</span></pre>
    </div>

    <div class="controls">

      <div class="input-row">
        <input id="prompt-input" type="text"
               placeholder="Describe what to build…"
               autocomplete="off" spellcheck="false" />
        <button id="send-btn" title="Send (Enter)">➤</button>
        <button id="mic-btn" title="Record voice via backend microphone">🎙️</button>
      </div>

      <div class="duration-row" id="duration-row">
        <span class="duration-label">Record:</span>
        <button class="dur-btn" data-sec="5">5s</button>
        <button class="dur-btn active" data-sec="7">7s</button>
        <button class="dur-btn" data-sec="10">10s</button>
        <button class="dur-btn" data-sec="15">15s</button>
      </div>

      <div id="countdown-wrap"><div id="countdown-bar"></div></div>

      <div id="status-bar"></div>
      <button id="inject-btn">⚡ Inject Code into Editor</button>
    </div>

  </div>

  <script nonce="${nonce}">
    const vscode      = acquireVsCodeApi();
    const promptInput = document.getElementById('prompt-input');
    const logArea     = document.getElementById('log-area');
    const outputPre   = document.getElementById('output-pre');
    const statusBar   = document.getElementById('status-bar');
    const injectBtn   = document.getElementById('inject-btn');
    const micBtn      = document.getElementById('mic-btn');
    const sendBtn     = document.getElementById('send-btn');
    const outputBox   = document.getElementById('output-box');
    const countdownWrap = document.getElementById('countdown-wrap');
    const countdownBar  = document.getElementById('countdown-bar');

    let currentCode   = '';
    let selectedDur   = 7;
    let isRecording   = false;

    document.querySelectorAll('.dur-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.dur-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        selectedDur = parseInt(btn.dataset.sec, 10);
      });
    });

    function setStatus(msg, isError = false) {
      statusBar.textContent = msg;
      statusBar.className   = isError ? 'error-text' : '';
    }

    function addLog(text, isError = false) {
      const el = document.createElement('div');
      el.className  = 'log-line' + (isError ? ' error' : '');
      el.textContent = '› ' + text;
      logArea.appendChild(el);
      logArea.scrollTop = logArea.scrollHeight;
    }

    function typeWrite(text) {
      outputPre.textContent = '';
      injectBtn.style.display = 'none';
      let i = 0;
      function tick() {
        if (i < text.length) {
          outputPre.textContent += text[i++];
          outputBox.scrollTop = outputBox.scrollHeight;
          setTimeout(tick, 6);
        } else {
          if (text.includes('\\n') || text.length > 120) {
            injectBtn.style.display = 'block';
          }
        }
      }
      tick();
    }

    function submitText() {
      const text = promptInput.value.trim();
      if (!text) { return; }
      promptInput.value = '';
      addLog('YOU: ' + text);
      vscode.postMessage({ command: 'processCommand', text });
    }

    promptInput.addEventListener('keydown', e => { if (e.key === 'Enter') { submitText(); } });
    sendBtn.addEventListener('click', submitText);

    micBtn.addEventListener('click', () => {
      if (isRecording) { return; }
      startBackendRecording();
    });

    function startBackendRecording() {
      isRecording = true;
      micBtn.classList.add('recording');
      micBtn.textContent = '⏳';
      micBtn.disabled    = true;

      setStatus('🔴 Recording ' + selectedDur + 's… (speak now)');
      addLog('MIC: Backend recording started (' + selectedDur + 's)');

      countdownWrap.style.display = 'block';
      countdownBar.style.transition = 'none';
      countdownBar.style.transform  = 'scaleX(1)';
      countdownBar.getBoundingClientRect();
      countdownBar.style.transition = 'transform ' + selectedDur + 's linear';
      countdownBar.style.transform  = 'scaleX(0)';

      vscode.postMessage({ command: 'startRecording', duration: selectedDur });
    }

    function resetMicState() {
      isRecording = false;
      micBtn.classList.remove('recording');
      micBtn.textContent = '🎙️';
      micBtn.disabled    = false;
      countdownWrap.style.display = 'none';
      countdownBar.style.transform = 'scaleX(1)';
    }

    window.addEventListener('message', e => {
      const msg = e.data;

      if (msg.command === 'log') {
        addLog(msg.text);
        setStatus(msg.text);
      }
      if (msg.command === 'typeCode') {
        currentCode = msg.code || '';
        typeWrite(currentCode);
      }
      if (msg.command === 'error') {
        addLog(msg.text, true);
        setStatus(msg.text, true);
        resetMicState();
      }
      if (msg.command === 'recordingStopped') {
        resetMicState();
      }
    });

    injectBtn.addEventListener('click', () => {
      vscode.postMessage({ command: 'applyCode', code: currentCode });
      addLog('Code injected into editor.');
    });
  </script>

</body>
</html>`;
  }
}

export function deactivate() {}
