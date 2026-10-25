
# Cài thư viện trước:
# pip install fastapi uvicorn TikTokLive
# Chạy: python app.py
# Mở: http://127.0.0.1:8000

import asyncio
import re
from datetime import datetime
from urllib.parse import urlparse

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from TikTokLive import TikTokLiveClient
from TikTokLive.events import ConnectEvent, EnvelopeEvent

app = FastAPI()
client = None
task = None
status = "idle"
logs = []


def log(message, kind="info"):
    logs.insert(0, {
        "message": message,
        "kind": kind,
        "time": datetime.now().strftime("%H:%M:%S")
    })
    del logs[100:]


def username_from(value):
    value = value.strip()

    if value.startswith("@"):
        name = value[1:]
    else:
        url = urlparse(
            value if "://" in value else "https://" + value
        )
        if url.hostname not in (
            "tiktok.com", "www.tiktok.com",
            "m.tiktok.com", "vm.tiktok.com",
            "vt.tiktok.com"
        ):
            raise ValueError("Link không thuộc TikTok")

        match = re.search(r"/@([\w.]+)", url.path)
        if not match:
            raise ValueError("Hãy nhập @username của chủ LIVE")
        name = match.group(1)

    if not re.fullmatch(r"[\w.]{1,30}", name):
        raise ValueError("Username không hợp lệ")

    return name


PAGE = r"""
<!DOCTYPE html>
<html lang="vi">
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TikTok Chest Scanner</title>
<style>
body{background:#090b10;color:#fff;font:15px Arial;
margin:0;padding:25px 15px}
main{max-width:430px;margin:25px auto}
h1{text-align:center;color:#25e5db;font-size:25px}
p.sub{text-align:center;color:#8993a8}
.card{background:#151824;border:1px solid #30364a;
padding:20px;border-radius:15px;margin:18px 0}
input,button{width:100%;box-sizing:border-box;padding:14px;
border-radius:9px;margin-top:12px;font-size:14px}
input{background:#0b0e16;color:white;border:1px solid #394055}
button{border:0;font-weight:bold;cursor:pointer}
.start{background:#25e5db;color:#081313}
.stop{background:#30364a;color:white}
.event{background:#0c101a;padding:12px;margin-top:10px;
border-radius:8px;overflow-wrap:anywhere;line-height:1.5}
.chest{border:1px solid #25e5db;color:#6ff8e9}
small{color:#8c96aa}
</style>
<main>
<h1>QUÉT LINK TRUNG NAM</h1>
<p class="sub">TIKTOK LIVE · CHEST SCANNER</p>
<div class="card">
<label>Link LIVE hoặc @username</label>
<input id="link" placeholder="@ten_tai_khoan">
<button class="start" onclick="startScan()">BẮT ĐẦU QUÉT</button>
<button class="stop" onclick="stopScan()">DỪNG QUÉT</button>
<p id="status">Trạng thái: Chưa kết nối</p>
</div>
<div class="card">
<b>Nhật ký sự kiện</b>
<div id="logs"><small>Chưa có sự kiện.</small></div>
</div>
<p><small>Công cụ không tự mở rương hoặc nhận thưởng.
Khả năng phát hiện tùy thuộc dữ liệu TikTok cung cấp.</small></p>
</main>
<script>
let known = new Set();
async function startScan(){
 try{
  let r=await fetch('/start',{method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({link:document.getElementById('link').value})});
  let d=await r.json();
  if(!r.ok) throw Error(d.detail);
  document.getElementById('status').textContent=d.message;
 }catch(e){document.getElementById('status').textContent=e.message}
}
async function stopScan(){
 try{
  let r=await fetch('/stop',{method:'POST'});
  let d=await r.json();
  document.getElementById('status').textContent=d.message;
 }catch(e){}
}
async function refresh(){
 try{
  let r=await fetch('/status'), d=await r.json();
  document.getElementById('status').textContent='Trạng thái: '+d.status;
  let box=document.getElementById('logs');
  box.replaceChildren();
  if(!d.logs.length){box.textContent='Chưa có sự kiện.';return}
  d.logs.slice().reverse().forEach(e=>{
   let div=document.createElement('div');
   div.className='event '+(e.kind==='chest'?'chest':'');
   div.textContent=e.time+' — '+e.message;
   box.appendChild(div);
  });
 }catch(e){}
}
setInterval(refresh,1500);
refresh();
</script>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def home():
    return PAGE


class ScanRequest(BaseModel):
    link: str


@app.get("/status")
async def get_status():
    return {"status": status, "logs": logs}


@app.post("/start")
async def start(data: ScanRequest):
    global client, task, status

    if task and not task.done():
        raise HTTPException(409, "Đang quét. Hãy dừng trước.")

    try:
        username = username_from(data.link)
    except ValueError as e:
        raise HTTPException(400, str(e))

    logs.clear()
    status = "connecting"
    log("Đang kết nối @" + username)

    client = TikTokLiveClient(unique_id=username)

    @client.on(ConnectEvent)
    async def connected(event: ConnectEvent):
        global status
        status = "connected"
        log("Đã kết nối livestream")

    @client.on(EnvelopeEvent)
    async def chest(event: EnvelopeEvent):
        log("Phát hiện sự kiện rương/phong bao! Kiểm tra TikTok LIVE.",
            "chest")

    async def run():
        global status
        try:
            await client.start()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            status = "error"
            log("Kết nối lỗi: " + str(e)[:150])
        finally:
            if status != "error":
                status = "idle"

    task = asyncio.create_task(run())
    return {"message": "Đang kết nối @" + username}


@app.post("/stop")
async def stop():
    global client, task, status

    if client:
        try:
            await client.stop()
        except Exception:
            pass

    if task and not task.done():
        task.cancel()

    client = None
    task = None
    status = "idle"
    log("Đã dừng quét")
    return {"message": "Đã dừng quét"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
