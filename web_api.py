import asyncio
import json
import logging
import os
import sys
import glob
from typing import List, Dict
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright
from proxy.proxy_ip_pool import IpInfoModel, create_ip_pool
from var import crawler_type_var
from media_platform.xhs.login import XiaoHongShuLogin

# Add current directory to path
sys.path.append(os.getcwd())

import config
from media_platform.xhs import XiaoHongShuCrawler
from tools import utils
from store import xhs as xhs_store

# Configure logger to capture logs
class WebSocketLogHandler(logging.Handler):
    def __init__(self, websocket_manager):
        super().__init__()
        self.manager = websocket_manager

    def emit(self, record):
        log_entry = self.format(record)
        asyncio.create_task(self.manager.broadcast_log(log_entry))

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_log(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_json({"type": "log", "message": message})
            except:
                pass

    async def broadcast_comment(self, comment: Dict):
        for connection in self.active_connections:
            try:
                await connection.send_json({"type": "comment", "data": comment})
            except:
                pass
    
    async def broadcast_done(self, file_path: str):
        for connection in self.active_connections:
            try:
                await connection.send_json({"type": "done", "file_path": file_path})
            except:
                pass

manager = ConnectionManager()
app = FastAPI()

# Mount public directory
app.mount("/public", StaticFiles(directory="public"), name="public")

# Subclass Crawler to intercept comments
class WebXiaoHongShuCrawler(XiaoHongShuCrawler):
    async def start(self) -> None:
        playwright_proxy_format, httpx_proxy_format = None, None
        if config.ENABLE_IP_PROXY:
            ip_proxy_pool = await create_ip_pool(config.IP_PROXY_POOL_COUNT, enable_validate_ip=True)
            ip_proxy_info: IpInfoModel = await ip_proxy_pool.get_proxy()
            playwright_proxy_format, httpx_proxy_format = utils.format_proxy_info(ip_proxy_info)

        async with async_playwright() as playwright:
            # 根据配置选择启动模式
            if config.ENABLE_CDP_MODE:
                utils.logger.info("[WebXiaoHongShuCrawler] 使用CDP模式启动浏览器")
                self.browser_context = await self.launch_browser_with_cdp(
                    playwright,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.CDP_HEADLESS,
                )
            else:
                utils.logger.info("[WebXiaoHongShuCrawler] 使用标准模式启动浏览器")
                # Launch a browser context.
                chromium = playwright.chromium
                self.browser_context = await self.launch_browser(
                    chromium,
                    playwright_proxy_format,
                    self.user_agent,
                    headless=config.HEADLESS,
                )
            
            await self.browser_context.add_init_script(path="libs/stealth.min.js")
            self.context_page = await self.browser_context.new_page()
            await self.context_page.goto(self.index_url)

            # Create a client to interact with the xiaohongshu website.
            self.xhs_client = await self.create_xhs_client(httpx_proxy_format)
            
            # 在CDP模式下，先同步一次Cookie，确保复用真实浏览器登录态
            if config.ENABLE_CDP_MODE:
                await self.xhs_client.update_cookies(browser_context=self.browser_context)
            
            # Check login status and wait for login if needed
            if not await self.xhs_client.pong():
                utils.logger.info("Cookie失效，启动登录流程...")
                await manager.broadcast_log("检测到未登录，正在启动浏览器...")
                
                login_obj = XiaoHongShuLogin(
                    login_type=config.LOGIN_TYPE,
                    login_phone="", 
                    browser_context=self.browser_context,
                    context_page=self.context_page,
                    cookie_str=config.COOKIES,
                )
                await login_obj.begin()
                
                await manager.broadcast_log("请在弹出的浏览器中完成登录（扫码或短信）...")
                await manager.broadcast_log("登录成功后，爬虫将自动继续...")
                
                # Loop until login success
                max_retries = 300 # 5 minutes
                login_success = False
                for i in range(max_retries):
                    await asyncio.sleep(1)
                    await self.xhs_client.update_cookies(browser_context=self.browser_context)
                    if await self.xhs_client.pong():
                        await manager.broadcast_log("登录成功！继续抓取...")
                        login_success = True
                        break
                    if i % 5 == 0:
                        utils.logger.info(f"Waiting for login... {i}/{max_retries}")
                
                if not login_success:
                    raise Exception("登录超时，请重试")
                
                await asyncio.sleep(12)
                utils.logger.info("登录后静置 12 秒完成")
            
            crawler_type_var.set(config.CRAWLER_TYPE)
            if config.CRAWLER_TYPE == "search":
                await self.search()
            elif config.CRAWLER_TYPE == "detail":
                await self.get_specified_notes()
            elif config.CRAWLER_TYPE == "creator":
                await self.get_creators_and_notes()
            else:
                pass

            utils.logger.info("[WebXiaoHongShuCrawler.start] Xhs Crawler finished ...")

    async def get_comments(self, note_id: str, xsec_token: str, semaphore: asyncio.Semaphore):
        """Override to intercept comments"""
        async with semaphore:
            utils.logger.info(f"[WebXiaoHongShuCrawler] Begin get note id comments {note_id}")
            crawl_interval = config.CRAWLER_MAX_SLEEP_SEC
            
            # Custom callback to intercept and store
            async def custom_callback(note_id: str, comments: List[Dict]):
                # 1. Send to frontend
                if comments:
                    for comment in comments:
                        await manager.broadcast_comment(comment)
                # 2. Call original store logic
                await xhs_store.batch_update_xhs_note_comments(note_id, comments)

            await self.xhs_client.get_note_all_comments(
                note_id=note_id,
                xsec_token=xsec_token,
                crawl_interval=crawl_interval,
                callback=custom_callback, # Use custom callback
                max_count=config.CRAWLER_MAX_COMMENTS_COUNT_SINGLENOTES,
            )
            await asyncio.sleep(crawl_interval)
            utils.logger.info(f"[WebXiaoHongShuCrawler] Sleeping for {crawl_interval} seconds after fetching comments for note {note_id}")

@app.get("/")
async def get():
    return FileResponse("public/index.html")

@app.get("/download")
async def download(file_path: str):
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=os.path.basename(file_path))
    return {"error": "File not found"}

@app.websocket("/ws/crawl")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Attach log handler
    log_handler = WebSocketLogHandler(manager)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    log_handler.setFormatter(formatter)
    utils.logger.addHandler(log_handler)
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            if message.get("action") == "start":
                url = message.get("url")
                if url:
                    utils.logger.info(f"Received crawl request for: {url}")
                    # Configure Crawler
                    config.CRAWLER_TYPE = "detail"
                    config.XHS_SPECIFIED_NOTE_URL_LIST = [url]
                    config.HEADLESS = False # Show browser for login if needed
                    config.ENABLE_GET_COMMENTS = True
                    config.SAVE_DATA_OPTION = "csv" # Force CSV for easy download
                    
                    # Ensure data directory exists
                    os.makedirs("data/xhs/csv", exist_ok=True)

                    crawler = WebXiaoHongShuCrawler()
                    await crawler.start()
                    
                    # Find the generated file
                    # File pattern: data/xhs/csv/detail_comments_YYYY-MM-DD.csv
                    current_date = utils.utils.get_current_date()
                    expected_file = f"data/xhs/csv/detail_comments_{current_date}.csv"
                    
                    if os.path.exists(expected_file):
                        await manager.broadcast_done(expected_file)
                    else:
                        # Fallback: find latest modified csv
                        list_of_files = glob.glob('data/xhs/csv/*.csv') 
                        if list_of_files:
                            latest_file = max(list_of_files, key=os.path.getctime)
                            await manager.broadcast_done(latest_file)
                        else:
                            await manager.broadcast_log("Warning: Could not find output file.")

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        utils.logger.removeHandler(log_handler)
    except Exception as e:
        utils.logger.error(f"WebSocket Error: {e}")
        await manager.broadcast_log(f"Error: {e}")
    finally:
         if log_handler in utils.logger.handlers:
            utils.logger.removeHandler(log_handler)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
