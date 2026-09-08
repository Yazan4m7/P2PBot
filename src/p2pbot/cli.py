from __future__ import annotations

import argparse
import json
import time

from .binance_auth import BinanceAuthError
from .binance_public import BinancePublicClient, BinancePublicError
from .config import get_settings
from .db import Repository
from .service import BotService, MarketService


def make_service():
    settings = get_settings()
    repo = Repository(settings.database_url)
    repo.create_schema()
    client = BinancePublicClient(settings.binance_mgs_base, settings.request_timeout_seconds)
    market = MarketService(settings, repo, client)
    return settings, repo, client, market, BotService(settings, repo, market)


def main() -> None:
    parser = argparse.ArgumentParser(description='Binance P2P research/paper automation bot')
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('scan', help='Run one market scan'); scan.add_argument('--fiat', default=None); scan.add_argument('--asset', default=None)
    run = sub.add_parser('run', help='Continuously scan market (read-only)'); run.add_argument('--fiat', default=None); run.add_argument('--asset', default=None); run.add_argument('--interval', type=float, default=None)
    paper = sub.add_parser('paper', help='Run one paper-trade cycle'); paper.add_argument('--fiat', default=None); paper.add_argument('--asset', default=None)
    paper_run = sub.add_parser('paper-run', help='Continuously paper trade'); paper_run.add_argument('--fiat', default=None); paper_run.add_argument('--asset', default=None); paper_run.add_argument('--interval', type=float, default=None)
    sub.add_parser('recent', help='Show recent opportunities')
    sub.add_parser('paper-trades', help='Show recent paper trades')
    sub.add_parser('status', help='Show bot status')
    sub.add_parser('capabilities', help='Probe authenticated Binance read capabilities')
    sync = sub.add_parser('sync-orders', help='Sync personal P2P order history (read-only)'); sync.add_argument('--rows', type=int, default=50)
    args = parser.parse_args()
    settings, repo, client, market, bot = make_service()
    try:
        if args.command == 'scan': print(json.dumps(market.scan_and_analyze(args.fiat, args.asset), indent=2))
        elif args.command == 'recent': print(json.dumps(repo.recent_opportunities(50), indent=2))
        elif args.command == 'paper': print(json.dumps(bot.paper_once(args.fiat, args.asset), indent=2))
        elif args.command == 'paper-trades': print(json.dumps({'items': repo.recent_paper_trades(50), 'stats': repo.paper_stats()}, indent=2))
        elif args.command == 'status': print(json.dumps(bot.status(), indent=2))
        elif args.command == 'capabilities': print(json.dumps(bot.capabilities(), indent=2))
        elif args.command == 'sync-orders': print(json.dumps(bot.sync_account_orders(args.rows), indent=2))
        elif args.command in {'run', 'paper-run'}:
            interval = max(2.0, args.interval or settings.scan_interval_seconds)
            while True:
                try:
                    result = market.scan_and_analyze(args.fiat, args.asset) if args.command == 'run' else bot.paper_once(args.fiat, args.asset)
                    print(json.dumps(result))
                except (BinancePublicError, BinanceAuthError) as exc:
                    print(json.dumps({'error': str(exc)}))
                time.sleep(interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.close()


if __name__ == '__main__':
    main()
