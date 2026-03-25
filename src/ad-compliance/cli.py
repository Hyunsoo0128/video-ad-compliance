"""CLI entry point for the ad-compliance pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        description="Ad Compliance Pipeline – analyze a video for brand safety",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Video URL (S3 presigned or public)")
    group.add_argument("--file", help="Local video file path")
    parser.add_argument("--index", help="Index name (default: ad-compliance-prod)")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )

    result = run_pipeline(
        url=args.url,
        file_path=args.file,
        index_name=args.index,
    )

    report_json = result["report_json"]

    if args.output:
        with open(args.output, "w") as f:
            f.write(report_json)
        print(f"Report saved to {args.output}")
    else:
        print(report_json)

    # Exit code: 0=APPROVE, 1=REVIEW, 2=BLOCK
    decision = result["report"].decision.value
    sys.exit({"APPROVE": 0, "REVIEW": 1, "BLOCK": 2}.get(decision, 1))


if __name__ == "__main__":
    main()
