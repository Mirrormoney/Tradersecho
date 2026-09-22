"""Run the shared daily collection queue on a persistent local/Docker host."""
import argparse
import time
from .collection import run_batch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--loop', action='store_true')
    args = parser.parse_args()
    while True:
        try:
            result = run_batch()
            print(result, flush=True)
            if result['errors']:
                if not args.loop:
                    raise SystemExit(1)
                time.sleep(300)
            elif result['completed']:
                time.sleep(2)
                continue
            elif args.loop:
                time.sleep(300)
        except RuntimeError as exc:
            print(str(exc), flush=True)
            if not args.loop:
                raise SystemExit(1)
            time.sleep(300)
        if not args.loop:
            break


if __name__ == '__main__':
    main()
