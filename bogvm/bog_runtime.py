from __future__ import annotations

import json
import os
from pathlib import Path
import socket
from typing import Any


class BogCapabilityError(PermissionError):
    pass


def bog_read(path: str) -> bytes:
    response = _request("read", path=path)
    return bytes.fromhex(response["data_hex"])


def bog_write(path: str, data: str | bytes) -> dict:
    encoded = data.encode("utf-8") if isinstance(data, str) else bytes(data)
    return _request("write", path=path, data_hex=encoded.hex())


def bog_env(name: str) -> str:
    return _request("env", name=name)["value"]


def bog_dependency(package: str) -> dict:
    return _request("dependency", package=package)["verification"]


def bog_receipt() -> list[dict]:
    return _request("receipt")["calls"]


def _request(operation: str, **params: Any) -> dict:
    socket_path = os.environ.get("BOG_BROKER_SOCKET")
    token = os.environ.get("BOG_BROKER_TOKEN")
    if not socket_path or not token:
        raise BogCapabilityError("Bog brokered runtime is not active")
    request = {"operation": operation, "token": token, **params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(Path(socket_path)))
        client.sendall(json.dumps(request, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        response = json.loads(_read_line(client))
    if response.get("execution_status") != "completed":
        reason = response.get("failures", [{"reason": "capability request blocked"}])[0]["reason"]
        raise BogCapabilityError(reason)
    return response


def _read_line(client: socket.socket) -> str:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = client.recv(65536)
        if not chunk:
            break
        data.extend(chunk)
    return data.decode("utf-8")
