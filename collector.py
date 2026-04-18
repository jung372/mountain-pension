"""
산지연금 데이터 수집기 (GitHub Actions용)
- onbid.go.kr API에서 임야 공매 데이터 수집
- data/YYYY-MM-DD.json 으로 저장 후 GitHub Push
"""

import sys, io, os, re, json, time, requests
import pandas as pd
from datetime import datetime, timezone, timedelta

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

KST = timezone(timedelta(hours=9))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')
URL        = 'https://apis.data.go.kr/B010003/OnbidRlstListSrvc/getRlstCltrList'

AUTH_KEY = os.environ.get('ONBID_AUTH_KEY', '')

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
]

ROWS_PER_PAGE = 300
FOREST_SCAT   = {'임야'}


# ── 로그 ──────────────────────────────────────────────────────────────────────
def log(msg):
    print(f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}")


# ── 금액 포맷 ──────────────────────────────────────────────────────────────────
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


# ── 상태 판별 ─────────────────────────────────────────────────────────────────
def get_status(bid_bg_dt: str, bid_ed_dt: str) -> str:
    today = datetime.now(KST).date()
    for fmt in ('%Y%m%d%H%M%S', '%Y%m%d', '%Y-%m-%d'):
        try:
            bg = datetime.strptime(str(bid_bg_dt)[:len(fmt.replace('%Y','0000').replace('%m','00').replace('%d','00').replace('%H','00').replace('%M','00').replace('%S','00'))], fmt).date()
            ed = datetime.strptime(str(bid_ed_dt)[:len(fmt.replace('%Y','0000').replace('%m','00').replace('%d','00').replace('%H','00').replace('%M','00').replace('%S','00'))], fmt).date()
            if today < bg:
                return '공고중'
            if bg <= today <= ed:
                return '입찰중'
            return '종료'
        except Exception:
            continue
    return '미정'


def get_status_from_dates(bid_bg_dt: str, bid_ed_dt: str) -> str:
    today = datetime.now(KST).date()
    def parse_date(s):
        s = str(s or '').strip()
        for fmt in ('%Y%m%d%H%M%S', '%Y%m%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                return datetime.strptime(s[:len(fmt)-fmt.count('%')+(fmt.count('%')*2)], fmt).date()
            except Exception:
                pass
        # 숫자만 추출해서 8자리 시도
        digits = re.sub(r'\D', '', s)
        if len(digits) >= 8:
            try:
                return datetime.strptime(digits[:8], '%Y%m%d').date()
            except Exception:
                pass
        return None

    bg = parse_date(bid_bg_dt)
    ed = parse_date(bid_ed_dt)
    if bg is None or ed is None:
        return '미정'
    if today < bg:
        return '공고중'
    if bg <= today <= ed:
        return '입찰중'
    return '종료'


# ── 임야 판별 ─────────────────────────────────────────────────────────────────
def is_forest(item) -> bool:
    scat = item.get('cltrUsgSclsCtgrNm', '') or ''
    name = item.get('onbidCltrNm', '') or ''
    return scat in FOREST_SCAT or '임야' in name


# ── PNU / 등급 로드 ───────────────────────────────────────────────────────────
def load_pnu_lookup():
    path = os.path.join(SCRIPT_DIR, 'KIKcd_B.20260301.xlsx')
    if not os.path.exists(path):
        log(f'! PNU 참조 파일 없음: {path}')
        return {}
    try:
        df = pd.read_excel(path)
        lookup = {}
        for _, row in df.iterrows():
            code = str(row.iloc[0]).zfill(10)
            parts = [str(row.iloc[i]).strip() for i in range(1, 5) if pd.notna(row.iloc[i])]
            lookup[' '.join(parts)] = code
        log(f'PNU 참조 {len(lookup):,}건 로드')
        return lookup
    except Exception as e:
        log(f'! PNU 로드 오류: {e}')
        return {}

def load_grade_lookup():
    lookup = {}
    grade_files = [
        '강원 산지 등급_260309(필드 삭제).xlsx',
        '경북 산지 등급_260327.xlsx',
    ]
    for fname in grade_files:
        path = os.path.join(SCRIPT_DIR, fname)
        if not os.path.exists(path):
            log(f'! 등급 파일 없음 (건너뜀): {fname}')
            continue
        try:
            df = pd.read_excel(path)
            before = len(lookup)
            for _, row in df.iterrows():
                pnu   = str(row.iloc[0]).strip()
                grade = str(row.iloc[1]).strip()
                if pnu and grade and pnu != 'nan' and grade != 'nan':
                    lookup[pnu] = grade
            log(f'등급 로드: {fname} → +{len(lookup)-before:,}건')
        except Exception as e:
            log(f'! 등급 로드 오류 ({fname}): {e}')
    return lookup

def parse_lot_number(lot_str):
    category = '1'
    if '산' in lot_str:
        category = '2'
        lot_str = re.sub(r'[^0-9-]', '', lot_str.replace('산', ''))
    else:
        lot_str = re.sub(r'[^0-9-]', '', lot_str)
    if not lot_str:
        return category, '00000000'
    m = re.search(r'(\d+)(?:-(\d+))?', lot_str)
    if m:
        main = m.group(1).zfill(4)
        sub  = (m.group(2) or '0').zfill(4)
        return category, main + sub
    return category, '00000000'

def generate_pnu(addr, lookup):
    if not addr or not lookup:
        return ''
    primary = addr.split(',')[0].strip()
    parts   = primary.split()
    for i in range(len(parts), 0, -1):
        key = ' '.join(parts[:i])
        if key in lookup:
            lot  = parts[i] if i < len(parts) else ''
            cat, code = parse_lot_number(lot)
            return lookup[key] + cat + code
    key = ' '.join(parts[:-1])
    if key in lookup:
        cat, code = parse_lot_number(parts[-1])
        return lookup[key] + cat + code
    return ''


# ── 주소 추출 ─────────────────────────────────────────────────────────────────
def extract_addr(item):
    sido = item.get('lctnSdnm', '')
    sgg  = item.get('lctnSggnm', '')
    emd  = item.get('lctnEmdNm', '')
    name_addr  = (item.get('onbidCltrNm', '') or '').strip()
    jibun_addr = (item.get('ldnmAdrs', '') or '').strip()

    def has_jibun(s):
        return any(c.isdigit() for c in s) or '산' in s

    if has_jibun(name_addr):
        return name_addr
    if has_jibun(jibun_addr):
        return jibun_addr
    addr = name_addr if len(name_addr) >= len(jibun_addr) else jibun_addr
    return addr or ' '.join(filter(None, [sido, sgg, emd]))


# ── 아이템 정제 ───────────────────────────────────────────────────────────────
def clean_item(item):
    cltr_no  = item.get('cltrMngNo', '')
    pbct_no  = str(item.get('pbctCdtnNo', ''))
    addr     = extract_addr(item)
    sido     = item.get('lctnSdnm', '')
    sgg      = item.get('lctnSggnm', '')
    scat_nm  = item.get('cltrUsgSclsCtgrNm', '') or ''
    mcat_nm  = item.get('cltrUsgMclsCtgrNm', '') or ''
    appr_raw = safe_float(item.get('apslEvlAmt', 0))
    min_bid_raw = safe_float(str(item.get('lowstBidPrcIndctCont', '') or '').replace(',', ''))
    bid_bg   = item.get('cltrBidBgngDt', '')
    bid_ed   = item.get('cltrBidEndDt', '')

    return {
        'cltrNo'      : cltr_no,
        'cltrNm'      : item.get('onbidCltrNm', ''),
        'addr'        : addr,
        'sido'        : sido,
        'sigungu'     : sgg,
        'useNm'       : scat_nm or mcat_nm or '토지',
        'area'        : str(safe_float(item.get('landSqms', 0))),
        'apprAmt'     : fmt_amt(appr_raw),
        'minBidAmt'   : fmt_amt(min_bid_raw) if min_bid_raw > 0 else '비공개',
        'apprAmtRaw'  : appr_raw,
        'minBidAmtRaw': min_bid_raw,
        'usbdCnt'     : safe_int(item.get('usbdNft', 0)),
        'bidBgDt'     : bid_bg,
        'bidEdDt'     : bid_ed,
        'status'      : get_status_from_dates(bid_bg, bid_ed),
        'pbctNo'      : pbct_no,
        'pbctNsq'     : item.get('pbctNsq', ''),
        'prptDivNm'   : item.get('prptDivNm', ''),
        'orgNm'       : item.get('exctOrgNm', ''),
        'onbidUrl'    : (
            f"https://www.onbid.co.kr/op/pblc/cltrInfo/opMnrCltrDtlsForm.do"
            f"?cltrMngNo={cltr_no}&pbctCdtnNo={pbct_no}"
        ),
        'alcYn'       : 'Y' if item.get('alcYn') == 'Y' or '지분' in item.get('onbidCltrNm', '') else 'N',
        'grade'       : 'C',  # 이후 PNU 매칭으로 업데이트
        'pnu'         : '',
    }


# ── 지역 × 재산유형 수집 ──────────────────────────────────────────────────────
def fetch_region_prpt(region, prpt_cd, prpt_nm, seen_ids):
    results = []
    page    = 1
    while True:
        params = {
            'serviceKey' : AUTH_KEY,
            'pageNo'     : str(page),
            'numOfRows'  : str(ROWS_PER_PAGE),
            'resultType' : 'json',
            'prptDivCd'  : prpt_cd,
            'dspsMthodCd': '0001',
            'bidDivCd'   : '0001',
            'lctnSdnm'   : region,
        }
        try:
            resp = requests.get(URL, params=params, timeout=60)
            if resp.status_code != 200:
                log(f'  [HTTP오류] {resp.status_code}')
                break
            data   = resp.json()
            header = data.get('header', data.get('result', {}))
            rc     = header.get('resultCode', '')
            if rc == '03':
                break
            if rc not in ('00', '0', '200'):
                log(f'  [API오류] {rc}: {header.get("resultMsg","")}')
                return None

            body       = data.get('body', {})
            total_cnt  = int(body.get('totalCount', 0))
            items_node = body.get('items', {})
            raw        = items_node.get('item', []) if isinstance(items_node, dict) else []
            if isinstance(raw, dict):
                raw = [raw]

            for item in raw:
                if safe_int(item.get('usbdNft', 0)) < 2:
                    continue
                if not is_forest(item):
                    continue
                uid = item.get('cltrMngNo', '')
                if uid and uid in seen_ids:
                    continue
                if uid:
                    seen_ids.add(uid)
                results.append(clean_item(item))

            if page * ROWS_PER_PAGE >= total_cnt or len(raw) < ROWS_PER_PAGE:
                break
            page += 1
            time.sleep(0.3)
        except requests.exceptions.Timeout:
            log(f'  [타임아웃] {region}/{prpt_nm} p{page}')
            return None
        except Exception as e:
            log(f'  [오류] {e}')
            return None
    return results


# ── 전체 수집 ─────────────────────────────────────────────────────────────────
def fetch_all():
    all_items = []
    seen_ids  = set()
    has_error = False
    for prpt_cd, prpt_nm in PRPT_CODES:
        log(f'[{prpt_nm}] 수집 시작')
        for region in REGIONS:
            before = len(all_items)
            items  = fetch_region_prpt(region, prpt_cd, prpt_nm, seen_ids)
            if items is None:
                has_error = True
                continue
            all_items.extend(items)
            if len(all_items) > before:
                log(f'  {region}: +{len(all_items)-before}건 (누계 {len(all_items)}건)')
            time.sleep(0.2)
    if has_error:
        log('! 일부 지역 오류 발생 — 수집된 범위까지 저장')
    return all_items


# ── 저장 ──────────────────────────────────────────────────────────────────────
def save_json(items, date_str):
    os.makedirs(DATA_DIR, exist_ok=True)
    payload = {
        'date'      : date_str,
        'updatedAt' : datetime.now(KST).strftime('%Y-%m-%d %H:%M (KST)'),
        'totalCount': len(items),
        'items'     : items,
    }
    path = os.path.join(DATA_DIR, f'{date_str}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log(f'[완료] 저장: {path} ({len(items)}건)')
    return path


# ── 실행 ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    log('=' * 55)
    log('산지연금 데이터 수집 시작')
    t0       = time.time()
    today_str = datetime.now(KST).strftime('%Y-%m-%d')
    items    = fetch_all()

    if items:
        pnu_lookup = load_pnu_lookup()
        if pnu_lookup:
            log('PNU 코드 및 등급 매칭 중...')
            grade_lookup = load_grade_lookup()
            for item in items:
                pnu = generate_pnu(item['addr'], pnu_lookup)
                item['pnu']   = pnu
                item['grade'] = grade_lookup.get(pnu, 'C')
        save_json(items, today_str)
        log(f'최종: {len(items)}건 저장 ({time.time()-t0:.0f}초)')
    else:
        log('수집 데이터 없음')
    log('=' * 55)
