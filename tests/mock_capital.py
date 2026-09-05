"""Nachgebauter Capital.com-Server, um den Provider ohne Konto zu pruefen."""
import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

STATE = {"sessions": 0, "price_calls": 0, "expire_after": 10 ** 9,
         "calls_since_auth": 0, "expire_once": False}

RES_SECONDS = {
    "MINUTE": 60, "MINUTE_5": 300, "MINUTE_15": 900, "MINUTE_30": 1800,
    "HOUR": 3600, "HOUR_4": 14400, "DAY": 86400, "WEEK": 604800,
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):
        if not self.path.endswith("/session"):
            return self._send(404, {"errorCode": "not.found"})
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.headers.get("X-CAP-API-KEY") != "testkey":
            return self._send(401, {"errorCode": "error.invalid.api.key"})
        if body.get("identifier") != "user@example.com" or body.get("password") != "pw":
            return self._send(401, {"errorCode": "error.invalid.details"})
        STATE["sessions"] += 1
        STATE["calls_since_auth"] = 0
        self._send(200, {"currentAccountId": "12345"},
                   {"CST": f"cst-{STATE['sessions']}", "X-SECURITY-TOKEN": "tok"})

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path.endswith("/time"):
            return self._send(200, {"serverTime": int(time.time() * 1000)})

        if not self.headers.get("CST") or not self.headers.get("X-SECURITY-TOKEN"):
            return self._send(401, {"errorCode": "error.null.client.token"})

        STATE["calls_since_auth"] += 1
        if STATE["calls_since_auth"] > STATE["expire_after"]:
            # Einmaliger Ablauf: nach der Ablehnung gilt die naechste
            # Anmeldung wieder. So verhaelt sich der echte Dienst auch.
            if STATE.get("expire_once"):
                STATE["expire_after"] = 10 ** 9
            return self._send(401, {"errorCode": "error.invalid.session.token"})

        if "/prices/" in parsed.path:
            STATE["price_calls"] += 1
            epic = parsed.path.rsplit("/", 1)[-1]
            if epic == "UNKNOWN":
                return self._send(404, {"errorCode": "error.market.not.found"})
            res = query.get("resolution", ["HOUR"])[0]
            mx = int(query.get("max", ["100"])[0])
            to = query.get("to", [None])[0]
            end = (datetime.fromisoformat(to).replace(tzinfo=timezone.utc)
                   if to else datetime.now(timezone.utc))
            step = RES_SECONDS.get(res, 3600)

            prices = []
            for i in range(mx):
                when = end - timedelta(seconds=step * (mx - i))
                base = 1.10 + math.sin(when.timestamp() / 50000) * 0.01
                spread = 0.00008
                def px(v):
                    return {"bid": round(v - spread / 2, 6), "ask": round(v + spread / 2, 6)}
                prices.append({
                    "snapshotTime": when.strftime("%Y-%m-%dT%H:%M:%S"),
                    "snapshotTimeUTC": when.strftime("%Y-%m-%dT%H:%M:%S"),
                    "openPrice": px(base),
                    "highPrice": px(base + 0.0012),
                    "lowPrice": px(base - 0.0012),
                    "closePrice": px(base + 0.0004),
                    "lastTradedVolume": 500 + i,
                })
            return self._send(200, {"prices": prices, "instrumentType": "CURRENCIES"})

        if "/markets/" in parsed.path:
            return self._send(200, {"snapshot": {"bid": 1.09995, "offer": 1.10011}})

        if parsed.path.endswith("/markets"):
            return self._send(200, {"markets": [
                {"epic": "EURUSD", "instrumentName": "EUR/USD", "instrumentType": "CURRENCIES"}
            ]})

        self._send(404, {"errorCode": "not.found"})


def serve(port=8123):
    srv = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
