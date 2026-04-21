from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from core.file_utils import append_jsonl_rotating, write_json_atomic
from core.logger_config import get_logger


logger = get_logger(__name__)

class HikCallbackServer:
    """Receives callbacks from RCS-2000 and stores them locally for audit/debug."""

    def __init__(self, config: dict, output_dir: str | Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.host = str(config.get("host", "0.0.0.0")).strip() or "0.0.0.0"
        self.port = int(config.get("port", 9000))
        self.base_path = str(config.get("base_path", "/service/rest/agvCallbackService")).rstrip("/")
        self.validate_token_code = bool(config.get("validate_token_code", False))
        self.expected_token_code = str(config.get("token_code", "")).strip()
        self.expected_client_code = str(config.get("client_code", "")).strip()
        self.log_max_bytes = max(0, int(float(config.get("log_max_mb", 10.0)) * 1024 * 1024))
        self.log_backup_count = max(0, int(config.get("log_backup_count", 5)))
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        handler_cls = self._build_handler()
        self._server = ThreadingHTTPServer((self.host, self.port), handler_cls)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("[HIK-RCS] Callback server listening on http://%s:%s%s", self.host, self.port, self.base_path)

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def _build_handler(self):
        outer = self

        class CallbackHandler(BaseHTTPRequestHandler):
            server_version = "PIDVN-HIK-CB/1.0"

            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
                route_name = self._resolve_route(self.path)
                if route_name is None:
                    self._write_json(404, {"code": "404", "message": "unsupported callback", "reqCode": ""})
                    return

                body = self._read_json_body()
                req_code = str(body.get("reqCode", ""))
                if outer.validate_token_code:
                    if outer.expected_token_code and str(body.get("tokenCode", "")) != outer.expected_token_code:
                        self._write_json(403, {"code": "403", "message": "invalid tokenCode", "reqCode": req_code})
                        return
                    if outer.expected_client_code and str(body.get("clientCode", "")) != outer.expected_client_code:
                        self._write_json(403, {"code": "403", "message": "invalid clientCode", "reqCode": req_code})
                        return

                event = {
                    "path": self.path,
                    "route": route_name,
                    "payload": body,
                }
                outer._store_callback(route_name, event)
                self._write_json(200, {"code": "0", "message": "successful", "reqCode": req_code, "data": ""})

            def log_message(self, format_: str, *args) -> None:
                logger.debug("[HIK-RCS-CB] " + format_, *args)

            def _resolve_route(self, path: str) -> str | None:
                normalized = path.split("?", 1)[0].rstrip("/")
                for base_path in outer._accepted_base_paths():
                    routes = {
                        f"{base_path}/agvCallback": "agvCallback",
                        f"{base_path}/warnCallback": "warnCallback",
                        f"{base_path}/bindNotify": "bindNotify",
                    }
                    route_name = routes.get(normalized)
                    if route_name is not None:
                        return route_name
                return None

            def _read_json_body(self) -> dict[str, Any]:
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    content_length = 0
                raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
                try:
                    return json.loads(raw.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    return {"raw": raw.decode("utf-8", errors="replace")}

            def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return CallbackHandler

    def _store_callback(self, route_name: str, payload: dict[str, Any]) -> None:
        payload = dict(payload)
        payload.setdefault("stored_at_ts", time.time())
        latest_path = self.output_dir / f"{route_name}_latest.json"
        history_path = self.output_dir / f"{route_name}.jsonl"
        write_json_atomic(latest_path, payload)
        append_jsonl_rotating(
            history_path,
            payload,
            max_bytes=self.log_max_bytes,
            backup_count=self.log_backup_count,
        )
        logger.info("[HIK-RCS] callback=%s stored", route_name)

    def _accepted_base_paths(self) -> list[str]:
        base_path = self.base_path.rstrip("/")
        candidates = {base_path}
        suffix = "/agvCallbackService"
        if base_path.endswith(suffix):
            candidates.add(base_path[: -len(suffix)])
        else:
            candidates.add(base_path + suffix)
        return [item for item in candidates if item]
