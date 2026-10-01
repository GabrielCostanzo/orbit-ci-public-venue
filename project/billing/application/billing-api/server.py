"""Small, dependency-free Application for the image tutorial."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/invoice":
            settings = json.loads(Path(__file__).with_name("billing.json").read_text())
            tax = round(100 * settings["tax_rate"], 2)
            document = {"subtotal": 100, "tax": tax, "total": 100 + tax}
            status = 200
        else:
            healthy = self.path == "/health"
            document = {"application": "billing-api", "healthy": healthy}
            status = 200 if healthy else 404
        body = json.dumps(document).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
