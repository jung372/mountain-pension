
import pandas as pd
import json
import re
import os

def parse_lot_number(lot_str):
    # Determine land category (1 for general, 2 for mountain/산)
    category = "1"
    if "산" in lot_str:
        category = "2"
        # Remove '산' and any non-digit/dash characters like '번지'
        lot_str = re.sub(r'[^0-9-]', '', lot_str.replace("산", ""))
    else:
        lot_str = re.sub(r'[^0-9-]', '', lot_str)
    
    if not lot_str:
        return category, "00000000"

    # Split into main and sub numbers (본번-부번)
    match = re.search(r'(\d+)(?:-(\d+))?', lot_str)
    if match:
        main_num = match.group(1).zfill(4)
        sub_num = (match.group(2) if match.group(2) else "0").zfill(4)
        return category, main_num + sub_num
    else:
        return category, "00000000"

def get_pnu_lookup():
    excel_path = r'd:\05 AI 스터디\Sanji pension\KIKcd_B.20260301.xlsx'
    df = pd.read_excel(excel_path)
    
    # Use indices to avoid encoding issues with column names
    # Index 0: Code, 1: Sido, 2: Sigungu, 3: Eupmyeondong, 4: Ri
    lookup = {}
    for _, row in df.iterrows():
        try:
            code = str(row.iloc[0])
            if len(code) < 10: code = code.zfill(10)
            
            parts = []
            if pd.notna(row.iloc[1]): parts.append(str(row.iloc[1]).strip())
            if pd.notna(row.iloc[2]): parts.append(str(row.iloc[2]).strip())
            if pd.notna(row.iloc[3]): parts.append(str(row.iloc[3]).strip())
            if pd.notna(row.iloc[4]): parts.append(str(row.iloc[4]).strip())
            
            addr_key = " ".join(parts)
            lookup[addr_key] = code
        except:
            continue
    return lookup

def process_onbid_data(lookup):
    js_path = r'd:\05 AI 스터디\Sanji pension\onbid_data.js'
    if not os.path.exists(js_path):
        print(f"File not found: {js_path}")
        return

    with open(js_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    try:
        json_part = content.split('var ONBID_DATA = ')[1].strip()
        if json_part.endswith(';'): json_part = json_part[:-1]
        data = json.loads(json_part)
    except Exception as e:
        print(f"Error parsing JS: {e}")
        return
    
    count = 0
    for item in data['items']:
        addr = item.get('addr', '').strip()
        if not addr: continue
        
        # Clean address from extra spaces and comma-separated multiple lots
        # Example: "강원특별자치도 정선군 화암면 화암리 산21-4 , 산21-5"
        # We take the first part
        primary_addr = addr.split(',')[0].strip()
        parts = primary_addr.split()
        
        pnu = ""
        # Match from longest possible legal dong string
        # Typically addr is "Sido Sigungu Eupmyeondong Ri LotNumber"
        # We try to find the code for "Sido Sigungu Eupmyeondong Ri"
        
        found_dong_code = None
        lot_part = ""
        
        # Try matching prefixes
        for i in range(len(parts), 0, -1):
            dong_candidate = " ".join(parts[:i])
            if dong_candidate in lookup:
                found_dong_code = lookup[dong_candidate]
                # The next part is likely the lot number
                if i < len(parts):
                    lot_part = parts[i]
                break
        
        if found_dong_code:
            category, lot_code = parse_lot_number(lot_part)
            pnu = found_dong_code + category + lot_code
        else:
            # Fallback for multi-word lot numbers or parsing issues
            # Often the last part is the lot number
            dong_candidate = " ".join(parts[:-1])
            if dong_candidate in lookup:
                found_dong_code = lookup[dong_candidate]
                lot_part = parts[-1]
                category, lot_code = parse_lot_number(lot_part)
                pnu = found_dong_code + category + lot_code
            else:
                pnu = "NOT_FOUND"
        
        item['pnu'] = pnu
        count += 1
        
    # Serialize back
    new_js = "// 자동 생성 파일 - 직접 수정하지 마세요.\n"
    new_js += f"// 생성일시: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n"
    new_js += "var ONBID_DATA = " + json.dumps(data, indent=2, ensure_ascii=False) + ";"
    
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(new_js)
    print(f"Updated {count} items with PNU codes.")

if __name__ == "__main__":
    print("Loading legal dong codes...")
    lookup = get_pnu_lookup()
    print(f"Loaded {len(lookup)} mapping entries.")
    process_onbid_data(lookup)
