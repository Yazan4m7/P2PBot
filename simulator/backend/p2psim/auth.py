from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

from fastapi import Request

from .domain import SimulatorError


def verify_signed_request(request: Request, *, expected_api_key: str, expected_secret: str, required: bool = True) -> None:
    """Verify the simulator's fake Binance-compatible signed read requests."""
    if not required:
        return
    if request.headers.get("X-MBX-APIKEY") != expected_api_key:
        raise SimulatorError("INVALID_API_KEY", "Invalid simulator API key", status_code=401)
    pairs = list(request.query_params.multi_items())
    supplied = next((value for key, value in pairs if key == "signature"), None)
    unsigned = [(key, value) for key, value in pairs if key != "signature"]
    if not supplied:
        raise SimulatorError("MISSING_SIGNATURE", "Signature required", status_code=401)
    digest = hmac.new(expected_secret.encode("utf-8"), urlencode(unsigned).encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(supplied, digest):
        raise SimulatorError("INVALID_SIGNATURE", "Invalid simulator request signature", status_code=401)
    values = dict(unsigned)
    try:
        timestamp = int(values.get("timestamp", "0"))
        recv_window = int(values.get("recvWindow", "5000"))
    except ValueError as exc:
        raise SimulatorError("INVALID_TIMESTAMP", "Invalid timestamp", status_code=400) from exc
    if not 1 <= recv_window <= 60000:
        raise SimulatorError("INVALID_RECV_WINDOW", "recvWindow must be 1..60000", status_code=400)
    if abs(int(time.time() * 1000) - timestamp) > recv_window:
        raise SimulatorError("TIMESTAMP_OUTSIDE_WINDOW", "Timestamp outside recvWindow", status_code=400)
