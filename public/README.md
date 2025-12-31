# 小红书评论抓取前端使用说明

本目录包含小红书评论抓取工具的前端界面代码。

## 目录结构
- `index.html`: 主界面
- `style.css`: 样式文件
- `script.js`: 逻辑控制脚本

## 使用流程

### 1. 启动服务
在项目根目录下，运行以下命令启动 Web API 服务：

```bash
# 确保已安装依赖
pip install -r requirements.txt

# 启动 Web 服务
python3 web_api.py
```

### 2. 访问界面
打开浏览器，访问：
http://localhost:8000

### 3. 开始抓取
1. 在输入框中粘贴小红书帖子的 URL（例如：`https://www.xiaohongshu.com/explore/xxxxxx`）。
2. 点击“开始抓取”按钮。

### 4. 登录验证
- 如果是首次运行或 Cookie 已过期，系统会自动打开 Chrome 浏览器窗口。
- 请在弹出的浏览器中完成登录（扫码或短信验证）。
- 登录成功后，爬虫会自动继续运行，无需额外操作。

### 5. 查看结果与下载
- 抓取过程中，页面下方的表格会实时显示抓取到的评论。
- 左侧日志区会显示爬虫的运行状态。
- 抓取完成后，“下载表格 (CSV)”按钮会自动出现，点击即可下载结果文件。

## 故障排查：WebSocket 连接失败

- 现象：
  - 浏览器控制台报错：`WebSocket connection to 'ws://localhost:8000/ws/crawl' failed`
  - 终端日志出现：
    - `WARNING: Unsupported upgrade request`
    - `WARNING: No supported WebSocket library detected. Please use "pip install 'uvicorn[standard]'", or install 'websockets' or 'wsproto' manually.`
    - `GET /ws/crawl HTTP/1.1 404 Not Found`

- 原因：
  - `uvicorn` 以精简安装运行，缺少 WebSocket 支持的依赖（如 `websockets`/`wsproto`）。握手失败后被当作普通 GET 请求处理，导致 `/ws/crawl` 返回 404。

- 解决步骤：
  1. 将依赖升级为带标准扩展的 Uvicorn：
     - 编辑项目根目录 `requirements.txt`，把 `uvicorn==0.29.0` 改为 `uvicorn[standard]==0.29.0`。
  2. 重新安装依赖并重启服务：
     ```bash
     pip3 install -r requirements.txt
     python3 web_api.py
     ```
  3. 验证成功标志：
     - 终端出现 `WebSocket /ws/crawl [accepted]` 与 `connection open`
     - 页面状态显示“Connected to WebSocket”或不再提示“连接错误/断开”

> 备注：如果不修改 `requirements.txt`，也可手动安装 `websockets` 或 `wsproto`，但推荐使用 `uvicorn[standard]` 以一次性补齐所需依赖。
