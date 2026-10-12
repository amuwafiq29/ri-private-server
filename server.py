#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Renegade Immortal 1.19 - Private Server Emulator
- HTTP API emulator (login / server_list / shop / topup gratis)
- WebSocket game server emulator (unlimited jade, free buy)
- GM panel + SQLite account DB (stdlib only, tanpa pip install)
- Mode hybrid: gameplay diteruskan ke server resmi, tapi shop/topup/currency dipaksa gratis.

Cara pakai: python server.py  (lalu buka http://127.0.0.1:8080/ )
"""
import json, os, re, sqlite3, time, hashlib, threading, socket, base64
import urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))
# HOST di config = alamat yang diiklankan ke client (di-override env PUBLIC_HOST di VPS).
# Bind selalu 0.0.0.0 supaya bisa diakses dari emulator/HP/VPS, bukan cuma localhost.
HOST = os.environ.get("PUBLIC_HOST", CFG.get("host", "127.0.0.1")).strip() or "127.0.0.1"
BIND = os.environ.get("BIND_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("PORT", os.environ.get("HTTP_PORT", CFG.get("http_port", 8080))))
WS_PORT = int(os.environ.get("WS_PORT", CFG.get("ws_port", 29601)))
WS_PUBLIC_PORT = int(os.environ.get("WS_PUBLIC_PORT", WS_PORT))
PUBLIC_SCHEME = os.environ.get("PUBLIC_SCHEME", "https" if ("." in HOST and not HOST.replace(".", "").replace(":", "").isdigit()) else "http")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE_URL", f"{PUBLIC_SCHEME}://{HOST}").rstrip("/")
DATA_DIR = os.environ.get("DATA_DIR", BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, CFG.get("db_file", "ri.db"))
JADE_NEW = int(CFG.get("jade_new_account", 999999999))
GOLD_NEW = int(CFG.get("gold_new_account", 999999999))
SILVER_NEW = int(CFG.get("silver_new_account", 999999999))
VIP_NEW = int(CFG.get("vip_level_new_account", 15))

OFFICIAL_API = CFG.get("official_api", "https://xnh5api.51haodong.com")
OFFICIAL_CDN = CFG.get("official_cdn", "https://xnh5cdn.51haodong.com/en/resource/")

# ---------------- DB ----------------
def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS accounts(
      uid TEXT PRIMARY KEY, token TEXT, jade INTEGER, gold INTEGER,
      silver INTEGER, vip INTEGER, created INTEGER, last_login INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS topups(
      id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, goods TEXT,
      jade INTEGER, ts INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS shop_log(
      id INTEGER PRIMARY KEY AUTOINCREMENT, uid TEXT, shop_id TEXT,
      count INTEGER, price INTEGER, ts INTEGER)""")
    return c

def get_or_create(uid, token=""):
    c = db()
    r = c.execute("SELECT uid,token,jade,gold,silver,vip FROM accounts WHERE uid=?", (uid,)).fetchone()
    if not r:
        now = int(time.time())
        tok = token or hashlib.md5(f"{uid}{now}".encode()).hexdigest()
        c.execute("INSERT INTO accounts(uid,token,jade,gold,silver,vip,created,last_login) VALUES(?,?,?,?,?,?,?,?)",
                  (uid, tok, JADE_NEW, GOLD_NEW, SILVER_NEW, VIP_NEW, now, now))
        c.commit()
        r = (uid, tok, JADE_NEW, GOLD_NEW, SILVER_NEW, VIP_NEW)
    else:
        # selalu pastikan kaya raya (unlimited): top-up otomatis tiap login
        c.execute("UPDATE accounts SET jade=max(jade,?), gold=max(gold,?), silver=max(silver,?), vip=max(vip,?), last_login=? WHERE uid=?",
                  (JADE_NEW, GOLD_NEW, SILVER_NEW, VIP_NEW, int(time.time()), uid))
        c.commit()
        r = c.execute("SELECT uid,token,jade,gold,silver,vip FROM accounts WHERE uid=?", (uid,)).fetchone()
    c.close()
    return {"uid": r[0], "token": r[1], "jade": r[2], "gold": r[3], "silver": r[4], "vip": r[5]}

def add_jade(uid, amount):
    c = db()
    get_or_create(uid)
    c.execute("UPDATE accounts SET jade=jade+? WHERE uid=?", (amount, uid))
    c.commit()
    r = c.execute("SELECT jade FROM accounts WHERE uid=?", (uid,)).fetchone()
    c.close()
    return r[0] if r else amount

# ---------------- HTTP ----------------
GM_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>RI Private Server - GM Panel</title>
<style>body{font-family:Consolas,monospace;background:#0d1117;color:#e6edf3;padding:24px}input,button{padding:8px;margin:4px;background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px}button{cursor:pointer}.card{border:1px solid #30363d;border-radius:10px;padding:16px;margin:12px 0;background:#161b22}a{color:#58a6ff}</style></head><body>
<h2>Renegade Immortal Private Server — GM Panel</h2>
<p>Server: <b>PRIVATE-GRATIS-1</b> | Shop: <b>GRATIS</b> | Topup: <b>GRATIS</b> | Jade akun baru: <b>999999999</b></p>
<div class="card"><h3>1) Tambah Jade</h3>
<input id="uid" placeholder="uid / nama akun" size="30"><input id="amt" placeholder="jumlah" value="999999999" size="15">
<button onclick="fetch('/gm/add_jade?uid='+encodeURIComponent(uid.value)+'&amount='+encodeURIComponent(amt.value)).then(r=>r.text()).then(t=>alert(t))">Kirim Jade</button></div>
<div class="card"><h3>2) Daftar akun</h3><button onclick="fetch('/gm/accounts').then(r=>r.text()).then(t=>document.getElementById('acc').textContent=t)">Lihat akun</button><pre id="acc"></pre></div>
<div class="card"><h3>3) Topup gratis (simulasi)</h3>
<input id="uid2" placeholder="uid" size="30"><input id="goods" placeholder="goods id, cth: jade_pack_648" size="25">
<button onclick="fetch('/gm/topup?uid='+encodeURIComponent(uid2.value)+'&goods='+encodeURIComponent(goods.value)).then(r=>r.text()).then(t=>alert(t))">Topup GRATIS</button></div>
<div class="card"><h3>4) Beli shop gratis (simulasi)</h3>
<input id="uid3" placeholder="uid" size="30"><input id="shop" placeholder="shop id" value="1001" size="12"><input id="cnt" placeholder="count" value="99" size="8">
<button onclick="fetch('/gm/buy?uid='+encodeURIComponent(uid3.value)+'&shop_id='+encodeURIComponent(shop.value)+'&count='+encodeURIComponent(cnt.value)).then(r=>r.text()).then(t=>alert(t))">Beli GRATIS</button></div>
<p>Status: <a href="/status">/status</a> | Server list: <a href="/Client/server_list">/Client/server_list</a></p>
</body></html>"""

class H(BaseHTTPRequestHandler):
    server_version = "RI-Private/1.19"
    def log_message(self, f, *a):
        print(f"[{self.client_address[0]}] {f % a}")

    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try: self.wfile.write(body)
        except Exception: pass

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        if p == "/ws" or p == "/ws/":
            return self._serve_ws_over_http()
        if p == "/" or p == "/gm":
            return self._send(200, GM_HTML, "text/html; charset=utf-8")
        if p == "/status":
            c = db(); n = c.execute("SELECT count(*) FROM accounts").fetchone()[0]; c.close()
            return self._send(200, {"ok": True, "server": CFG.get("server_name"),
                "free_shop": True, "free_topup": True, "accounts": n,
                "jade_new": JADE_NEW, "mode": CFG.get("mode"), "time": int(time.time())})
        if p == "/gm/accounts":
            c = db(); rows = c.execute("SELECT uid,jade,gold,silver,vip,last_login FROM accounts ORDER BY last_login DESC LIMIT 200").fetchall(); c.close()
            return self._send(200, [{"uid": r[0], "jade": r[1], "gold": r[2], "silver": r[3], "vip": r[4], "last": r[5]} for r in rows])
        if p == "/gm/add_jade":
            uid = q.get("uid", ["player1"])[0]; amt = int(q.get("amount", ["999999999"])[0])
            return self._send(200, {"ok": True, "uid": uid, "jade": add_jade(uid, amt)})
        if p == "/gm/topup":
            uid = q.get("uid", ["player1"])[0]; goods = q.get("goods", ["jade_pack_648"])[0]
            acc = get_or_create(uid); new = add_jade(uid, int(CFG.get("topup_gives_jade", 99999999)))
            c = db(); c.execute("INSERT INTO topups(uid,goods,jade,ts) VALUES(?,?,?,?)", (uid, goods, new, int(time.time()))); c.commit(); c.close()
            return self._send(200, {"ok": True, "msg": "topup GRATIS sukses", "uid": uid, "goods": goods, "jade": new, "price": 0})
        if p == "/gm/buy":
            uid = q.get("uid", ["player1"])[0]; shop = q.get("shop_id", ["1001"])[0]; cnt = int(q.get("count", ["1"])[0])
            acc = get_or_create(uid)
            c = db(); c.execute("INSERT INTO shop_log(uid,shop_id,count,price,ts) VALUES(?,?,?,?,?)", (uid, shop, cnt, 0, int(time.time()))); c.commit(); c.close()
            return self._send(200, {"ok": True, "msg": "beli GRATIS sukses", "uid": uid, "shop_id": shop, "count": cnt, "price": 0, "jade": acc["jade"]})
        if p.startswith("/resource/"):
            # proxy CDN resmi supaya client patch tidak perlu hosting 400MB
            target = OFFICIAL_CDN + p[len("/resource/"):]
            try:
                req = urllib.request.Request(target, headers={"User-Agent": "RI-Private"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    data = r.read()
                self.send_response(200); self.send_header("Content-Length", str(len(data)))
                ct = r.headers.get_content_type() if hasattr(r.headers, "get_content_type") else "application/octet-stream"
                self.send_header("Content-Type", ct); self.end_headers()
                try: self.wfile.write(data)
                except Exception: pass
                return
            except Exception as e:
                return self._send(502, {"ok": False, "err": f"cdn proxy gagal: {e}"})
        if p.startswith("/Client/"):
            return self._handle_client(p, q, b"")
        return self._send(404, {"ok": False, "err": "not found", "path": p})

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(ln) if ln else b""
        u = urllib.parse.urlparse(self.path)
        p, q = u.path, urllib.parse.parse_qs(u.query)
        if p.startswith("/resource/"):
            return self.do_GET()
        if p.startswith("/Client/") or "server_list" in p or "login" in p or "game_center" in p or "pay" in p or "order" in p or "charge" in p:
            return self._handle_client(p, q, body)
        if p.startswith("/gm/"):
            return self.do_GET()
        # catch-all: anggap sukses gratis (shop/buy/topup dari client)
        print(f"[CATCH-ALL] {p} body={body[:500]!r}")
        try: data = json.loads(body.decode(errors="ignore") or "{}")
        except Exception: data = {}
        uid = str(data.get("uid") or data.get("account") or q.get("uid", ["player1"])[0])
        acc = get_or_create(uid)
        return self._send(200, {"success": 1, "code": 1, "ok": True, "msg": "GRATIS (private server)",
            "price": 0, "jade": acc["jade"], "gold": acc["gold"], "vip": acc["vip"], "message": {"jade": acc["jade"]}})

    def do_OPTIONS(self):
        self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS"); self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    # ---- WebSocket di port HTTP yang sama (untuk Coolify/VPS: cukup expose 1 port) ----
    def _serve_ws_over_http(self):
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            return self._send(400, {"ok": False, "err": "gunakan client WebSocket di /ws"})
        acc = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        try:
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", acc); self.end_headers()
            conn = self.connection
            conn.settimeout(None)
            print(f"[WS-HTTP] client {self.client_address} tersambung via /ws")
            ws_send(conn, unlimited_push())
            while True:
                op, data = ws_recv(conn)
                if op == 0x8: break
                handle_ws_message(conn, data, op, self.client_address)
        except Exception as e:
            print(f"[WS-HTTP] {self.client_address} putus: {e}")
        finally:
            self.close_connection = True

    # ---- emulator endpoint /Client/* ----
    def _handle_client(self, p, q, body):
        raw = body.decode(errors="ignore") if body else ""
        params = {}
        try:
            if raw and "=" in raw and raw.strip()[0] != "{":
                params = dict(urllib.parse.parse_qsl(raw))
            elif raw:
                params = json.loads(raw)
        except Exception: pass
        for k, v in q.items(): params.setdefault(k, v[0] if v else "")
        print(f"[API] {p} params={str(params)[:400]}")
        account = str(params.get("account") or params.get("uid") or params.get("userid") or "player1")
        acc = get_or_create(account)
        if "server_list" in p:
            srv = {"socket": HOST, "ip": HOST, "host": HOST,
                   "port": WS_PUBLIC_PORT, "port2": WS_PUBLIC_PORT, "status": 1, "open_time": 0,
                   "recomed": 1, "isnew": 1, "is_maintain": 0, "zone_id": CFG.get("server_zone_id", 1),
                   "zone_name": CFG.get("server_name", "PRIVATE-GRATIS-1"),
                   "platform": "private", "roles": [],
                   "ws_url": f"{'wss' if PUBLIC_SCHEME == 'https' else 'ws'}://{HOST}/ws"}
            return self._send(200, {"success": 1, "code": 1, "error_msg": "",
                "message": {"server_list": [srv], "recom_server": srv, "new_server": srv,
                            "notice": "Private server: semua GRATIS, jade unlimited."}})
        if "web_login_check" in p:
            return self._send(200, {"code": 1, "success": 1,
                "message": {"account": account, "token": acc["token"], "uid": account,
                            "jade": acc["jade"], "gold": acc["gold"], "vip": acc["vip"]},
                "account": account, "token": acc["token"], "uid": account})
        if "game_center" in p:
            return self._send(200, {"success": 1, "code": 1, "message": {"status": 1, "gift": [{"id": 1, "jade": JADE_NEW}]}})
        # pay / order / recharge / verify -> selalu sukses Rp0
        if any(k in p for k in ["pay", "order", "charge", "recharge", "verify", "buy", "shop", "goods"]):
            new = add_jade(account, int(CFG.get("topup_gives_jade", 99999999)))
            c = db(); c.execute("INSERT INTO topups(uid,goods,jade,ts) VALUES(?,?,?,?)", (account, p, new, int(time.time()))); c.commit(); c.close()
            return self._send(200, {"success": 1, "code": 1, "ok": True, "msg": "Topup GRATIS sukses",
                "price": 0, "pay_status": 1, "jade": new, "gold": acc["gold"],
                "message": {"pay_status": 1, "jade": new, "price": 0}})
        return self._send(200, {"success": 1, "code": 1, "message": {"jade": acc["jade"], "gold": acc["gold"], "vip": acc["vip"]}})

# ---------------- WebSocket (RFC6455 minimal, stdlib) ----------------
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
def ws_handshake(conn, req):
    h = {}
    for line in req.split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1); h[k.strip().lower()] = v.strip()
    key = h.get("sec-websocket-key", "")
    acc = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
    conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Accept: {acc}\r\n\r\n").encode())

def ws_send(conn, payload: bytes, opcode=0x1):
    ln = len(payload); hdr = bytes([0x80 | opcode])
    if ln < 126: hdr += bytes([ln])
    elif ln < 65536: hdr += bytes([126]) + ln.to_bytes(2, "big")
    else: hdr += bytes([127]) + ln.to_bytes(8, "big")
    conn.sendall(hdr + payload)

def ws_recv(conn):
    h = conn.recv(2)
    if len(h) < 2: raise ConnectionError("closed")
    mask = (h[1] & 0x80) != 0; ln = h[1] & 0x7F
    if ln == 126: ln = int.from_bytes(conn.recv(2), "big")
    elif ln == 127: ln = int.from_bytes(conn.recv(8), "big")
    mk = conn.recv(4) if mask else b""
    data = b""
    while len(data) < ln:
        ch = conn.recv(ln - len(data))
        if not ch: break
        data += ch
    if mask: data = bytes(b ^ mk[i % 4] for i, b in enumerate(data))
    return (h[0] & 0x0F), data

def unlimited_push():
    return json.dumps({"cmd": "role_update", "jade": JADE_NEW, "gold": GOLD_NEW,
        "silver": SILVER_NEW, "vip": VIP_NEW, "msg": "PRIVATE SERVER: unlimited",
        "SCMD_18000": {"jade": JADE_NEW}, "price": 0}).encode()

def handle_ws_message(conn, data, op, addr):
    txt = ""
    try: txt = data.decode(errors="ignore")
    except Exception: pass
    print(f"[WS {addr}] opcode={op} len={len(data)} data={txt[:400]!r} hex={data[:64].hex()}")
    # heuristik: jika paket berisi kata shop/buy/pay/recharge/goods -> balas sukses gratis
    low = txt.lower()
    if any(k in low for k in ["buy", "shop", "pay", "recharge", "charge", "goods", "order", "jade", "yuanbao"]):
        # paksa harga 0: ganti angka price jadi 0 di echo
        mod = re.sub(r'"price"\s*:\s*\d+', '"price":0', txt) or txt
        resp = json.dumps({"success": 1, "code": 1, "ok": True, "price": 0,
            "msg": "GRATIS (private)", "jade": JADE_NEW, "echo": mod[:500]}).encode()
        ws_send(conn, resp)
        ws_send(conn, unlimited_push())
    elif txt.strip().startswith("{"):
        # JSON umum: echo sukses + unlimited
        try:
            o = json.loads(txt)
            uid = str(o.get("uid") or o.get("account") or "player1")
            acc = get_or_create(uid)
            ws_send(conn, json.dumps({"success": 1, "ok": True, "price": 0,
                "jade": acc["jade"], "gold": acc["gold"], "vip": acc["vip"], "echo_cmd": o.get("cmd")}).encode())
        except Exception:
            ws_send(conn, unlimited_push())
    else:
        # biner (protokol SCMD game): balas dengan push unlimited agar client tidak stuck,
        # plus log untuk reverse engineering lanjutan (lihat console)
        ws_send(conn, unlimited_push())

def handle_ws(conn, addr):
    try:
        req = conn.recv(4096).decode(errors="ignore")
        if "Upgrade" not in req and "upgrade" not in req:
            conn.close(); return
        ws_handshake(conn, req)
        print(f"[WS] client {addr} tersambung (private server, jade unlimited)")
        ws_send(conn, unlimited_push())
        while True:
            op, data = ws_recv(conn)
            if op == 0x8: break
            handle_ws_message(conn, data, op, addr)
    except Exception as e:
        print(f"[WS] {addr} putus: {e}")
    finally:
        try: conn.close()
        except Exception: pass

def ws_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((BIND, WS_PORT)); s.listen(50)
    print(f"[WS] game server jalan di {BIND}:{WS_PORT} (Egret WS, unlimited jade)")
    while True:
        c, a = s.accept()
        threading.Thread(target=handle_ws, args=(c, a), daemon=True).start()

def main():
    db().close()
    print("=" * 60)
    print(" Renegade Immortal 1.19 — PRIVATE SERVER (semua GRATIS)")
    print(f" HTTP API : http://{BIND}:{HTTP_PORT}/  (GM panel + /Client/* + /resource/ + /ws)")
    print(f" URL publik: {PUBLIC_BASE}/  (iklan ke client: {HOST})")
    print(f" WS GAME  : ws://{BIND}:{WS_PORT} + {PUBLIC_BASE.replace('http', 'ws')}/ws")
    print(f" Akun baru otomatis dapat jade={JADE_NEW}, gold={GOLD_NEW}, vip={VIP_NEW}")
    print(" Patch client: jalankan build_apk.py --host DOMAIN-VPS, atau patch_client.py (LAN),")
    print("  atau di emulator ubah hosts: xnh5api.51haodong.com -> IP server")
    print("=" * 60)
    threading.Thread(target=ws_loop, daemon=True).start()
    srv = ThreadingHTTPServer((BIND, HTTP_PORT), H)
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nBerhenti.")

if __name__ == "__main__":
    main()
