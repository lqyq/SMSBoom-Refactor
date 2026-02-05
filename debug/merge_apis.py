import json
import os

def merge_apis(source_file, target_file):
    if not os.path.exists(source_file):
        print(f"源文件 {source_file} 不存在")
        return

    if not os.path.exists(target_file):
        print(f"目标文件 {target_file} 不存在")
        return

    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            new_apis = json.load(f)
        
        with open(target_file, 'r', encoding='utf-8') as f:
            existing_apis = json.load(f)
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误: {e}")
        return

    # 使用 URL 作为去重键
    existing_urls = set(api['url'] for api in existing_apis)
    
    added_count = 0
    for api in new_apis:
        # 清理 URL 中的变量格式，确保统一
        # 假设现有 api.json 使用 [phone] 作为占位符
        # 我们的提取脚本已经处理了 ${e} -> [phone]
        
        url = api['url']
        if url not in existing_urls:
            existing_apis.append(api)
            existing_urls.add(url)
            added_count += 1
    
    if added_count > 0:
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(existing_apis, f, ensure_ascii=False, indent=4)
        print(f"成功合并 {added_count} 个新接口到 {target_file}")
    else:
        print("没有新的接口需要合并")

if __name__ == "__main__":
    merge_apis('debug/bangtang_apis.json', 'api.json')
