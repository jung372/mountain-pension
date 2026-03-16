
import sys
import io

# Ensure UTF-8 output for terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import json
import os

def check_status():
    js_path = r'd:\05 AI 스터디\Sanji pension\onbid_data.js'
    print(f"--- 파일 확인: {js_path} ---")
    
    if not os.path.exists(js_path):
        print("에러: onbid_data.js 파일이 없습니다.")
        return

    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        json_str = content.split('var ONBID_DATA = ')[1].strip()
        if json_str.endswith(';'): json_str = json_str[:-1]
        data = json.loads(json_str)
        
        items = data.get('items', [])
        print(f"총 아이템 수: {len(items)}")
        
        if items:
            sample = items[0]
            print(f"샘플 주소: {sample.get('addr')}")
            print(f"샘플 PNU: {sample.get('pnu')}")
            
            pnu_exists = all('pnu' in item for item in items[:10])
            print(f"상위 10개 PNU 존재 여부: {pnu_exists}")
            
            pnu_values = [item.get('pnu') for item in items[:5]]
            print(f"샘플 PNU 값들: {pnu_values}")

    except Exception as e:
        print(f"에러: 파일 파싱 중 오류 발생 - {e}")

if __name__ == "__main__":
    check_status()
