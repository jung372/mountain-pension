"""
산지연금 S/A 등급 변동 알림 (GitHub Actions용)
- 전일 vs 금일 data/YYYY-MM-DD.json 비교
- 텔레그램 Bot API로 알림 전송 (HTML 파싱 모드)
"""

import os, sys, json, requests
from datetime import datetime, timezone, timedelta, date

KST       = timezone(timedelta(hours=9))
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(SCRIPT_DIR, 'data')

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID   = os.environ.get('TELEGRAM_CHAT_ID', '')
SITE_URL  = os.environ.get('SITE_URL', 'https://your-github-username.github.io/mountain-pension/')

TARGET_GRADES   = {'S', 'A'}
BIDDABLE_STATUS = {'입찰중', '공고중'}


# ── 데이터 로드 ───────────────────────────────────────────────────────────────
def load_data(date_str: str) -> dict:
    path = os.path.join(DATA_DIR, f'{date_str}.json')
    if not os.path.exists(path):
        return {}
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def get_sa_items(data: dict) -> dict:
    """cltrNo → item 딕셔너리 (S/A 등급만)"""
    return {
        item['cltrNo']: item
        for item in data.get('items', [])
        if item.get('grade') in TARGET_GRADES and item.get('cltrNo')
    }


# ── 변동 분석 ─────────────────────────────────────────────────────────────────
def analyze(prev_items: dict, curr_items: dict) -> dict:
    new_s, new_a         = [], []
    changed_s, changed_a = [], []

    for cltr_no, curr in curr_items.items():
        grade = curr.get('grade', '')
        if cltr_no not in prev_items:
            (new_s if grade == 'S' else new_a).append(curr)
        else:
            prev_status = prev_items[cltr_no].get('status', '')
            curr_status = curr.get('status', '')
            if prev_status and curr_status and prev_status != curr_status:
                entry = {**curr, 'prevStatus': prev_status}
                (changed_s if grade == 'S' else changed_a).append(entry)

    return {
        'new_s'    : new_s,
        'new_a'    : new_a,
        'changed_s': changed_s,
        'changed_a': changed_a,
    }


# ── 증감 텍스트 ───────────────────────────────────────────────────────────────
def delta_text(curr: int, prev: int) -> str:
    if prev == 0:
        return f'+{curr}건' if curr > 0 else '전일과 동일'
    diff = curr - prev
    if diff > 0:
        return f'+{diff}건 증가'
    if diff < 0:
        return f'{diff}건 감소'
    return '전일과 동일'


# ── 메시지 구성 ───────────────────────────────────────────────────────────────
def build_message(prev_data: dict, curr_data: dict, changes: dict, today_str: str) -> str:
    prev_items = get_sa_items(prev_data)
    curr_items = get_sa_items(curr_data)

    # ── 현황 집계 ──
    def count_biddable(items_dict):
        return sum(1 for i in items_dict.values() if i.get('status') in BIDDABLE_STATUS)

    def count_grade(items_dict, grade):
        return sum(1 for i in items_dict.values() if i.get('grade') == grade)

    curr_bid   = count_biddable(curr_items)
    prev_bid   = count_biddable(prev_items)
    curr_s     = count_grade(curr_items, 'S')
    prev_s     = count_grade(prev_items, 'S')
    curr_a     = count_grade(curr_items, 'A')
    prev_a     = count_grade(prev_items, 'A')

    total_changes = (
        len(changes['new_s']) + len(changes['new_a']) +
        len(changes['changed_s']) + len(changes['changed_a'])
    )

    lines = [
        f'[📅 산지연금 일일 변동 보고] {today_str}',
        '',
        '📊 <b>등급별 현황 요약</b>',
        f'• 입찰가능 물건 (S/A등급만): {curr_bid}건 ({delta_text(curr_bid, prev_bid)})',
        f'• S등급 물건: {curr_s}건 ({delta_text(curr_s, prev_s)})',
        f'• A등급 물건: {curr_a}건 ({delta_text(curr_a, prev_a)})',
    ]

    # ── 변동 상세 ──
    lines += ['', '🔔 <b>주요 변동 상세 (S/A)</b>']

    if total_changes == 0:
        lines.append('  변동 사항 없음')
    else:
        # S등급
        s_total = len(changes['new_s']) + len(changes['changed_s'])
        if s_total > 0:
            lines.append(f'⭐ <b>S등급 변동: {s_total}건</b>')
            for item in changes['new_s']:
                lines.append(f'  🆕 신규: {item.get("addr","")} ({item.get("cltrNo","")})')
            for item in changes['changed_s']:
                lines.append(
                    f'  🔄 상태변경: {item.get("cltrNm","")} '
                    f'({item.get("prevStatus","")} → <b>{item.get("status","")}</b>)'
                )

        # A등급
        a_total = len(changes['new_a']) + len(changes['changed_a'])
        if a_total > 0:
            lines.append(f'✨ <b>A등급 변동: {a_total}건</b>')
            for item in changes['new_a']:
                lines.append(f'  🆕 신규: {item.get("addr","")} ({item.get("cltrNo","")})')
            for item in changes['changed_a']:
                lines.append(
                    f'  🔄 상태변경: {item.get("cltrNm","")} '
                    f'({item.get("prevStatus","")} → <b>{item.get("status","")}</b>)'
                )

    lines += [
        '',
        f'📍 <a href="{SITE_URL}">산지연금 모니터링 사이트 바로가기</a>',
    ]

    return '\n'.join(lines)


# ── 텔레그램 전송 ─────────────────────────────────────────────────────────────
def send_telegram(text: str):
    url  = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    data = {
        'chat_id'   : CHAT_ID,
        'text'      : text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
    }
    resp = requests.post(url, data=data, timeout=30)
    if resp.status_code == 200:
        print('[완료] 텔레그램 메시지 전송 성공')
    else:
        print(f'[오류] 텔레그램 전송 실패: {resp.status_code} {resp.text}')
        sys.exit(1)


# ── 실행 ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    now       = datetime.now(KST)
    today_str = now.strftime('%Y-%m-%d')
    prev_str  = (now - timedelta(days=1)).strftime('%Y-%m-%d')

    print(f'[비교] {prev_str} → {today_str}')

    curr_data = load_data(today_str)
    prev_data = load_data(prev_str)

    if not curr_data:
        print(f'[오류] 금일 데이터 없음: data/{today_str}.json')
        sys.exit(1)

    if not prev_data:
        print(f'[경고] 전일 데이터 없음: data/{prev_str}.json — 신규 기준으로만 비교')

    curr_items = get_sa_items(curr_data)
    prev_items = get_sa_items(prev_data)
    changes    = analyze(prev_items, curr_items)

    if not BOT_TOKEN or not CHAT_ID:
        print('[오류] TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 환경변수 미설정')
        sys.exit(1)

    message = build_message(prev_data, curr_data, changes, today_str)
    print('─' * 50)
    print(message)
    print('─' * 50)
    send_telegram(message)
