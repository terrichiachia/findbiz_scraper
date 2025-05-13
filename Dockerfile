# 使用單一階段構建，基於 Python
FROM python:3.11-bullseye
WORKDIR /app

# 設定 pip
RUN mkdir -p /root/.pip && \
    echo "[global]" > /root/.pip/pip.conf && \
    echo "trusted-host = pypi.org files.pythonhosted.org" >> /root/.pip/pip.conf && \
    echo "timeout = 1000" >> /root/.pip/pip.conf

# 安裝基本工具和必要庫
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget gnupg unzip curl ca-certificates \
    fonts-noto-cjk fonts-noto-cjk-extra \
    fonts-arphic-ukai fonts-arphic-uming \
    fonts-ipafont-mincho fonts-ipafont-gothic fonts-unfonts-core \
    xvfb x11vnc fluxbox xterm \
    libnss3 libgconf-2-4 libfontconfig1 libxi6 libxshmfence1 \
    libxtst6 fonts-liberation libasound2 libatk-bridge2.0-0 \
    libatk1.0-0 libgdk-pixbuf2.0-0 libgtk-3-0 libgbm1 && \
    rm -rf /var/lib/apt/lists/*

# 設定 Chrome 源並安裝
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    rm -rf /var/lib/apt/lists/*

# 檢查安裝的 Chrome 版本
RUN CHROME_VERSION=$(google-chrome --version | awk '{print $3}') && \
    echo "Installed Chrome version: $CHROME_VERSION"

# 手動下載和安裝固定版本的 ChromeDriver (使用與 Chrome 版本相容的版本)
RUN DRIVER_VERSION="123.0.6312.58" && \
    mkdir -p /opt/chromedriver-$DRIVER_VERSION && \
    cd /tmp && \
    wget -q https://chromedriver.storage.googleapis.com/$DRIVER_VERSION/chromedriver_linux64.zip && \
    unzip chromedriver_linux64.zip && \
    mv chromedriver /usr/local/bin/chromedriver && \
    chmod +x /usr/local/bin/chromedriver && \
    rm chromedriver_linux64.zip && \
    chromedriver --version || echo "ChromeDriver installation failed, but continuing"

# 創建啟動腳本，用於啟動 Xvfb 和 Chrome 的虛擬顯示服務器
RUN echo '#!/bin/bash' > /usr/local/bin/start-xvfb.sh && \
    echo 'Xvfb :99 -screen 0 1920x1080x24 &' >> /usr/local/bin/start-xvfb.sh && \
    echo 'export DISPLAY=:99' >> /usr/local/bin/start-xvfb.sh && \
    echo 'exec "$@"' >> /usr/local/bin/start-xvfb.sh && \
    chmod +x /usr/local/bin/start-xvfb.sh

# 安裝Python依賴
COPY requirements.txt .
RUN pip --trusted-host pypi.org --trusted-host files.pythonhosted.org --default-timeout=1000 install --upgrade pip && \
    pip --trusted-host pypi.org --trusted-host files.pythonhosted.org --default-timeout=1000 install -r requirements.txt

# 複製專案檔案
COPY . /app/

# 如果有 wait-for-postgres.sh 腳本，則添加執行權限
RUN if [ -f /app/wait-for-postgres.sh ]; then chmod +x /app/wait-for-postgres.sh; fi

# 建立下載資料夾
RUN mkdir -p /app/downloads && chmod 777 /app/downloads

# 環境變數
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:99

# 使用啟動腳本啟動 Xvfb 和程式
ENTRYPOINT ["/usr/local/bin/start-xvfb.sh", "python", "scrape_and_print.py"]