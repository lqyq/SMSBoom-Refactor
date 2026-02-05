# encoding=utf8
import httpx
import re
import json
import logging
from typing import List, Dict, Any, Generator

logger = logging.getLogger("scraper")

class BaseScraper:
    def __init__(self, url: str, key: str = ""):
        self.url = url
        self.key = key
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.9 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "priority": "u=0, i",
            "sec-ch-ua": "\"Chromium\";v=\"140\", \"Not=A?Brand\";v=\"24\", \"Microsoft Edge\";v=\"140\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "sec-fetch-user": "?1",
            "Upgrade-Insecure-Requests": "1",
            "Cookie": "sl-session=7KOyN4RAg2kmYoiutahBeA==; sl-challenge-server=cloud; sl_jwt_session=nb6Bn4WvswJWNS0SNHOndUlr6XXkyFOrb191uQ+QMRUm78nRuOi9l/aXrwpOQn8Z; sl_jwt_sign="
        }

    def scrape(self) -> Generator[Dict[str, Any], None, None]:
        """执行爬取，通过 yield 返回日志和结果"""
        raise NotImplementedError

class GenericScraper(BaseScraper):
    """通用网页爬虫，基于正则匹配 img 标签中的接口"""
    def scrape(self) -> Generator[Dict[str, Any], None, None]:
        apis = []
        default_phone = "15019682928" if not self.key else re.findall(r'=(\d{10,})',self.key)[0]
        
        yield {"type": "log", "message": f"开始爬取通用站点: {self.url}"}
        
        try:
            with httpx.Client(verify=False, timeout=10, follow_redirects=True) as client:
                # 模拟请求首页
                try:
                    client.get(self.url, headers=self.headers)
                except:
                    pass
                # 请求带 key 的页面
                target_url = f"{self.url}?hm={default_phone}&ok=" if not self.key else f"{self.url}?{self.key}"
                yield {"type": "log", "message": f"正在请求目标页面: {target_url}"}
                
                resp = client.get(target_url, headers=self.headers)
                print(resp.text)
                # 基于 spider-api.py 的正则
                pat = re.compile(r"<img src='(.*?)' alt")
                raw_apis = pat.findall(resp.text)
                
                yield {"type": "log", "message": f"查找到原始接口数量: {len(raw_apis)}"}
                
                for api in raw_apis:
                    if default_phone not in api:
                        continue
                    
                    # 清洗并转换
                    clean_api = api.strip().replace(" ", "").replace(default_phone, "[phone]")
                    
                    if not (clean_api.startswith("http://") or clean_api.startswith("https://")):
                        continue
                        
                    api_item = {
                        "desc": "通用采集",
                        "url": clean_api,
                        "method": "GET",
                        "header": "",
                        "data": ""
                    }
                    apis.append(api_item)
                    yield {"type": "log", "message": f"发现有效接口: {clean_api[:50]}..."}
                    
        except Exception as e:
            yield {"type": "error", "message": f"爬取失败: {str(e)}"}
            
        yield {"type": "result", "data": apis}
        yield {"type": "done"}

class BangtangScraper(BaseScraper):
    """针对棒糖测压的 JS 脚本解析器"""
    def scrape(self) -> Generator[Dict[str, Any], None, None]:
        apis = []
        yield {"type": "log", "message": "开始解析棒糖测压接口..."}
        
        try:
            # with httpx.Client(verify=False, timeout=10, follow_redirects=True) as client:
                yield {"type": "log", "message": f"正在请求页面寻找 JS 脚本: {self.url}"}
                # resp = client.get(self.url, headers=self.headers)
                
                # 寻找 chunk js
                
                # js_match = re.search(r'src="(.*?chunk-.*?\.js)"', resp.text)
                # if not js_match:
                #     js_url = f"{self.url.rstrip('/')}/static/js/chunk-526.js"
                # else:
                #     js_url = js_match.group(1)
                #     if not js_url.startswith("http"):
                #         from urllib.parse import urljoin
                #         js_url = urljoin(self.url, js_url)

                # yield {"type": "log", "message": f"正在下载并解析 JS: {js_url}"}
                # js_resp = client.get(js_url, headers=self.headers)
                # content = js_resp.text

                # from .. import debug
                # from debug
                import os,sys
                parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, 'debug'))
                sys.path.insert(0, parent_dir)

                # 导入模块
                import fetch_bangtang_file 
                content = fetch_bangtang_file.fetch_bangtang_api(self.url)
                
                regex = r'\{method\s*:\s*["\'](\w+)["\']\s*,\s*url\s*:\s*[`"\'](.*?)[`\'"]\s*(?:,\s*params\s*:\s*(.*?))?(?:,\s*referer\s*:\s*["\'](.*?)["\'])?\}'
                matches = re.finditer(regex, content)
                
                for match in matches:
                    method = match.group(1).upper()
                    url = match.group(2).replace('${e}', '[phone]')
                    params_raw = match.group(3)
                    referer = match.group(4)
                    
                    api_entry = {
                        "desc": "来自棒糖测压",
                        "url": url,
                        "method": method,
                        "header": {"Referer": referer} if referer else "",
                        "data": ""
                    }
                    
                    if method == 'POST' and params_raw:
                        param_pairs = re.findall(r'(\w+)\s*:\s*(\w+)', params_raw)
                        data_parts = []
                        for key, val in param_pairs:
                            if val == 'e':
                                data_parts.append(f"{key}=[phone]")
                        if data_parts:
                            api_entry['data'] = "&".join(data_parts)
                    
                    apis.append(api_entry)
                    yield {"type": "log", "message": f"解析到接口: {url[:50]}..."}

        except Exception as e:
            yield {"type": "error", "message": f"棒糖解析失败: {str(e)}"}
            
        yield {"type": "result", "data": apis}
        yield {"type": "done"}

class SMSTestScraper(BaseScraper):
    """针对 SMSTest (lazy52) 的解析器"""
    def scrape(self) -> Generator[Dict[str, Any], None, None]:
        apis = []
        yield {"type": "log", "message": "开始解析 SMSTest 接口..."}
        
        try:
            with httpx.Client(verify=False, timeout=10, follow_redirects=True) as client:
                yield {"type": "log", "message": f"正在请求页面源码: {self.url}"}
                resp = client.get(self.url, headers=self.headers)
                content = resp.text

                block_pattern = re.compile(
                    r"url:\s*'([^']+)',\s*"
                    r"method:\s*'([^']+)',\s*"
                    r"headers:\s*\(\)\s*=>\s*\(\{(.*?)\}\),\s*"
                    r"data:\s*\(phoneNumber,\s*times\)\s*=>\s*\(\{(.*?)\}\)",
                    re.DOTALL
                )
                
                matches = block_pattern.finditer(content)
                for match in matches:
                    url = match.group(1)
                    method_raw = match.group(2)
                    headers_raw = match.group(3)
                    data_raw = match.group(4)
                    
                    method = "POST" if "POST" in method_raw else "GET"
                    
                    def quick_parse(raw):
                        res = {}
                        pairs = re.findall(r"['\"]?(\w+)['\"]?\s*:\s*['\"]?([^'\",\s\}]+)['\"]?", raw)
                        for k, v in pairs:
                            if v == "phoneNumber": v = "[phone]"
                            res[k] = v
                        return res

                    headers = quick_parse(headers_raw)
                    data_dict = quick_parse(data_raw)
                    
                    data_str = ""
                    if method == "POST" and "JSON" not in method_raw:
                        data_str = "&".join([f"{k}={v}" for k, v in data_dict.items()])
                    else:
                        data_str = data_dict

                    api_entry = {
                        "desc": "来自 SMSTest",
                        "url": url,
                        "method": method,
                        "header": headers,
                        "data": data_str
                    }
                    apis.append(api_entry)
                    yield {"type": "log", "message": f"解析到接口: {url[:50]}..."}
                    
        except Exception as e:
            yield {"type": "error", "message": f"SMSTest 解析失败: {str(e)}"}
            
        yield {"type": "result", "data": apis}
        yield {"type": "done"}

def get_scraper(scraper_type: str, url: str, key: str = "") -> BaseScraper:
    mapping = {
        "generic": GenericScraper,
        "bangtang": BangtangScraper,
        "smstest": SMSTestScraper
    }
    scraper_cls = mapping.get(scraper_type, GenericScraper)
    return scraper_cls(url, key)
