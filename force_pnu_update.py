
import sys
import io
import os

# Set UTF-8 encoding for stdout/stderr
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import pandas as pd
import json
import re
from datetime import datetime

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'onbid_data.js')
EXCEL_FILE  = os.path.join(SCRIPT_DIR, 'KIKcd_B.20260301.xlsx')
GRADE_FILE  = os.path.join(SCRIPT_DIR, '강원 산지 등급_260309(필드 삭제).xlsx')

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def get_pnu_lookup():
    if not os.path.exists(EXCEL_FILE):
        log(f"엑셀 파일 없음: {EXCEL_FILE}")
        return {}
    try:
        log("PNU 참조 데이터를 불러오는 중...")
        df = pd.read_excel(EXCEL_FILE)
        lookup = {}
        for _, row in df.iterrows():
            code = str(row.iloc[0]).zfill(10)
            parts = [str(row.iloc[i]).strip() for i in [1,2,3,4] if pd.notna(row.iloc[i])]
            addr_key = " ".join(parts)
            lookup[addr_key] = code
        log(f"참조 데이터 {len(lookup)}건 로드 완료")
        return lookup
    except Exception as e:
        log(f"엑셀 로드 오류: {e}")
        return {}

def get_grade_lookup():
    if not os.path.exists(GRADE_FILE):
        log(f"등급 엑셀 파일 없음: {GRADE_FILE}")
        return {}
    try:
        log("강원 산지 등급 데이터를 불러오는 중...")
        # Columns: ['PNU_CD(New)', 'ADDR_NM', '구분', '등급']
        df = pd.read_excel(GRADE_FILE)
        grade_lookup = {}
        for _, row in df.iterrows():
            pnu = str(row['PNU_CD(New)']).strip()
            grade = str(row['등급']).strip()
            if pnu and grade:
                grade_lookup[pnu] = grade
        log(f"등급 데이터 {len(grade_lookup)}건 로드 완료")
        return grade_lookup
    except Exception as e:
        log(f"등급 엑셀 로드 오류: {e}")
        return {}

def parse_lot(lot_str):
    category = "1"
    if "산" in lot_str:
        category = "2"
        lot_str = lot_str.replace("산", "")
    
    lot_str = re.sub(r'[^0-9-]', '', lot_str)
    if not lot_str: return category, "00000000"
    
    match = re.search(r'(\d+)(?:-(\d+))?', lot_str)
    if match:
        main_num = match.group(1).zfill(4)
        sub_num = (match.group(2) if match.group(2) else "0").zfill(4)
        return category, main_num + sub_num
    return category, "00000000"

def generate_pnu(addr, lookup):
    if not addr or not lookup: return ""
    base_addr = addr.split(',')[0].strip()
    parts = base_addr.split()
    
    for i in range(len(parts), 0, -1):
        dong_candidate = " ".join(parts[:i])
        if dong_candidate in lookup:
            dong_code = lookup[dong_candidate]
            lot_part = parts[i] if i < len(parts) else ""
            cat, lot = parse_lot(lot_part)
            return dong_code + cat + lot
    return "NOT_FOUND"

def update_data():
    log("onbid_data.js의 PNU 및 등급 정보를 업데이트합니다.")
    if not os.path.exists(OUTPUT_FILE):
        log("파일 없음: onbid_data.js")
        return

    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        json_str = content.split('var ONBID_DATA = ')[1].strip()
        if json_str.endswith(';'): json_str = json_str[:-1]
        data = json.loads(json_str)
        
        pnu_lookup = get_pnu_lookup()
        grade_lookup = get_grade_lookup()
        
        pnu_success = 0
        grade_success = 0
        
        for item in data.get('items', []):
            addr = item.get('addr', '')
            pnu = generate_pnu(addr, pnu_lookup)
            item['pnu'] = pnu
            
            # Match Grade
            if pnu in grade_lookup:
                item['grade'] = grade_lookup[pnu]
                grade_success += 1
            else:
                # If not found in custom list, default to C
                item['grade'] = 'C'

            
            # Extract sigungu
            if 'sigungu' not in item and addr:
                parts = addr.split()
                if len(parts) > 1:
                    item['sigungu'] = parts[1]
            
            if pnu != "NOT_FOUND":
                pnu_success += 1
        
        # Save back
        data['updatedAt'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        new_content = "// 자동 생성 파일 - 직접 수정하지 마세요.\n"
        new_content += f"// 업데이트: {data['updatedAt']}\n"
        new_content += "var ONBID_DATA = " + json.dumps(data, indent=2, ensure_ascii=False) + ";"
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            f.write(new_content)
        
        log(f"업데이트 완료: {len(data['items'])}건 중 PNU {pnu_success}건 성공, 등급 매칭 {grade_success}건 성공")
        
    except Exception as e:
        log(f"파일 업데이트 중 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    update_data()
