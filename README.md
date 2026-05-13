# ETF Daily Portfolio Report

每天用 GitHub Actions 抓取 ezmoney ETF 投資組合，和上一份 JSON 快照比較，輸出持股現況 HTML。目前包含 00981A（49YTW）與 00403A（63YTW），首頁會先顯示 00981A，再顯示 00403A。

## 會產生什麼

- `daily_reports/raw/49YTW_YYYY-MM-DD.json`：每日原始資料快照，下一天用來比較
- `daily_reports/html/49YTW_YYYY-MM-DD.html`：每日 HTML 報表
- `daily_reports/csv/49YTW_YYYY-MM-DD.csv`：每日 CSV
- `daily_reports/latest.json`：最新 JSON
- `daily_reports/latest.html`：最新合併 HTML
- `daily_reports/index.html`：GitHub Pages 首頁，內容同最新合併 HTML
- `daily_reports/latest_49YTW.html`：00981A 最新 HTML
- `daily_reports/latest_63YTW.html`：00403A 最新 HTML

持股現況會依「市值 Amount」由大到小排序，張數增減會用今日股數和上一份 JSON 股數比較。若昨天有持股但今天清空，會顯示持有張數 `0`、負的張數增減，備註為 `清空`。

## GitHub Actions 設定

workflow 已放在：

```text
.github/workflows/daily-etf-report.yml
```

預設每天台灣時間 18:05 執行一次：

```yaml
- cron: "5 10 * * *"
```

GitHub Actions 的 cron 預設使用 UTC，所以 `10:05 UTC = 18:05 Asia/Taipei`。

## GitHub Repo 要開的設定

1. 到 GitHub 建一個 repo，然後把這個專案 push 上去。
2. 進 repo 的 `Settings` -> `Actions` -> `General`。
3. 在 `Workflow permissions` 選：

```text
Read and write permissions
```

4. 勾選允許 GitHub Actions 建立/核准 pull request 的選項可不用勾，這裡不需要。
5. 進 `Settings` -> `Pages`。
6. `Build and deployment` 的 `Source` 選：

```text
GitHub Actions
```

## 第一次執行

第一次沒有昨天 JSON，所以報表會顯示「無比較」。第二天開始就會自動比較前一份快照。

你可以先手動跑一次：

1. 到 repo 的 `Actions`
2. 選 `Daily ETF report`
3. 按 `Run workflow`

成功後會 commit `daily_reports` 回 repo，並部署 GitHub Pages。

## 本機測試

```bash
python3 daily_etf_portfolio.py --fund-code 49YTW --output-dir daily_reports
```

看報表：

```text
daily_reports/latest.html
```

## 換基金代碼

目前 workflow 固定：

```bash
python daily_etf_portfolio.py --fund-code 49YTW 63YTW --output-dir daily_reports
```

如果要調整 ETF，把 workflow 裡的 `49YTW 63YTW` 改成你要的 `fundCode` 清單即可。順序會決定首頁報表上下順序。
