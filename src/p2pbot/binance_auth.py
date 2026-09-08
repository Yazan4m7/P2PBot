from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode

import httpx


class BinanceAuthError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class BinanceAuthClient:
    """Authenticated Binance SAPI client limited to account/P2P read operations."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        timeout_seconds: float = 15.0,
        recv_window_ms: int = 5000,
        transport=None,
    ):
        if not api_key or not api_secret:
            raise ValueError('api_key and api_secret are required')
        self.base_url = base_url.rstrip('/')
        self.api_secret = api_secret.encode('utf-8')
        self.recv_window_ms = recv_window_ms
        self.client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_seconds,
            headers={
                'X-MBX-APIKEY': api_key,
                'User-Agent': 'p2pbot/0.2 read-only',
            },
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _signed_params(self, params: Iterable[tuple[str, Any]] | None = None) -> list[tuple[str, str]]:
        ordered = [(str(k), str(v)) for k, v in (params or []) if v is not None]
        ordered.append(('recvWindow', str(self.recv_window_ms)))
        ordered.append(('timestamp', str(int(time.time() * 1000))))
        query = urlencode(ordered)
        signature = hmac.new(self.api_secret, query.encode('utf-8'), hashlib.sha256).hexdigest()
        return [*ordered, ('signature', signature)]

    def _request(self, method: str, path: str, params: Iterable[tuple[str, Any]] | None = None) -> Any:
        signed = self._signed_params(params)
        try:
            response = self.client.request(method, path, params=signed)
        except httpx.HTTPError as exc:
            raise BinanceAuthError(f'Binance network error: {exc}') from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {'msg': response.text}
        if response.is_error:
            code = payload.get('code') if isinstance(payload, dict) else None
            msg = payload.get('msg') if isinstance(payload, dict) else None
            raise BinanceAuthError(
                str(msg or payload or f'HTTP {response.status_code}'),
                status_code=response.status_code,
                code=code if isinstance(code, int) else None,
            )
        return payload

    def list_order_history(
        self,
        *,
        trade_type: str | None = None,
        start_timestamp: int | None = None,
        end_timestamp: int | None = None,
        page: int = 1,
        rows: int = 20,
    ) -> Any:
        params: list[tuple[str, Any]] = [('page', page), ('rows', rows)]
        if trade_type:
            params.append(('tradeType', trade_type.upper()))
        if start_timestamp is not None:
            params.append(('startTimestamp', start_timestamp))
        if end_timestamp is not None:
            params.append(('endTimestamp', end_timestamp))
        return self._request('GET', '/sapi/v1/c2c/orderMatch/listUserOrderHistory', params)

    def get_order_summary(self) -> Any:
        return self._request('GET', '/sapi/v1/c2c/orderMatch/getUserOrderSummary')

    def get_agent_order_detail(self, order_number: str) -> Any:
        return self._request('POST', '/sapi/v1/c2c/agent/orderMatch/getUserOrderDetail', [('orderNumber', order_number)])

    def get_available_ad_categories(self) -> Any:
        return self._request('GET', '/sapi/v1/c2c/agent/ads/getAvailableAdsCategory')

    def capability_probe(self) -> dict[str, Any]:
        checks: dict[str, Any] = {
            'auth_configured': True,
            'personal_order_history': False,
            'order_summary': False,
            'agent_order_detail': 'not_probed_without_order_number',
            'ad_management_eligibility': False,
            'notes': [],
        }
        for name, fn in (
            ('personal_order_history', lambda: self.list_order_history(rows=1)),
            ('order_summary', self.get_order_summary),
            ('ad_management_eligibility', self.get_available_ad_categories),
        ):
            try:
                fn()
                checks[name] = True
            except BinanceAuthError as exc:
                checks[name] = False
                checks['notes'].append(
                    {'capability': name, 'error': str(exc), 'http_status': exc.status_code, 'code': exc.code}
                )
        return checks
