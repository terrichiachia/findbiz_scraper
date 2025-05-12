import requests
from bs4 import BeautifulSoup
import time
import uuid

# 設置 headers 模擬瀏覽器
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://findbiz.nat.gov.tw/fts/query/QueryList/queryList.do'
}

# 查詢首頁 URL
base_url = "https://findbiz.nat.gov.tw/fts/query/QueryList/queryList.do"
detail_url = "https://findbiz.nat.gov.tw/fts/query/QueryCmpyDetail/queryCmpyDetail.do"

def get_company_details(ban_no):
    # 使用 Session 保持 cookie 和 session 狀態
    session = requests.Session()
    
    try:
        # 訪問查詢首頁，獲取初始頁面
        response = session.get(base_url, headers=headers)
        response.raise_for_status()
        
        # 模擬表單提交
        payload = {
            'banNo': ban_no,
            'fhl': 'zh_TW',
            'objectId': '',  # 留空，由伺服器生成
            'disj': ''       # 留空，由伺服器生成
        }
        
        # 提交查詢請求，獲取重定向的詳細頁
        response = session.post(base_url, data=payload, headers=headers, allow_redirects=True)
        response.raise_for_status()
        
        # 解析詳細頁 HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 提取公司資料（根據實際 HTML 結構調整）
        company_data = {}
        
        # 假設公司名稱在 <h1> 或某個特定 class
        company_name = soup.select_one('h1') or soup.select_one('.company-name')
        company_data['name'] = company_name.text.strip() if company_name else 'N/A'
        
        # 提取其他欄位（範例：地址、資本額等）
        info_table = soup.select_one('table.company-info')  # 根據實際 class 或結構調整
        if info_table:
            rows = info_table.select('tr')
            for row in rows:
                cols = row.select('td')
                if len(cols) >= 2:
                    key = cols[0].text.strip()
                    value = cols[1].text.strip()
                    company_data[key] = value
        
        return company_data
    
    except requests.RequestException as e:
        print(f"Error fetching data for banNo {ban_no}: {e}")
        return None
    finally:
        session.close()

def main():
    # 測試用 banNo 清單
    ban_nos = ['22099131', '12345678']  # 替換為實際的統一編號清單
    
    for ban_no in ban_nos:
        print(f"\nCrawling data for banNo: {ban_no}")
        data = get_company_details(ban_no)
        if data:
            print("Company Data:")
            for key, value in data.items():
                print(f"{key}: {value}")
        else:
            print(f"No data found for banNo: {ban_no}")
        
        # 避免過快請求，加入延遲
        time.sleep(2)

if __name__ == "__main__":
    main()