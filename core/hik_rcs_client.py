from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib import error, request

from core.file_utils import append_jsonl_rotating
from core.logger_config import get_logger


logger = get_logger(__name__)


class HikRcsClient:
    """Thin REST client for the HIK RCS APIs used by the Vision bridge."""

    def __init__(self, config: dict, output_dir: str | Path) -> None:
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.output_dir / "http_exchange.jsonl"

        self.scheme = str(config.get("scheme", "http")).strip() or "http"
        self.host = str(config.get("host", "127.0.0.1")).strip()
        self.rpc_port = int(config.get("rpc_port", 8182))
        self.dps_port = int(config.get("dps_port", 8083))
        self.rpc_ports = self._parse_ports(config.get("rpc_ports"), fallback=self.rpc_port)
        self.dps_ports = self._parse_ports(config.get("dps_ports"), fallback=self.dps_port)
        self.rpc_base_path = str(config.get("rpc_base_path", "/rcms/services/rest/hikRpcService")).rstrip("/")
        self.query_agv_path = str(config.get("query_agv_path", "/rcms-dps/rest/queryAgvStatus")).strip()
        self.timeout_sec = float(config.get("http_timeout_sec", 3.0))
        self.client_code = str(config.get("client_code", "")).strip()
        self.token_code = str(config.get("token_code", "")).strip()
        self.include_interface_name = bool(config.get("include_interface_name", False))
        self.http_log_max_bytes = max(0, int(float(config.get("http_log_max_mb", 20.0)) * 1024 * 1024))
        self.http_log_backup_count = max(0, int(config.get("http_log_backup_count", 5)))

    @staticmethod
    def _parse_ports(raw_value: Any, *, fallback: int) -> list[int]:
        ports: list[int] = []
        if isinstance(raw_value, list):
            for value in raw_value:
                try:
                    port = int(value)
                except (TypeError, ValueError):
                    continue
                if port not in ports:
                    ports.append(port)
        if fallback not in ports:
            ports.append(fallback)
        return ports

    @staticmethod
    def make_req_code(seed: str) -> str:
        return hashlib.md5(seed.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def now_text() -> str:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

    def build_base_payload(self, req_code: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "reqCode": req_code,
            "reqTime": self.now_text(),
        }
        if self.client_code:
            payload["clientCode"] = self.client_code
        if self.token_code:
            payload["tokenCode"] = self.token_code
        return payload

    def call_rpc(self, api_name: str, payload: dict[str, Any], req_code: str | None = None) -> dict[str, Any]:
        req_code = req_code or self.make_req_code(f"{api_name}:{json.dumps(payload, sort_keys=True, ensure_ascii=False)}")
        merged = self.build_base_payload(req_code)
        merged.update({key: value for key, value in payload.items() if value is not None})
        if self.include_interface_name:
            merged.setdefault("interfaceName", api_name)
        urls = [
            f"{self.scheme}://{self.host}:{port}{self.rpc_base_path}/{api_name}"
            for port in self.rpc_ports
        ]
        return self._post_json_with_fallback(urls, api_name, merged)

    def query_agv_status(self, payload: dict[str, Any], req_code: str | None = None) -> dict[str, Any]:
        req_code = req_code or self.make_req_code(f"queryAgvStatus:{json.dumps(payload, sort_keys=True, ensure_ascii=False)}")
        merged = self.build_base_payload(req_code)
        merged.update({key: value for key, value in payload.items() if value is not None})
        if self.include_interface_name:
            merged.setdefault("interfaceName", "queryAgvStatus")
        urls = [
            f"{self.scheme}://{self.host}:{port}{self.query_agv_path}"
            for port in self.dps_ports
        ]
        return self._post_json_with_fallback(urls, "queryAgvStatus", merged)

    def bind_pod_and_berth(
        self,
        *,
        req_code: str,
        pod_code: str,
        position_code: str,
        ind_bind: str,
        pod_dir: str | None = None,
        character_value: str | None = None,
    ) -> dict[str, Any]:
        return self.call_rpc(
            "bindPodAndBerth",
            {
                "podCode": pod_code,
                "positionCode": position_code,
                "podDir": pod_dir,
                "characterValue": character_value,
                "indBind": ind_bind,
            },
            req_code=req_code,
        )

    def bind_pod_and_mat(
        self,
        *,
        req_code: str,
        pod_code: str,
        material_lot: str,
        ind_bind: str,
    ) -> dict[str, Any]:
        return self.call_rpc(
            "bindPodAndMat",
            {
                "podCode": pod_code,
                "materialLot": material_lot,
                "indBind": ind_bind,
            },
            req_code=req_code,
        )

    def bind_ctnr_and_bin(
        self,
        *,
        req_code: str,
        ctnr_code: str,
        ctnr_typ: str,
        ind_bind: str,
        stg_bin_code: str | None = None,
        position_code: str | None = None,
        bin_name: str | None = None,
        character_value: str | None = None,
    ) -> dict[str, Any]:
        return self.call_rpc(
            "bindCtnrAndBin",
            {
                "ctnrCode": ctnr_code,
                "ctnrTyp": ctnr_typ,
                "stgBinCode": stg_bin_code,
                "positionCode": position_code,
                "binName": bin_name,
                "characterValue": character_value,
                "indBind": ind_bind,
            },
            req_code=req_code,
        )

    def lock_position(self, *, req_code: str, position_code: str, ind_bind: str) -> dict[str, Any]:
        return self.call_rpc(
            "lockPosition",
            {
                "positionCode": position_code,
                "indBind": ind_bind,
            },
            req_code=req_code,
        )

    def probe_ctnr_binding(
        self,
        *,
        ctnr_typ: str,
        probe_ctnr_code: str,
        stg_bin_code: str | None = None,
        position_code: str | None = None,
        bin_name: str | None = None,
        character_value: str | None = None,
    ) -> dict[str, Any]:
        if not stg_bin_code and not position_code:
            return {
                "code": "CONFIG_ERROR",
                "message": "one of stg_bin_code/position_code is required",
                "reqCode": "",
                "bound": None,
                "bound_ctnr_code": "",
            }

        bind_req_code = self.make_req_code(
            f"probe-bind:{ctnr_typ}:{probe_ctnr_code}:{stg_bin_code or ''}:{position_code or ''}"
        )
        bind_response = self.bind_ctnr_and_bin(
            req_code=bind_req_code,
            ctnr_code=probe_ctnr_code,
            ctnr_typ=ctnr_typ,
            ind_bind="1",
            stg_bin_code=stg_bin_code,
            position_code=position_code,
            bin_name=bin_name,
            character_value=character_value,
        )

        result: dict[str, Any] = {
            "code": str(bind_response.get("code", "")),
            "message": str(bind_response.get("message", "")),
            "reqCode": str(bind_response.get("reqCode", bind_req_code)),
            "bound": None,
            "bound_ctnr_code": "",
            "probe_response": bind_response,
        }

        if self.is_success(bind_response):
            cleanup_req_code = self.make_req_code(
                f"probe-unbind:{ctnr_typ}:{probe_ctnr_code}:{stg_bin_code or ''}:{position_code or ''}"
            )
            cleanup_response = self.bind_ctnr_and_bin(
                req_code=cleanup_req_code,
                ctnr_code=probe_ctnr_code,
                ctnr_typ=ctnr_typ,
                ind_bind="0",
                stg_bin_code=stg_bin_code,
                position_code=position_code,
                bin_name=bin_name,
                character_value=character_value,
            )
            result.update(
                {
                    "bound": False,
                    "bound_ctnr_code": "",
                    "cleanup_response": cleanup_response,
                }
            )
            return result

        existing_ctnr_code = self.extract_bound_ctnr_code(bind_response)
        if existing_ctnr_code:
            result.update(
                {
                    "bound": True,
                    "bound_ctnr_code": existing_ctnr_code,
                }
            )
        return result

    @staticmethod
    def is_success(response: dict[str, Any]) -> bool:
        return str(response.get("code", "")) == "0"

    @staticmethod
    def extract_bound_ctnr_code(response: dict[str, Any]) -> str:
        message = str(response.get("message", "")).strip()
        if not message:
            return ""
        match = re.search(r"has bind container code[:\s]+([^\s,;]+)", message, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _post_json(self, url: str, api_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        response_body = ""
        response_payload: dict[str, Any]
        http_status = 200
        try:
            with request.urlopen(req, timeout=self.timeout_sec) as resp:
                http_status = int(getattr(resp, "status", 200))
                response_body = resp.read().decode("utf-8", errors="replace")
                response_payload = json.loads(response_body) if response_body else {}
        except error.HTTPError as exc:
            http_status = exc.code
            response_body = exc.read().decode("utf-8", errors="replace")
            try:
                response_payload = json.loads(response_body) if response_body else {}
            except json.JSONDecodeError:
                response_payload = {
                    "code": str(http_status),
                    "message": response_body or str(exc),
                    "reqCode": payload.get("reqCode", ""),
                }
        except Exception as exc:
            response_payload = {
                "code": "HTTP_ERROR",
                "message": str(exc),
                "reqCode": payload.get("reqCode", ""),
            }

        exchange = {
            "timestamp": self.now_text(),
            "elapsed_ms": round((time.time() - started) * 1000.0, 2),
            "api_name": api_name,
            "url": url,
            "http_status": http_status,
            "request": payload,
            "response": response_payload,
        }
        self._append_jsonl(
            self.log_path,
            exchange,
            max_bytes=self.http_log_max_bytes,
            backup_count=self.http_log_backup_count,
        )
        logger.info(
            "[HIK-RCS] api=%s req=%s code=%s message=%s",
            api_name,
            payload.get("reqCode", ""),
            response_payload.get("code", ""),
            response_payload.get("message", ""),
        )
        return response_payload

    def _post_json_with_fallback(self, urls: list[str], api_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_response: dict[str, Any] = {
            "code": "HTTP_ERROR",
            "message": "no endpoint configured",
            "reqCode": payload.get("reqCode", ""),
        }
        for index, url in enumerate(urls):
            response = self._post_json(url, api_name, payload)
            code = str(response.get("code", ""))
            if code == "0":
                return response
            if code not in {"HTTP_ERROR", "404"}:
                return response
            last_response = response
            if index < len(urls) - 1:
                logger.warning("[HIK-RCS] fallback api=%s next_url=%s", api_name, urls[index + 1])
        return last_response

    @staticmethod
    def _append_jsonl(path: Path, payload: dict[str, Any], *, max_bytes: int, backup_count: int) -> None:
        append_jsonl_rotating(path, payload, max_bytes=max_bytes, backup_count=backup_count)
