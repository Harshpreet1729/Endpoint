"""Local test receiver: retry endpoint fails once, fail endpoint always fails."""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

captures = []


class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode()
        delivery_id = self.headers.get("X-EventGate-Delivery-ID")
        previous = sum(item["id"] == delivery_id for item in captures)
        captures.append({"id": delivery_id, "body": body, "signature": self.headers.get("X-EventGate-Signature")})
        self.send_response(500 if self.path == "/fail" or (self.path == "/retry" and previous == 0) else 200)
        self.end_headers()
        self.wfile.write(b"receiver result")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(captures).encode())

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 9000), Receiver).serve_forever()
