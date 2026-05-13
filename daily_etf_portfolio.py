#!/usr/bin/env python3
"""Daily runner for ezmoney ETF portfolio reports."""

from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from ezmoney_etf_portfolio import (
    Portfolio,
    build_status_rows,
    date_only,
    display_status_rows,
    fetch_html,
    format_diff,
    format_lots,
    parse_portfolio,
    portfolio_from_json,
    report_title,
    stock_detail_rows,
    write_csv,
    write_status_html,
)


DEFAULT_FUND_CODES = ["49YTW", "63YTW"]


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


def escape(value: Any) -> str:
    return html.escape(str(value))


def status_table_rows(rows: list[dict[str, Any]]) -> str:
    body_rows: list[str] = []
    for row in rows:
        remark = str(row["備註"])
        remark_class = {
            "加碼": "buy",
            "新增": "new",
            "減碼": "sell",
            "清空": "clear",
            "持平": "flat",
        }.get(remark, "unknown")
        row_class = "new-row" if remark == "新增" else ""
        body_rows.append(
            '<tr class="{row_class}">'
            '<td>{name}</td>'
            '<td>{code}</td>'
            '<td>{holding}</td>'
            '<td>{diff}</td>'
            '<td class="remark {remark_class}">{remark}</td>'
            '</tr>'.format(
                row_class=row_class,
                name=escape(row["股票名稱"]),
                code=escape(row["代碼"]),
                holding=escape(format_lots(row["持有張數"])),
                diff=escape(format_diff(row["張數增減"])),
                remark_class=remark_class,
                remark=escape(remark),
            )
        )
    return "".join(body_rows)


def report_section(portfolio: Portfolio, rows: list[dict[str, Any]]) -> str:
    report_date = rows[0]["日期"] if rows else ""
    return "".join(
        [
            '<section class="report-section">',
            '<div class="brand">ezmoney ETF portfolio</div>',
            f'<h1>{escape(report_title(portfolio))}</h1>',
            f'<div class="meta">{escape(report_date)} ｜ 共 {len(rows)} 檔持股</div>',
            '<div class="rule"></div>',
            '<table><thead><tr>',
            '<th>股票名稱</th><th>代碼</th><th>持有張數</th><th>張數增減</th><th>備註</th>',
            '</tr></thead><tbody>',
            status_table_rows(rows),
            '</tbody></table>',
            '</section>',
        ]
    )


def write_combined_status_html(
    path: Path, reports: list[tuple[Portfolio, list[dict[str, Any]]]]
) -> None:
    sections = "".join(report_section(portfolio, rows) for portfolio, rows in reports)
    document = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>ETF 持股現況</title>
  <style>
    body {{
      margin: 0;
      background: #eef3f7;
      color: #1c2733;
      font-family: "PingFang TC", "Microsoft JhengHei", Arial, sans-serif;
    }}
    .page {{
      width: 900px;
      margin: 0 auto;
      padding: 28px 42px 36px;
      background: #f7fafc;
    }}
    .report-section {{
      margin-bottom: 64px;
    }}
    .report-section:last-child {{
      margin-bottom: 0;
    }}
    .brand {{
      text-align: right;
      color: #12345b;
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0;
      margin-bottom: 18px;
    }}
    h1 {{
      text-align: center;
      color: #0b3768;
      font-size: 30px;
      margin: 0 0 26px;
      letter-spacing: 0;
    }}
    .meta {{
      text-align: center;
      color: #8a8f96;
      font-size: 18px;
      margin-bottom: 12px;
    }}
    .rule {{
      border-top: 4px solid #093a74;
      margin-bottom: 46px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 27px;
      line-height: 1.12;
      background: white;
    }}
    th {{
      background: #003774;
      color: white;
      font-size: 26px;
      padding: 4px 8px;
      border: 1px solid #d9dee4;
      font-weight: 800;
    }}
    td {{
      text-align: center;
      padding: 3px 8px;
      border: 1px solid #d9dee4;
      height: 30px;
    }}
    tbody tr:nth-child(even) td {{
      background: #e8edf2;
    }}
    tbody tr.new-row td {{
      background: #ffdbe0;
    }}
    .remark.buy {{
      color: #b4202a;
      font-weight: 800;
    }}
    .remark.sell, .remark.clear {{
      color: #149447;
      font-weight: 800;
    }}
    .remark.new {{
      color: #d05a31;
      font-weight: 800;
    }}
    .remark.flat, .remark.unknown {{
      color: #222;
      font-weight: 500;
    }}
  </style>
</head>
<body>
  <main class="page">
    {sections}
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def write_combined_csv(path: Path, reports: list[tuple[Portfolio, list[dict[str, Any]]]]) -> None:
    rows: list[dict[str, Any]] = []
    for portfolio, status_rows in reports:
        for row in display_status_rows(status_rows):
            rows.append(
                {
                    "FundCode": portfolio.fund_code,
                    "FundName": portfolio.fund_name,
                    **row,
                }
            )
    write_csv(path, rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="每日抓取 ezmoney ETF 持股，跟上一份快照比較並輸出 HTML。"
    )
    parser.add_argument(
        "--fund-code",
        nargs="+",
        default=DEFAULT_FUND_CODES,
        help="基金代碼，可輸入多個；預設 49YTW 63YTW",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "daily_reports",
        help="輸出資料夾，預設為專案內 daily_reports",
    )
    parser.add_argument(
        "--previous-json",
        type=Path,
        help="指定比較用的上一份 JSON；只建議單基金模式使用",
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

    reports: list[tuple[Portfolio, list[dict[str, Any]]]] = []
    latest_json_for_first_fund: Path | None = None
    latest_dates: list[str] = []

    for index, fund_code in enumerate(args.fund_code):
        portfolio = parse_portfolio(fetch_html(fund_code))
        current_date = portfolio_date(portfolio)
        latest_dates.append(current_date)

        current_json = raw_dir / f"{fund_code}_{current_date}.json"
        current_html = html_dir / f"{fund_code}_{current_date}.html"
        current_csv = csv_dir / f"{fund_code}_{current_date}.csv"

        previous_json = args.previous_json if len(args.fund_code) == 1 else None
        if previous_json is None:
            previous_json = newest_prior_snapshot(raw_dir, fund_code, current_date)

        previous_portfolio = portfolio_from_json(previous_json) if previous_json else None
        status_rows = build_status_rows(portfolio, previous_portfolio)

        write_raw_json(current_json, portfolio)
        write_status_html(current_html, portfolio, status_rows)
        write_csv(current_csv, display_status_rows(status_rows))

        if not args.no_latest:
            copy_latest(current_json, output_dir / f"latest_{fund_code}.json")
            copy_latest(current_html, output_dir / f"latest_{fund_code}.html")
            copy_latest(current_csv, output_dir / f"latest_{fund_code}.csv")
            if index == 0:
                latest_json_for_first_fund = current_json

        reports.append((portfolio, status_rows))

        compare_text = str(previous_json) if previous_json else "無上一份快照，首次執行以 0 比較"
        print(f"fund_code={fund_code}")
        print(f"portfolio_date={current_date}")
        print(f"previous_json={compare_text}")
        print(f"raw_json={current_json}")
        print(f"html={current_html}")
        print(f"csv={current_csv}")

    if reports and not args.no_latest:
        write_combined_status_html(output_dir / "latest.html", reports)
        copy_latest(output_dir / "latest.html", output_dir / "index.html")
        write_combined_csv(output_dir / "latest.csv", reports)
        if latest_json_for_first_fund is not None:
            copy_latest(latest_json_for_first_fund, output_dir / "latest.json")

    print(f"report_dates={','.join(latest_dates)}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"錯誤: {exc}", file=sys.stderr)
        raise SystemExit(1)
