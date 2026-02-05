import re, json, os

def extract_smstest_apis(file_path):
    print(f"Reading file: {file_path}")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"File not found: {file_path}")
        return []

    # Locate the apiRequests array
    start_marker = "const apiRequests = ["
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print("Could not find 'const apiRequests = ['")
        return []

    # Heuristic to find the end of the array: Look for a line starting with indent and "]"
    # But simpler: scan forward and count brackets?
    # Or just Regex find all objects inside.
    
    # Let's extract everything from start_marker downwards
    sub_content = content[start_idx + len(start_marker):]
    
    # We will iterate through the string and extract objects
    # Pattern to match:
    # {
    #    url: '...',
    #    method: '...',
    #    headers: ... ({ ... }),
    #    data: ... ({ ... })
    # }
    
    # Since regex is hard for nested structures, let's process block by block using the fact that they are separated by "},"
    
    # First, trim until the first "{"
    first_brace = sub_content.find('{')
    if first_brace == -1:
        return []
    
    # We'll split by "},\n" or similar. 
    # Looking at the file, the indentation is consistent: "            },"
    
    # Let's try to match each object using a regex that looks for url, method, headers, data
    # We will search for pattern:
    # url: '([^']+)'
    # method: '([^']+)'
    # headers: \(\) => \(\{([\s\S]*?)\}\)
    # data: \(phoneNumber, times\) => \(\{([\s\S]*?)\}\)
    
    # Note: The order of fields seems consistent in the file.
    
    apis = []
    
    # Regex to find one object block. 
    # We use finditer on the whole content section
    
    block_pattern = re.compile(
        r"url:\s*'([^']+)',\s*"
        r"method:\s*'([^']+)',\s*"
        r"headers:\s*\(\)\s*=>\s*\(\{(.*?)\}\),\s*"
        r"data:\s*\(phoneNumber,\s*times\)\s*=>\s*\(\{(.*?)\}\)",
        re.DOTALL
    )
    
    matches = block_pattern.finditer(sub_content)
    
    for match in matches:
        url = match.group(1)
        method_raw = match.group(2)
        headers_raw = match.group(3)
        data_raw = match.group(4)
        
        # Process Method
        method = "GET"
        is_json = False
        if "POST" in method_raw:
            method = "POST"
            if "JSON" in method_raw:
                is_json = True
            
        # Process Headers
        headers = parse_js_object(headers_raw)
        
        # Process Data
        # Replace phoneNumber variable with "[phone]"
        data_raw_processed = data_raw.replace("phoneNumber", "'[phone]'")
        data = parse_js_object(data_raw_processed)
        
        # If it's not JSON (i.e. Form), convert data dict to string if it is a dict
        if not is_json and isinstance(data, dict):
            # Convert dict to query string
            # We need to handle nested dicts? Usually form data is flat.
            # If there are nested dicts in form data, they might be ignored or stringified.
            # Let's assume flat for now or simple string conversion.
            data_parts = []
            for k, v in data.items():
                # v might be '[phone]' or other values
                data_parts.append(f"{k}={v}")
            data = "&".join(data_parts)
        
        api_entry = {
            "desc": "来自smstest.lazy52.com",
            "url": url,
            "method": method,
            "header": headers,
            "data": data
        }
        
        apis.append(api_entry)
        
    return apis

def parse_js_object(raw_str):
    """
    Tries to convert a JS object string (key: value, ...) into a Python dict.
    """
    # 1. Remove comments if any (simple ones)
    lines = raw_str.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line: continue
        if line.startswith('//'): continue
        cleaned_lines.append(line)
    
    full_str = " ".join(cleaned_lines)
    
    # 2. Add quotes around keys
    # Keys are usually 'key' or just key. In this file they seem to be 'key' or key.
    # The file has: 'Connection': 'keep-alive' (quoted keys)
    # And: 'mobileNo': phoneNumber (quoted keys)
    # And nested: 'params': { "mobile": phoneNumber }
    
    # If keys are already quoted with single quotes, we need to ensure double quotes for JSON
    
    # Strategy: 
    # - Replace ' with "
    # - Handle trailing commas
    
    # Simple replacement of ' with "
    # Note: This might break if the content contains ' inside string. 
    # But usually in these files valid chars are simple.
    
    json_str = full_str.replace("'", '"')
    
    # Remove trailing commas before }
    json_str = re.sub(r',\s*}', '}', json_str)
    # Remove trailing comma at the end of the string if it exists (not strictly valid in JSON but we are parsing list of pairs)
    if json_str.endswith(','):
        json_str = json_str[:-1]
        
    # Wrap in braces to make it a valid JSON object string if it's just content
    if not json_str.strip().startswith('{'):
        json_str = "{" + json_str + "}"
        
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback manual parsing or return raw string if complex
        # print(f"Failed to parse JSON: {json_str[:50]}...")
        return try_manual_parsing(json_str)

def try_manual_parsing(json_str):
    """
    Extremely basic parser for flat dictionaries if json.loads fails.
    """
    # Remove outer braces
    inner = json_str.strip("{}")
    parts = inner.split(',')
    res = {}
    for part in parts:
        if ':' in part:
            k, v = part.split(':', 1)
            k = k.strip().strip('"')
            v = v.strip().strip('"')
            res[k] = v
    return res

if __name__ == "__main__":
    source_file = "debug/view-source_https___smstest.lazy52.com.html"
    apis = extract_smstest_apis(source_file)
    print(f"Extracted {len(apis)} APIs")
    
    output_file = "debug/smstest_apis.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(apis, f, ensure_ascii=False, indent=4)
    print(f"Saved to {output_file}")
