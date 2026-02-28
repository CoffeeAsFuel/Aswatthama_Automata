import * as vscode from 'vscode';

export function activate(context: vscode.ExtensionContext) {

 const provider = new MedhavinViewProvider(context.extensionUri);

 context.subscriptions.push(
 vscode.window.registerWebviewViewProvider("medhavinSidebar", provider)
 );
}

class MedhavinViewProvider implements vscode.WebviewViewProvider {

 constructor(private readonly extensionUri: vscode.Uri) {}

 resolveWebviewView(webviewView: vscode.WebviewView) {

 webviewView.webview.options = {
 enableScripts: true
 };

 webviewView.webview.html = this.getHtml();

// 🔹 ADD THIS
 webviewView.webview.onDidReceiveMessage(async (message) => {
 switch (message.command) {

 case 'processCommand':
 await this.handleCommand(message.text, webviewView);
 break;

 case 'applyCode':
 await this.applyCodeToEditor(message.code);
 break;
 }
 });
}

 private getHtml(): string {
 return`
<!DOCTYPE html>
<html>
<head>
 <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
 <style>
 :root { --neon: #00f2fe; --spectral: linear-gradient(90deg, #4285F4, #9B72CB, #D96570); }
 body { margin: 0; background: #000; color: #fff; font-family: 'Inter', sans-serif; overflow: hidden; height: 100vh; }

 #canvas-hud { position: absolute; top: 0; left: 0; width: 100%; height: 100%; z-index: 1; }

 .content-layer {
 position: relative; z-index: 10; display: flex; flex-direction: column;
 height: 100vh; padding: 30px; box-sizing: border-box; pointer-events: none;
 }

 /* Giant Typography */
 .title { font-size: 42px; font-weight: 900; letter-spacing: -2px; line-height: 1; margin: 0; background: var(--spectral); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
 .version { font-size: 10px; letter-spacing: 4px; color: var(--neon); opacity: 0.6; margin-bottom: 30px; }

 /* Bulky Glass Container */
 .glass-view {
 flex-grow: 1; background: rgba(255, 255, 255, 0.02); backdrop-filter: blur(25px);
 border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 30px;
 padding: 30px; overflow-y: auto; pointer-events: auto;
 box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
 }

 #log-flow { font-family: 'Fira Code', monospace; font-size: 11px; color: var(--neon); opacity: 0.5; margin-bottom: 20px; }
 pre { font-family: 'Fira Code', monospace; font-size: 18px; line-height: 1.6; color: #fff; margin: 0; }

 /* Interactive Controls */
 .control-panel { margin-top: 30px; pointer-events: auto; }
 .input-bar {
 background: rgba(255,255,255,0.05); border-radius: 20px; border: 1px solid rgba(255,255,255,0.1);
 display: flex; align-items: center; padding: 5px 20px;
 }
 input { flex: 1; background: transparent; border: none; color: #fff; padding: 20px; font-size: 20px; outline: none; }

 .inject-btn {
 width: 100%; margin-top: 20px; padding: 22px; border-radius: 18px;
 background: var(--spectral); color: #fff; font-weight: 900; font-size: 18px;
 border: none; cursor: pointer; display: none; text-transform: uppercase;
 box-shadow: 0 10px 30px rgba(66, 133, 244, 0.3);
 }
 </style>
</head>
<body>
 <div id="canvas-hud"></div>

 <div class="content-layer">
 <h1 class="title">MEDHAVIN PRO</h1>
 <div class="version">NEURAL COMMAND INTERFACE v2.0</div>

 <div class="glass-view" id="scroller">
 <div id="log-flow"></div>
 <pre id="code-output">// AWAITING QUANTUM SIGNAL...</pre>
 </div>

 <div class="control-panel">
 <div class="input-bar">
 <input id="prompt" placeholder="Describe the feature..." autocomplete="off" />
 <div style="font-size: 28px; cursor: pointer;">🎙️</div>
 </div>
 <button id="inject" class="inject-btn">Instate Code Base</button>
 </div>
 </div>

 <script>
 const vscode = acquireVsCodeApi();

 // --- PRO 3D SPATIAL ENGINE ---
 const scene = new THREE.Scene();
 const camera = new THREE.PerspectiveCamera(75, window.innerWidth/window.innerHeight, 0.1, 1000);
 const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
 renderer.setSize(window.innerWidth, window.innerHeight);
 document.getElementById('canvas-hud').appendChild(renderer.domElement);

 // Starfield
 const starGeo = new THREE.BufferGeometry();
 const starCoords = [];
 for(let i=0; i<1500; i++) {
 starCoords.push(THREE.MathUtils.randFloatSpread(20), THREE.MathUtils.randFloatSpread(20), THREE.MathUtils.randFloatSpread(20));
 }
 starGeo.setAttribute('position', new THREE.Float32BufferAttribute(starCoords, 3));
 const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({color: 0x4285F4, size: 0.05}));
 scene.add(stars);

 // Mouse-Reactive Wireframe
 const geom = new THREE.TorusKnotGeometry(1.5, 0.4, 100, 16);
 const wire = new THREE.Mesh(geom, new THREE.MeshBasicMaterial({ color: 0x9B72CB, wireframe: true, transparent: true, opacity: 0.2 }));
 scene.add(wire);
 camera.position.z = 6;

 let mouseX = 0, mouseY = 0;
 document.onmousemove = (e) => {
 mouseX = (e.clientX / window.innerWidth) - 0.5;
 mouseY = (e.clientY / window.innerHeight) - 0.5;
 };

 function animate() {
 requestAnimationFrame(animate);
 wire.rotation.y += 0.005;
 // Reactive Tilt
 wire.rotation.x += (mouseY * 0.5 - wire.rotation.x) * 0.05;
 wire.rotation.y += (mouseX * 0.5 - wire.rotation.y) * 0.05;
 stars.rotation.y += 0.0005;
 renderer.render(scene, camera);
 }
 animate();

 // --- Controller ---
 const input = document.getElementById('prompt');
 const logs = document.getElementById('log-flow');
 const output = document.getElementById('code-output');
 const injectBtn = document.getElementById('inject');
 let currentCode = "";

 input.onkeydown = (e) => {
 if(e.key === 'Enter') {
 vscode.postMessage({ command: 'processCommand', text: input.value });
 addLog("SIGNAL_SENT: " + input.value);
 input.value = "";
 }
 };

 window.addEventListener('message', e => {
 if(e.data.command === 'log') addLog(e.data.text);
 if(e.data.command === 'typeCode') {
 currentCode = e.data.code;
 typeWriter(currentCode);
 }
 });

 function addLog(t) {
 const d = document.createElement('div');
 d.innerText = ">> " + t;
 logs.appendChild(d);
 document.getElementById('scroller').scrollTop = document.getElementById('scroller').scrollHeight;
 }

 function typeWriter(t) {
 let i = 0; output.innerText = "";
 injectBtn.style.display = 'none';
 function type() {
 if(i < t.length) {
 output.innerText += t.charAt(i++);
 setTimeout(type, 10);
 } else { injectBtn.style.display = 'block'; }
 }
 type();
 }

 injectBtn.onclick = () => vscode.postMessage({ command: 'applyCode', code: currentCode });
 </script>
</body>
</html>`;
 }
 private async handleCommand(text: string, webviewView: vscode.WebviewView) {

 webviewView.webview.postMessage({ command: 'log', text: 'Processing...' });

 try {
 const response = await fetch("http://127.0.0.1:8000/ask", {
 method: "POST",
 headers: { "Content-Type": "application/json" },
 body: JSON.stringify({ prompt: text })
 });

 const data: any = await response.json();

 webviewView.webview.postMessage({
 command: "typeCode",
 code: data.data || data.message || JSON.stringify(data)
 });

 } catch (error: any) {
 webviewView.webview.postMessage({
 command: "log",
 text: "Backend error: " + error.message
 });
 }
}

private async applyCodeToEditor(code: string) {
 const editor = vscode.window.activeTextEditor;
 if (!editor) return;

 const fullRange = new vscode.Range(
 editor.document.positionAt(0),
 editor.document.positionAt(editor.document.getText().length)
 );

 await editor.edit(editBuilder => {
 editBuilder.replace(fullRange, code);
 });
}}

 export function deactivate() {}