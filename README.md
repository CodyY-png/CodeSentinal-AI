# CodeSentinel AI：第一階段

目標：先理解「規格 → 測試 → 發現錯誤 → 修正 → 再測試」。
目前尚未串接 AI，也尚未建立網頁。demo_app/order.py 刻意保留兩個錯誤。

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

預期 2 個通過、2 個失敗。滿額門檻與負數驗證的測試應失敗。
測試失敗時，指令結束碼為 1，是這次示範的預期結果。

## 4. 修正程式

把 demo_app/order.py 改成：

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

下一階段：把執行指令包成自動執行器，再串接 AI 生成測試。
