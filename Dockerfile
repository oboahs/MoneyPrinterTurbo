# Use an official Python runtime as a parent image
FROM python:3.11-slim-bullseye

# Set the working directory in the container
WORKDIR /MoneyPrinterTurbo

# 设置/MoneyPrinterTurbo目录权限为777
RUN chmod 777 /MoneyPrinterTurbo

ENV PYTHONPATH="/MoneyPrinterTurbo"
ENV PLAYWRIGHT_BROWSERS_PATH="/opt/patchright-browsers"

# 本地用户默认继续优先使用国内镜像；GitHub Actions 发布 GHCR 镜像时使用 default，
# 避免海外 runner 访问国内镜像过慢导致镜像发布长时间卡住。
ARG DOCKER_BUILD_MIRROR=china
ARG PIP_USE_OFFICIAL=0

# social-auto-upload is intentionally pinned so platform automation does not
# change underneath an existing MoneyPrinterTurbo image. Override these build
# args explicitly when testing a newer upstream revision.
ARG SOCIAL_AUTO_UPLOAD_REPO=https://github.com/dreammis/social-auto-upload.git
ARG SOCIAL_AUTO_UPLOAD_REF=008e4ff66abdf48eb1f4b999272ef979711af436

# Install system dependencies with retry logic.
# intel-media-va-driver provides the iHD VA-API backend used by Intel Quick Sync
# on NAS hosts that expose /dev/dri to this container.  The remaining desktop
# libraries are required by patchright Chromium used for local social publishing.
RUN if [ "$DOCKER_BUILD_MIRROR" = "china" ]; then \
        echo "deb http://mirrors.aliyun.com/debian bullseye main" > /etc/apt/sources.list && \
        echo "deb http://mirrors.aliyun.com/debian-security bullseye-security main" >> /etc/apt/sources.list; \
    else \
        echo "Using default Debian mirrors"; \
    fi && \
    ( \
        for i in 1 2 3; do \
            echo "Attempt $i: installing system dependencies"; \
            apt-get update && apt-get install -y --no-install-recommends \
                git \
                ffmpeg \
                intel-media-va-driver \
                libnss3 \
                libnspr4 \
                libdbus-1-3 \
                libatk1.0-0 \
                libatk-bridge2.0-0 \
                libatspi2.0-0 \
                libxcomposite1 \
                libxdamage1 \
                libxfixes3 \
                libxrandr2 \
                libgbm1 \
                libxkbcommon0 \
                libasound2 \
                libgl1 && break || \
            echo "Attempt $i failed, retrying..."; \
            if [ "$DOCKER_BUILD_MIRROR" = "china" ] && [ $i -eq 3 ]; then \
                echo "Aliyun mirror failed, switching to Tsinghua mirror"; \
                sed -i 's/mirrors.aliyun.com/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list && \
                sed -i 's/mirrors.aliyun.com\/debian-security/mirrors.tuna.tsinghua.edu.cn\/debian-security/g' /etc/apt/sources.list && \
                ( \
                    apt-get update && apt-get install -y --no-install-recommends \
                        git \
                        ffmpeg \
                        intel-media-va-driver \
                        libnss3 \
                        libnspr4 \
                        libdbus-1-3 \
                        libatk1.0-0 \
                        libatk-bridge2.0-0 \
                        libatspi2.0-0 \
                        libxcomposite1 \
                        libxdamage1 \
                        libxfixes3 \
                        libxrandr2 \
                        libgbm1 \
                        libxkbcommon0 \
                        libasound2 \
                        libgl1 || \
                    ( \
                        echo "Tsinghua mirror failed, switching to default Debian mirror"; \
                        sed -i 's/mirrors.tuna.tsinghua.edu.cn/deb.debian.org/g' /etc/apt/sources.list && \
                        sed -i 's/mirrors.tuna.tsinghua.edu.cn\/debian-security/security.debian.org/g' /etc/apt/sources.list; \
                        apt-get update && apt-get install -y --no-install-recommends \
                            git \
                            ffmpeg \
                            intel-media-va-driver \
                            libnss3 \
                            libnspr4 \
                            libdbus-1-3 \
                            libatk1.0-0 \
                            libatk-bridge2.0-0 \
                            libatspi2.0-0 \
                            libxcomposite1 \
                            libxdamage1 \
                            libxfixes3 \
                            libxrandr2 \
                            libgbm1 \
                            libxkbcommon0 \
                            libasound2 \
                            libgl1; \
                    ); \
                ); \
            fi; \
            sleep 5; \
        done \
    ) && rm -rf /var/lib/apt/lists/*

# Copy only the requirements.txt first to leverage Docker cache
COPY requirements.txt ./

# 本地默认优先国内 PyPI 镜像；GHCR 发布使用官方 PyPI，避免海外 runner 因跨境镜像访问变慢。
RUN if [ "$PIP_USE_OFFICIAL" = "1" ]; then \
        pip install --no-cache-dir --retries 3 --timeout 60 -r requirements.txt; \
    else \
        pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --retries 3 --timeout 60 -r requirements.txt || \
        pip install --no-cache-dir -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple/ --trusted-host mirrors.tuna.tsinghua.edu.cn --retries 3 --timeout 60 -r requirements.txt || \
        pip install --no-cache-dir --retries 3 --timeout 60 -r requirements.txt; \
    fi

# Install the browser-based social publishing runtime separately from the main
# Python dependency graph.  --no-deps avoids downgrading MoneyPrinterTurbo's
# requests package to the exact version pinned by the upstream project; the
# compatible browser/runtime dependencies are installed explicitly instead.
RUN mkdir -p /opt/social-auto-upload && \
    git -C /opt/social-auto-upload init && \
    git -C /opt/social-auto-upload remote add origin "$SOCIAL_AUTO_UPLOAD_REPO" && \
    git -C /opt/social-auto-upload fetch --depth 1 origin "$SOCIAL_AUTO_UPLOAD_REF" && \
    git -C /opt/social-auto-upload checkout --detach FETCH_HEAD && \
    cp /opt/social-auto-upload/conf.example.py /opt/social-auto-upload/conf.py && \
    if [ "$PIP_USE_OFFICIAL" = "1" ]; then \
        pip install --no-cache-dir --retries 3 --timeout 60 \
            patchright==1.58.2 \
            'opencv-python>=4.13.0.92' \
            qrcode==8.2 \
            'segno>=1.6.6' && \
        pip install --no-cache-dir --no-deps -e /opt/social-auto-upload; \
    else \
        (pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com --retries 3 --timeout 60 \
            patchright==1.58.2 \
            'opencv-python>=4.13.0.92' \
            qrcode==8.2 \
            'segno>=1.6.6' || \
         pip install --no-cache-dir --retries 3 --timeout 60 \
            patchright==1.58.2 \
            'opencv-python>=4.13.0.92' \
            qrcode==8.2 \
            'segno>=1.6.6') && \
        pip install --no-cache-dir --no-deps -e /opt/social-auto-upload; \
    fi && \
    mkdir -p /opt/social-auto-upload/cookies && \
    if [ "$DOCKER_BUILD_MIRROR" = "china" ]; then \
        PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright patchright install chromium || patchright install chromium; \
    else \
        patchright install chromium; \
    fi

# Now copy the rest of the codebase into the image
COPY . .

# Expose the port the app runs on
EXPOSE 8501

# 容器内部必须监听 0.0.0.0，宿主机仍通过 docker 端口映射限制为 127.0.0.1。
# browser.serverAddress 只决定浏览器展示的访问地址，不能替代 server.address。
CMD ["streamlit", "run", "./webui/Main.py", "--server.address=0.0.0.0", "--server.port=8501", "--browser.serverAddress=127.0.0.1", "--server.enableCORS=True", "--browser.gatherUsageStats=False", "--client.toolbarMode=minimal", "--logger.hideWelcomeMessage=True", "--server.showEmailPrompt=False"]

# 1. Build the Docker image using the following command
# docker build -t moneyprinterturbo .

# 2. Run the Docker container using the following command
## For Linux or MacOS:
# docker run -v $(pwd)/config.toml:/MoneyPrinterTurbo/config.toml -v $(pwd)/storage:/MoneyPrinterTurbo/storage -v $(pwd)/storage/social-auto-upload/cookies:/opt/social-auto-upload/cookies -p 127.0.0.1:8501:8501 moneyprinterturbo
## For Windows:
# docker run -v ${PWD}/config.toml:/MoneyPrinterTurbo/config.toml -v ${PWD}/storage:/MoneyPrinterTurbo/storage -v ${PWD}/storage/social-auto-upload/cookies:/opt/social-auto-upload/cookies -p 127.0.0.1:8501:8501 moneyprinterturbo
