from __future__ import annotations

import argparse
import json

import uvicorn

from .api import engine


def main() -> None:
    parser = argparse.ArgumentParser(description="P2P deterministic simulator")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8090)
    reset = sub.add_parser("reset")
    reset.add_argument("--seed", type=int, default=None)
    sub.add_parser("status")
    adv = sub.add_parser("advance")
    adv.add_argument("seconds", type=float)
    sub.add_parser("tick")
    args = parser.parse_args()
    if args.command == "serve":
        uvicorn.run("p2psim.api:app", host=args.host, port=args.port, reload=False)
    elif args.command == "reset":
        print(json.dumps(engine.reset(seed=args.seed), indent=2))
    elif args.command == "status":
        print(json.dumps(engine.status(), indent=2))
    elif args.command == "advance":
        print(json.dumps(engine.advance(args.seconds), indent=2))
    elif args.command == "tick":
        print(json.dumps(engine.market_tick(), indent=2))


if __name__ == "__main__":
    main()
