import re
import json

def extract_apis_from_js(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 正则表达式匹配对象字面量，包含 method, url, params 等字段
    # 注意：JS 代码是压缩过的，所有内容可能在一行或少数几行
    # 我们寻找类似 {method:"get",url:`...`,params:...} 的模式
    
    # 匹配 method:"..."
    method_pattern = r'method\s*:\s*["\'](\w+)["\']'
    # 匹配 url: "..." 或 url: `...`
    url_pattern = r'url\s*:\s*[`"\']([^`"\']+)[\'"`]'
    # 匹配 referer (可选)
    referer_pattern = r'referer\s*:\s*["\']([^"\']+)["\']'

    # 由于是压缩代码，我们尝试分割成较小的块或查找特定数组结构
    # 在 chunk-526.js 中，API 列表似乎在一个数组中：p=e=>[{method:..., ...}, ...]
    
    start_index = content.find('p=e=>[')
    if start_index == -1:
        print("未找到 API 数组起始位置")
        return []

    # 简单提取数组部分（需要更健壮的解析，这里假设数组结束于 `];` 或 `}]`）
    # 考虑到嵌套结构，简单的 find 可能不够，但可以尝试提取足够长的字符串
    array_content = content[start_index:]
    
    # 使用正则查找所有匹配项
    # 构造一个能匹配整个对象的正则比较复杂，不如分别提取
    
    # 更好的策略：
    # 1. 找到包含 http/https 的 url 字段
    # 2. 向前查找 method
    # 3. 向后查找 params (通常 params 紧跟在 url 后面)

    apis = []
    
    # 查找所有 url:`...` 或 url:"..."
    # 考虑到模板字符串 `${e}` 代表手机号
    regex = r'\{method\s*:\s*["\'](\w+)["\']\s*,\s*url\s*:\s*[`"\'](.*?)[\'"`]\s*(?:,\s*params\s*:\s*(.*?))?(?:,\s*referer\s*:\s*["\'](.*?)["\'])?\}'
    
    matches = re.finditer(regex, content)
    
    for match in matches:
        method = match.group(1)
        url = match.group(2)
        params_raw = match.group(3)
        referer = match.group(4)
        
        # 处理 URL 中的变量
        url = url.replace('${e}', '[phone]')
        
        # 构建 API 对象
        api_entry = {
            "desc": "来自棒糖测压", # 默认描述
            "url": url,
            "method": method.upper(),
            "header": "",
            "data": ""
        }
        
        # 处理 Referer
        if referer:
            api_entry['header'] = {"Referer": referer}

        # 处理 Params (GET 请求通常参数在 URL 里，POST 请求在 data 里)
        if method.lower() == 'post' and params_raw:
             # 尝试解析 params
             # params:{phoneNumber:e} -> "phoneNumber=[phone]"
             # 这是一个简单的转换，复杂的对象可能需要更细致的解析
             if '{' in params_raw and '}' in params_raw:
                 # 提取 key:value
                 param_pairs = re.findall(r'(\w+)\s*:\s*(\w+)', params_raw)
                 data_parts = []
                 for key, val in param_pairs:
                     if val == 'e':
                         data_parts.append(f"{key}=[phone]")
                     else:
                         # 这里 val 可能是字符串常量，但在压缩代码中通常被替换了
                         # 如果 val 是 "..." 格式
                         pass 
                         # 暂时只处理简单的 key=[phone]
                 
                 if data_parts:
                     api_entry['data'] = "&".join(data_parts)
            
        apis.append(api_entry)

    return apis

if __name__ == "__main__":
    extracted_apis = extract_apis_from_js('debug/chunk-526.js')
    print(f"提取到 {len(extracted_apis)} 个接口")
    
    # 保存到文件以便查看
    with open('debug/bangtang_apis.json', 'w', encoding='utf-8') as f:
        json.dump(extracted_apis, f, ensure_ascii=False, indent=4)
