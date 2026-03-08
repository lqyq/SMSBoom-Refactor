# encoding=utf8
import asyncio
import threading
import json
import re
import logging
import os
import platform
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Request, Response
from queue import Queue, Empty
import time
from urllib.parse import urlparse, quote

logger = logging.getLogger("playwright_capture")

class PlaywrightCapture:
    """
    Playwright 抓包控制器
    负责启动浏���器、监听请求、过滤目标 API 并将结果推送到事件队列
    """
    
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(PlaywrightCapture, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        
        self.browser_context: Optional[BrowserContext] = None
        self.playwright = None
        
        self.phone: str = ""
        self.pure_phone: str = "" # 纯数字手机号
        self.event_queue: Queue = Queue()
        self.is_running: bool = False
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        
        # 已捕获的请求指纹，防止重复推送 (method + url)
        self.seen_requests = set()
        
        # 默认的用户数据目录
        self.default_user_data_dir = os.path.join(os.getcwd(), "browser_data")

    def _get_system_user_data_dir(self) -> Optional[str]:
        """获取系统默认浏览器用户数据目录 (仅支持 Windows)"""
        if platform.system() != "Windows":
            return None
        
        local_app_data = os.environ.get('LOCALAPPDATA')
        if not local_app_data:
            return None
            
        # 优先 Edge
        edge_path = os.path.join(local_app_data, r"Microsoft\Edge\User Data")
        if os.path.exists(edge_path):
            return edge_path
            
        # 其次 Chrome
        chrome_path = os.path.join(local_app_data, r"Google\Chrome\User Data")
        if os.path.exists(chrome_path):
            return chrome_path
            
        return None

    def start_capture(self, phone: str, initial_urls: Optional[List[str]] = None, user_data_dir: Optional[str] = None, use_system_profile: bool = False):
        """启动抓包会话，支持批量打开 URL"""
        with self._lock:
            if self.is_running:
                raise RuntimeError("Capture session already running")
            
            self.phone = phone
            # 提取纯数字手机号用于更灵活的匹配
            self.pure_phone = ''.join(filter(str.isdigit, phone))
            self.is_running = True
            self.stop_event.clear()
            self.seen_requests.clear()
            
            # 清空旧队列
            while not self.event_queue.empty():
                try:
                    self.event_queue.get_nowait()
                except Empty:
                    break
            
            if initial_urls is None:
                initial_urls = ["https://www.google.com"]
            elif isinstance(initial_urls, str):
                initial_urls = [initial_urls]
            
            target_user_data_dir = user_data_dir if user_data_dir else self.default_user_data_dir
            
            self.thread = threading.Thread(target=self._run_async_loop, args=(initial_urls, target_user_data_dir, use_system_profile))
            self.thread.daemon = True
            self.thread.start()
            
            logger.info(f"Capture session started for phone: {phone}")

    def stop_capture(self):
        """停止抓包会话"""
        with self._lock:
            if not self.is_running:
                return
            
            self.is_running = False
            self.stop_event.set()
            
            # 等待线程结束（可选，这���非阻塞）
            logger.info("Capture session stopping...")

    def get_events(self) -> list:
        """获取所有待处理事件"""
        events = []
        try:
            while True:
                event = self.event_queue.get_nowait()
                events.append(event)
        except Empty:
            pass
        return events

    def _run_async_loop(self, initial_urls: List[str], user_data_dir: str, use_system_profile: bool = False):
        """在独立线程中运行 asyncio 事件循环"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            loop.run_until_complete(self._main_logic(initial_urls, user_data_dir, use_system_profile))
        except Exception as e:
            logger.exception(f"Async loop error: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})
        finally:
            loop.close()
            with self._lock:
                self.is_running = False
            self.event_queue.put({"type": "status", "message": "stopped"})

    async def _main_logic(self, initial_urls: List[str], user_data_dir: str, use_system_profile: bool = False):
        """Playwright 主逻辑"""
        try:
            # 如果请求使用系统 Profile
            if use_system_profile:
                system_path = self._get_system_user_data_dir()
                if system_path:
                    user_data_dir = system_path
                    self.event_queue.put({"type": "log", "message": f"正在尝试使用系统默认浏览器配置: {user_data_dir}"})
                else:
                    self.event_queue.put({"type": "error", "message": "未找到系统浏览器配置文件，将使用独立环境"})

            # 确保用户数据目录存在
            if not os.path.exists(user_data_dir):
                os.makedirs(user_data_dir)
                
            async with async_playwright() as p:
                self.playwright = p
                
                # 启动参数配置
                launch_args = [
                    "--no-sandbox", 
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled", # 禁用自动化特征
                    "--excludeSwitches=enable-automation", # 排除自动化开关
                    "--disable-infobars", # 禁用信息栏
                    "--no-first-run", # 禁用首次运行向导
                    "--password-store=basic", # 使用基础密码存储
                    "--use-mock-keychain", # 使用模拟钥匙串
                ]
                
                # 尝试使用持久化上下文启动
                # 根据用户数据目录智能判断浏览器通道
                channel_to_use = "msedge" # 默认 Edge
                if "Chrome" in user_data_dir and "Edge" not in user_data_dir:
                    channel_to_use = "chrome"

                context = None
                try:
                    context = await p.chromium.launch_persistent_context(
                        user_data_dir=user_data_dir,
                        channel=channel_to_use,
                        headless=False, 
                        args=launch_args,
                        viewport={"width": 1280, "height": 800},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0" # 模拟 Edge UA
                    )
                except Exception as e:
                    if "SingletonLock" in str(e):
                        error_msg = "启动失败：浏览器文件被占用。请务必先关闭所有已打开的 Edge/Chrome 浏览器窗口，然后重试。"
                        self.event_queue.put({"type": "error", "message": error_msg})
                        return

                    # 如果指定通道启动失败，尝试回退到 Chromium (仅非系统环境)
                    if use_system_profile:
                        # 系统环境模式下，如果指定浏览器启动失败，不建议回退到 bundled chromium，因为 profile 可能不兼容
                        self.event_queue.put({"type": "error", "message": f"启动系统默认浏览器({channel_to_use})失败: {str(e)}"})
                        return

                    # 如果没有 Edge，回退到默��
                    try:
                        context = await p.chromium.launch_persistent_context(
                            user_data_dir=user_data_dir,
                            headless=False, 
                            args=launch_args,
                            viewport={"width": 1280, "height": 800}
                        )
                    except Exception as inner_e:
                        if "SingletonLock" in str(inner_e):
                            error_msg = "启动失败：浏览器文件被占用。请务必先关闭所有已打开的 Edge/Chrome 浏览器窗口，然后重试。"
                            self.event_queue.put({"type": "error", "message": error_msg})
                            return
                        raise inner_e
                
                self.browser_context = context
                
                # 注入更强的反检测脚本
                await self._add_stealth_scripts(context)
                
                # 监听上下文级别的新页面事件
                context.on("page", self._on_new_page)
                
                self.event_queue.put({"type": "log", "message": f"浏览器已启动 (Persistent Profile: {os.path.basename(user_data_dir)})"})
                
                # 批量打开初始页面
                if initial_urls:
                    # 获取当前已有的页面（通常启动时会有一个空白页）
                    pages = context.pages
                    first_page = pages[0] if pages else await context.new_page()
                    
                    for i, url in enumerate(initial_urls):
                        if i == 0:
                            page = first_page
                        else:
                            # 稍微延迟一下，避免并发太高被风控
                            await asyncio.sleep(1)
                            page = await context.new_page()
                            
                        self._setup_page_listeners(page)
                        self.event_queue.put({"type": "log", "message": f"正在打开: {url}"})
                        try:
                            # 不等待完全加载，避免阻塞后续页面打开
                            asyncio.create_task(page.goto(url, timeout=30000))
                        except Exception as e:
                            self.event_queue.put({"type": "error", "message": f"打开页面失败: {url} - {e}"})

                # 持续运行直到收到停止信号或所有页面关闭
                while not self.stop_event.is_set():
                    if not context.pages:
                        self.event_queue.put({"type": "log", "message": "所有标签页已关闭"})
                        break
                    await asyncio.sleep(0.5)
                
                await context.close()
                
        except Exception as e:
            logger.exception(f"Playwright error: {e}")
            self.event_queue.put({"type": "error", "message": f"引擎错误: {str(e)}"})

    async def _add_stealth_scripts(self, context: BrowserContext):
        """注入增强版反自动化检测脚本"""
        await context.add_init_script("""
            // 1. 屏蔽 navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });

            // 2. 模拟 window.chrome
            if (!window.chrome) {
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };
            }

            // 3. 模拟插件 (Plugins)
            if (navigator.plugins.length === 0) {
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [
                        {
                            0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            length: 1,
                            name: "Chrome PDF Plugin"
                        },
                        {
                            0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                            description: "Portable Document Format",
                            filename: "internal-pdf-viewer",
                            length: 1,
                            name: "Chrome PDF Viewer"
                        },
                        {
                            0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
                            description: "Native Client Executable",
                            filename: "internal-nacl-plugin",
                            length: 1,
                            name: "Native Client"
                        }
                    ],
                });
            }

            // 4. 模拟语言 (Languages)
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en', 'en-US'],
            });

            // 5. 绕过权限查询 (Permissions)
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // 6. WebGL 厂商伪装
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // UNMASKED_VENDOR_WEBGL
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                // UNMASKED_RENDERER_WEBGL
                if (parameter === 37446) {
                    return 'Intel(R) Iris(R) Xe Graphics';
                }
                return getParameter(parameter);
            };
        """)

    def _on_new_page(self, page: Page):
        """处理新标签页"""
        self.event_queue.put({"type": "log", "message": "检测到新标签页"})
        self._setup_page_listeners(page)

    def _setup_page_listeners(self, page: Page):
        """为页面设置监听器"""
        # 使用 response 事件来获取响应内容，request 事件只能获取请求信息
        page.on("response", self._handle_response)

    async def _handle_response(self, response: Response):
        """处理捕获的响应"""
        try:
            request = response.request
            url = request.url
            method = request.method
            
            # 1. 获取 post data (尝试多种方式)
            post_data = ""
            try:
                post_data = request.post_data or ""
                # 如果 post_data 为空但有 buffer，尝试手动解码
                if not post_data and request.post_data_buffer:
                    try:
                        post_data = request.post_data_buffer.decode('utf-8', errors='ignore')
                    except:
                        pass
            except Exception as e:
                logger.debug(f"Error getting post data: {e}")

            # 2. 核心过滤：检查手机号 (精确匹配，防止误匹配长数字串)
            has_phone = self._check_phone_exact(url) or self._check_phone_exact(post_data)
            
            # 3. 检查 Header (某些 API 会把手机号放在 Header)
            headers = {}
            if not has_phone:
                try:
                    # 优先使用异步的 all_headers，如果失败则回退到同步的 headers
                    headers = await request.all_headers()
                except:
                    headers = request.headers

                for v in headers.values():
                    if self._check_phone_exact(str(v)):
                        has_phone = True
                        break
            
            # 4. 如果没匹配到手机号，则进行基础过滤
            if not has_phone:
                resource_type = request.resource_type
                if resource_type in ['image', 'stylesheet', 'font', 'media']:
                    return
                # 排除常见无关后缀
                if url.endswith(('.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.woff', '.svg')):
                    return
                # 既没手机号也不是静态资源，也丢弃
                return

            # 5. 确保 headers 已获取 (如果之前匹配成功跳过了获取步骤)
            if not headers:
                try:
                    headers = await request.all_headers()
                except:
                    headers = request.headers

            # 4. 生成指纹去重 (包含 method, url 和 post_data 的前 100 个字符)
            # 这样即使 URL 相同，如果 Body 不同（比如换了手机号或参数），也会被捕获
            body_part = post_data[:100] if post_data else ""
            fingerprint = f"{method}:{url}:{body_part}"
            if fingerprint in self.seen_requests:
                return
            self.seen_requests.add(fingerprint)
            
            # 4. 获取页面标题作为描述
            page_title = ""
            try:
                # 尝试获取发出请求的页面的标题
                # 注��：如果请求来自 iframe，request.frame.page 仍然指向主页面
                if request.frame and request.frame.page:
                    page_title = await request.frame.page.title()
            except:
                pass

            desc = page_title if page_title else self._generate_desc(url)

            # 获取响应内容 (可能失败或为空)
            resp_text = ""
            resp_status = response.status
            try:
                # 限制响应体大小，避免过大导致卡顿
                body_bytes = await response.body()
                if len(body_bytes) < 1024 * 100: # 100KB
                    try:
                        resp_text = body_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        resp_text = body_bytes.decode('gbk', errors='ignore')
                else:
                    resp_text = f"[响应体过大: {len(body_bytes)} bytes]"
            except Exception as e:
                resp_text = f"[无法获取响应: {str(e)}]"

            # 5. 构造结果
            api_info = {
                "desc": desc,
                "url": url,
                "method": method,
                "header": self._clean_headers(headers),
                "data": post_data,
                "original_phone": self.phone,
                "title": page_title,
                "status": resp_status,
                "response": resp_text
            }
            
            self.event_queue.put({
                "type": "result", 
                "data": api_info,
                "message": f"捕获到潜在 API: {method} {url[:50]}... (Status: {resp_status})"
            })
            logger.info(f"Captured API: {method} {url} Status: {resp_status}")

        except Exception as e:
            # 避免在这里抛出异常导致循环中断
            logger.error(f"Error handling request: {e}")

    def _clean_headers(self, headers: Dict[str, str]) -> Dict[str, str]:
        """清洗 Header，保留关键字段，并标准化大小写"""
        # 标准头部映射 (小写 -> 标准写法)
        # 即使 HTTP/1.1 标准说 Header 不区分大小写，但部分服务器/WAF 会校验大小写 (指纹识别)
        # Playwright/Chrome 默认返回全小写 (HTTP/2 标准)，因此我们需要手动还原
        header_map = {
            'user-agent': 'User-Agent',
            'content-type': 'Content-Type',
            'referer': 'Referer',
            'origin': 'Origin',
            'authorization': 'Authorization',
            'x-requested-with': 'X-Requested-With',
            'cookie': 'Cookie',
            'accept': 'Accept',
            'accept-encoding': 'Accept-Encoding',
            'accept-language': 'Accept-Language',
            'connection': 'Connection',
            'host': 'Host'
        }
        
        keep_headers = list(header_map.keys())
        cleaned = {}
        
        for k, v in headers.items():
            k_lower = k.lower()
            if k_lower in keep_headers or k_lower.startswith('x-') or k_lower.startswith('bx-'):
                # 尝试获取标准写法
                standard_key = header_map.get(k_lower)
                
                # 处理 X- 开头的自定义头部，尝试转为 Title-Case (如 x-auth-token -> X-Auth-Token)
                if not standard_key and k_lower.startswith('x-'):
                    standard_key = '-'.join([part.capitalize() for part in k_lower.split('-')])
                
                # 如果没有找到标准写法，就用原 key
                final_key = standard_key if standard_key else k
                
                cleaned[final_key] = v
        return cleaned

    def _check_phone_exact(self, content: str) -> bool:
        """精确检查内容中是否包含目标手机号（防止误匹配长数字串）"""
        if not content:
            return False
        
        # 动态构建并缓存正则模式
        if not hasattr(self, '_phone_patterns') or getattr(self, '_last_pattern_phone', None) != self.phone:
            self._last_pattern_phone = self.phone
            match_targets = [self.phone]
            if self.pure_phone and self.pure_phone != self.phone:
                match_targets.append(self.pure_phone)
            
            all_targets = set()
            for t in match_targets:
                if t:
                    all_targets.add(t)
                    all_targets.add(quote(t))
            
            self._phone_patterns = []
            for t in all_targets:
                # 匹配逻辑：前后不能有数字，允许常见国家码前缀 (86, +86, 086)
                # 使用 re.IGNORECASE 处理 URL 编码的大小写问题
                pattern = re.compile(rf"(?<![0-9])(?:\+?86|086)?{re.escape(t)}(?![0-9])", re.IGNORECASE)
                self._phone_patterns.append(pattern)
        
        for pattern in self._phone_patterns:
            if pattern.search(content):
                return True
        return False

    def _generate_desc(self, url: str) -> str:
        """从 URL 生成简短描述"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            path = parsed.path.split('/')[-1]
            return f"抓包-{domain}-{path}"
        except:
            return "抓包采集"

# 单例实例
capture_manager = PlaywrightCapture()
