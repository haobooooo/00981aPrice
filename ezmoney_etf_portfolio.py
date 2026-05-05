#!/usr/bin/env python3
"""Fetch ezmoney ETF portfolio data from the fund info page."""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


BASE_URL = "https://www.ezmoney.com.tw/ETF/Fund/Info"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class HiddenDataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.data_by_id: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "div":
            return

        attr_map = {name: value for name, value in attrs}
        element_id = attr_map.get("id")
        data_content = attr_map.get("data-content")
        if element_id and data_content is not None:
            self.data_by_id[element_id] = data_content


@dataclass(frozen=True)
class Portfolio:
    fund: dict[str, Any]
    assets: list[dict[str, Any]]
    detail_schema: list[dict[str, Any]]

    @property
    def fund_name(self) -> str:
        return str(self.fund.get("sFundName") or self.fund.get("sFundShortName") or "")

    @property
    def fund_code(self) -> str:
        return str(self.fund.get("sFundCode") or "")

    @property
    def stock_no(self) -> str:
        return str(self.fund.get("sStockNo") or "").strip()

    @property
    def stock_name(self) -> str:
        return str(self.fund.get("sStockName") or self.fund.get("sFundShortName") or "").strip()


def fetch_html(fund_code: str) -> str:
    query = urlencode({"fundCode": fund_code})
    request = Request(f"{BASE_URL}?{query}", headers={"User-Agent": USER_AGENT})
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    with opener.open(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def parse_json_block(parser: HiddenDataParser, element_id: str) -> Any:
    raw = parser.data_by_id.get(element_id)
    if raw is None:
        raise ValueError(f"找不到頁面 hidden data: {element_id}")
    return json.loads(html.unescape(raw))


def parse_portfolio(page_html: str) -> Portfolio:
    parser = HiddenDataParser()
    parser.feed(page_html)

    return Portfolio(
        fund=parse_json_block(parser, "DataFund"),
        assets=parse_json_block(parser, "DataAsset"),
        detail_schema=parse_json_block(parser, "DataAssetDetailSchema"),
    )


def portfolio_from_json(path: Path) -> Portfolio:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return Portfolio(
        fund=data["fund"],
        assets=data["assets"],
        detail_schema=data.get("detail_schema", []),
    )


def flatten_details(portfolio: Portfolio) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset in portfolio.assets:
        details = asset.get("Details") or []
        if not isinstance(details, list):
            continue

        for detail in details:
            if not isinstance(detail, dict):
                continue
            row = {
                "FundCode": portfolio.fund_code,
                "FundName": portfolio.fund_name,
                "AssetCode": asset.get("AssetCode"),
                "AssetName": asset.get("AssetName"),
                "TranDate": detail.get("TranDate") or asset.get("EndDate"),
                "DetailCode": detail.get("DetailCode"),
                "DetailName": detail.get("DetailName"),
                "Share": detail.get("Share"),
                "Amount": detail.get("Amount"),
                "NavRate": detail.get("NavRate"),
                "MoneyType": detail.get("MoneyType") or asset.get("MoneyType"),
                "Sequence": detail.get("Sequence"),
                "EditTime": detail.get("EditTime") or asset.get("EditDate"),
            }
            rows.append(row)

    return sorted(rows, key=lambda row: (str(row["AssetCode"]), row["Sequence"] or 0))


def stock_detail_rows(portfolio: Portfolio) -> list[dict[str, Any]]:
    return [row for row in flatten_details(portfolio) if row["AssetCode"] == "ST"]


def as_lots(share: Any) -> int | None:
    if not isinstance(share, (int, float)):
        return None
    return int(round(share / 1000))


def date_only(value: Any) -> str:
    if not value:
        return ""
    return str(value).split("T", 1)[0]


def report_title(portfolio: Portfolio) -> str:
    stock_name = portfolio.stock_name.replace("主動", "", 1).strip()
    stock_no = portfolio.stock_no
    if stock_no:
        return f"{stock_name} ({stock_no}) 持股現況"
    return f"{portfolio.fund_name} 持股現況"


def build_status_rows(
    portfolio: Portfolio, previous_portfolio: Portfolio | None = None
) -> list[dict[str, Any]]:
    previous_by_code: dict[str, dict[str, Any]] = {}
    if previous_portfolio is not None:
        previous_by_code = {
            str(row["DetailCode"]): row for row in stock_detail_rows(previous_portfolio)
        }

    rows: list[dict[str, Any]] = []
    has_previous = previous_portfolio is not None
    for row in stock_detail_rows(portfolio):
        code = str(row["DetailCode"])
        holding_lots = as_lots(row["Share"])
        previous_lots = as_lots(previous_by_code.get(code, {}).get("Share"))

        diff_lots: int | None = None
        remark = "無比較"
        if has_previous:
            diff_lots = (holding_lots or 0) - (previous_lots or 0)
            if previous_lots is None and (holding_lots or 0) > 0:
                remark = "新增"
            elif diff_lots > 0:
                remark = "加碼"
            elif diff_lots < 0:
                remark = "減碼"
            else:
                remark = "持平"

        rows.append(
            {
                "股票名稱": row["DetailName"],
                "代碼": code,
                "持有張數": holding_lots,
                "_sort_amount": row["Amount"],
                "張數增減": diff_lots,
                "備註": remark,
                "日期": date_only(row["TranDate"]),
            }
        )

    return sorted(rows, key=lambda row: row["_sort_amount"] or 0, reverse=True)


def display_status_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in rows
    ]


def asset_summary(portfolio: Portfolio) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for asset in portfolio.assets:
        rows.append(
            {
                "FundCode": portfolio.fund_code,
                "FundName": portfolio.fund_name,
                "AssetCode": asset.get("AssetCode"),
                "AssetName": asset.get("AssetName"),
                "MoneyType": asset.get("MoneyType"),
                "Value": asset.get("Value"),
                "Weight": asset.get("Weight"),
                "StartDate": asset.get("StartDate"),
                "EndDate": asset.get("EndDate"),
                "EditDate": asset.get("EditDate"),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError("沒有資料可匯出 CSV")

    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def format_lots(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value)


def format_diff(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, (int, float)):
        return str(value)
    if value > 0:
        return f"+{value:,.0f}"
    if value < 0:
        return f"{value:,.0f}"
    return "0"


def write_status_html(path: Path, portfolio: Portfolio, rows: list[dict[str, Any]]) -> None:
    report_date = rows[0]["日期"] if rows else ""
    title = report_title(portfolio)
    escaped_title = html.escape(title)
    escaped_date = html.escape(str(report_date))

    body_rows = []
    for row in rows:
        remark = str(row["備註"])
        remark_class = {
            "加碼": "buy",
            "新增": "new",
            "減碼": "sell",
            "持平": "flat",
        }.get(remark, "unknown")
        row_class = "new-row" if remark == "新增" else ""
        body_rows.append(
            "<tr class=\"{row_class}\">"
            "<td>{name}</td>"
            "<td>{code}</td>"
            "<td>{holding}</td>"
            "<td>{diff}</td>"
            "<td class=\"remark {remark_class}\">{remark}</td>"
            "</tr>".format(
                row_class=row_class,
                name=html.escape(str(row["股票名稱"])),
                code=html.escape(str(row["代碼"])),
                holding=html.escape(format_lots(row["持有張數"])),
                diff=html.escape(format_diff(row["張數增減"])),
                remark_class=remark_class,
                remark=html.escape(remark),
            )
        )

    document = f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <title>{escaped_title}</title>
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
    .remark.sell {{
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
    <div class="brand">ezmoney ETF portfolio</div>
    <h1>{escaped_title}</h1>
    <div class="meta">{escaped_date} ｜ 共 {len(rows)} 檔持股</div>
    <div class="rule"></div>
    <table>
      <thead>
        <tr>
          <th>股票名稱</th>
          <th>代碼</th>
          <th>持有張數</th>
          <th>張數增減</th>
          <th>備註</th>
        </tr>
      </thead>
      <tbody>
        {''.join(body_rows)}
      </tbody>
    </table>
  </main>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def print_summary(portfolio: Portfolio) -> None:
    print(f"{portfolio.fund_code} {portfolio.fund_name}")
    print("基金投資組合摘要")
    for row in asset_summary(portfolio):
        value = row["Value"]
        weight = row["Weight"]
        value_text = f"{value:,.0f}" if isinstance(value, (int, float)) else value
        weight_text = f"{weight:,.0f}" if isinstance(weight, (int, float)) else weight
        print(f"- {row['AssetCode']} {row['AssetName']}: value={value_text}, weight={weight_text}")


def main() -> int:
    arg_parser = argparse.ArgumentParser(
        description="抓取統一投信 ezmoney ETF 基金投資組合。"
    )
    arg_parser.add_argument("--fund-code", default="49YTW", help="基金代碼，預設 49YTW")
    arg_parser.add_argument("--json", type=Path, help="輸出完整 JSON 到指定檔案")
    arg_parser.add_argument("--previous-json", type=Path, help="用上一份 JSON 計算張數增減")
    arg_parser.add_argument("--summary-csv", type=Path, help="輸出資產摘要 CSV")
    arg_parser.add_argument("--details-csv", type=Path, help="輸出持股/標的明細 CSV")
    arg_parser.add_argument("--status-csv", type=Path, help="輸出持股現況 CSV")
    arg_parser.add_argument("--status-html", type=Path, help="輸出持股現況 HTML 報表")
    args = arg_parser.parse_args()

    portfolio = parse_portfolio(fetch_html(args.fund_code))
    previous_portfolio = portfolio_from_json(args.previous_json) if args.previous_json else None
    status_rows = build_status_rows(portfolio, previous_portfolio)
    print_summary(portfolio)

    if args.json:
        args.json.write_text(
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
        print(f"\n已輸出 JSON: {args.json}")

    if args.summary_csv:
        write_csv(args.summary_csv, asset_summary(portfolio))
        print(f"已輸出摘要 CSV: {args.summary_csv}")

    if args.details_csv:
        write_csv(args.details_csv, flatten_details(portfolio))
        print(f"已輸出明細 CSV: {args.details_csv}")

    if args.status_csv:
        write_csv(args.status_csv, display_status_rows(status_rows))
        print(f"已輸出持股現況 CSV: {args.status_csv}")

    if args.status_html:
        write_status_html(args.status_html, portfolio, status_rows)
        print(f"已輸出持股現況 HTML: {args.status_html}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"錯誤: {exc}", file=sys.stderr)
        raise SystemExit(1)
