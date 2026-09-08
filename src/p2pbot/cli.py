from __future__ import annotations

import argparse
import json
import time

from .binance_public import BinancePublicClient, BinancePublicError
from .config import get_settings
from .db import Repository
from .service import MarketService


def make_service():
    settings = get_settings()
    repo = Repository(settings.database_url)
    repo.create_schema()
    client = BinancePublicClient(settings.binance_mgs_base, settings.request_timeout_seconds)
    return settings, repo, client, MarketService(settings, repo, client)


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only Binance P2P scanner/opportunity engine")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Run one market scan")
    scan.add_argument("--fiat", default=None)
    scan.add_argument("--asset", default=None)

    run = sub.add_parser("run", help="Continuously scan market")
    run.add_argument("--fiat", default=None)
    run.add_argument("--asset", default=None)
    run.add_argument("--interval", type=float, default=None)

    sub.add_parser("recent", help="Show recent stored opportunities")

    args = parser.parse_args()
    settings, repo, client, service = make_service()
    try:
        if args.command == "scan":
            print(json.dumps(service.scan_and_analyze(args.fiat, args.asset), indent=2))
        elif args.command == "recent":
            print(json.dumps(repo.recent_opportunities(50), indent=2))
        elif args.command == "run":
            interval = max(2.0, args.interval or settings.scan_interval_seconds)
            while True:
                try:
                    result = service.scan_and_analyze(args.fiat, args.asset)
                    top = result["opportunities"][0] if result["opportunities"] else None
                    print(json.dumps({**{k: v for k, v in result.items() if k != "opportunities"}, "top": top}))
                except BinancePublicError as exc:
                    print(json.dumps({"error": str(exc)}))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == "__main__":
    main()
