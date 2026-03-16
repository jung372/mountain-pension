"""
onbid.go.kr 산지 공매 데이터 자동 수집 스크립트
- API: 한국자산관리공사_차세대 온비드 부동산 물건목록 조회서비스 (data.go.kr/data/15157207)
- 매일 1회 실행 (Windows 작업 스케줄러 연동)
- 결과를 onbid_data.js 파일로 저장 (HTML에서 직접 로드 가능)

[수정 이력]
v1.5 - 지분 물건 여부(quotaYn) 수집 추가
     - 주소 추출 로직 강화: onbidCltrNm 우선, 지번 없으면 ldnmAdrs 사용
     - 임야 필터: cltrUsgMclsCtgrNm = '토지' OR 물건명에 임야 포함
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import requests
import json
import os
from datetime import datetime
import time
import pandas as pd
import re

# ─────────────────────────────────────────────
# 1. 설정 정보
# ─────────────────────────────────────────────
URL = 'https://apis.data.go.kr/B010003/OnbidRlstListSrvc/getRlstCltrList'

def load_env():
    """.env 파일에서 환경변수 로드 (python-dotenv 대용)"""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

# 환경 변수 로드
load_env()

# 환경 변수에서 AUTH_KEY 가져오기 (GitHub Actions 또는 로컬 .env)
AUTH_KEY = os.environ.get('ONBID_AUTH_KEY')

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(SCRIPT_DIR, 'onbid_data.js')
LOG_FILE    = os.path.join(SCRIPT_DIR, 'fetch_log.txt')

# ─────────────────────────────────────────────
# 2. 수집 대상 지역 + 재산유형 조합
#    ★ 핵심 변경:
#      - lctnSdnm 으로 지역 직접 필터 (서버 측 필터)
#      - 1페이지만 아닌 전 페이지 수집
#      - bidDivCd 제거 (현장입찰도 포함)
# ─────────────────────────────────────────────
REGIONS = [
    '강원특별자치도', '경기도', '경상북도', '경상남도',
    '전라남도', '전북특별자치도', '충청북도', '충청남도',
    '인천광역시', '서울특별시', '부산광역시',
    '대구광역시', '광주광역시', '대전광역시',
    '울산광역시', '세종특별자치시', '제주특별자치도',
]

PRPT_CODES = [
    ('0007', '압류재산'),
    ('0005', '기타일반재산'),
    # ('0010', '국유재산'),   # 임야 데이터 없음 (사전 확인)
    # ('0003', '금융권담보재산'),  # 임야 데이터 없음 (사전 확인)
]

ROWS_PER_PAGE = 300   # API 부하 및 타임아웃 방지를 위해 적정 수준으로 조정

# ─────────────────────────────────────────────
# 3. 임야 판별 기준
#    API 응답에서 임야(산지)는 cltrUsgMclsCtgrNm = '토지' 또는
#    cltrUsgSclsCtgrNm에 '임야', '전', '답' 등 포함
# ─────────────────────────────────────────────
# 온비드 사이트 기준 "임야" = cltrUsgSclsCtgrNm 산지성 지목
# 사용자의 요청에 따라 '전', '답' 등은 제외하고 순수 '임야'만 필터링합니다.
FOREST_SCAT = {
    '임야',       # 임야 (핵심)
}

def is_forest(item):
    """임야/산지 물건인지 판별 - 온비드 사이트와 동일 기준"""
    scat = item.get('cltrUsgSclsCtgrNm', '') or ''
    name = item.get('onbidCltrNm', '') or ''
    # 소분류(지목)가 산지성이면 포함
    if scat in FOREST_SCAT:
        return True
    # 물건명에 '임야' 직접 표기된 경우
    if '임야' in name:
        return True
    return False


# ─────────────────────────────────────────────
# 4. 로그 함수
# ─────────────────────────────────────────────
def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{now}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass

# ─────────────────────────────────────────────
# 5. 금액 포맷
# ─────────────────────────────────────────────
def fmt_amt(val):
    try:
        v = float(val)
    except (TypeError, ValueError):
        return '비공개'
    if v <= 0:
        return '비공개'
    if v >= 100_000_000:
        return f"{v/100_000_000:,.1f}억원"
    if v >= 10_000:
        return f"{v/10_000:,.0f}만원"
    return f"{v:,.0f}원"

def safe_float(val):
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0

def safe_int(val):
    try:
        return int(float(val or 0))
    except (TypeError, ValueError):
        return 0

# ─────────────────────────────────────────────
# 5.5 PNU 생성 유틸리티
# ─────────────────────────────────────────────
def get_pnu_lookup():
    excel_path = os.path.join(SCRIPT_DIR, 'KIKcd_B.20260301.xlsx')
    if not os.path.exists(excel_path):
        log(f"! PNU 참조 파일 없음: {excel_path}")
        return {}
    
    try:
        df = pd.read_excel(excel_path)
        lookup = {}
        for _, row in df.iterrows():
            code = str(row.iloc[0]).zfill(10)
            parts = [str(row.iloc[i]).strip() for i in [1,2,3,4] if pd.notna(row.iloc[i])]
            addr_key = " ".join(parts)
            lookup[addr_key] = code
        log(f"PNU 참조 데이터 {len(lookup)}건 로드 완료")
        return lookup
    except Exception as e:
        log(f"! PNU 참조 파일 로드 오류: {e}")
        return {}

def get_grade_lookup():
    excel_path = os.path.join(SCRIPT_DIR, '강원 산지 등급_260309(필드 삭제).xlsx')
    if not os.path.exists(excel_path):
        log(f"! 등급 참조 파일 없음: {excel_path}")
        return {}
    try:
        df = pd.read_excel(excel_path)
        lookup = {}
        for _, row in df.iterrows():
            pnu = str(row['PNU_CD(New)']).strip()
            grade = str(row['등급']).strip()
            if pnu and grade:
                lookup[pnu] = grade
        log(f"등급 참조 데이터 {len(lookup)}건 로드 완료")
        return lookup
    except Exception as e:
        log(f"! 등급 참조 파일 로드 오류: {e}")
        return {}


def parse_lot_number(lot_str):
    category = "1"
    if "산" in lot_str:
        category = "2"
        lot_str = re.sub(r'[^0-9-]', '', lot_str.replace("산", ""))
    else:
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
    primary_addr = addr.split(',')[0].strip()
    parts = primary_addr.split()
    
    for i in range(len(parts), 0, -1):
        dong_candidate = " ".join(parts[:i])
        if dong_candidate in lookup:
            dong_code = lookup[dong_candidate]
            lot_part = parts[i] if i < len(parts) else ""
            category, lot_code = parse_lot_number(lot_part)
            return dong_code + category + lot_code
            
    # Fallback
    dong_candidate = " ".join(parts[:-1])
    if dong_candidate in lookup:
        dong_code = lookup[dong_candidate]
        lot_part = parts[-1]
        category, lot_code = parse_lot_number(lot_part)
        return dong_code + category + lot_code
    return ""

# ─────────────────────────────────────────────
# 6. 필드 정제
# ─────────────────────────────────────────────
def clean_item(item):
    cltr_no = item.get('cltrMngNo', '')
    pbct_no = str(item.get('pbctCdtnNo', ''))
    usbd_cnt = safe_int(item.get('usbdNft', 0))

    sido = item.get('lctnSdnm', '')
    sgg  = item.get('lctnSggnm', '')
    emd  = item.get('lctnEmdNm', '')
    
    name_addr = (item.get('onbidCltrNm', '') or '').strip()
    jibun_addr = (item.get('ldnmAdrs', '') or '').strip()
    
    def has_jibun(s):
        return any(c.isdigit() for c in s) or '산' in s

    if has_jibun(name_addr):
        addr = name_addr
    elif has_jibun(jibun_addr):
        addr = jibun_addr
    else:
        addr = name_addr if len(name_addr) > len(jibun_addr) else jibun_addr
        if not addr:
            addr = ' '.join(filter(None, [sido, sgg, emd]))

    mcat_nm = item.get('cltrUsgMclsCtgrNm', '') or ''
    scat_nm = item.get('cltrUsgSclsCtgrNm', '') or ''
    use_nm  = scat_nm or mcat_nm or '토지'

    min_bid_raw = item.get('lowstBidPrcIndctCont', '') or ''
    try:
        min_bid_num = safe_float(str(min_bid_raw).replace(',', ''))
    except:
        min_bid_num = 0.0
    min_bid_str = fmt_amt(min_bid_num) if min_bid_num > 0 else '비공개'

    appr_raw = safe_float(item.get('apslEvlAmt', 0))
    apsl_rto = item.get('apslPrcCtrsLowstBidRto', None)

    onbid_url = (
        f"https://www.onbid.co.kr/op/pblc/cltrInfo/opMnrCltrDtlsForm.do"
        f"?cltrMngNo={cltr_no}&pbctCdtnNo={pbct_no}"
    )

    return {
        'cltrNo'      : cltr_no,
        'cltrNm'      : item.get('onbidCltrNm', ''),
        'addr'        : addr,
        'sido'        : sido,
        'sigungu'     : sgg,
        'useNm'       : use_nm,
        'area'        : str(safe_float(item.get('landSqms', 0))),
        'apprAmt'     : fmt_amt(appr_raw),
        'minBidAmt'   : min_bid_str,
        'apprAmtRaw'  : appr_raw,
        'minBidAmtRaw': min_bid_num,
        'usbdCnt'     : usbd_cnt,
        'bidBgDt'     : item.get('cltrBidBgngDt', ''),
        'bidEdDt'     : item.get('cltrBidEndDt', ''),
        'pbctNo'      : pbct_no,
        'pbctNsq'     : item.get('pbctNsq', ''),
        'prptDivNm'   : item.get('prptDivNm', ''),
        'orgNm'       : item.get('exctOrgNm', ''),
        'thumbUrl'    : item.get('thnlImgUrlAdr', ''),
        'onbidUrl'    : onbid_url,
        'apslPrcRto'  : apsl_rto,
        'batcBidYn'   : item.get('batcBidYn', 'N'),
        'pvctTrgtYn'  : item.get('pvctTrgtYn', 'N'),
        'alcYn'       : 'Y' if item.get('alcYn') == 'Y' or '지분' in item.get('onbidCltrNm', '') else 'N',
    }

# ─────────────────────────────────────────────
# 7. 단일 (지역, 재산유형) 조합 전 페이지 수집
# ─────────────────────────────────────────────
def fetch_region_prpt(region, prpt_cd, prpt_nm, seen_ids):
    """지역 + 재산유형 조합으로 모든 페이지 수집"""
    results = []
    page = 1

    while True:
        params = {
            'serviceKey'  : AUTH_KEY,
            'pageNo'      : str(page),
            'numOfRows'   : str(ROWS_PER_PAGE),
            'resultType'  : 'json',
            'prptDivCd'   : prpt_cd,
            'dspsMthodCd' : '0001',   # 매각
            'bidDivCd'    : '0001',   # 전자입찰 (필수 파라미터)
            'lctnSdnm'    : region,   # 지역 필터 (서버 측)
        }
        try:
            resp = requests.get(URL, params=params, timeout=60)
            if resp.status_code != 200:
                log(f"    [HTTP오류] {resp.status_code}")
                break

            data = resp.json()
            header = data.get('header', data.get('result', {}))
            rc = header.get('resultCode', '')

            if rc == '03':   # NODATA
                break
            if rc not in ('00', '0', '200'):
                log(f"    [API오류] {rc}: {header.get('resultMsg','')}")
                return None

            body = data.get('body', {})
            total_cnt = int(body.get('totalCount', 0))
            items_node = body.get('items', {})
            raw = items_node.get('item', []) if isinstance(items_node, dict) else []
            if isinstance(raw, dict):
                raw = [raw]

            for item in raw:
                usbd = safe_int(item.get('usbdNft', 0))
                if usbd < 2:
                    continue
                if not is_forest(item):
                    continue
                uid = item.get('cltrMngNo', '')
                if uid and uid in seen_ids:
                    continue
                if uid:
                    seen_ids.add(uid)
                results.append(clean_item(item))

            # 페이지 끝 판단
            if page * ROWS_PER_PAGE >= total_cnt or len(raw) < ROWS_PER_PAGE:
                break
            page += 1
            time.sleep(0.3)   # API 호출 간격

        except requests.exceptions.Timeout:
            log(f"    [타임아웃] {region}/{prpt_nm} p{page}")
            return None
        except Exception as e:
            log(f"    [오류] {e}")
            return None

    return results

# ─────────────────────────────────────────────
# 8. 전체 수집
# ─────────────────────────────────────────────
def fetch_all():
    all_items = []
    seen_ids  = set()
    has_error = False

    for prpt_cd, prpt_nm in PRPT_CODES:
        log(f"[{prpt_nm}] 지역별 수집 시작 ({len(REGIONS)}개 지역)")
        for region in REGIONS:
            before = len(all_items)
            items = fetch_region_prpt(region, prpt_cd, prpt_nm, seen_ids)
            if items is None:
                has_error = True
                continue
            all_items.extend(items)
            added = len(all_items) - before
            if added > 0:
                log(f"  {region}: +{added}건 (누계 {len(all_items)}건)")
            time.sleep(0.2)

    # 일부 지역에서 오류가 발생하더라도 수집된 데이터가 있다면 반환 (부분 성공 허용)
    if has_error:
        log("! 주의: 일부 지역 또는 재산유형 수집 중 오류(타임아웃 등)가 발생했습니다. 수집된 범위까지만 저장합니다.")
    return all_items

# ─────────────────────────────────────────────
# 9. JS 파일로 저장
# ─────────────────────────────────────────────
def save_as_js(items):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    payload = {
        'updatedAt' : now_str,
        'totalCount': len(items),
        'items'     : items,
    }
    js_content = (
        "// 자동 생성 파일 - 직접 수정하지 마세요.\n"
        f"// 생성일시: {now_str}\n"
        "var ONBID_DATA = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n"
    )
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(js_content)
    log(f"[완료] 저장: {OUTPUT_FILE} ({len(items)}건)")

# ─────────────────────────────────────────────
# 10. 실행
# ─────────────────────────────────────────────
if __name__ == '__main__':
    log("=" * 55)
    log("산지 공매 데이터 수집 시작 (v1.5 — 전 지역/전 페이지)")
    t0 = time.time()
    items = fetch_all()
    elapsed = time.time() - t0
    
    if items:
        # PNU 생성
        lookup = get_pnu_lookup()
        if lookup:
            log("PNU 코드 및 등급 생성 중...")
            grade_lookup = get_grade_lookup()
            for item in items:
                pnu = generate_pnu(item['addr'], lookup)
                item['pnu'] = pnu
                # Match Grade
                if pnu in grade_lookup:
                    item['grade'] = grade_lookup[pnu]
                else:
                    item['grade'] = 'C'

        
        save_as_js(items)
        log(f"최종 결과: 유찰 2회 이상 임야 {len(items)}건 저장 ({elapsed:.0f}초)")
    else:
        log("수집된 데이터가 없거나 수집 중 오류가 발생했습니다.")
        
    log("수집 완료")
    log("=" * 55)
