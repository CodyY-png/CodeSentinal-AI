# CodeSentinel AI 開發進度

更新日期：2026 年 11 月 14 日

## 本機模型驗證

透過上傳 API 將成績範例交給 Ollama 的 `qwen2.5-coder:3b`。兩個模組均產生候選測試，
診斷清單均為空。候選斷言涵蓋三個已知錯誤，但缺少匯入，且把正常案例的
平均分數 `86.25` 寫成 `88.5`。補上匯入並修正預期值後，pytest 實際重現
三個錯誤，正常案例通過。報告尚未達到可直接使用的程度。

## 目前成果

網頁可選擇本機 Python 專案，預覽逐模組的 LLM 請求，並啟動 pytest。
候選生成已用模擬回應驗證。真實模型與執行隔離仍待驗證。

## 已完成項目

- 示範專案：訂單金額計算與明確功能規格。
- 單元測試：正常金額、999 元未滿門檻、超過門檻、恰好滿額與負數輸入。
- 錯誤修正：折扣門檻改為包含 1,000 元，負數金額拋出 ValueError。
- 自動執行器：每次執行建立獨立報告，保存 summary.json、results.xml 與 pytest.log。
- 執行狀態：區分通過、測試失敗、執行錯誤與逾時。
- AI 串接程式：可指定 Python 專案，遞迴掃描並逐模組產生請求與候選測試。
- 後端：健康檢查、建立分析、查詢單次結果、最近任務清單。
- SQLite：保存 API 任務，重啟後保留完成結果，未完成任務標記為中斷。
- 並行限制：同時只接受一個 API 分析任務，忙碌時回應 409。
- 網頁：啟動測試、設定逾時、狀態自動更新、歷史切換與錯誤紀錄展開。
- 文件：操作 README、專題 PPT、Word 與純文字提案。

## 已驗證結果

- 11 個平台檢查通過，包含網頁生成 API 的模擬回應及指定專案的 pytest 執行。
- API 整合檢查實際執行 pytest 並讀取結果，確認歷史紀錄重啟後仍可查詢。
- 目前 5 個示範測試通過。第一版修正前曾記錄 2 個通過、2 個失敗。
- 已在瀏覽器操作「啟動測試」，確認執行中狀態自動更新至全部通過。
- AI 預覽模式與離線回應解析檢查通過，沒有呼叫真實模型 API。
- 全專案離線預覽為 api.py、generate_tests.py、run_analysis.py 與 demo_app/order.py 建立請求。
- CLI 與網頁可執行指定專案的 pytest。本倉庫共 16 個測試通過。

網頁驗證截圖：output/CodeSentinel_dashboard.png。
本機執行資料位於 reports/ 與 generated/，不納入 Git。

## 尚未完成與限制

- 尚未設定模型 API 帳號並驗證真實生成結果。
- 網頁已接入專案選擇、逐模組請求預覽與候選生成。候選測試仍需人工檢查後加入專案測試套件。
- 已提供本機 Python ZIP 上傳和無規格診斷。Docker 隔離、帳號權限、GitHub 自動觸發及多語言支援仍待開發。
- 尚未將覆蓋率整合至自動執行器與控制台。
- 後端僅供本機單程序使用，沒有登入與公開服務部署機制。
- 現有逾時控制僅終止 pytest 主程序，不是完整的程序樹資源隔離。
- 歷史紀錄尚未保存程式碼快照，不能作為完整的版本品質比較。
- 原始提案 PPT／Word 是規劃文件，進度以本文件與 README 為準。

## 後續開發順序

1. 設定模型與金鑰，實際生成第一份測試並檢查預期結果。
2. 建立 Docker 執行隔離與資源限制，驗證失敗和逾時處理。
3. 將已核對的候選測試接到隔離執行流程。
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
