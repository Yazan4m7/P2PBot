from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

import httpx

from .domain import Ad, Merchant


class BinancePublicError(RuntimeError):
    pass


def _first(mapping: dict[str, Any], *keys: str, default=None):
    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "":
            return value
    return default


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _completion_pct(value: Any) -> float | None:
    result = _float(value)
    if result is None:
        return None
    # Binance surfaces historically used both 0..1 and 0..100 representations.
    if 0 <= result <= 1:
        result *= 100
    return max(0.0, min(100.0, result))


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []

    candidates: list[Any] = [payload.get("data"), payload.get("rows"), payload.get("list")]
    data = payload.get("data")
    if isinstance(data, dict):
        candidates.extend([data.get("data"), data.get("rows"), data.get("list"), data.get("items")])
    for candidate in candidates:
        if isinstance(candidate, list):
            return [x for x in candidate if isinstance(x, dict)]
    return []


def _payment_methods(ad: dict[str, Any], item: dict[str, Any]) -> tuple[str, ...]:
    raw = _first(ad, "tradeMethods", "payTypes", "tradeMethodIdentifiers")
    if raw is None:
        raw = _first(item, "tradeMethods", "payTypes", "tradeMethodIdentifiers", default=[])
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, Iterable) or isinstance(raw, (dict, bytes)):
        return ()

    methods: list[str] = []
    for method in raw:
        if isinstance(method, str):
            identifier = method
        elif isinstance(method, dict):
            identifier = _first(
                method,
                "identifier",
                "tradeMethodIdentifier",
                "tradeMethodName",
                "payType",
                "name",
            )
        else:
            identifier = None
        if identifier:
            normalized = str(identifier).strip().upper()
            if normalized and normalized not in methods:
                methods.append(normalized)
    return tuple(methods)


def parse_ads(payload: Any, *, trade_type: str, asset: str, fiat: str) -> list[Ad]:
    parsed: list[Ad] = []
    for item in _extract_items(payload):
        ad = item.get("adv") if isinstance(item.get("adv"), dict) else item
        merchant_data = (
            item.get("advertiser")
            if isinstance(item.get("advertiser"), dict)
            else item.get("merchant")
            if isinstance(item.get("merchant"), dict)
            else item.get("advertiserInfo")
            if isinstance(item.get("advertiserInfo"), dict)
            else item
        )

        ad_no = _first(ad, "adNo", "advNo", "advertisementNo", "id")
        price = _decimal(_first(ad, "price", "advPrice"))
        if not ad_no or price is None or price <= 0:
            continue

        merchant_no = _first(
            merchant_data,
            "merchantNo",
            "userNo",
            "advertiserNo",
            "userId",
            default=f"unknown:{ad_no}",
        )
        nickname = _first(
            merchant_data,
            "nickName",
            "nickname",
            "merchantNick",
            "userName",
            default=str(merchant_no),
        )

        merchant = Merchant(
            merchant_no=str(merchant_no),
            nickname=str(nickname),
            completion_rate_pct=_completion_pct(
                _first(merchant_data, "monthFinishRate", "completionRate", "finishRate")
            ),
            order_count=_int(
                _first(merchant_data, "monthOrderCount", "orderCount", "completedOrderNumOfLatest30day")
            ),
            avg_release_seconds=_float(
                _first(merchant_data, "avgReleaseTimeOfLatest30day", "advConfirmTime", "releaseTime")
            ),
            merchant_type=str(_first(merchant_data, "userType", "merchantType", "type", default="")) or None,
        )

        parsed.append(
            Ad(
                ad_no=str(ad_no),
                trade_type=trade_type.upper(),
                asset=asset.upper(),
                fiat=fiat.upper(),
                price=price,
                available_asset=_decimal(
                    _first(ad, "surplusAmount", "tradableQuantity", "availableAmount", "surplus")
                ),
                min_fiat=_decimal(
                    _first(ad, "minSingleTransAmount", "minSingleTransQuantity", "minAmount", "minLimit")
                ),
                max_fiat=_decimal(
                    _first(ad, "maxSingleTransAmount", "maxSingleTransQuantity", "maxAmount", "maxLimit")
                ),
                payment_methods=_payment_methods(ad, item),
                merchant=merchant,
                raw=item,
            )
        )
    return parsed


class BinancePublicClient:
    """Client for Binance's public P2P/C2C agent market-data endpoints only."""

    def __init__(self, base_url: str, timeout_seconds: float = 15.0, transport=None):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers={"User-Agent": "p2p-market-research/0.1"},
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _get(self, path: str, params: list[tuple[str, str]] | dict[str, Any]) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = self.client.get(path, params=params)
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict) and payload.get("success") is False:
                    raise BinancePublicError(str(payload.get("message") or payload.get("messageDetail") or payload))
                return payload
            except (httpx.HTTPError, ValueError, BinancePublicError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (2**attempt))
        raise BinancePublicError(f"Binance public P2P request failed after retries: {last_error}") from last_error

    def check_version(self, version: str = "2.0.0") -> dict[str, Any] | None:
        try:
            payload = self._get("/bapi/c2c/v1/public/c2c/agent/check-version", {"version": version})
            return payload if isinstance(payload, dict) else None
        except BinancePublicError:
            return None

    def get_trade_methods(self, fiat: str) -> list[dict[str, Any]]:
        payload = self._get("/bapi/c2c/v1/public/c2c/agent/trade-methods", {"fiat": fiat.upper()})
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            data = payload.get("data", [])
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
        return []

    def get_ads(
        self,
        *,
        fiat: str,
        asset: str,
        trade_type: str,
        limit: int = 20,
        payment_methods: list[str] | None = None,
    ) -> list[Ad]:
        tt = trade_type.upper()
        if tt not in {"BUY", "SELL"}:
            raise ValueError("trade_type must be BUY or SELL")
        if not 1 <= limit <= 20:
            raise ValueError("limit must be between 1 and 20")

        params: list[tuple[str, str]] = [
            ("fiat", fiat.upper()),
            ("asset", asset.upper()),
            ("tradeType", tt),
            ("limit", str(limit)),
        ]
        for method in payment_methods or []:
            params.append(("tradeMethodIdentifiers", method.upper()))

        payload = self._get("/bapi/c2c/v1/public/c2c/agent/ad-list", params)
        return parse_ads(payload, trade_type=tt, asset=asset, fiat=fiat)
