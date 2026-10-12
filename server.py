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
import json, os, re, sqlite3, struct, time, hashlib, threading, socket, base64
import urllib.request, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(BASE, "config.json"), encoding="utf-8"))
try:
    PROTO_SEND = {int(k): v for k, v in json.load(
        open(os.path.join(BASE, "proto_send.json"), encoding="utf-8")).items()}
    PROTO_RECV = {int(k): v for k, v in json.load(
        open(os.path.join(BASE, "proto_recv.json"), encoding="utf-8")).items()}
except Exception as e:
    print(f"[PROTO] tabel tidak termuat: {e}")
    PROTO_SEND, PROTO_RECV = {}, {}
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
RESOURCE_DIR = os.environ.get("RESOURCE_DIR", os.path.join(DATA_DIR, "game_resource"))

_MIME = {".json": "application/json", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".dbbin": "application/octet-stream",
         ".fnt": "text/plain", ".ogg": "audio/ogg", ".m4a": "audio/mp4",
         ".mp3": "audio/mpeg", ".txt": "text/plain", ".sk": "application/octet-stream"}

def mime_for(name):
    return _MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream")

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
    c.execute("""CREATE TABLE IF NOT EXISTS roles(
      uid TEXT PRIMARY KEY, rid INTEGER, name TEXT, career INTEGER,
      sex INTEGER, lev INTEGER, reg_time INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS heroes(
      uid TEXT, hid INTEGER, base_id INTEGER, lev INTEGER, star INTEGER,
      PRIMARY KEY (uid, hid))""")
    c.execute("""CREATE TABLE IF NOT EXISTS items(
      uid TEXT, iid INTEGER, pos INTEGER, base_id INTEGER, bind INTEGER,
      quantity INTEGER, lev INTEGER, color INTEGER,
      PRIMARY KEY (uid, iid))""")
    c.execute("""CREATE TABLE IF NOT EXISTS mails(
      uid TEXT, mid INTEGER, subject TEXT, content TEXT, status INTEGER,
      items_json TEXT, PRIMARY KEY (uid, mid))""")
    c.execute("""CREATE TABLE IF NOT EXISTS formations(
      uid TEXT PRIMARY KEY, data_json TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS hangup(
      uid TEXT PRIMARY KEY, cur_id INTEGER, last_time INTEGER)""")
    return c

# Starter Team resmi (hero_data group 13 key 1) + item_data base_id asli
STARTER_HEROES = [
    (104070, "Teng Huayuan", 1, 1, 5),
    (204030, "Zhou Yi", 2, 1, 5),
    (204070, "Feng Luan", 2, 1, 5),
    (104020, "Six Desires", 1, 4, 5),
    (204060, "Zhou Yun", 2, 2, 5),
    (204050, "Mo Zhi", 2, 3, 5),
]
STARTER_ITEMS = [  # (base_id, quantity, color)
    (1, 1000, 3), (4, 1000, 3), (1000050, 100, 4), (1000080, 20, 4),
]
WELCOME_GIFT = [(1000080, 10), (1000050, 50)]

def get_heroes(uid):
    c = db()
    rows = c.execute("SELECT hid,base_id,lev,star FROM heroes WHERE uid=? ORDER BY hid", (uid,)).fetchall()
    c.close()
    names = {b: n for b, n, _, _, _ in STARTER_HEROES}
    out = []
    for hid, base, lev, star in rows:
        info = next((h for h in STARTER_HEROES if h[0] == base), (base, f"Hero-{base}", 1, 1, star))
        out.append({"id": hid, "base_id": base, "realm": info[2], "career": info[3],
                    "name": info[1], "lev": lev, "stage": 0, "star": star,
                    "fc": 5000, "hp": 8000, "hp_max": 8000, "skin_id": 0, "wake_lev": 0})
    return out

def get_hangup(uid):
    c = db()
    r = c.execute("SELECT cur_id,last_time FROM hangup WHERE uid=?", (uid,)).fetchone()
    if not r:
        now = int(time.time())
        c.execute("INSERT INTO hangup(uid,cur_id,last_time) VALUES(?,?,?)", (uid, 1, now))
        c.commit()
        r = (1, now)
    c.close()
    return {"cur_id": r[0], "last_time": r[1]}

def set_hangup(uid, cur_id):
    c = db()
    c.execute("INSERT OR REPLACE INTO hangup(uid,cur_id,last_time) VALUES(?,?,?)",
              (uid, cur_id, int(time.time())))
    c.commit()
    c.close()

def level_up(uid, n=1):
    c = db()
    r = c.execute("SELECT lev FROM roles WHERE uid=?", (uid,)).fetchone()
    if not r:
        now = int(time.time())
        c.execute("INSERT INTO roles(uid,rid,name,career,sex,lev,reg_time) VALUES(?,?,?,?,?,?,?)",
                  (uid, 100001, "Hero", 1, 1, 1 + n, now))
        c.commit()
        c.close()
        return 1 + n
    c.execute("UPDATE roles SET lev=lev+? WHERE uid=?", (n, uid))
    r = c.execute("SELECT lev FROM roles WHERE uid=?", (uid,)).fetchone()
    c.commit()
    c.close()
    return r[0] if r else 1

def get_bag(uid):
    c = db()
    rows = c.execute("SELECT iid,pos,base_id,bind,quantity,lev,color FROM items WHERE uid=? ORDER BY pos", (uid,)).fetchall()
    c.close()
    return [{"id": r[0], "old_id": 0, "pos": r[1], "base_id": r[2], "bind": r[3],
             "quantity": r[4], "lev": r[5], "color": r[6], "exattr": [], "attr": []} for r in rows]

def bag_add(uid, base_id, quantity, bind=1, color=3):
    c = db()
    r = c.execute("SELECT iid,quantity,pos FROM items WHERE uid=? AND base_id=? AND bind=?",
                  (uid, base_id, bind)).fetchone()
    if r:
        c.execute("UPDATE items SET quantity=quantity+? WHERE uid=? AND iid=?", (quantity, uid, r[0]))
        iid, pos = r[0], r[2]
    else:
        mx = c.execute("SELECT max(iid),max(pos) FROM items WHERE uid=?", (uid,)).fetchone()
        iid, pos = (mx[0] or 0) + 1, (mx[1] or 0) + 1
        c.execute("INSERT INTO items(uid,iid,pos,base_id,bind,quantity,lev,color) VALUES(?,?,?,?,?,?,?,?)",
                  (uid, iid, pos, base_id, bind, quantity, 1, color))
    c.commit()
    c.close()
    return {"id": iid, "pos": pos, "base_id": base_id, "bind": bind,
            "quantity": (r[1] + quantity) if r else quantity, "lev": 1, "color": color,
            "exattr": [], "attr": []}

def grant_starter(uid):
    c = db()
    has = c.execute("SELECT count(*) FROM heroes WHERE uid=?", (uid,)).fetchone()[0]
    if has:
        c.close()
        return False
    for i, (base, _n, _r, _c, star) in enumerate(STARTER_HEROES, start=1):
        c.execute("INSERT INTO heroes(uid,hid,base_id,lev,star) VALUES(?,?,?,?,?)",
                  (uid, i, base, 1, star))
    for pos, (base, qty, color) in enumerate(STARTER_ITEMS, start=1):
        c.execute("INSERT INTO items(uid,iid,pos,base_id,bind,quantity,lev,color) VALUES(?,?,?,?,?,?,?,?)",
                  (uid, pos, pos, base, 1, qty, 1, color))
    c.execute("INSERT OR IGNORE INTO mails(uid,mid,subject,content,status,items_json) VALUES(?,?,?,?,?,?)",
              (uid, 1, "Welcome to GRATIS-1",
               "Welcome, Cultivator! Everything here is FREE: shop, top-up, summons. Claim the gift below and enjoy unlimited jade!",
               0, json.dumps([{"base_id": b, "bind": 1, "quantity": q, "exattr": []} for b, q in WELCOME_GIFT])))
    c.execute("INSERT OR IGNORE INTO formations(uid,data_json) VALUES(?,?)",
              (uid, json.dumps([{"type": 0, "pos_list": [{"pos": i, "id": i} for i in range(1, 7)], "counter_id": 0}])))
    c.commit()
    c.close()
    return True

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

def get_role(uid):
    c = db()
    r = c.execute("SELECT rid,name,career,sex,lev,reg_time FROM roles WHERE uid=?", (uid,)).fetchone()
    c.close()
    if not r:
        return None
    return {"rid": r[0], "name": r[1], "career": r[2], "sex": r[3], "lev": r[4], "reg_time": r[5]}

def create_role(uid, name, career, sex):
    c = db()
    mx = c.execute("SELECT max(rid) FROM roles").fetchone()[0] or 100000
    rid, now = mx + 1, int(time.time())
    c.execute("INSERT OR REPLACE INTO roles(uid,rid,name,career,sex,lev,reg_time) VALUES(?,?,?,?,?,?,?)",
              (uid, rid, name, career, sex, 1, now))
    c.commit()
    c.close()
    return {"rid": rid, "name": name, "career": career, "sex": sex, "lev": 1, "reg_time": now}

# ---------------- Protokol game biner (Egret, little-endian) ----------------
# framing: uint32LE total(=payload+2) + uint16LE cmd + payload
def _enc_val(t, v, buf):
    if t in ("int8", "byte"):
        buf += struct.pack("b", int(v))
    elif t == "uint8":
        buf += struct.pack("B", int(v))
    elif t == "int16":
        buf += struct.pack("<h", int(v))
    elif t == "uint16":
        buf += struct.pack("<H", int(v))
    elif t == "int32":
        buf += struct.pack("<i", int(v))
    elif t == "uint32":
        buf += struct.pack("<I", int(v) & 0xFFFFFFFF)
    elif t == "int64":
        v = int(v) & 0xFFFFFFFFFFFFFFFF
        buf += struct.pack("<II", v & 0xFFFFFFFF, (v >> 32) & 0xFFFFFFFF)
    elif t == "string":
        b = str(v).encode("utf-8")[:65500]
        buf += struct.pack("<H", len(b)) + b
    elif t == "array":
        raise ValueError("array perlu fields")
    else:
        raise ValueError(f"tipe tak dikenal: {t}")
    return buf

def proto_encode(schema, obj):
    buf = bytearray()
    for f in schema:
        v = obj.get(f["name"])
        if f["type"] == "array":
            items = v or []
            buf += struct.pack("<h", len(items))
            for it in items:
                sub = proto_encode(f["fields"], it)
                buf += sub
        else:
            if v is None:
                v = 0 if f["type"] != "string" else ""
            buf = _enc_val(f["type"], v, buf)
    return bytes(buf)

class _R:
    def __init__(self, data):
        self.d, self.p = data, 0
    def take(self, n):
        if self.p + n > len(self.d):
            raise ValueError("paket pendek")
        b = self.d[self.p:self.p + n]
        self.p += n
        return b

def proto_decode(schema, data):
    r, out = _R(data), {}
    for f in schema:
        t = f["type"]
        if t in ("int8", "byte"):
            out[f["name"]] = struct.unpack("b", r.take(1))[0]
        elif t == "uint8":
            out[f["name"]] = struct.unpack("B", r.take(1))[0]
        elif t == "int16":
            out[f["name"]] = struct.unpack("<h", r.take(2))[0]
        elif t == "uint16":
            out[f["name"]] = struct.unpack("<H", r.take(2))[0]
        elif t == "int32":
            out[f["name"]] = struct.unpack("<i", r.take(4))[0]
        elif t == "uint32":
            out[f["name"]] = struct.unpack("<I", r.take(4))[0]
        elif t == "int64":
            lo, hi = struct.unpack("<II", r.take(8))
            v = lo | (hi << 32)
            out[f["name"]] = v - (1 << 64) if hi >= 0x80000000 else v
        elif t == "string":
            ln = struct.unpack("<H", r.take(2))[0]
            out[f["name"]] = r.take(ln).decode("utf-8", errors="replace")
        elif t == "array":
            n = struct.unpack("<h", r.take(2))[0]
            arr = []
            for _ in range(max(0, n)):
                sub, r.p = _decode_at(f["fields"], r.d, r.p)
                arr.append(sub)
            out[f["name"]] = arr
    return out

def _decode_at(schema, data, pos):
    r = _R(data)
    r.p = pos
    out = {}
    for f in schema:
        t = f["type"]
        if t in ("int8", "byte"):
            out[f["name"]] = struct.unpack("b", r.take(1))[0]
        elif t == "uint8":
            out[f["name"]] = struct.unpack("B", r.take(1))[0]
        elif t == "int16":
            out[f["name"]] = struct.unpack("<h", r.take(2))[0]
        elif t == "uint16":
            out[f["name"]] = struct.unpack("<H", r.take(2))[0]
        elif t == "int32":
            out[f["name"]] = struct.unpack("<i", r.take(4))[0]
        elif t == "uint32":
            out[f["name"]] = struct.unpack("<I", r.take(4))[0]
        elif t == "int64":
            lo, hi = struct.unpack("<II", r.take(8))
            v = lo | (hi << 32)
            out[f["name"]] = v - (1 << 64) if hi >= 0x80000000 else v
        elif t == "string":
            ln = struct.unpack("<H", r.take(2))[0]
            out[f["name"]] = r.take(ln).decode("utf-8", errors="replace")
        elif t == "array":
            n = struct.unpack("<h", r.take(2))[0]
            arr = []
            for _ in range(max(0, n)):
                sub, r.p = _decode_at(f["fields"], r.d, r.p)
                arr.append(sub)
            out[f["name"]] = arr
    return out, r.p

def game_frame(cmd, payload: bytes) -> bytes:
    return struct.pack("<IH", len(payload) + 2, cmd) + payload

def zero_obj(schema):
    o = {}
    for f in schema:
        if f["type"] == "array":
            o[f["name"]] = []
        elif f["type"] == "string":
            o[f["name"]] = ""
        else:
            o[f["name"]] = 0
    return o

SUCCESS_FIELDS = {"code", "res", "result", "success", "status"}

def role_info_obj(uid):
    acc = get_or_create(uid)
    r = get_role(uid) or {"rid": 100001, "name": "Hero", "career": 1, "sex": 1, "lev": 1, "reg_time": int(time.time())}
    now = int(time.time())
    base = {"rid": r["rid"], "name": r["name"], "zone_aid": 1, "zone_id": 1,
            "reg_pf": "private", "career": r["career"], "realm": 1, "lev": r["lev"],
            "sex": r["sex"], "map_id": 0, "map_base_id": 0, "xpos": 0, "ypos": 0,
            "gold": acc["gold"], "gold_bind": acc["gold"], "coin": 999999999,
            "coin_bind": 999999999, "charge": 0, "money": 999999999,
            "exp": 0, "exp_max": 100, "vip_lev": acc["vip"], "vip_exp": 999999,
            "guild_name": "", "guild_id": 0, "guild_job": 0, "guild_iden_name": "",
            "every_day_charge": 0, "energy": 9999, "hero_soul": 999999,
            "prestige": 999999, "exploit": 999999, "explore": 999999,
            "contribution": 999999, "hero_exp": 0, "travel": 0, "artifact_soul": 999999,
            "strategy": 0, "jade": acc["jade"], "call_score": 0, "call_score_max": 0,
            "fc": 999999, "looks": [], "rename_cnt": 99, "province": "", "city": "",
            "secret": 0, "devote_score": 0, "reg_time": r["reg_time"]}
    if 12011 in PROTO_RECV:
        full = zero_obj(PROTO_RECV[12011])
        full.update({k: v for k, v in base.items() if k in full})
        return full
    return base

def handle_game_packet(cmd, payload, sess):
    """Kembalikan list bytes paket balasan (sudah di-frame)."""
    out = []
    def reply(rcmd, obj):
        schema = PROTO_RECV.get(rcmd, [])
        full = zero_obj(schema)
        full.update({k: v for k, v in obj.items() if k in full})
        pkt = game_frame(rcmd, proto_encode(schema, full))
        print(f"[GAME] -> R{rcmd} len={len(pkt)} hex={pkt[:48].hex()}")
        out.append(pkt)
    try:
        schema = PROTO_SEND.get(cmd)
        data = proto_decode(schema, payload) if schema else {"_raw": payload[:64].hex()}
    except Exception as e:
        print(f"[GAME] cmd {cmd}: decode gagal: {e} hex={payload[:96].hex()}")
        return out
    brief = {k: (str(v)[:40]) for k, v in data.items() if not k.startswith("_")}
    print(f"[GAME] C{cmd} {brief}")
    now = int(time.time())
    if cmd == 10000:  # login
        uid = str(data.get("account") or "player1")
        sess["uid"] = uid
        get_or_create(uid)
        r = get_role(uid)
        roles = [{"rid": r["rid"], "name": r["name"], "career": r["career"],
                  "sex": r["sex"], "lev": r["lev"], "reg_time": r["reg_time"]}] if r else []
        reply(10000, {"code": 1, "msg": "", "roles": roles, "version": "1.0.81"})
    elif cmd == 10002:  # daftar role
        uid = sess.get("uid", "player1")
        r = get_role(uid)
        lst = [{"role_id": r["rid"], "role_name": r["name"], "career": r["career"],
                "sex": r["sex"], "lev": r["lev"]}] if r else []
        reply(10002, {"role_list": lst})
    elif cmd == 10004:  # buat role
        uid = sess.get("uid", "player1")
        r = create_role(uid, str(data.get("name") or "Hero"),
                        int(data.get("career") or 1), int(data.get("sex") or 1))
        acc = get_or_create(uid)
        reply(10004, {"code": 1, "id": r["rid"], "msg": "", "name": r["name"],
                      "pf": "private", "zone_id": 1, "sex": r["sex"], "lev": 1,
                      "vip_lev": acc["vip"], "gold": acc["gold"], "time": now,
                      "source_share_rid": 0})
    elif cmd == 10006:  # masuk game
        reply(10006, {"code": 1, "msg": "", "timestamp": now, "world_lev": 1, "evolve_flag": 0})
        uid = sess.get("uid", "player1")
        grant_starter(uid)
        reply(12011, role_info_obj(uid))  # info role + jade unlimited
        heroes = get_heroes(uid)
        reply(11076, {"hero_list": heroes, "select_hero_id": heroes[0]["id"] if heroes else 0})
        reply(12260, {"transform_list": [{"base_id": h["base_id"], "star": h["star"],
                                          "skin_active": 0, "hero_id": h["id"]} for h in heroes]})
    elif cmd == 10007:  # re-enter
        reply(10007, {"code": 1, "msg": "", "timestamp": now, "world_lev": 1, "evolve_flag": 0})
    elif cmd == 10008:
        reply(10008, {"res": 1})
    elif cmd == 10010:
        reply(10010, {"now": now})
    elif cmd == 10012:
        reply(10012, {"now": now, "open_time": now})
    elif cmd == 17000:  # tas
        uid = sess.get("uid", "player1")
        reply(17000, {"storagetype": int(data.get("storagetype") or 0),
                      "volume": 500, "items": get_bag(uid)})
    elif cmd == 16000:  # mail list
        uid = sess.get("uid", "player1")
        c = db()
        rows = c.execute("SELECT mid,subject,content,status,items_json FROM mails WHERE uid=? ORDER BY mid", (uid,)).fetchall()
        c.close()
        mails = []
        for mid, subj, cont, st, ijs in rows:
            try:
                items = json.loads(ijs or "[]")
            except Exception:
                items = []
            mails.append({"id": mid, "send_time": now - 60, "from_rid": 0,
                          "from_name": "GRATIS-1", "to_rid": 0, "to_name": "",
                          "status": st, "subject": subj, "content": cont,
                          "assets": [], "items": items})
        reply(16000, {"sign": 1, "mails": mails})
    elif cmd == 16001:  # baca mail
        uid = sess.get("uid", "player1")
        ids = [int(x["id"]) for x in (data.get("ids") or [])]
        if ids:
            c = db()
            c.execute(f"UPDATE mails SET status=1 WHERE uid=? AND mid IN ({','.join('?'*len(ids))})",
                      [uid] + ids)
            c.commit()
            c.close()
        reply(16001, {"code": 1})
    elif cmd == 16002:  # klaim mail
        uid = sess.get("uid", "player1")
        ids = [int(x["id"]) for x in (data.get("ids") or [])]
        gained = []
        c = db()
        for (mid,) in [(i,) for i in ids]:
            r = c.execute("SELECT status,items_json FROM mails WHERE uid=? AND mid=?", (uid, mid)).fetchone()
            if r and r[0] != 2:
                try:
                    items = json.loads(r[1] or "[]")
                except Exception:
                    items = []
                for it in items:
                    gained.append(bag_add(uid, int(it.get("base_id", 0)),
                                          int(it.get("quantity", 0)), int(it.get("bind", 1))))
                c.execute("UPDATE mails SET status=2 WHERE uid=? AND mid=?", (uid, mid))
        c.commit()
        c.close()
        reply(16002, {"code": 1})
        if gained:
            reply(17001, {"notice": 1, "storagetype": 0, "items": gained})
    elif cmd == 11046:  # daftar hero
        uid = sess.get("uid", "player1")
        reply(11046, {"type": int(data.get("type") or 0), "hero_list": get_heroes(uid)})
    elif cmd == 11077:  # hero per grid
        uid = sess.get("uid", "player1")
        reply(11077, {"grid_id": int(data.get("grid_id") or 0), "hero_list": get_heroes(uid)})
    elif cmd == 11004:  # dungeon harian: type harus echo (config client keyed by type)
        reply(11004, {"type": int(data.get("type") or 1), "dungeon_list": [],
                      "his_list": [], "enter_count": 99, "buy_count": 0,
                      "total_buy_count": 99, "today_pass": 0,
                      "max_pass_dungoen_id": 0})
    elif cmd == 12260:  # transform list
        uid = sess.get("uid", "player1")
        heroes = get_heroes(uid)
        reply(12260, {"transform_list": [{"base_id": h["base_id"], "star": h["star"],
                                          "skin_active": 0, "hero_id": h["id"]} for h in heroes]})
        uid = sess.get("uid", "player1")
        heroes = get_heroes(uid)
        reply(12260, {"transform_list": [{"base_id": h["base_id"], "star": h["star"],
                                          "skin_active": 0, "hero_id": h["id"]} for h in heroes]})
    elif cmd == 32804:  # load formasi
        uid = sess.get("uid", "player1")
        c = db()
        r = c.execute("SELECT data_json FROM formations WHERE uid=?", (uid,)).fetchone()
        c.close()
        try:
            fl = json.loads(r[0]) if r else []
        except Exception:
            fl = []
        reply(32804, {"formation_list": fl})
    elif cmd == 32803:  # simpan formasi
        uid = sess.get("uid", "player1")
        fl = data.get("formation_list") or []
        c = db()
        c.execute("INSERT OR REPLACE INTO formations(uid,data_json) VALUES(?,?)",
                  (uid, json.dumps(fl)))
        c.commit()
        c.close()
        reply(32803, {"res": 1, "msg": "", "action": int(data.get("action") or 0),
                      "my_signup": 0, "formation_list": fl})
    elif cmd == 14101:  # info hangup/dream path: cur stage valid biar map render
        uid = sess.get("uid", "player1")
        hg = get_hangup(uid)
        reply(14101, {"cur_id": hg["cur_id"], "reward_ids": [], "last_time": hg["last_time"],
                      "max_minute": 480, "left_free_count": 5, "left_buy_count": 5,
                      "is_active": 1, "next_cost": 0,
                      "chapter_ids": [{"chapter_id": 1}], "need_to_active": 0,
                      "pass_all": 0, "is_activity_open": 1, "reward_all": 0,
                      "ids": [], "show_new_task": 0})
    elif cmd == 14102:  # challenge stage: selalu menang, maju + naik level
        uid = sess.get("uid", "player1")
        hg = get_hangup(uid)
        new_id = hg["cur_id"] + 1
        set_hangup(uid, new_id)
        level_up(uid, 1)
        gained = [bag_add(uid, 1, 200), bag_add(uid, 4, 2000), bag_add(uid, 1000080, 3)]
        add_jade(uid, 50)
        reply(14102, {"res": 1, "msg": "", "next_id": new_id, "pass_all": 0})
        drops = [{"base_id": 1, "bind": 1, "num": 200},
                 {"base_id": 4, "bind": 1, "num": 2000},
                 {"base_id": 1000080, "bind": 1, "num": 3}]
        reply(14106, {"list": drops, "res": 1, "type": 0})
        reply(17001, {"notice": 1, "storagetype": 0, "items": gained})
        reply(12011, role_info_obj(uid))
        hg2 = get_hangup(uid)
        reply(14101, {"cur_id": hg2["cur_id"], "reward_ids": [], "last_time": hg2["last_time"],
                      "max_minute": 480, "left_free_count": 5, "left_buy_count": 5,
                      "is_active": 1, "next_cost": 0,
                      "chapter_ids": [{"chapter_id": 1}], "need_to_active": 0,
                      "pass_all": 0, "is_activity_open": 1, "reward_all": 0,
                      "ids": [], "show_new_task": 0})
    elif cmd == 14103:  # klaim AFK
        uid = sess.get("uid", "player1")
        gained = [bag_add(uid, 1, 200), bag_add(uid, 4, 500)]
        reply(14103, {"res": 1, "msg": "", "last_time": int(time.time())})
        reply(14106, {"list": [{"base_id": 1, "bind": 1, "num": 200},
                               {"base_id": 4, "bind": 1, "num": 500}],
                      "res": 1, "type": 0})
        reply(17001, {"notice": 1, "storagetype": 0, "items": gained})
        c = db()
        c.execute("UPDATE hangup SET last_time=? WHERE uid=?", (int(time.time()), uid))
        c.commit()
        c.close()
    elif cmd == 14104:  # klaim reward stage
        reply(14104, {"res": 1, "msg": "", "id": int(data.get("id") or 0), "reward_all": 0})
    elif cmd == 14108:  # challenge chapter
        uid = sess.get("uid", "player1")
        hg = get_hangup(uid)
        reply(14108, {"res": 1, "msg": "", "chapter_id": int(data.get("chapter_id") or 1),
                      "next_id": hg["cur_id"]})
    else:
        rschema = PROTO_RECV.get(cmd)
        if rschema is not None:
            obj = zero_obj(rschema)
            req = data if isinstance(data, dict) else {}
            for f in rschema:
                if f["name"] in SUCCESS_FIELDS and f["type"] in ("int8", "uint8", "int16", "uint16", "int32", "uint32"):
                    obj[f["name"]] = 1
                elif f["name"] in req and not isinstance(req[f["name"]], (dict, list)):
                    try:  # echo field request -> balasan (id/type/grid/dll)
                        obj[f["name"]] = type(obj[f["name"]])(req[f["name"]])
                    except Exception:
                        pass
            if "now" in obj:
                obj["now"] = now
            if "timestamp" in obj:
                obj["timestamp"] = now
            if "open_time" in obj and not obj["open_time"]:
                obj["open_time"] = now
            out.append(game_frame(cmd, proto_encode(rschema, obj)))
            print(f"[GAME] C{cmd}: balasan generik (auto-nol)")
        else:
            print(f"[GAME] C{cmd}: tanpa skema, diabaikan")
    return out

# ---------------- HTTP ----------------
GM_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>RI Private Server - GM Panel</title>
<style>body{font-family:Consolas,monospace;background:#0d1117;color:#e6edf3;padding:24px}input,button{padding:8px;margin:4px;background:#161b22;color:#e6edf3;border:1px solid #30363d;border-radius:6px}button{cursor:pointer}.card{border:1px solid #30363d;border-radius:10px;padding:16px;margin:12px 0;background:#161b22}a{color:#58a6ff}</style></head><body>
<h2>Renegade Immortal Private Server — GM Panel</h2>
<p>Server: <b>GRATIS-1</b> | Shop: <b>GRATIS</b> | Topup: <b>GRATIS</b> | Jade akun baru: <b>999999999</b></p>
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
<div class="card"><h3>5) Set level role (buka fitur terkunci level)</h3>
<input id="uid4" placeholder="uid" size="30"><input id="lev" placeholder="level" value="55" size="8">
<button onclick="fetch('/gm/set_level?uid='+encodeURIComponent(uid4.value)+'&lev='+encodeURIComponent(lev.value)).then(r=>r.text()).then(t=>alert(t))">Set Level</button></div>
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
        if p == "/gm/set_level":
            uid = q.get("uid", ["player1"])[0]; lev = int(q.get("lev", ["50"])[0])
            r = get_role(uid)
            if not r:
                return self._send(200, {"ok": False, "err": "role belum ada (masuk game dulu)"})
            c = db(); c.execute("UPDATE roles SET lev=? WHERE uid=?", (lev, uid)); c.commit(); c.close()
            return self._send(200, {"ok": True, "uid": uid, "lev": lev,
                "note": "relogin / reconnect agar level baru tampil"})
        if p.startswith("/resource/") or p == "/version.manifest":
            # version.manifest selalu dijawab versi lokal (1.0.81) supaya client
            # tidak menganggap ada update (resmi sudah 1.0.89).
            if p.rsplit("/", 1)[-1] == "version.manifest":
                return self._send(200, {"version": "1.0.81", "tasteVersion": "1.0.81",
                                        "baseVersion": "1.0.81"})
            # Serve lokal dulu (file 1.0.81 persis dari XAPK, taruh di $RESOURCE_DIR),
            # kalau tidak ada baru proxy ke CDN resmi. Ini yang bikin scene hitam
            # kalau CDN resmi sudah beda versi (404) — semua kegagalan dicatat.
            rel = p[len("/resource/"):]
            local = os.path.join(RESOURCE_DIR, rel)
            if os.path.isfile(local):
                with open(local, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Type", mime_for(rel))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try: self.wfile.write(data)
                except Exception: pass
                return
            # proxy CDN resmi supaya client patch tidak perlu hosting 400MB
            target = OFFICIAL_CDN + rel
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
                print(f"[CDN-FAIL] {p} -> {target} : {e}")
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
            sess, buf = {}, bytearray()
            while True:
                op, data = ws_recv(conn)
                if op == 0x8: break
                if op == 0x9:
                    ws_send(conn, data, opcode=0xA)
                    continue
                handle_ws_message(conn, data, op, self.client_address, sess, buf)
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
                   "zone_name": CFG.get("server_name", "GRATIS-1"),
                   "platform": "private", "roles": [],
                   "is_wss": 0,
                   "ws_url": f"{'wss' if PUBLIC_SCHEME == 'https' else 'ws'}://{HOST}/ws"}
            return self._send(200, {"success": 1, "code": 1, "error_msg": "",
                "message": {"server_list": [srv], "recom_server": srv, "new_server": srv,
                            "notice": "Private server: semua GRATIS, jade unlimited."}})
        if "get_ver_first" in p:
            # versi disamakan dengan bawaan APK (1.0.81) supaya tidak ada update.
            return self._send(200, {"success": 1, "code": 1, "version": "1.19",
                "res_ver": "1.0.81", "res_ver_trial": "1.0.81"})
        if "get_ver" in p:
            return self._send(200, {"success": 1, "code": 1, "version": "1.0.81",
                "taste_version": "1.0.81", "taste_patch_time": "",
                "package_version": "1.0.81", "patch_time": "",
                "res_channelids": [], "scsm_channelids": [], "akfb_channelids": [],
                "mpay_channelids": [], "ad_channelids": [], "display_mini_game": 0})
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

def handle_ws_message(conn, data, op, addr, sess, buf):
    if op == 0x1:  # teks (kompatibilitas lama / debug)
        txt = data.decode(errors="ignore")
        print(f"[WS {addr}] teks len={len(data)} {txt[:200]!r}")
        ws_send(conn, unlimited_push())
        return
    if op != 0x2:  # bukan biner/data: abaikan (ping/pong/close ditangani pemanggil)
        return
    buf += data
    if op == 0x2 and len(buf) < 200:
        print(f"[WS {addr}] biner {len(data)}B hex={data[:96].hex()}")
    while len(buf) >= 6:
        total, cmd = struct.unpack("<IH", buf[:6])
        if total < 2 or total > 10 * 1024 * 1024:
            print(f"[GAME {addr}] framing rusak total={total}, reset buffer")
            buf.clear()
            return
        if len(buf) < 4 + total:
            break  # tunggu sisa bytes
        payload = bytes(buf[6:4 + total])
        del buf[:4 + total]
        for pkt in handle_game_packet(cmd, payload, sess):
            ws_send(conn, pkt, opcode=0x2)

def handle_ws(conn, addr):
    sess, buf = {}, bytearray()
    try:
        req = conn.recv(4096).decode(errors="ignore")
        if "Upgrade" not in req and "upgrade" not in req:
            conn.close(); return
        ws_handshake(conn, req)
        print(f"[WS] client {addr} tersambung (protokol game biner)")
        while True:
            op, data = ws_recv(conn)
            if op == 0x8: break
            if op == 0x9:  # ping -> pong
                ws_send(conn, data, opcode=0xA)
                continue
            handle_ws_message(conn, data, op, addr, sess, buf)
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
