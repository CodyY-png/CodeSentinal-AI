# CodeSentinel AI

目標：先理解「規格 → 測試 → 發現錯誤 → 修正 → 再測試」。
目前已建立 AI 生成串接程式（尚未真實 API 驗證）、本機 FastAPI 後端與測試控制台。
已加入自動測試執行器，並修正
demo_app/order.py 的滿額門檻與負數驗證錯誤。

## 目前進度

更新日期：2026 年 11 月 9 日。現階段已完成本機測試控制台，
能透過網頁啟動固定示範專案的測試，查詢結果並保留歷史紀錄。

- 已完成：示範規格與測試、錯誤修正、自動執行器、JSON／XML／日誌報告。
- 已完成：FastAPI 任務 API、SQLite 紀錄、網頁啟動與狀態自動更新。
- 已建立：AI 測試生成串接與離線預覽，尚未進行真實 API 驗證。
- 驗證結果：9 個平台檢查通過、4 個示範測試通過，並已操作瀏覽器確認完整流程。
- 下一階段：取得模型 API 存取後驗證生成結果，再加入 Docker 隔離與 AI 生成介面。

詳細完成項目、限制與後續工作見 [PROGRESS.md](PROGRESS.md)。
啟動指令見第 8 節，網頁操作見第 9 節。

## 1. 準備 Python

安裝 Python 3.12 或更新的穩定版，關閉並重新開啟 PowerShell，確認：

```powershell
py --version
```

## 2. 建立環境並安裝測試工具

```powershell
cd 'C:\Users\User\Documents\ChatGPT\CodeSentinel AI'
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

直接使用虛擬環境的 Python，不需要執行 Activate.ps1。

## 3. 執行測試

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

目前版本預期 4 個測試全部通過。第一版刻意保留錯誤時，
滿額門檻與負數驗證的測試會失敗，結果為 2 個通過、2 個失敗。
測試失敗時，指令結束碼為 1；全部通過時為 0。

## 4. 修正程式

目前 demo_app/order.py 已修正為：

```python
def calculate_total(amount):
    if amount < 0:
        raise ValueError("amount must be non-negative")
    if amount >= 1000:
        return amount * 0.9
    return amount
```

再次執行步驟 3，預期 4 個測試全部通過。

## 5. 產生報告

```powershell
New-Item -ItemType Directory -Force reports | Out-Null
.\.venv\Scripts\python.exe -m pytest -v --junitxml=reports/results.xml --cov=demo_app --cov-branch --cov-report=term-missing --cov-report=html
Start-Process .\htmlcov\index.html
```

results.xml 是之後後端可讀取的測試結果；htmlcov/index.html 是可用瀏覽器開啟的覆蓋率報告。
覆蓋率代表程式被測試執行到的程度，不代表正確率。

## 檔案分工

- SPEC.md：決定正確行為的功能規格。
- demo_app/order.py：被測試的程式。
- tests/test_order.py：依據規格撰寫的測試。
- requirements.txt：需要安裝的套件。

## 6. 使用自動執行器

```powershell
.\.venv\Scripts\python.exe run_analysis.py
```

執行器會使用目前的 Python 啟動 pytest，將每次結果保存在獨立的
`reports/<執行編號>/` 目錄，避免覆蓋前一次紀錄：

- `summary.json`：狀態、通過與失敗數量，以及每個測試的結果。
- `results.xml`：pytest 產生的原始測試報告。
- `pytest.log`：完整執行輸出，供排查問題。

預設 60 秒逾時，可使用 `--timeout 30` 調整。
狀態區分 `passed`、`tests_failed`、`runner_error` 與 `timeout`。
測試失敗不等於已確認程式缺陷，仍需檢查規格與測試本身。
執行器結束碼：通過為 0、測試失敗為 1、執行錯誤為 2、逾時為 124。

此版本僅執行可信的本機示範測試，尚未提供 Docker 隔離。
逾時控制會終止 pytest 主程序，並非完整的子程序樹資源控制。
本階段尚未加入覆蓋率彙整。AI 測試生成操作如下。

## 7. AI 測試生成

此版本先串接 OpenAI Responses API，使用 Python 標準函式庫，不需新增套件。
沒有 API 帳號時先執行預覽：

```powershell
.\.venv\Scripts\python.exe generate_tests.py --dry-run
```

這會將實際預計送出的請求寫入 `generated/<執行編號>/request.json`，
不連線、不產生 AI 測試，也不產生 API 費用。
請求只包含 `SPEC.md`、`demo_app/order.py` 與生成指示，不會讀取整個專案。

有 API 帳號後，在本機 PowerShell 設定環境變數：

```powershell
$env:OPENAI_MODEL = '填入帳號可使用且支援 Responses API 的模型名稱'
$secret = Read-Host '輸入 OpenAI API 金鑰' -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new('', $secret).Password
.\.venv\Scripts\python.exe generate_tests.py
```

金鑰不應貼在聊天或寫入程式。程式從環境變數讀取設定，不會自動載入 `.env`。
生成會將上述規格與程式傳至 OpenAI，並依帳號 API 用量計費。
程式設定回應長度上限，不自動重試。實際可用模型與費率依你的帳號而定。

成功後會得到 `test_order_candidate.py.txt`，以及包含回應編號、模型與 token
使用量的 `metadata.json`。產生失敗會記錄 `error.json`。
每次任務獨立保存，`generated/` 不納入 Git。

程式會解析 Python 語法並確認至少一個 test_* 函式，但這不代表程式安全或答案正確。
目前沒有 Docker 隔離，因此先檢查候選內容的 import、頂層操作、測試斷言與規格依據。
確認後才手動複製，將下方「執行編號」換成這次的資料夾名稱：

```powershell
Copy-Item '.\generated\執行編號\test_order_candidate.py.txt' '.\tests\test_ai_order.py'
.\.venv\Scripts\python.exe run_analysis.py
```

若已存在 `tests/test_ai_order.py`，請先比較或備份再複製。
執行後通過數取決於模型實際生成的案例，不是固定數字。
測試結束後可移除目前 PowerShell 的金鑰環境變數：

```powershell
Remove-Item Env:OPENAI_API_KEY
```

離線檢查 API 回應解析與錯誤處理：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s checks -v
```

這些是平台本身的檢查，與 `tests/` 內的待測專案案例分開。
尚未完成真實 API 端到端驗證。

API 依據：https://developers.openai.com/api/docs/guides/text

## 8. 啟動本機後端

安裝新增依賴後啟動，保持這個 PowerShell 視窗開啟：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

在瀏覽器開啟 http://127.0.0.1:8000/docs ，這是自動產生的 API 操作頁面，
不是最終產品網頁。點選 POST /analyses，再點 Try it out，使用以下 JSON 後按 Execute：

```json
{"timeout": 60}
```

回應 202 表示已接受任務，回傳的 id 是本次任務編號。
開啟 GET /analyses/{task_id}，填入這個 id 並執行，查看狀態與 result。
目前修正後示範程式預期 result.counts 為 passed 4、failed 0。
狀態可能是 queued、running、passed、tests_failed、timeout、runner_error 或 interrupted。
GET /analyses 列出最近任務，GET /health 確認服務是否啟動。

也可另開 PowerShell 呼叫：

```powershell
$task = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/analyses' -ContentType 'application/json' -Body '{"timeout":60}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/analyses/$($task.id)" | ConvertTo-Json -Depth 10
```

若第一次查詢仍是 queued 或 running，稍後再執行查詢指令。
執行時按 Ctrl+C 停止後端。任務紀錄保存在 reports/tasks.sqlite3，完成結果重新啟動後仍可讀取。
啟動時將尚未完成的任務標示 interrupted，不會自動重跑。
透過 API 建立的任務才會出現在列表，先前 CLI 報告尚未匯入資料庫。

此版本使用單程序 FastAPI 背景任務，每次只接受一個分析，忙碌時回應 409。
請勿增加 --workers 或在任務執行時使用 --reload。
目前只在本機使用，沒有登入、上傳或任意指令執行介面，僅執行專案固定的 tests/。
尚未連接 LLM、獨立任務佇列或 Docker，因此不能作為公開服務部署。

平台檢查（包含一次真實 pytest 執行）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s checks -v
```

背景任務參考：https://fastapi.tiangolo.com/tutorial/background-tasks/

## 9. 使用網頁控制台

使用步驟 8 的指令啟動後端後，開啟 http://127.0.0.1:8000/ 。
若服務先前已啟動，請等待任務完成，按 Ctrl+C 再重新啟動以載入新路由。

按「啟動測試」建立任務，頁面自動更新狀態與各個測試結果。
左側可切換最近 20 次 API 任務，失敗案例可展開執行紀錄。
連線失敗時會顯示提示，可使用「重新整理」重試。

頁面由 web/index.html、web/style.css、web/app.js 組成，FastAPI 在同一個服務
提供網頁與 API。此版本不需要 Node.js、React 或另外啟動前端伺服器。
LLM 生成與專案上傳尚未接入介面，目前只執行可信的固定本機測試。
