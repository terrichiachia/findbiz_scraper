# 台灣公司資料爬蟲

這個專案是一個自動化工具，用於從台灣商業司公司登記資料網站 (https://findbiz.nat.gov.tw) 爬取公司資訊。爬蟲會根據統一編號抓取公司基本資料、董監事資料、經理人資料、分公司資料和工廠資料，並儲存到 PostgreSQL 資料庫。

## 功能特色

- 根據統一編號查詢公司資訊
- 完整擷取各項公司登記資料
- 支援批次查詢多家公司
- 自動儲存查詢結果至資料庫
- 自動產生友善列印 PDF 檔案
- 完整的錯誤處理和日誌記錄
- 使用 Docker 容器化方便部署

## 系統需求

- Docker 和 Docker Compose
- 網際網路連線

## 快速開始

### 使用 Docker Compose 運行

1. 複製專案到本地
   ```bash
   git clone https://github.com/terrichiachia/findbiz_scraper.git
   cd findbiz_scraper
   ```
2. 啟動服務
   ```bash
   docker-compose up -d
   ```
3. 運行爬蟲查詢特定公司
    ```bash
    # 查詢單一公司
    docker-compose run --rm scraper python -c "from scraper import query_company; print(query_company('22099131'))"

    # 或執行批次查詢腳本
    docker-compose run --rm scraper python scrape_and_print.py
    ```
4. 查看日誌
    ```bash
    docker-compose logs -f scraper
    ```
5. 停止服務
    ```bash
    docker-compose down
    ```
## 設定參數
編輯 `docker-compose.yml` 文件來修改資料庫連線設定:
    ```bash
    services:
  scraper:
    environment:
      - POSTGRES_DB=company_data
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=1234
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
    ```
## 自訂查詢公司清單
編輯 `scrape_and_print.py` 檔案中的 `companies_to_query` 列表來設定要查詢的公司統一編號:
    ```python
    companies_to_query = [
        "22178368", # 微星科技
        "22099131", # 台灣積體電路製造股份有限公司
        "84149961", # 聯發科
        "22555003", # 統一超商
        "04351626", # 光泉牧場
        "11768704", # 義美
        "71620635", # 可果美
        "03707901", # 中油
        "73008303", # 大成長城
        "11111111" # 測試
        ]
    ```