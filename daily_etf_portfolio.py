#!/usr/bin/env python3
"""Daily runner for ezmoney ETF portfolio reports.

This script is intended for cron. It fetches today's portfolio, compares it
with the most recent prior JSON snapshot, and writes an HTML report.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import date
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from ezmoney_etf_portfolio import (
    Portfolio,
    build_status_rows,
    date_only,
    display_status_rows,
    fetch_html,
    parse_portfolio,
    portfolio_from_json,
    stock_detail_rows,
    write_csv,
    write_status_html,
)


def portfolio_date(portfolio: Portfolio) -> str:
    stock_rows = stock_detail_rows(portfolio)
    if stock_rows:
        tran_date = date_only(stock_rows[0].get("TranDate"))
        if tran_date:
            return tran_date
    return date.today().isoformat()


def write_raw_json(path: Path, portfolio: Portfolio) -> None:
    path.write_text(
        json.dumps(
            {
                "fund": portfolio.fund,
                "assets": portfolio.assets,
                "detail_schema": portfolio.detail_schema,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def newest_prior_snapshot(raw_dir: Path, fund_code: str, current_date: str) -> Path | None:
    candidates = sorted(raw_dir.glob(f"{fund_code}_*.json"), reverse=True)
    for path in candidates:
        stem_date = path.stem.removeprefix(f"{fund_code}_")
        if stem_date < current_date:
            return path
    return None


def copy_latest(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="每日抓取 ezmoney ETF 持股，跟上一份快照比較並輸出 HTML。"
    )
    parser.add_argument("--fund-code", default="49YTW", help="基金代碼，預設 49YTW")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "daily_reports",
        help="輸出資料夾，預設為專案內 daily_reports",
    )
    parser.add_argument(
        "--previous-json",
        type=Path,
        help="指定比較用的上一份 JSON；未指定時會自動找最近一天快照",
    )
    parser.add_argument(
        "--no-latest",
        action="store_true",
        help="不要更新 latest.html/latest.csv/latest.json",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    raw_dir = output_dir / "raw"
    html_dir = output_dir / "html"
    csv_dir = output_dir / "csv"
    raw_dir.mkdir(parents=True, exist_ok=True)
    html_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    portfolio = parse_portfolio(fetch_html(args.fund_code))
    current_date = portfolio_date(portfolio)

    current_json = raw_dir / f"{args.fund_code}_{current_date}.json"
    current_html = html_dir / f"{args.fund_code}_{current_date}.html"
    current_csv = csv_dir / f"{args.fund_code}_{current_date}.csv"

    previous_json = args.previous_json
    if previous_json is None:
        previous_json = newest_prior_snapshot(raw_dir, args.fund_code, current_date)

    previous_portfolio = portfolio_from_json(previous_json) if previous_json else None
    status_rows = build_status_rows(portfolio, previous_portfolio)

    write_raw_json(current_json, portfolio)
    write_status_html(current_html, portfolio, status_rows)
    write_csv(current_csv, display_status_rows(status_rows))

    if not args.no_latest:
        copy_latest(current_json, output_dir / "latest.json")
        copy_latest(current_html, output_dir / "latest.html")
        copy_latest(current_html, output_dir / "index.html")
        copy_latest(current_csv, output_dir / "latest.csv")

    compare_text = str(previous_json) if previous_json else "無上一份快照，首次執行不比較"
    print(f"fund_code={args.fund_code}")
    print(f"portfolio_date={current_date}")
    print(f"previous_json={compare_text}")
    print(f"raw_json={current_json}")
    print(f"html={current_html}")
    print(f"csv={current_csv}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"錯誤: {exc}", file=sys.stderr)
        raise SystemExit(1)
