import os
import logging
import time
import re
import base64
import psycopg2
from psycopg2 import sql
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

DB_CONFIG = {
    "dbname": os.environ.get("POSTGRES_DB", "company_data"),
    "user": os.environ.get("POSTGRES_USER", "postgres"),
    "password": os.environ.get("POSTGRES_PASSWORD", "1234"),
    "host": os.environ.get("POSTGRES_HOST", "postgres"),  # Docker 內部服務名
    "port": os.environ.get("POSTGRES_PORT", "5432"),
}

default_url = (
    f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}"
)

DATABASE_URL = os.getenv("DATABASE_URL", default_url)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


# 設定日誌記錄
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def setup_driver():
    """設置 WebDriver，適用於 Docker 環境"""
    options = webdriver.ChromeOptions()

    # Docker 環境下的必需選項
    options.add_argument("--headless")  # Docker 中必須使用無頭模式
    options.add_argument("--no-sandbox")  # 避免沙箱問題
    options.add_argument("--disable-dev-shm-usage")  # 避免共享內存有限問題
    options.add_argument("--disable-gpu")  # 禁用 GPU 硬件加速
    options.add_argument("--window-size=1920,1080")

    # 啟用 Chrome 的 print-to-pdf 功能
    options.add_argument("--enable-print-browser")
    options.add_argument("--kiosk-printing")  # 啟用靜默列印

    # 設置用戶代理
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    # Docker 中直接使用 ChromeDriver
    try:
        driver = webdriver.Chrome(options=options)
        return driver
    except Exception as e:
        logging.error(f"無法創建 Chrome WebDriver: {e}")

        # 嘗試指定 ChromeDriver 路徑
        try:
            # Docker 中 ChromeDriver 的可能路徑
            driver_paths = [
                "/usr/bin/chromedriver",
                "/usr/local/bin/chromedriver",
                "/opt/chromedriver",
                "/opt/selenium/chromedriver",
            ]

            for path in driver_paths:
                if os.path.exists(path):
                    logging.info(f"嘗試使用 ChromeDriver 路徑: {path}")
                    driver = webdriver.Chrome(executable_path=path, options=options)
                    return driver

            # 如果上面都失敗，嘗試使用預設的 Remote WebDriver
            logging.info("嘗試連接到 Selenium 伺服器...")
            driver = webdriver.Remote(
                command_executor="http://selenium:4444/wd/hub",  # 標準 Selenium Grid URL
                options=options,
            )
            return driver
        except Exception as e2:
            logging.error(f"所有 WebDriver 嘗試都失敗: {e2}")
            raise


def create_output_directory(subdirectory=""):
    """
    創建輸出目錄，設置為當前工作目錄中的 downloads 資料夾

    Args:
        subdirectory: 可選的子目錄名稱，將在 downloads 目錄中創建

    Returns:
        創建的目錄路徑
    """
    # 獲取當前工作目錄
    current_dir = os.getcwd()

    # 創建主要的 downloads 目錄
    downloads_dir = os.path.join(current_dir, "downloads")
    if not os.path.exists(downloads_dir):
        os.makedirs(downloads_dir)
        logging.info(f"創建主要輸出目錄: {downloads_dir}")

    # 如果指定了子目錄，則在 downloads 中創建子目錄
    if subdirectory:
        output_dir = os.path.join(downloads_dir, subdirectory)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            logging.info(f"創建子輸出目錄: {output_dir}")
        return output_dir

    return downloads_dir


def print_friendly_to_pdf(driver, output_filename):
    """
    點擊網頁中的"友善列印"按鈕，然後將結果保存為PDF

    Args:
        driver: Selenium WebDriver 實例
        output_filename: 輸出的PDF檔名
    """
    logging.info(f"正在使用網頁的友善列印功能生成PDF: {output_filename}")

    try:
        # 尋找頁面上的"友善列印"連結並點擊
        friendly_print_btn = driver.find_element(By.ID, "friendlyPrint")
        logging.info("找到友善列印按鈕，準備點擊")
        driver.execute_script("arguments[0].click();", friendly_print_btn)

        # 等待"友善列印"視圖加載完成
        time.sleep(5)  # 給予足夠時間加載列印視圖

        # 檢查是否有列印視圖元素出現，確認列印視圖已加載
        try:
            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.ID, "printArea"))
            )
            logging.info("列印視圖已加載")
        except:
            logging.warning("無法確認列印視圖是否已加載，但仍將繼續")

        # 使用Chrome的列印功能將當前頁面保存為PDF
        logging.info("開始將頁面保存為PDF")

        # 設置列印選項
        print_options = {
            "landscape": False,  # 縱向列印
            "displayHeaderFooter": False,  # 不顯示頁眉和頁腳
            "printBackground": True,  # 列印背景圖像
            "preferCSSPageSize": True,  # 優先使用CSS頁面尺寸
            "scale": 1.0,  # 縮放比例
            "paperWidth": 8.27,  # A4紙寬度（英寸）
            "paperHeight": 11.69,  # A4紙高度（英寸）
            "marginTop": 0.4,  # 上邊距（英寸）
            "marginBottom": 0.4,  # 下邊距（英寸）
            "marginLeft": 0.4,  # 左邊距（英寸）
            "marginRight": 0.4,  # 右邊距（英寸）
            "pageRanges": "",  # 留空表示列印所有頁面
        }

        # 執行列印命令
        result = driver.execute_cdp_cmd("Page.printToPDF", print_options)

        # 將Base64編碼的PDF數據寫入檔案
        with open(output_filename, "wb") as f:
            f.write(base64.b64decode(result["data"]))

        logging.info(f"PDF已成功保存到: {output_filename}")
        return True

    except Exception as e:
        logging.error(f"生成PDF時發生錯誤: {e}")
        return False


from sqlalchemy import create_engine, text
import os, logging


def init_database():
    """
    使用 SQLAlchemy Engine 建立所需的 PostgreSQL 表格（若不存在則創建）。
    全部操作包在同一個 transaction 裡，確保原子性。
    """
    try:
        with engine.begin() as conn:
            # 1. companies
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                registration_number VARCHAR(8) UNIQUE NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                registration_authority VARCHAR(255),
                registration_status VARCHAR(50),
                address TEXT,
                data_type VARCHAR(50),
                approval_date VARCHAR(50),
                last_change_date VARCHAR(50),
                capital_amount NUMERIC,
                paid_in_capital NUMERIC,
                share_value NUMERIC,
                issued_shares NUMERIC,
                representative VARCHAR(100),
                foreign_company_name TEXT,
                special_shares_status TEXT,
                veto_shares_status TEXT,
                business_items TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
                )
            )

            # 2. directors
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS directors (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                sequence_number VARCHAR(10),
                position VARCHAR(100),
                name VARCHAR(100),
                representing_entity TEXT,
                shares_held NUMERIC,
                tenure_info TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
                )
            )

            # 3. managers
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS managers (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                sequence_number VARCHAR(10),
                name VARCHAR(100),
                appointment_date VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
                )
            )

            # 4. branch_companies
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS branch_companies (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                sequence_number VARCHAR(10),
                registration_number VARCHAR(8),
                branch_name VARCHAR(255),
                registration_status VARCHAR(50),
                approval_date VARCHAR(50),
                last_change_date VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
                )
            )

            # 5. factories
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS factories (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                sequence_number VARCHAR(10),
                registration_number VARCHAR(20),
                factory_name VARCHAR(255),
                registration_status VARCHAR(50),
                approval_date VARCHAR(50),
                last_change_date VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
                )
            )

            # 6. pdf_files
            conn.execute(
                text(
                    """
            CREATE TABLE IF NOT EXISTS pdf_files (
                id SERIAL PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
                file_name VARCHAR(255),
                file_path TEXT,
                file_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
                )
            )

        logging.info("資料庫表已成功創建或已存在")
        return True

    except Exception as e:
        logging.error(f"初始化資料庫失敗: {e}")
        return False


def save_to_database(company_data, registration_number, pdf_path=None):
    """
    用 SQLAlchemy Engine 將公司資料寫入或更新到 PostgreSQL 資料庫。

    Args:
        company_data: dict，包含 keys:
            '基本資料', '詳細基本資料',
            '董監事資料', '經理人資料', '分公司資料', '工廠資料'
        registration_number: str，8 位統一編號
        pdf_path: str or None，若使用「友善列印」生成 PDF 的檔案路徑
    """
    try:
        with engine.begin() as conn:
            # 1. 準備公司基本資料
            basic_info = company_data.get("基本資料", {})
            detailed_info = company_data.get("詳細基本資料", {})
            company_info = {**basic_info, **detailed_info}

            # 清理並組裝要寫入 companies 的欄位
            company_values = {
                "registration_number": registration_number,
                "company_name": company_info.get("公司名稱", ""),
                "registration_authority": company_info.get("登記機關", ""),
                "registration_status": company_info.get("登記現況", ""),
                "address": company_info.get("公司所在地", ""),
                "data_type": company_info.get("資料種類", ""),
                "approval_date": company_info.get("核准設立日期", ""),
                "last_change_date": company_info.get("最後核准變更日期", ""),
                "capital_amount": company_info.get("資本總額(元)", "").replace(",", "")
                or None,
                "paid_in_capital": company_info.get("實收資本額(元)", "").replace(
                    ",", ""
                )
                or None,
                "share_value": company_info.get("每股金額(元)", "") or None,
                "issued_shares": company_info.get("已發行股份總數(股)", "").replace(
                    ",", ""
                )
                or None,
                "representative": company_info.get("代表人姓名", ""),
                "foreign_company_name": company_info.get("章程所訂外文公司名稱", ""),
                "special_shares_status": company_info.get("複數表決權特別股", ""),
                "veto_shares_status": company_info.get(
                    "對於特定事項具否決權特別股", ""
                ),
                "business_items": company_info.get("所營事業資料", "").replace(
                    "\n", " "
                ),
            }

            # 2. Upsert companies
            result = conn.execute(
                text("SELECT id FROM companies WHERE registration_number = :no"),
                {"no": registration_number},
            )
            row = result.first()

            if row:
                company_id = row.id
                # update
                conn.execute(
                    text(
                        """
                    UPDATE companies
                       SET company_name = :company_name,
                           registration_authority = :registration_authority,
                           registration_status = :registration_status,
                           address = :address,
                           data_type = :data_type,
                           approval_date = :approval_date,
                           last_change_date = :last_change_date,
                           capital_amount = :capital_amount,
                           paid_in_capital = :paid_in_capital,
                           share_value = :share_value,
                           issued_shares = :issued_shares,
                           representative = :representative,
                           foreign_company_name = :foreign_company_name,
                           special_shares_status = :special_shares_status,
                           veto_shares_status = :veto_shares_status,
                           business_items = :business_items,
                           updated_at = CURRENT_TIMESTAMP
                     WHERE id = :id
                """
                    ),
                    {**company_values, "id": company_id},
                )
            else:
                # insert
                result = conn.execute(
                    text(
                        """
                    INSERT INTO companies (
                        registration_number, company_name, registration_authority,
                        registration_status, address, data_type,
                        approval_date, last_change_date, capital_amount,
                        paid_in_capital, share_value, issued_shares,
                        representative, foreign_company_name,
                        special_shares_status, veto_shares_status, business_items
                    ) VALUES (
                        :registration_number, :company_name, :registration_authority,
                        :registration_status, :address, :data_type,
                        :approval_date, :last_change_date, :capital_amount,
                        :paid_in_capital, :share_value, :issued_shares,
                        :representative, :foreign_company_name,
                        :special_shares_status, :veto_shares_status, :business_items
                    ) RETURNING id
                """
                    ),
                    company_values,
                )
                company_id = result.scalar()

            # 3. 董監事（directors）
            conn.execute(
                text("DELETE FROM directors WHERE company_id = :cid"),
                {"cid": company_id},
            )
            directors = company_data.get("董監事資料", [])
            # 任期資訊
            tenure = next((d["任期資訊"] for d in directors if "任期資訊" in d), "")
            directors = [d for d in directors if "任期資訊" not in d]
            for d in directors:
                dv = {
                    "company_id": company_id,
                    "sequence_number": d.get("序號"),
                    "position": d.get("職稱"),
                    "name": d.get("姓名"),
                    "representing_entity": d.get("所代表法人"),
                    "shares_held": d.get("持有股份數(股)", "").replace(",", "") or None,
                    "tenure_info": tenure,
                }
                conn.execute(
                    text(
                        """
                    INSERT INTO directors (
                        company_id, sequence_number, position, name,
                        representing_entity, shares_held, tenure_info
                    ) VALUES (
                        :company_id, :sequence_number, :position, :name,
                        :representing_entity, :shares_held, :tenure_info
                    )
                """
                    ),
                    dv,
                )

            # 4. 經理人（managers）
            conn.execute(
                text("DELETE FROM managers WHERE company_id = :cid"),
                {"cid": company_id},
            )
            for m in company_data.get("經理人資料", []):
                mv = {
                    "company_id": company_id,
                    "sequence_number": m.get("序號"),
                    "name": m.get("姓名"),
                    "appointment_date": m.get("到職日期"),
                }
                conn.execute(
                    text(
                        """
                    INSERT INTO managers (
                        company_id, sequence_number, name, appointment_date
                    ) VALUES (
                        :company_id, :sequence_number, :name, :appointment_date
                    )
                """
                    ),
                    mv,
                )

            # 5. 分公司（branch_companies）
            conn.execute(
                text("DELETE FROM branch_companies WHERE company_id = :cid"),
                {"cid": company_id},
            )
            branches = company_data.get("分公司資料", [])
            if branches != ["查無符合結果"]:
                for idx, b in enumerate(branches, 1):
                    bv = {
                        "company_id": company_id,
                        "sequence_number": b.get("序號") or str(idx),
                        "registration_number": b.get("統一編號"),
                        "branch_name": b.get("分公司名稱"),
                        "registration_status": b.get("登記現況"),
                        "approval_date": b.get("分公司核准設立日期"),
                        "last_change_date": b.get("最後核准變更日期"),
                    }
                    conn.execute(
                        text(
                            """
                        INSERT INTO branch_companies (
                            company_id, sequence_number, registration_number,
                            branch_name, registration_status,
                            approval_date, last_change_date
                        ) VALUES (
                            :company_id, :sequence_number, :registration_number,
                            :branch_name, :registration_status,
                            :approval_date, :last_change_date
                        )
                    """
                        ),
                        bv,
                    )

            # 6. 工廠（factories）
            conn.execute(
                text("DELETE FROM factories WHERE company_id = :cid"),
                {"cid": company_id},
            )
            factories = company_data.get("工廠資料", [])
            if factories != ["查無符合結果"]:
                for f in factories:
                    fv = {
                        "company_id": company_id,
                        "sequence_number": f.get("序號"),
                        "registration_number": f.get("登記編號"),
                        "factory_name": f.get("工廠名稱"),
                        "registration_status": f.get("登記現況"),
                        "approval_date": f.get("工廠登記核准日期"),
                        "last_change_date": f.get("最後核准變更日期"),
                    }
                    conn.execute(
                        text(
                            """
                        INSERT INTO factories (
                            company_id, sequence_number, registration_number,
                            factory_name, registration_status,
                            approval_date, last_change_date
                        ) VALUES (
                            :company_id, :sequence_number, :registration_number,
                            :factory_name, :registration_status,
                            :approval_date, :last_change_date
                        )
                    """
                        ),
                        fv,
                    )

            # 7. PDF 檔案紀錄（pdf_files）
            if pdf_path:
                exists = conn.execute(
                    text(
                        """
                    SELECT id FROM pdf_files 
                     WHERE company_id = :cid AND file_path = :fp
                """
                    ),
                    {"cid": company_id, "fp": pdf_path},
                ).first()

                if not exists:
                    pf = {
                        "company_id": company_id,
                        "file_name": os.path.basename(pdf_path),
                        "file_path": pdf_path,
                        "file_type": "complete_info",
                    }
                    conn.execute(
                        text(
                            """
                        INSERT INTO pdf_files (
                            company_id, file_name, file_path, file_type
                        ) VALUES (
                            :company_id, :file_name, :file_path, :file_type
                        )
                    """
                        ),
                        pf,
                    )

        logging.info(f"已成功將統一編號 {registration_number} 的資料保存到資料庫")
    except Exception as e:
        logging.error(f"保存資料到資料庫時發生錯誤: {e}")


def extract_search_result_info(soup):
    """從搜尋結果頁面提取基本資訊"""
    info = {}
    try:
        # 嘗試提取新版清單格式資料
        vParagraph = soup.select_one("#vParagraph")
        if vParagraph:
            panel = vParagraph.select_one(".panel")
            if panel:
                # 提取公司名稱
                company_name = panel.select_one(".panel-heading a")
                if company_name:
                    info["公司名稱"] = company_name.get_text(strip=True)

                # 提取其他資訊
                details_div = panel.select_one('div[style="padding: 5px 10px;"]')
                if details_div:
                    text = details_div.get_text(separator=",").strip()
                    parts = [part.strip() for part in text.split(",")]

                    for part in parts:
                        if ":" in part:
                            key, value = part.split(":", 1)
                            info[key.strip()] = value.strip()
                        elif "：" in part:
                            key, value = part.split("：", 1)
                            info[key.strip()] = value.strip()
    except Exception as e:
        logging.error(f"提取搜尋結果頁資訊時發生錯誤: {e}")
    return info


def extract_company_base_info(soup):
    """從公司基本資料頁籤提取資訊"""
    info = {}
    try:
        table = soup.select_one("#tabCmpyContent table.table")
        if table:
            rows = table.select("tr")
            for row in rows:
                cells = row.select("td")
                if len(cells) >= 2:
                    key = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    info[key] = value
    except Exception as e:
        logging.error(f"提取公司基本資料時發生錯誤: {e}")
    return info


def extract_shareholder_info(soup):
    """從董監事資料頁籤提取資訊"""
    info = []
    try:
        # 提取任期資訊
        tenure_div = soup.select_one(
            "#tabShareHolderContent div:not(.table-responsive)"
        )
        if tenure_div:
            tenure_text = tenure_div.get_text(strip=True)
            info.append({"任期資訊": tenure_text})

        # 提取董監事列表
        table = soup.select_one("#tabShareHolderContent .table-responsive table.table")
        if table:
            headers = [th.get_text(strip=True) for th in table.select("thead th")]
            rows = table.select("tbody tr")

            for row in rows:
                # 跳過分頁資訊的行
                if row.select_one("td[colspan]"):
                    continue

                cells = row.select("td")
                if len(cells) >= 4:  # 確保有足夠的列
                    shareholder = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            shareholder[headers[i]] = cell.get_text(strip=True)
                    if shareholder:
                        info.append(shareholder)
    except Exception as e:
        logging.error(f"提取董監事資料時發生錯誤: {e}")
    return info


def extract_manager_info(soup):
    """從經理人資料頁籤提取資訊"""
    info = []
    try:
        table = soup.select_one("#tabMgrContent .table-responsive table.table")
        if table:
            headers = [th.get_text(strip=True) for th in table.select("thead th")]
            rows = table.select("tbody tr")

            for row in rows:
                # 跳過分頁資訊的行
                if row.select_one("td[colspan]"):
                    continue

                cells = row.select("td")
                if len(cells) >= 3:  # 確保有足夠的列
                    manager = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            manager[headers[i]] = cell.get_text(strip=True)
                    if manager:
                        info.append(manager)
    except Exception as e:
        logging.error(f"提取經理人資料時發生錯誤: {e}")
    return info


def extract_branch_info(soup):
    """從分公司資料頁籤提取資訊"""
    info = []
    try:
        table = soup.select_one("#tabBrCmpyContent .table-responsive table.table")
        if table:
            # 檢查是否有「查無符合結果」的訊息
            no_result = table.select_one('tr td[colspan="6"]')
            if no_result and "查無符合結果" in no_result.get_text():
                return ["查無符合結果"]

            headers = [th.get_text(strip=True) for th in table.select("thead th")]
            rows = table.select("tbody tr")

            for row in rows:
                # 跳過分頁資訊的行
                if row.select_one("td[colspan]"):
                    continue

                cells = row.select("td")
                if len(cells) >= 6:  # 確保有足夠的列
                    branch = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            branch[headers[i]] = cell.get_text(strip=True)
                    if branch:
                        info.append(branch)
    except Exception as e:
        logging.error(f"提取分公司資料時發生錯誤: {e}")
    return info


def extract_factory_info(soup):
    """從工廠資料頁籤提取資訊"""
    info = []
    try:
        table = soup.select_one("#tabFactoryContent .table-responsive table.table")
        if table:
            # 檢查是否有「查無符合結果」的訊息
            no_result = table.select_one('tr td[colspan="6"]')
            if no_result and "查無符合結果" in no_result.get_text():
                return ["查無符合結果"]

            headers = [th.get_text(strip=True) for th in table.select("thead th")]
            rows = table.select("tbody tr")

            for row in rows:
                # 跳過分頁資訊的行
                if row.select_one('td[colspan="6"]'):
                    continue

                cells = row.select("td")
                if len(cells) >= 6:  # 確保有足夠的列
                    factory = {}
                    for i, cell in enumerate(cells):
                        if i < len(headers):
                            # 如果是工廠名稱欄位，從連結中提取純文字
                            if i == 2:  # 假設第三欄是工廠名稱
                                factory_link = cell.select_one("a")
                                if factory_link:
                                    factory[headers[i]] = factory_link.get_text(
                                        strip=True
                                    )
                                else:
                                    factory[headers[i]] = cell.get_text(strip=True)
                            else:
                                factory[headers[i]] = cell.get_text(strip=True)
                    if factory:
                        info.append(factory)
    except Exception as e:
        logging.error(f"提取工廠資料時發生錯誤: {e}")
    return info


def query_company(registration_number):
    if not registration_number.isdigit() or len(registration_number) != 8:
        logging.error("統一編號無效。")
        return None

    driver = None
    try:
        driver = setup_driver()

        # 步驟 1: 前往搜尋頁面
        logging.info("前往網站...")
        driver.get("https://findbiz.nat.gov.tw/fts/query/QueryBar/queryInit.do")

        # 等待頁面加載
        wait = WebDriverWait(driver, 20)

        # 檢查是否需要同意條款
        try:
            agree_button = wait.until(EC.element_to_be_clickable((By.ID, "agree")))
            logging.info("點擊同意按鈕...")
            agree_button.click()
        except (TimeoutException, NoSuchElementException):
            logging.info("無需點擊同意按鈕")

        # 輸入統一編號
        logging.info("等待輸入欄位...")
        input_el = wait.until(EC.element_to_be_clickable((By.ID, "qryCond")))
        input_el.clear()
        input_el.send_keys(registration_number)

        # 點擊查詢按鈕
        logging.info("點擊查詢按鈕...")
        driver.find_element(By.ID, "qryBtn").click()

        # 等待結果頁面加載
        logging.info("等待結果面板...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".panel-heading")))

        # 確保頁面完全加載
        time.sleep(2)

        # 嘗試提取基本資料
        logging.info("先提取搜尋結果頁的基本資訊...")
        html = driver.page_source
        soup = BeautifulSoup(html, "lxml")
        basic_info = extract_search_result_info(soup)

        # 嘗試多種方法點擊詳細資料連結
        logging.info("尋找詳細資料連結...")
        detail_link_clicked = False

        # 方法1: 透過類別選擇器
        try:
            detail_span = wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "span.moreLinkMouseOut"))
            )
            logging.info("點擊詳細資料連結(方法1)...")
            driver.execute_script("arguments[0].click();", detail_span)
            detail_link_clicked = True
        except Exception as e:
            logging.warning(f"方法1點擊詳細資料連結失敗: {e}")

        # 方法2: 透過文字內容
        if not detail_link_clicked:
            try:
                detail_span = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, "//span[contains(text(), '詳細資料')]")
                    )
                )
                logging.info("點擊詳細資料連結(方法2)...")
                driver.execute_script("arguments[0].click();", detail_span)
                detail_link_clicked = True
            except Exception as e:
                logging.warning(f"方法2點擊詳細資料連結失敗: {e}")

        # 方法3: 直接透過詳細資料頁URL進入
        if not detail_link_clicked:
            logging.info("嘗試透過直接訪問URL獲取詳細資料(方法3)...")
            driver.get(
                f"https://findbiz.nat.gov.tw/fts/query/QueryCmpyDetail/queryCmpyDetail.do?banNo={registration_number}"
            )
            detail_link_clicked = True

        # 等待詳細資料頁面加載
        logging.info("等待詳細資料頁面加載...")
        try:
            # 等待頁籤加載完成
            wait.until(EC.presence_of_element_located((By.ID, "tabCmpy")))
            time.sleep(2)
        except TimeoutException:
            logging.error("無法加載詳細資料頁面，可能頁面結構已更改或網站無回應")
            # 保存當前頁面以便調試
            with open("error_page_detail.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)

            # 如果無法加載詳細資料頁面，則只返回基本資訊
            return {"基本資料": basic_info}

        # 步驟 4: 提取公司的各種資訊
        company_data = {}
        company_data["基本資料"] = basic_info  # 保留搜尋結果頁的基本資訊

        # 提取詳細頁的基本資料
        logging.info("提取公司詳細基本資料...")
        html = driver.page_source
        soup = BeautifulSoup(html, "lxml")
        company_data["詳細基本資料"] = extract_company_base_info(soup)

        # 點擊「董監事資料」頁籤並提取資訊
        try:
            logging.info("提取董監事資料...")
            tab_share_holder = driver.find_element(By.ID, "tabShareHolder")
            driver.execute_script("arguments[0].click();", tab_share_holder)
            time.sleep(2)
            html = driver.page_source
            soup = BeautifulSoup(html, "lxml")
            company_data["董監事資料"] = extract_shareholder_info(soup)
        except Exception as e:
            logging.error(f"提取董監事資料時發生錯誤: {e}")
            company_data["董監事資料"] = []

        # 點擊「經理人資料」頁籤並提取資訊
        try:
            logging.info("提取經理人資料...")
            tab_mgr = driver.find_element(By.ID, "tabMgr")
            driver.execute_script("arguments[0].click();", tab_mgr)
            time.sleep(2)
            html = driver.page_source
            soup = BeautifulSoup(html, "lxml")
            company_data["經理人資料"] = extract_manager_info(soup)
        except Exception as e:
            logging.error(f"提取經理人資料時發生錯誤: {e}")
            company_data["經理人資料"] = []

        # 點擊「分公司資料」頁籤並提取資訊
        try:
            logging.info("提取分公司資料...")
            tab_br_cmpy = driver.find_element(By.ID, "tabBrCmpy")
            driver.execute_script("arguments[0].click();", tab_br_cmpy)
            time.sleep(2)
            html = driver.page_source
            soup = BeautifulSoup(html, "lxml")
            company_data["分公司資料"] = extract_branch_info(soup)
        except Exception as e:
            logging.error(f"提取分公司資料時發生錯誤: {e}")
            company_data["分公司資料"] = []

        # 點擊「工廠資料」頁籤並提取資訊
        try:
            logging.info("提取工廠資料...")
            tab_factory = driver.find_element(By.ID, "tabFactory")
            driver.execute_script("arguments[0].click();", tab_factory)
            time.sleep(2)
            html = driver.page_source
            soup = BeautifulSoup(html, "lxml")
            company_data["工廠資料"] = extract_factory_info(soup)

            # 頁面可能有分頁，處理下一頁工廠資料
            logging.info("檢查工廠資料是否有多頁...")

            # 更精確地解析分頁資訊
            pagination = soup.select_one("ul.pagination")
            if pagination:
                # 嘗試找到最後一頁的數字
                last_page_num = 1

                # 方法1: 尋找最後一頁链接前的文字 (通常此頁會是最大頁碼)
                last_page_link = pagination.select_one("li:nth-last-child(2) a")
                if last_page_link and last_page_link.get_text(strip=True).isdigit():
                    last_page_num = int(last_page_link.get_text(strip=True))

                # 方法2: 尋找所有數字链接，找出最大的
                if last_page_num == 1:  # 如果方法1沒找到
                    for link in pagination.select("li a"):
                        link_text = link.get_text(strip=True)
                        if link_text.isdigit():
                            page_num = int(link_text)
                            if page_num > last_page_num:
                                last_page_num = page_num

                # 方法3: 從分頁信息文字中提取(例如 "共39筆、分2頁")
                if last_page_num == 1:  # 如果前兩種方法都沒找到
                    pagination_info = soup.select_one('tr td[colspan="6"]')
                    if pagination_info:
                        pagination_text = pagination_info.get_text(strip=True)
                        match = re.search(r"共\d+筆、分(\d+)頁", pagination_text)
                        if match:
                            last_page_num = int(match.group(1))

                logging.info(f"工廠資料共 {last_page_num} 頁")

                # 從第2頁開始處理（第1頁已經處理過）
                if last_page_num > 1:
                    for page_num in range(2, last_page_num + 1):
                        try:
                            logging.info(f"提取工廠資料第 {page_num} 頁...")

                            # 嘗試多種方式點擊頁碼
                            clicked = False

                            # 方法1: 直接點擊數字頁碼
                            try:
                                page_link = driver.find_element(
                                    By.XPATH,
                                    f"//ul[contains(@class, 'pagination')]/li/a[text()='{page_num}']",
                                )
                                driver.execute_script(
                                    "arguments[0].click();", page_link
                                )
                                clicked = True
                            except Exception as e:
                                logging.warning(
                                    f"無法通過數字點擊第 {page_num} 頁: {e}"
                                )

                            # 方法2: 使用 gotoPageFact 函數 (通過 JavaScript 直接調用)
                            if not clicked:
                                try:
                                    logging.info(
                                        f"嘗試使用 gotoPageFact 函數點擊第 {page_num} 頁..."
                                    )
                                    driver.execute_script(f"gotoPageFact({page_num});")
                                    clicked = True
                                except Exception as e:
                                    logging.warning(f"無法使用 gotoPageFact 函數: {e}")

                            if clicked:
                                # 等待頁面加載
                                time.sleep(2)
                                wait.until(
                                    EC.presence_of_element_located(
                                        (
                                            By.CSS_SELECTOR,
                                            "#tabFactoryContent .table-responsive table.table",
                                        )
                                    )
                                )

                                html = driver.page_source
                                soup = BeautifulSoup(html, "lxml")
                                additional_factory_info = extract_factory_info(soup)
                                company_data["工廠資料"].extend(additional_factory_info)
                            else:
                                logging.error(
                                    f"無法點擊到第 {page_num} 頁，嘗試了所有可能的方法"
                                )
                                break

                        except Exception as e:
                            logging.warning(
                                f"提取工廠資料第 {page_num} 頁時發生錯誤: {e}"
                            )
            else:
                logging.info("工廠資料只有一頁或無分頁導航")
        except Exception as e:
            logging.error(f"提取工廠資料時發生錯誤: {e}")
            company_data["工廠資料"] = []

        # 使用網頁的友善列印功能生成PDF
        output_dir = create_output_directory(registration_number)
        pdf_filename = os.path.join(
            output_dir, f"company_{registration_number}_complete.pdf"
        )
        pdf_generated = print_friendly_to_pdf(driver, pdf_filename)

        # 保存資料到資料庫
        if pdf_generated:
            save_to_database(company_data, registration_number, pdf_filename)
        else:
            save_to_database(company_data, registration_number)

        return company_data

    except Exception as e:
        logging.error(f"錯誤: {e}")
        # 保存頁面內容以便調試
        if driver:
            try:
                html = driver.page_source
                with open("error_page.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logging.info("已將錯誤頁面保存到 error_page.html")
            except:
                pass
        return None

    finally:
        if driver:
            driver.quit()


def main():
    """
    主程序入口
    """
    try:
        # 初始化資料庫
        conn = init_database()
        if not conn:
            logging.error("無法初始化資料庫，程序終止")
            return

        # 查詢台積電
        registration_number = "22099131"
        logging.info(f"開始查詢統一編號為 {registration_number} 的公司資料")

        company_data = query_company(registration_number)

        if company_data:
            logging.info("成功提取公司詳細資料，資料已保存到資料庫")
        else:
            logging.error("無法獲取公司詳細資料")

    except Exception as e:
        logging.error(f"主程序執行錯誤: {e}")


# 參數化爬蟲程式
def batch_query_companies(registration_numbers):
    """
    批量查詢公司資料

    Args:
        registration_numbers: 統一編號列表
    """
    try:
        # 初始化資料庫
        conn = init_database()
        if not conn:
            logging.error("無法初始化資料庫，程序終止")
            return

        for registration_number in registration_numbers:
            logging.info(f"開始查詢統一編號為 {registration_number} 的公司資料")

            try:
                company_data = query_company(registration_number)

                if company_data:
                    logging.info(
                        f"成功提取統一編號為 {registration_number} 的公司詳細資料，資料已保存到資料庫"
                    )
                else:
                    logging.error(
                        f"無法獲取統一編號為 {registration_number} 的公司詳細資料"
                    )

                # 間隔一段時間，避免頻繁請求
                time.sleep(5)
            except Exception as e:
                logging.error(
                    f"查詢統一編號為 {registration_number} 的公司資料時發生錯誤: {e}"
                )
                continue

    except Exception as e:
        logging.error(f"批量查詢程序執行錯誤: {e}")


if __name__ == "__main__":
    # 執行單一公司查詢
    # main()

    # 或者批量查詢多家公司
    companies_to_query = [
        "22099131",  # 台積電
        "04595600",  # 中油
        "84149786",  # 中華電信
        "86517384",  # 富邦金控
        "12345678",  # 錯誤的統編
        "04793480",  # 統一超商
        "23757560",  # 全家便利商店
        "11111111",  # 錯誤的統編
        "06501701",  # 遠東百貨
        "83007252",  # 台北捷運
    ]
    batch_query_companies(companies_to_query)
