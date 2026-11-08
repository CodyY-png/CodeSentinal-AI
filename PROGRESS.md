# CodeSentinel AI 開發進度

更新日期：2026 年 11 月 9 日

## 目前成果

已完成可在本機操作的測試平台。使用者從網頁啟動分析，後端執行固定的
Python 示範測試，保存報告並自動更新畫面。現階段測試案例由人工撰寫，
尚未完成 AI 生成到執行的整合。

## 已完成項目

- 示範專案：訂單金額計算與明確功能規格。
- 單元測試：正常金額、超過門檻、恰好滿額與負數輸入。
- 錯誤修正：折扣門檻改為包含 1,000 元，負數金額拋出 ValueError。
- 自動執行器：每次執行建立獨立報告，保存 summary.json、results.xml 與 pytest.log。
- 執行狀態：區分通過、測試失敗、執行錯誤與逾時。
- AI 串接程式：建立 OpenAI Responses API 請求、預覽模式、回應解析與語法檢查。
- 後端：健康檢查、建立分析、查詢單次結果、最近任務清單。
- SQLite：保存 API 任務，重啟後保留完成結果，未完成任務標記為中斷。
- 並行限制：同時只接受一個 API 分析任務，忙碌時回應 409。
- 網頁：啟動測試、設定逾時、狀態自動更新、歷史切換與錯誤紀錄展開。
- 文件：操作 README、專題 PPT、Word 與純文字提案。

## 已驗證結果

- 9 個平台檢查通過，包括 API 輸入驗證、任務衝突、重啟恢復與異常處理。
- API 整合檢查實際執行 pytest 並讀取結果，確認歷史紀錄重啟後仍可查詢。
- 修正後 4 個示範測試通過。修正前曾記錄 2 個通過、2 個失敗。
- 已在瀏覽器操作「啟動測試」，確認執行中狀態自動更新至全部通過。
- AI 預覽模式與離線回應解析檢查通過，沒有呼叫真實模型 API。

網頁驗證截圖：output/CodeSentinel_dashboard.png。
本機執行資料位於 reports/ 與 generated/，不納入 Git。

## 尚未完成與限制

- 尚未設定模型 API 帳號並驗證真實生成結果。
- AI 生成尚未接入網頁，候選測試需人工檢查後再加入 tests/。
- 尚未提供 Docker 隔離、專案上傳、GitHub 自動觸發或多語言支援。
- 尚未將覆蓋率整合至自動執行器與控制台。
- 後端僅供本機單程序使用，沒有登入與公開服務部署機制。
- 現有逾時控制僅終止 pytest 主程序，不是完整的程序樹資源隔離。
- 歷史紀錄尚未保存程式碼快照，不能作為完整的版本品質比較。
- 原始提案 PPT／Word 是規劃文件，進度以本文件與 README 為準。

## 後續開發順序

1. 設定模型與金鑰，實際生成第一份測試並檢查預期結果。
2. 建立 Docker 執行隔離與資源限制，驗證失敗和逾時處理。
3. 將 AI 生成與候選測試檢查流程接入控制台。
4. 彙整覆蓋率與程式版本資訊，支援可追溯的品質比較。
5. 製作帶有已知錯誤的評估資料與可重現展示流程。

## 重現檢查

在專案根目錄執行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s checks -v
.\.venv\Scripts\python.exe run_analysis.py
.\.venv\Scripts\python.exe generate_tests.py --dry-run
```

啟動平台：

```powershell
.\.venv\Scripts\python.exe -m uvicorn api:app --host 127.0.0.1 --port 8000
```

瀏覽器開啟 http://127.0.0.1:8000/ 。
