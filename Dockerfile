# === 第一階段：建立 Python 套件 wheel ===
FROM python:3.11-slim AS builder
WORKDIR /app

# 安裝用於下載及解壓的工具
RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  wget gnupg unzip curl && \
  rm -rf /var/lib/apt/lists/*

# 複製並打包 Python 依賴
COPY requirements.txt .
RUN pip install --upgrade pip && \
  pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# === 第二階段：最終運行環境 ===
FROM python:3.11-slim
WORKDIR /app

# 安裝 Chrome、中文字型，以及必要底層函式庫
RUN apt-get update && \
  apt-get install -y --no-install-recommends \
  wget gnupg unzip curl \
  libnss3 libgconf-2-4 libfontconfig1 fonts-liberation \
  fonts-noto-cjk fonts-noto-cjk-extra \
  fonts-arphic-ukai fonts-arphic-uming \
  fonts-ipafont-mincho fonts-ipafont-gothic fonts-unfonts-core && \
  # 新增 Google Chrome 的 apt repository
  wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \
  | gpg --dearmor -o /usr/share/keyrings/google-linux-signing-key.gpg && \
  echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-linux-signing-key.gpg] \
  http://dl.google.com/linux/chrome/deb/ stable main" \
  > /etc/apt/sources.list.d/google-chrome.list && \
  apt-get update && \
  apt-get install -y --no-install-recommends google-chrome-stable && \
  rm -rf /var/lib/apt/lists/*

# 偵測 Chrome 版本並下載對應 ChromeDriver
RUN CHROME_VERSION="$(google-chrome --version | awk '{print $3}')" && \
  CHROME_MAJOR="$(echo $CHROME_VERSION | cut -d. -f1)" && \
  echo "Detected Chrome Major Version: $CHROME_MAJOR" && \
  # 取得對應版本的 ChromeDriver
  LATEST=$(curl -s "https://googlechromelabs.github.io/chrome-for-testing/LATEST_RELEASE_${CHROME_MAJOR}") && \
  curl -sSL "https://storage.googleapis.com/chrome-for-testing-public/${LATEST}/linux64/chromedriver-linux64.zip" -o /tmp/chromedriver.zip && \
  unzip /tmp/chromedriver.zip -d /tmp/ && \
  mv /tmp/chromedriver-linux64/chromedriver /usr/local/bin/chromedriver && \
  chmod +x /usr/local/bin/chromedriver && \
  rm -rf /tmp/chromedriver* /tmp/chromedriver-linux64

# 複製並安裝 Python 套件
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --no-cache-dir --find-links /wheels -r requirements.txt && \
  rm -rf /wheels

# 複製程式碼與環境設定檔
COPY scrape_and_print.py . 

# 在 Dockerfile 中添加啟動腳本
COPY wait-for-postgres.sh /app/
RUN chmod +x /app/wait-for-postgres.sh




# 建立下載資料夾並設為 Volume
RUN mkdir -p /app/downloads && chmod 777 /app/downloads
VOLUME [ "/app/downloads" ]

# 環境變數
ENV PYTHONUNBUFFERED=1

# 預設執行指令
ENTRYPOINT ["./wait-for-postgres.sh", "postgres:5432", "--", "python", "scrape_and_print.py"]
