"""Command line interface: `sentinel screen|serve|data|train|eval`."""

from __future__ import annotations

import argparse
import json
import os
import sys


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="sentinel", description="Prompt-injection screening layer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("screen", help="screen text (argument or stdin) and print the decision")
    s.add_argument("text", nargs="?", help="text to screen; reads stdin if omitted")
    s.add_argument("--source", choices=["user", "document", "tool"], default="user")
    s.add_argument("--rules-only", action="store_true", help="do not load the classifier")
    s.add_argument("--json", action="store_true", help="print the full decision as JSON")

    v = sub.add_parser("serve", help="run the FastAPI service and web UI")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8108)

    sub.add_parser("data", help="download the public datasets (pinned revisions) and build the splits")
    sub.add_parser("train", help="fine-tune the classifier (arguments are passed to sentinel.train)", add_help=False)
    sub.add_parser("eval", help="evaluate everything and write docs/data/*.json (arguments passed through)", add_help=False)
    sub.add_parser("export-rules", help="print the rule catalogue as JSON")

    args, rest = ap.parse_known_args(argv)
    if args.cmd == "screen":
        from .screen import Sentinel

        text = args.text if args.text is not None else sys.stdin.read()
        sent = Sentinel(None) if args.rules_only else Sentinel.load()
        d = sent.screen(text, source=args.source, log=False)
        if args.json:
            print(json.dumps(d.to_dict(), indent=2, ensure_ascii=False))
        else:
            score = "n/a (rules-only)" if d.score is None else f"{d.score:.3f}"
            print(f"{d.action.upper()}  score={score}  mode={d.mode}")
            print(d.reason)
            for h in d.hits:
                print(f"  - {h.rule_id} [{h.severity}] {h.category}: {text[h.start:h.end][:80]!r}")
            for n in d.notes:
                print(f"  note: {n}")
        sys.exit({"allow": 0, "flag": 10, "block": 20}[d.action])
    elif args.cmd == "serve":
        import uvicorn

        uvicorn.run("sentinel.server.app:app_factory", factory=True, host=args.host, port=args.port, log_level="info")
    elif args.cmd == "data":
        from . import data

        data.fetch()
        r = data.build()
        print(json.dumps(r["sizes"], indent=2))
    elif args.cmd == "train":
        from .train import main as train_main

        train_main(rest)
    elif args.cmd == "eval":
        from .evaluate import main as eval_main

        eval_main(rest)
    elif args.cmd == "export-rules":
        from .rules import rule_catalogue

        print(json.dumps(rule_catalogue(), indent=2))
    os.environ.setdefault("PYTHONUTF8", "1")


if __name__ == "__main__":
    main()
