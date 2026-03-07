#!/usr/bin/python3
# coding=utf8
# Swagger/OpenAPI 接口自动提取工具
# Author: SMSBoom Team

import httpx
import json
import re
import sys
from loguru import logger
import click
from urllib.parse import urlparse, urljoin

# 配置 logger
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> - <level>{level}</level> - <level>{message}</level>",
    colorize=True
)

class SwaggerHunter:
    def __init__(self, url):
        self.original_url = url
        self.base_url = self._get_base_url(url)
        self.docs_url = self._get_docs_url(url)
        self.found_apis = []

    def _get_base_url(self, url):
        """获取基础域名"""
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    def _get_docs_url(self, url):
        """尝试推断 JSON 文档地址"""
        # 如果以 .json 结尾，直接使用
        if url.endswith('.json'):
            return url
        
        # 常见的 swagger json 地址
        candidates = [
            "/v2/api-docs",
            "/v3/api-docs",
            "/swagger/v1/swagger.json",
            "/api-docs",
            "/api/v2/api-docs"
        ]
        
        # 如果用户输入的是 swagger-ui.html，尝试去掉它
        clean_url = url.split('/swagger-ui')[0]
        if clean_url != url:
            # 这是一个猜测的基础路径
            pass

        return url  # 默认先按原样尝试，实际逻辑在 fetch 中处理

    def fetch_json(self):
        """获取 Swagger JSON 定义"""
        possible_urls = []
        if self.original_url.endswith('.json'):
            possible_urls.append(self.original_url)
        else:
            # 如果是 UI 地址，尝试探测常见的 JSON 地址
            base_clean = self.original_url.split('/swagger-ui')[0].split('/doc.html')[0]
            if base_clean.endswith('/'):
                base_clean = base_clean[:-1]
            
            possible_urls = [
                f"{base_clean}/v2/api-docs",
                f"{base_clean}/v3/api-docs",
                f"{base_clean}/swagger/v1/swagger.json",
                f"{base_clean}/swagger-resources", # 有时需要先读这个获取分组
            ]

        for url in possible_urls:
            logger.info(f"尝试获取文档: {url}")
            try:
                with httpx.Client(verify=False, timeout=10) as client:
                    resp = client.get(url)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            if 'swagger' in data or 'openapi' in data:
                                logger.success(f"成功获取 Swagger 文档: {url}")
                                return data
                        except:
                            pass
            except Exception as e:
                logger.debug(f"请求失败: {e}")
        
        logger.error("无法获取有效的 Swagger JSON 文档")
        return None

    def parse_definitions(self, data, ref):
        """解析引用对象 (简易版)"""
        # ref example: "#/definitions/UserDTO" or "#/components/schemas/UserDTO"
        if not ref:
            return {}
        
        parts = ref.split('/')
        model_name = parts[-1]
        
        schema = {}
        
        # 处理 v2 definitions
        if 'definitions' in data and model_name in data['definitions']:
            props = data['definitions'][model_name].get('properties', {})
            for k, v in props.items():
                schema[k] = "" # 默认空值
                
        # 处理 v3 components
        elif 'components' in data and 'schemas' in data['components'] and model_name in data['components']['schemas']:
             props = data['components']['schemas'][model_name].get('properties', {})
             for k, v in props.items():
                schema[k] = ""

        return schema

    def extract_apis(self, json_data):
        """提取短信相关接口"""
        if not json_data:
            return

        paths = json_data.get('paths', {})
        base_path = json_data.get('basePath', '')
        if base_path == '/': base_path = ''

        # 关键词列表
        keywords = ['sms', 'code', 'verify', 'mobile', '验证码', '短信']
        
        for path, methods in paths.items():
            for method, details in methods.items():
                # 检查是否包含关键词 (URL 或 描述)
                summary = details.get('summary', '')
                description = details.get('description', '')
                tags = str(details.get('tags', []))
                
                full_text = f"{path} {summary} {description} {tags}".lower()
                
                if any(kw in full_text for kw in keywords):
                    # 排除明显不相关的 (比如验证验证码，而不是发送)
                    if 'check' in full_text or 'validate' in full_text or '校验' in full_text:
                        continue

                    # 构造完整 URL
                    full_url = f"{self.base_url}{base_path}{path}"
                    
                    api_item = {
                        "desc": summary or description or path,
                        "url": full_url,
                        "method": method.upper(),
                        "header": {"Content-Type": "application/json"} if method.upper() == "POST" else "",
                        "data": {}
                    }

                    # 解析参数
                    parameters = details.get('parameters', [])
                    
                    # 1. 处理 query/formData 参数
                    params_data = ""
                    json_body = {}
                    
                    for param in parameters:
                        p_in = param.get('in')
                        p_name = param.get('name')
                        
                        if p_in == 'query':
                            if method.upper() == 'GET':
                                sep = '&' if params_data else ''
                                val = "[phone]" if 'phone' in p_name.lower() or 'mobile' in p_name.lower() else ""
                                params_data += f"{sep}{p_name}={val}"
                            
                        elif p_in == 'body':
                            # 处理 Body 引用
                            schema = param.get('schema', {})
                            ref = schema.get('$ref')
                            if ref:
                                json_body = self.parse_definitions(json_data, ref)
                                # 尝试填充手机号字段
                                for k in json_body.keys():
                                    if 'phone' in k.lower() or 'mobile' in k.lower() or 'tel' in k.lower():
                                        json_body[k] = "[phone]"
                    
                    # 2. 处理 requestBody (OpenAPI v3)
                    if 'requestBody' in details:
                        content = details['requestBody'].get('content', {})
                        if 'application/json' in content:
                            schema = content['application/json'].get('schema', {})
                            ref = schema.get('$ref')
                            if ref:
                                json_body = self.parse_definitions(json_data, ref)
                                for k in json_body.keys():
                                    if 'phone' in k.lower() or 'mobile' in k.lower() or 'tel' in k.lower():
                                        json_body[k] = "[phone]"

                    if method.upper() == "POST":
                        # 优先使用 JSON body
                        if json_body:
                            api_item['data'] = json_body
                        elif params_data:
                            api_item['data'] = params_data
                            api_item['header'] = "" # 表单通常不需要特定json头，或者设为 urlencoded
                    else:
                        if params_data:
                            # GET 请求参数拼接到 URL 或 data (根据 SMSBoom 的习惯，GET 通常拼在 URL)
                            # 这里为了格式统一，如果 data 有值，smsboom 核心代码需要支持处理
                            # 暂时保留在 data 字段，或者手动拼接到 url
                            if '?' not in full_url:
                                full_url += "?" + params_data
                            else:
                                full_url += "&" + params_data
                            api_item['url'] = full_url
                            api_item['data'] = ""

                    # 必须包含 [phone] 占位符才算有效接口
                    data_str = str(api_item['data']) + api_item['url']
                    if "[phone]" in data_str:
                        self.found_apis.append(api_item)
                        logger.success(f"发现潜在接口: {summary} - {full_url}")

    def save(self, filename="swagger_apis.json"):
        if not self.found_apis:
            logger.warning("未找到有效接口")
            return
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.found_apis, f, ensure_ascii=False, indent=4)
        logger.info(f"已保存 {len(self.found_apis)} 个接口到 {filename}")

@click.command()
@click.option('--url', prompt='Swagger 文档地址', help='Swagger UI 或 JSON 地址')
def main(url):
    """Swagger 接口提取工具"""
    hunter = SwaggerHunter(url)
    data = hunter.fetch_json()
    if data:
        hunter.extract_apis(data)
        hunter.save()

if __name__ == '__main__':
    main()
