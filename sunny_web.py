"""
Sunny AI v5.0 — Web Interface (FastAPI + WebSocket)
Chạy: python sunny_web.py
Mở : http://localhost:7860
"""
import os, sys, json, asyncio, threading, traceback, datetime, re
from pathlib import Path

try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
    from fastapi.responses import HTMLResponse
    import uvicorn
except ImportError:
    print("[ERROR] Run: pip install fastapi uvicorn")
    sys.exit(1)

from core.config  import APP_VERSION, DEVICE, MODEL_NAME, vram_gb, FILES, HAS_TTS, HAS_MIC
from core.memory  import VectorMemory, ConversationManager
from core.brain   import SunnyBrain
from core.planner import PlanExecutor
from tools.reader import read_file as _read_file
from tools.voice  import AudioMouth, AudioEar

import psutil

# ── Logging ───────────────────────────────────────────────────
_log_lock = threading.Lock()

def write_log(msg: str):
    # FIX (GPT): lock để tránh nhiều thread ghi đè lên nhau
    try:
        with _log_lock:
            with open(FILES["LOG"], "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception: pass

def maintain_logs():
    log = FILES["LOG"]
    if os.path.exists(log) and os.path.getsize(log) > 2*1024*1024:
        try:
            with open(log, "r", encoding="utf-8") as f: lines = f.readlines()
            with open(log, "w", encoding="utf-8") as f: f.writelines(lines[-1000:])
        except Exception: pass

# ── Report writer ─────────────────────────────────────────────
class ReportWriter:
    DIR = "reports"

    @staticmethod
    def save(src: str, content: str) -> str:
        Path(ReportWriter.DIR).mkdir(exist_ok=True)
        name = os.path.splitext(os.path.basename(src))[0]
        ts   = datetime.datetime.now().strftime("%Y-%m-%d_%Hh%M")
        out  = Path(ReportWriter.DIR) / f"REPORT_{name}_{ts}.txt"
        with open(out, "w", encoding="utf-8") as f:
            f.write(f"=== SUNNY AI REPORT ===\nSource: {src}\nCreated: {datetime.datetime.now()}\n{'='*30}\n\n{content}")
        return str(out)

# ── Model loader ──────────────────────────────────────────────
def load_model():
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        import torch
        print(f"[Sunny] Loading {MODEL_NAME} on {DEVICE.upper()}...")
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        tok = AutoTokenizer.from_pretrained(MODEL_NAME)
        m = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
        )
        m.eval()
        print("[Sunny] Model ready.")
        return m, tok
    except Exception as e:
        write_log(f"MODEL_LOAD_ERROR: {e}")
        print(f"[Sunny] Model load failed: {e}\n[Sunny] Running in demo mode.")
        return None, None

# ── Startup ───────────────────────────────────────────────────
maintain_logs()
write_log(f"SESSION_START | Sunny v{APP_VERSION} | {DEVICE.upper()} | {MODEL_NAME}")

os.makedirs(FILES["UPLOAD_DIR"], exist_ok=True)

model, tokenizer = load_model()
vmem   = VectorMemory()
brain  = SunnyBrain(model, tokenizer) if model else None
conv   = ConversationManager()
if brain:
    executor = PlanExecutor(brain)
else:
    executor = None

# FIX (GPT): lock tránh race condition khi 2 user switch model cùng lúc
_model_lock = threading.Lock()

# ── Voice ─────────────────────────────────────────────────────
mouth = AudioMouth()

def _voice_callback(event: str, data: str):
    """Callback từ AudioEar — sẽ được override trong WS handler."""
    pass

ear = AudioEar(callback=_voice_callback)

# ── FastAPI ───────────────────────────────────────────────────
app = FastAPI(title=f"Sunny AI v{APP_VERSION}")

class ConnManager:
    def __init__(self): self.active: list[WebSocket] = []
    async def connect(self, ws):
        await ws.accept(); self.active.append(ws)
    def disconnect(self, ws):
        if ws in self.active: self.active.remove(ws)
    async def send(self, ws, data):
        try: await ws.send_json(data)
        except Exception: self.disconnect(ws)

manager = ConnManager()

# ── HTML ──────────────────────────────────────────────────────
HTML = r'''<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>☀️ Sunny AI v5.0</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Syne:wght@700;800&display=swap" rel="stylesheet">
<style>
:root{
  --bg:#07070f;--surface:#0c0c1a;--panel:#101022;--border:#1a1a30;
  --accent:#f59e0b;--cyan:#06b6d4;--green:#10b981;--red:#ef4444;
  --purple:#a78bfa;--pink:#f9a8d4;--blue:#60a5fa;
  --text:#e2e8f0;--muted:#475569;
}
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;overflow:hidden}
body{font-family:'JetBrains Mono',monospace;background:var(--bg);color:var(--text);display:flex;flex-direction:column;height:100vh}

/* Grid bg */
body::before{content:'';position:fixed;inset:0;
  background-image:linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px);
  background-size:48px 48px;opacity:.12;pointer-events:none;z-index:0}

header,nav,.main,.foot{position:relative;z-index:1}

/* Header */
header{display:flex;align-items:center;justify-content:space-between;
  padding:10px 20px;background:var(--surface);border-bottom:1px solid var(--border);flex-shrink:0}
.logo{font-family:'Syne',sans-serif;font-size:1.25rem;font-weight:800;color:var(--accent);letter-spacing:.04em}
.logo span{color:var(--cyan)}
.hinfo{display:flex;gap:12px;align-items:center;font-size:.7rem;color:var(--muted)}
.badge{background:var(--panel);border:1px solid var(--border);border-radius:3px;padding:2px 7px;font-size:.66rem}
.badge.gpu{color:var(--accent);border-color:var(--accent)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--green);animation:pulse 2s infinite}
.dot.off{background:var(--red);animation:none}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}

/* Toolbar */
nav{display:flex;gap:5px;padding:7px 14px;background:var(--panel);border-bottom:1px solid var(--border);flex-wrap:wrap;flex-shrink:0}
.tb{background:var(--surface);border:1px solid var(--border);color:var(--muted);
  font-family:'JetBrains Mono',monospace;font-size:.7rem;padding:4px 11px;border-radius:3px;
  cursor:pointer;transition:all .15s;white-space:nowrap}
.tb:hover{color:var(--text);border-color:var(--cyan)}
.tb.red:hover{border-color:var(--red);color:var(--red)}
#proc{font-size:.68rem;color:var(--muted);margin-left:auto;padding:0 8px}

/* Layout */
.main{display:flex;flex:1;overflow:hidden}

/* Sidebar */
aside{width:210px;background:var(--panel);border-right:1px solid var(--border);
  display:flex;flex-direction:column;padding:10px;gap:10px;overflow-y:auto;flex-shrink:0}
aside::-webkit-scrollbar{width:3px}
aside::-webkit-scrollbar-thumb{background:var(--border)}
.stitle{font-size:.62rem;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;
  border-bottom:1px solid var(--border);padding-bottom:5px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:5px;padding:9px;display:flex;flex-direction:column;gap:5px}
.row{display:flex;justify-content:space-between;font-size:.66rem;color:var(--muted)}
.row .v{color:var(--text)}.row .v.ok{color:var(--green)}.row .v.warn{color:var(--accent)}
.mbtn{flex:1;background:var(--surface);border:1px solid var(--border);color:var(--muted);
  font-family:'JetBrains Mono',monospace;font-size:.72rem;font-weight:700;
  padding:5px 0;border-radius:3px;cursor:pointer;transition:all .15s}
.mbtn:hover{color:var(--text);border-color:var(--cyan)}
.mbtn.active{background:var(--accent);color:#000;border-color:var(--accent)}
.mbtn:disabled{opacity:.4;cursor:not-allowed}

/* Loading overlay */
#loading-overlay{
  display:none;position:fixed;inset:0;z-index:999;
  background:rgba(7,7,15,.92);backdrop-filter:blur(4px);
  flex-direction:column;align-items:center;justify-content:center;gap:16px;
}
#loading-overlay.on{display:flex}
.spinner{width:48px;height:48px;border:3px solid var(--border);
  border-top-color:var(--accent);border-radius:50%;animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.load-title{font-family:'Syne',sans-serif;font-size:1.1rem;font-weight:800;color:var(--accent)}
.load-sub{font-size:.75rem;color:var(--muted);text-align:center}
#fi{display:none}

/* Chat */
.chat-wrap{flex:1;display:flex;flex-direction:column;overflow:hidden}
#chat{flex:1;overflow-y:auto;padding:14px 18px;display:flex;flex-direction:column;gap:3px}
#chat::-webkit-scrollbar{width:3px}
#chat::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}

.msg{font-size:.8rem;line-height:1.65;padding:1px 0;animation:fi .2s ease}
@keyframes fi{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
.msg.user{color:var(--blue)}.msg.ai{color:var(--pink)}
.msg.sys{color:var(--accent);font-size:.72rem}
.msg.plan{color:var(--purple);font-size:.72rem;font-style:italic}
.msg.tool{color:var(--green);font-size:.72rem}
.msg.err{color:var(--red)}
.pfx{font-weight:700;margin-right:5px}

/* Typing */
.typing{display:none;align-items:center;gap:3px;padding:3px 18px;color:var(--muted);font-size:.7rem}
.typing.on{display:flex}
.td{width:5px;height:5px;border-radius:50%;background:var(--pink);animation:bounce 1.2s infinite}
.td:nth-child(2){animation-delay:.2s}.td:nth-child(3){animation-delay:.4s}
@keyframes bounce{0%,80%,100%{transform:translateY(0);opacity:.5}40%{transform:translateY(-5px);opacity:1}}

/* Input */
.foot{padding:10px 14px;background:var(--panel);border-top:1px solid var(--border);
  display:flex;gap:7px;align-items:center;flex-shrink:0}
#inp{flex:1;background:var(--surface);border:1px solid var(--border);color:var(--text);
  font-family:'JetBrains Mono',monospace;font-size:.83rem;padding:9px 13px;
  border-radius:4px;outline:none;transition:border .15s}
#inp:focus{border-color:var(--cyan)}
#inp::placeholder{color:var(--muted)}
#sbtn{background:var(--accent);color:#000;border:none;font-family:'Syne',sans-serif;
  font-weight:800;font-size:.78rem;padding:9px 16px;border-radius:4px;
  cursor:pointer;transition:all .15s;white-space:nowrap}
#sbtn:hover{background:#fbbf24;transform:translateY(-1px)}
#sbtn:disabled{background:var(--border);color:var(--muted);transform:none;cursor:not-allowed}

/* Example prompts */
.examples{padding:6px 18px;display:flex;gap:6px;flex-wrap:wrap;border-top:1px solid var(--border);background:var(--surface)}
.ex{background:var(--panel);border:1px solid var(--border);color:var(--muted);
  font-size:.65rem;padding:3px 9px;border-radius:3px;cursor:pointer;transition:all .15s}
.ex:hover{color:var(--text);border-color:var(--purple)}
</style>
</head>
<body>

<header>
  <div class="logo">☀️ SUNNY<span>AI</span> <small style="font-size:.65em;font-weight:400;color:var(--muted)">v5.0</small></div>
  <div class="hinfo">
    <span id="mbadge" class="badge gpu">--</span>
    <span id="vbadge" class="badge">Memory: --</span>
    <div class="dot" id="cdot"></div>
    <span id="clbl" style="font-size:.68rem">Connecting...</span>
  </div>
</header>

<!-- Loading overlay khi switch model -->
<div id="loading-overlay">
  <div class="spinner"></div>
  <div class="load-title">☀️ Switching Model...</div>
  <div class="load-sub" id="load-msg">Loading model, please wait...<br>This may take 2–5 minutes.</div>
</div>

<nav>
  <button class="tb" onclick="qa('search')">🌐 Search</button>
  <button class="tb" onclick="trigUp()">📄 Read File</button>
  <button class="tb" onclick="qa('report')">📊 Report</button>
  <button class="tb" onclick="qa('diary')">📔 Diary</button>
  <button class="tb" onclick="qa('mem')">🧠 Memory</button>
  <button class="tb" id="micbtn" onclick="toggleMic()">🎙️ Mic</button>
  <button class="tb" onclick="qa('scan_temp')">🔍 Scan Temp</button>
  <button class="tb red" onclick="qa('delete_temp')">🗑️ Delete Temp</button>
  <button class="tb red" onclick="clearChat()">✖ Clear</button>
  <span id="proc"></span>
</nav>

<div class="main">
  <aside>
    <div class="stitle">Model</div>
    <div class="card">
      <div class="row"><span>Active</span><span class="v ok" id="sm-active" style="font-size:.58rem">--</span></div>
      <div style="display:flex;gap:5px;margin-top:6px">
        <button class="mbtn" id="btn3b" onclick="switchModel('3b')">3B</button>
        <button class="mbtn" id="btn8b" onclick="switchModel('8b')">8B</button>
      </div>
      <div style="font-size:.6rem;color:var(--muted);margin-top:4px" id="mhint">3B: &lt;7GB VRAM | 8B: ≥7GB</div>
    </div>

    <div class="stitle">System</div>
    <div class="card">
      <div class="row"><span>Device</span><span class="v" id="sd">--</span></div>
      <div class="row"><span>VRAM</span><span class="v" id="sv">--</span></div>
      <div class="row"><span>Model</span><span class="v" id="sm" style="font-size:.58rem">--</span></div>
      <div class="row"><span>CPU</span><span class="v" id="sc">--</span></div>
      <div class="row"><span>RAM</span><span class="v" id="sr">--</span></div>
    </div>

    <div class="stitle">Memory</div>
    <div class="card">
      <div class="row"><span>FAISS</span><span class="v ok" id="sf">--</span></div>
      <div class="row"><span>JSON</span><span class="v" id="sj">--</span></div>
    </div>

    <div class="stitle">Security</div>
    <div class="card">
      <div class="row"><span>Sandbox</span><span class="v ok">Active</span></div>
      <div class="row"><span>Path check</span><span class="v ok">Symlink-safe</span></div>
      <div class="row"><span>Injection</span><span class="v ok">Sanitized</span></div>
    </div>

    <div class="stitle">Voice</div>
    <div class="card">
      <div class="row"><span>TTS</span><span class="v" id="stts">--</span></div>
      <div class="row"><span>STT</span><span class="v" id="sstt">--</span></div>
    </div>

    <div class="stitle">Upload</div>
    <div class="upzone" onclick="trigUp()">📎 Click to upload<br>PDF/DOCX/XLSX/TXT</div>
    <input type="file" id="fi" accept=".pdf,.docx,.xlsx,.xls,.txt,.csv,.md" onchange="upFile(this)">
  </aside>

  <div class="chat-wrap">
    <div id="chat">
      <div class="msg sys"><span class="pfx">&gt;&gt;</span>Sunny AI v5.0 initializing...</div>
    </div>
    <div class="typing" id="typ">
      <div class="td"></div><div class="td"></div><div class="td"></div>
      <span style="margin-left:5px">Sunny đang suy nghĩ...</span>
    </div>

    <div class="examples" id="exrow">
      <span style="font-size:.65rem;color:var(--muted);margin-right:4px">Try:</span>
      <button class="ex" onclick="fillEx(this)">Tìm tin tức AI mới nhất</button>
      <button class="ex" onclick="fillEx(this)">Phân tích file report.xlsx</button>
      <button class="ex" onclick="fillEx(this)">Dọn file rác trong C:\\Temp</button>
      <button class="ex" onclick="fillEx(this)">Xem pin điện thoại</button>
      <button class="ex" onclick="fillEx(this)">Em nhớ gì về cuộc trò chuyện trước?</button>
    </div>

    <div class="foot">
      <input id="inp" type="text" placeholder="Nhắn gì đó với Sunny..." autocomplete="off">
      <button id="sbtn" onclick="send()">SEND ▶</button>
    </div>
  </div>
</div>

<script>
let ws, busy=false, curAI=null;

function connect(){
  ws=new WebSocket(`ws://${location.host}/ws`);
  ws.onopen=()=>{
    document.getElementById('cdot').className='dot';
    document.getElementById('clbl').textContent='Connected';
    ws.send(JSON.stringify({type:'info'}));
    setInterval(()=>ws.send(JSON.stringify({type:'sysinfo'})),3000);
  };
  ws.onclose=()=>{
    document.getElementById('cdot').className='dot off';
    document.getElementById('clbl').textContent='Reconnecting...';
    setTimeout(connect,2000);
  };
  ws.onmessage=e=>handle(JSON.parse(e.data));
}

function handle(d){
  switch(d.type){
    case 'info':
      document.getElementById('sd').textContent=d.device.toUpperCase();
      document.getElementById('sv').textContent=d.vram>0?d.vram.toFixed(1)+'GB':'N/A';
      document.getElementById('sm').textContent=d.model.split('/').pop();
      document.getElementById('sf').textContent=d.vec_entries+' entries';
      document.getElementById('sj').textContent=d.json_entries+' entries';
      document.getElementById('mbadge').textContent=d.device.toUpperCase()+' | '+d.model.split('/').pop();
      document.getElementById('vbadge').textContent=d.vec_enabled?'FAISS: '+d.vec_entries:'JSON only';
      // Model active label
      const smA=document.getElementById('sm-active');
      if(smA) smA.textContent=d.model.split('/').pop();
      // Highlight active button
      const is8b=d.model.toLowerCase().includes('8b');
      setModelBtns(is8b?'8b':'3b');
      // Voice status
      const ttsEl=document.getElementById('stts');
      const sttEl=document.getElementById('sstt');
      if(ttsEl){ttsEl.textContent=d.has_tts?'Ready':'Disabled';ttsEl.className='v '+(d.has_tts?'ok':'warn');}
      if(sttEl){sttEl.textContent=d.has_mic?'Ready':'Disabled';sttEl.className='v '+(d.has_mic?'ok':'warn');}
      break;
    case 'model_switched':
      hideLoading();
      setBusy(false);
      msg('sys','✅ Switched to: '+d.model);
      ws.send(JSON.stringify({type:'info'}));
      break;
    case 'model_error':
      hideLoading();
      setBusy(false);
      msg('err','❌ Switch failed: '+d.text);
      break;
    case 'sysinfo':
      document.getElementById('sc').textContent=d.cpu+'%';
      document.getElementById('sr').textContent=d.ram+'%';
      break;
    case 'sys': msg('sys',d.text); setStatus(''); break;
    case 'plan': msg('plan','📋 '+d.text); break;
    case 'tool': msg('tool','🔧 '+d.text); break;
    case 'stream_start':
      typing(false);
      curAI=msg('ai','','Sunny');
      break;
    case 'stream_token':
      if(curAI){curAI.querySelector('.mc').textContent+=d.token;scrollBot();}
      break;
    case 'stream_end':
      curAI=null; setBusy(false); ws.send(JSON.stringify({type:'info'}));
      // Reset mic button
      micOn=false;
      const mb=document.getElementById('micbtn');
      if(mb){mb.style.borderColor='';mb.style.color='';mb.textContent='🎙️ Mic';}
      break;
    case 'voice_text':
      // Text từ STT — fill vào input và auto send
      document.getElementById('inp').value=d.text;
      micOn=false;
      const mb2=document.getElementById('micbtn');
      if(mb2){mb2.style.borderColor='';mb2.style.color='';mb2.textContent='🎙️ Mic';}
      send();
      break;
    case 'error': msg('err','⚠️ '+d.text); setBusy(false); break;
    case 'status': setStatus(d.text); break;
    case 'mem_stats':
      msg('sys',`🧠 FAISS: ${d.vec} | JSON: ${d.json} | Engine: ${d.enabled?'Active':'JSON-only'}`); break;
  }
}

function msg(type,text,pfx=''){
  const c=document.getElementById('chat');
  const d=document.createElement('div');
  d.className='msg '+type;
  d.innerHTML=pfx?`<span class="pfx">${pfx}:</span><span class="mc">${text}</span>`
                 :`<span class="mc">${text}</span>`;
  c.appendChild(d); scrollBot(); return d;
}
function scrollBot(){const c=document.getElementById('chat');c.scrollTop=c.scrollHeight}
function typing(on){document.getElementById('typ').className='typing'+(on?' on':'')}
function setBusy(v){
  busy=v;
  document.getElementById('sbtn').disabled=v;
  document.getElementById('inp').disabled=v;
  typing(v); if(!v)setStatus('');
}
function setStatus(t){document.getElementById('proc').textContent=t}

function send(){
  if(busy)return;
  const inp=document.getElementById('inp');
  const m=inp.value.trim(); if(!m)return;
  inp.value=''; msg('user',m,'You'); setBusy(true);
  ws.send(JSON.stringify({type:'chat',message:m}));
}
let micOn=false;
function toggleMic(){
  if(busy)return;
  micOn=!micOn;
  const btn=document.getElementById('micbtn');
  if(micOn){
    btn.style.borderColor='var(--red)';
    btn.style.color='var(--red)';
    btn.textContent='🔴 Listening...';
    ws.send(JSON.stringify({type:'mic_start'}));
  } else {
    btn.style.borderColor='';btn.style.color='';
    btn.textContent='🎙️ Mic';
  }
}
function qa(a){
  if(busy)return;
  const map={
    search     : 'Tìm kiếm: ',
    report     : 'Tạo báo cáo: ',
    diary      : 'Đọc nhật ký',
    scan_temp  : 'Quét rác trong thư mục TEMP',
    delete_temp: 'Xóa rác trong thư mục TEMP',
    mem        : null,
  };
  if(a==='mem'){ws.send(JSON.stringify({type:'mem_stats'}));return;}
  const inp=document.getElementById('inp');
  inp.value=map[a]||''; inp.focus();
  // Auto send nếu không cần input thêm
  if(['diary','scan_temp','delete_temp'].includes(a)) send();
}
function clearChat(){
  ws.send(JSON.stringify({type:'clear'}));
  document.getElementById('chat').innerHTML='';
  msg('sys','── Cleared ──');
}

function switchModel(size){
  if(busy) return;
  const confirmed = confirm(
    size==='8b'
      ? '⚠️ Switch sang model 8B?\n\nCần VRAM ≥7GB. App sẽ bị khóa 2–5 phút trong khi load.'
      : '⚠️ Switch sang model 3B?\n\nApp sẽ bị khóa 2–5 phút trong khi load.'
  );
  if(!confirmed) return;
  showLoading(`Loading ${size==='8b'?'Hermes 3 8B':'Llama 3.2 3B'}...`);
  // FIX (Gemini): setBusy để chặn mọi chat request khi model đang reload
  setBusy(true);
  ws.send(JSON.stringify({type:'switch_model', size}));
}

function showLoading(msg){
  document.getElementById('load-msg').innerHTML = msg + '<br>This may take 2–5 minutes.';
  document.getElementById('loading-overlay').className='on';
}
function hideLoading(){
  document.getElementById('loading-overlay').className='';
}
function setModelBtns(active){
  document.getElementById('btn3b').className='mbtn'+(active==='3b'?' active':'');
  document.getElementById('btn8b').className='mbtn'+(active==='8b'?' active':'');
}
function trigUp(){document.getElementById('fi').click()}
async function upFile(input){
  const f=input.files[0]; if(!f)return;
  const fd=new FormData(); fd.append('file',f);
  msg('sys','📎 Uploading: '+f.name+'...');
  try{
    const r=await fetch('/upload',{method:'POST',body:fd});
    const d=await r.json();
    if(d.path){document.getElementById('inp').value=`Phân tích file: "${d.path}"`;}
    else msg('err','Upload failed: '+(d.error||'unknown'));
  }catch(e){msg('err','Upload error: '+e);}
  input.value='';
}
function fillEx(btn){
  document.getElementById('inp').value=btn.textContent;
  document.getElementById('inp').focus();
}
document.getElementById('inp').addEventListener('keydown',e=>{
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}
});
connect();
</script>
</body>
</html>'''

# ── Routes ─────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root(): return HTML

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    safe_name = re.sub(r'[^\w\-. ]', '_', Path(file.filename).name)
    if not safe_name or safe_name.startswith('.'):
        return {"error": "Invalid filename."}
    dest = Path(FILES["UPLOAD_DIR"]) / safe_name
    if not str(dest.resolve()).startswith(str(Path(FILES["UPLOAD_DIR"]).resolve())):
        return {"error": "Path traversal detected."}
    # FIX (GPT): giới hạn 20MB — tránh crash RAM khi upload file lớn
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        return {"error": "File too large. Maximum 20MB."}
    with open(dest, "wb") as f:
        f.write(content)
    return {"path": str(dest.absolute())}

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            await handle_ws(ws, data)
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as e:
        write_log(f"WS_ERROR: {e}")
        manager.disconnect(ws)

async def handle_ws(ws: WebSocket, data: dict):
    t = data.get("type", "")

    if t == "info":
        stats = vmem.stats()
        await manager.send(ws, {
            "type": "info", "device": DEVICE, "vram": vram_gb,
            "model": MODEL_NAME,
            "vec_enabled": stats["vector_enabled"],
            "vec_entries": stats["vector_entries"],
            "json_entries": stats["json_entries"],
            "has_tts": mouth.is_available,
            "has_mic": ear.is_available,
        })

    elif t == "sysinfo":
        await manager.send(ws, {
            "type": "sysinfo",
            "cpu": f"{psutil.cpu_percent(interval=None):.0f}",
            "ram": f"{psutil.virtual_memory().percent:.0f}",
        })

    elif t == "mic_start":
        loop = asyncio.get_event_loop()
        def mic_cb(event: str, data: str):
            if event == "USER_VOICE":
                asyncio.run_coroutine_threadsafe(
                    manager.send(ws, {"type": "voice_text", "text": data}), loop
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    manager.send(ws, {"type": "sys", "text": data}), loop
                )
        ear.callback = mic_cb
        # FIX (Gemini): chạy trong executor — không block FastAPI event loop
        await loop.run_in_executor(None, ear.listen_once)

    elif t == "mem_stats":
        s = vmem.stats()
        await manager.send(ws, {"type":"mem_stats","vec":s["vector_entries"],
                                 "json":s["json_entries"],"enabled":s["vector_enabled"]})

    elif t == "clear":
        conv.clear()

    elif t == "switch_model":
        size = data.get("size", "3b")
        loop = asyncio.get_event_loop()
        asyncio.get_event_loop().run_in_executor(
            None, lambda: _switch_model(ws, size, loop)
        )

    elif t == "chat":
        msg = data.get("message", "").strip()
        if not msg: return
        if not brain:
            await manager.send(ws, {"type":"sys","text":"Demo mode — install unsloth for AI."})
            return
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: process(ws, msg, loop))


def _switch_model(ws: WebSocket, size: str, loop):
    """Load model mới, thay thế brain + executor toàn cục."""
    global model, tokenizer, brain, executor

    def send(d): asyncio.run_coroutine_threadsafe(manager.send(ws, d), loop)

    # FIX (GPT): lock tránh 2 user switch cùng lúc
    if not _model_lock.acquire(blocking=False):
        send({"type": "model_error", "text": "Another model switch in progress. Please wait."})
        return

    MODEL_3B = "unsloth/Llama-3.2-3B-Instruct-bnb-4bit"
    MODEL_8B = "unsloth/Hermes-3-Llama-3.1-8B-bnb-4bit"
    target   = MODEL_8B if size == "8b" else MODEL_3B

    write_log(f"SWITCH_MODEL: {size.upper()} → {target}")
    try:
        import gc, torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        # Unload model cũ
        if model is not None:
            del model, tokenizer
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        # Load model mới
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        new_tok = AutoTokenizer.from_pretrained(target)
        new_model = AutoModelForCausalLM.from_pretrained(
            target,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
        )
        new_model.eval()

        # Cập nhật globals
        model     = new_model
        tokenizer = new_tok
        brain     = SunnyBrain(model, tokenizer)
        executor  = PlanExecutor(brain)
        conv.clear()  # Reset conversation vì tokenizer mới

        write_log(f"SWITCH_MODEL_OK: {target}")
        send({"type": "model_switched", "model": target})

    except Exception as e:
        write_log(f"SWITCH_MODEL_ERROR: {e}")
        send({"type": "model_error", "text": str(e)})
    finally:
        _model_lock.release()


def process(ws: WebSocket, msg: str, loop):
    def send(d): asyncio.run_coroutine_threadsafe(manager.send(ws, d), loop)

    try:
        msg_lower = msg.lower()

        # ── Vector memory ─────────────────────────────────────
        mem_results = vmem.search(msg)
        memory_ctx  = vmem.format_context(mem_results)
        if mem_results:
            send({"type":"sys","text":f"🧠 {len(mem_results)} relevant memories"})

        # ── Report mode ───────────────────────────────────────
        if any(k in msg_lower for k in ["generate report","gen report","tạo báo cáo","sinh báo cáo"]):
            paths = _extract_paths(msg)
            if paths:
                send({"type":"plan","text":"Mode: Report Generation"})
                data_txt = _read_file(paths[0])
                send({"type":"tool","text":f"Read: {os.path.basename(paths[0])}"})
                send({"type":"stream_start"})
                response = brain.generate_report(data_txt, os.path.basename(paths[0]))
                saved    = ReportWriter.save(paths[0], response)
                response += f"\n\n✅ Saved: {saved}"
                for chunk in [response[i:i+60] for i in range(0,len(response),60)]:
                    send({"type":"stream_token","token":chunk})
                send({"type":"stream_end"})
                brain.save(msg, response, vmem)
                return

        # ── Planning ──────────────────────────────────────────
        send({"type":"plan","text":"Planning..."})
        plan = brain.make_plan(msg, conv.get(), memory_ctx)
        if any(s["action"] != "none" for s in plan):
            steps = " → ".join(f"[{s['action']}]" for s in plan if s["action"] != "none")
            send({"type":"plan","text":f"Plan: {steps}"})

        # ── Execute ───────────────────────────────────────────
        def status_cb(txt): send({"type":"tool","text":txt})
        tool_data = executor.run(plan, msg, conv.get(), status_cb, use_react=True)

        # ── Stream answer ─────────────────────────────────────
        send({"type":"stream_start"})
        streamer = brain.think_stream(msg, tool_data, conv.get(), memory_ctx)
        full    = ""
        buf_tts = ""   # buffer TTS mid-stream như v39
        for tok in streamer:
            full    += tok
            buf_tts += tok
            send({"type":"stream_token","token":tok})
            # Đọc từng câu khi gặp dấu kết thúc — mượt hơn đọc sau khi xong
            if mouth.is_available and any(p in tok for p in ".!?\n") and len(buf_tts) > 15:
                mouth.speak(buf_tts)
                buf_tts = ""
        # Đọc phần còn lại nếu có
        if mouth.is_available and buf_tts.strip():
            mouth.speak(buf_tts)

        conv.add("user", msg)
        conv.add("assistant", full)
        brain.save(msg, full, vmem)
        send({"type":"stream_end"})

    except Exception as e:
        write_log(f"PROCESS_ERROR: {traceback.format_exc()}")
        send({"type":"error","text":str(e)})


def _extract_paths(msg: str) -> list[str]:
    quoted = re.findall(r'["\']([^"\']+)["\']', msg)
    win    = re.findall(
        r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]+'
        r'\.(?:pdf|docx|xlsx|xls|txt|csv|md)', msg, re.IGNORECASE)
    unix   = re.findall(
        r'/(?:home|mnt|tmp|Users?|Desktop|Documents?|Downloads?)'
        r'[^\s<>"|?*\n\r]+\.(?:pdf|docx|xlsx|xls|txt|csv|md)', msg, re.IGNORECASE)
    return [p.strip().rstrip(".,;") for p in quoted+win+unix
            if os.path.exists(p.strip().rstrip(".,;"))]


# ── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\n{'='*52}")
    print(f"  ☀️  SUNNY AI v{APP_VERSION}")
    print(f"  Device : {DEVICE.upper()} | VRAM: {vram_gb:.1f}GB")
    print(f"  Model  : {MODEL_NAME.split('/')[-1]}")
    print(f"  Memory : {'FAISS' if vmem.enabled else 'JSON fallback'}")
    print(f"  Open   : http://localhost:7860")
    print(f"{'='*52}\n")
    uvicorn.run(app, host="0.0.0.0", port=7860, log_level="warning")
