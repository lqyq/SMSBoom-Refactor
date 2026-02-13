import requests
import re
import os
from urllib.parse import urljoin

def fetch_bangtang_api(base_url="https://sms.bangtang.top/", save_chunk_file=False):
    print(f"正在访问: {base_url}")
    try:
        # 1. 获取主页 HTML
        response = requests.get(base_url, verify=False) # 忽略 SSL 证书验证，防止报错
        response.raise_for_status()
        html_content = response.text
        
        # 2. 查找 app.js 的路径
        # <script defer="defer" src="js/app.d7cd958f.js"></script>
        app_js_match = re.search(r'src=["\'](js/app\..*?\.js)["\']', html_content)
        if not app_js_match:
            print("未能在 HTML 中找到 app.js")
            return ''
            
        app_js_path = app_js_match.group(1)
        app_js_url = urljoin(base_url, app_js_path)
        print(f"找到 app.js: {app_js_url}")
        
        # 3. 获取 app.js 内容
        app_response = requests.get(app_js_url, verify=False)
        app_response.raise_for_status()
        app_js_content = app_response.text
        
        # 4. 查找含 API 的 chunk ID
        # 寻找 home 路由对应的 chunk ID
        # {path:"/",name:"home",component:()=>t.e(526).then(t.bind(t,4226))}
        chunk_id_match = re.search(r'path:\s*["\']\/["\'],\s*name:\s*["\']home["\'],\s*component:\s*\(\)\s*=>\s*\w\.e\((\d+)\)', app_js_content)
        
        if not chunk_id_match:
            print("未能在 app.js 中找到 home 路由的 chunk ID")
            # 备选方案：直接查找可能包含 API 的 chunk（通常比较大或者有特定特征）
            # 这里暂时只依赖 home 路由
            return ''
            
        chunk_id = chunk_id_match.group(1)
        print(f"找到目标 Chunk ID: {chunk_id}")
        
        # 5. 查找 Chunk 的 Hash 或文件名生成逻辑
        # t.u=function(e){return"js/"+e+".979e53a9.js"}
        # 或者查找 map: {526:"..."}
        # 尝试匹配 return "js/" + e + ".HASH.js"
        hash_match = re.search(r'return\s*["\']js/["\']\s*\+\s*e\s*\+\s*["\']\.(.*?)\.js["\']', app_js_content)
        
        chunk_filename = ""
        if hash_match:
            file_hash = hash_match.group(1)
            chunk_filename = f"js/{chunk_id}.{file_hash}.js"
        else:
            # 尝试查找 map 形式: {526:"hash", ...}
            # 这是简化查找，实际 webpack runtime 更复杂
            print("未能直接匹配到简单的 hash 生成逻辑，尝试查找 map...")
            # 这里的正则需要根据实际情况调整
            return ''
            
        chunk_url = urljoin(base_url, chunk_filename)
        print(f"目标文件 URL: {chunk_url}")
        
        # 6. 下载目标文件
        chunk_response = requests.get(chunk_url, verify=False)
        chunk_response.raise_for_status()
        
        if not save_chunk_file:
            return chunk_response.text
        
        save_path = f"debug/chunk-{chunk_id}.js"
        # 确保目录存在
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(chunk_response.text)
            
        print(f"文件已保存至: {save_path}")
        return save_path

    except Exception as e:
        print(f"发生错误: {e}")
        return ''

if __name__ == "__main__":
    # 禁用 urllib3 的警告
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    saved_file = fetch_bangtang_api()
    if saved_file:
        print("任务完成！")
        # 这里可以接着调用提取脚本
        # import extract_bangtang
        # apis = extract_bangtang.extract_apis_from_js(saved_file)
        # print(f"提取到 {len(apis)} 个接口")
    else:
        print("任务失败")
