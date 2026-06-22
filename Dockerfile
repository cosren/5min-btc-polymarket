# 基础镜像：Python 3.10 on slim Debian
FROM python:3.10-slim

# 维护者标签
LABEL maintainer="5min-btc-polymarket"

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖清单
COPY requirements.txt .

# 升级 pip 并安装 Python 依赖
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 创建日志目录
RUN mkdir -p data/logs && chmod 755 data/logs

# 暴露端口：8080 健康检查，8186 Web 仪表盘
EXPOSE 8080
EXPOSE 8186

# 设置环境变量（容器模式）
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 纸面交易 + 保守策略 + Web 仪表盘
CMD ["python", "src/core/trade_runner.py", "--paper-trade", "--profile", "conservative", "--web"]