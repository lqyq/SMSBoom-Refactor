import json
import os

def merge_apis(source_file, target_file):
    """
    Merges APIs from source_file into target_file, avoiding duplicates based on URL.
    """
    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            new_apis = json.load(f)
    except FileNotFoundError:
        print(f"Error: Source file '{source_file}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from '{source_file}'.")
        return

    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            existing_apis = json.load(f)
    except FileNotFoundError:
        print(f"Warning: Target file '{target_file}' not found. Creating new file.")
        existing_apis = []
    except json.JSONDecodeError:
        print(f"Error: Failed to decode JSON from '{target_file}'.")
        return

    # Create a set of existing URLs for fast lookup
    existing_urls = {api.get('url') for api in existing_apis if api.get('url')}
    
    added_count = 0
    for api in new_apis:
        url = api.get('url')
        if url and url not in existing_urls:
            existing_apis.append(api)
            existing_urls.add(url)
            added_count += 1
            print(f"Added new API: {api.get('desc', 'No Description')} - {url}")

    if added_count > 0:
        with open(target_file, 'w', encoding='utf-8') as f:
            json.dump(existing_apis, f, indent=4, ensure_ascii=False)
        print(f"Successfully merged {added_count} new APIs into '{target_file}'.")
    else:
        print("No new APIs were added (all duplicates).")

if __name__ == "__main__":
    source = 'debug/github_api.json'
    target = 'api.json'
    merge_apis(source, target)
