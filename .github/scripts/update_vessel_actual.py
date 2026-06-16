#!/usr/bin/env python3
"""
VESSEL STATUS - Actual ETD Auto Update v2.0
bookings_for_vss.json에서 부킹 목록을 읽어 VSS/toyoshingo.com에서 출항일 자동 갱신
대응 선사: SINOKOR, HEUNG A, DONG YOUNG, YANGMING, NAMSUNG, KMTC, CNC(CMA CGM)
"""
import json, re, sys, time, urllib.request, os, base64
from datetime import datetime

# ── GitHub 설정 ──
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = 'MHLEE205/VESSEL_STATUS'
API = 'https://api.github.com'

# ── VSS 선사별 URL 매핑 ──
VSS_CONFIG = {
    "SINOKOR":    {"base": "https://www.toyoshingo.com/sinokor/index.php",  "ports": {"TOKYO":13,"OSAKA":11,"NAGOYA":30,"HAKATA":41,"SENDAI":19,"AKITA":17,"KANAZAWA":33,"NIIGATA":24,"YOKOHAMA":13,"ISHIKARI":7}},
    "HEUNG A":    {"base": "https://www.toyoshingo.com/heunga/index.php",   "ports": {"TOKYO":13,"OSAKA":11,"NAGOYA":30,"HAKATA":41,"SENDAI":19,"AKITA":17,"YOKOHAMA":13,"ISHIKARI":7}},
    "HEUNG-A":    {"base": "https://www.toyoshingo.com/heunga/index.php",   "ports": {"TOKYO":13,"OSAKA":11,"NAGOYA":30,"HAKATA":41,"SENDAI":19,"AKITA":17,"YOKOHAMA":13,"ISHIKARI":7}},
    "NAMSUNG":    {"base": "https://www.toyoshingo.com/namsung/index.php",  "ports": {"TOKYO":13,"OSAKA":11,"NAGOYA":30,"SENDAI":19,"YOKOHAMA":13}},
    "KMTC":       {"base": "https://www.toyoshingo.com/kmtc/index.php",     "ports": {"TOKYO":13,"OSAKA":11,"NAGOYA":30,"HAKATA":41,"SENDAI":19,"YOKOHAMA":13}},
    "DONG YOUNG": {"base": "https://www.toyoshingo.com/dongjin/index.php",  "ports": {"TOKYO":13,"OSAKA":11,"NAGOYA":35,"HAKATA":41,"YOKOHAMA":13}},
    "YANGMING":   {"base": "https://www.toyoshingo.com/yangming/index.php", "ports": {"TOKYO":13,"OSAKA":11,"NAGOYA":30,"HAKATA":41,"YOKOHAMA":13,"KOBE":41}},
    "CNC":        {"base": "https://www.toyoshingo.com/cmacgm/index.php",   "ports": {"TOKYO":13,"YOKOHAMA":11,"NAGOYA":35,"KOBE":41}},
}

# INTERASIA는 새 사이트로 이전 - vessel-schedule-service.com (API 방식으로 추후 대응)

def github_get(path):
    req = urllib.request.Request(f"{API}/repos/{REPO}/contents/{path}")
    req.add_header('Authorization', f'token {GITHUB_TOKEN}')
    req.add_header('Accept', 'application/json')
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.load(res)

def github_put(path, content_str, message, sha=None):
    payload = {
        "message": message,
        "content": base64.b64encode(content_str.encode('utf-8')).decode('utf-8')
    }
    if sha:
        payload["sha"] = sha
    req = urllib.request.Request(f"{API}/repos/{REPO}/contents/{path}",
        data=json.dumps(payload).encode('utf-8'), method='PUT')
    req.add_header('Authorization', f'token {GITHUB_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.load(res)

def fetch_vss(url):
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.read().decode('shift-jis', errors='replace')
    except Exception as e:
        print(f"  Fetch error: {e}")
        return None

def parse_vessels(html):
    """VSS 페이지에서 본선명과 Sailing 날짜 파싱"""
    vessels = {}
    if not html:
        return vessels
    pattern = re.compile(
        r'Vessel\s*Name\s*\n\s*:\s*(.+?)\n.*?Voyage\s*\n\s*:\s*(.+?)\n.*?Sailing\s*\n\s*:\s*(.+?)(?:\n|$)',
        re.DOTALL
    )
    for m in pattern.finditer(html):
        vname = re.sub(r'\s*\([^)]+\)\s*$', '', m.group(1).strip()).strip()
        voyage = m.group(2).strip()
        sailing = m.group(3).strip()
        omit = '--OMIT--' in sailing
        date = ''
        if re.match(r'\d{4}/\d{2}/\d{2}', sailing):
            date = sailing[:10].replace('/', '-')
        vessels[vname] = {'voyage': voyage, 'sailing': date, 'omit': omit}
    return vessels

def match_vessel(vessel_name, vessel_map):
    """본선명으로 VSS 데이터 매칭"""
    vn = vessel_name.upper()
    base = re.sub(r'\s+\d{3,4}[EWNS/]+\s*$', '', vn).strip()
    base = re.sub(r'\s+[0-9A-Z]{6,}\s*$', '', base).strip()
    base = re.sub(r'\s+0[A-Z0-9]{4,}\s*$', '', base).strip()
    
    for v, data in vessel_map.items():
        v_up = v.upper()
        if base == v_up or vn == v_up:
            return data
        if len(base) >= 8 and (base[:10] in v_up or v_up[:10] in base):
            return data
    return None

def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"=== Vessel Actual ETD Update v2.0 - {now} ===")

    # 1. bookings_for_vss.json 읽기
    try:
        bkg_data = github_get('bookings_for_vss.json')
        bookings = json.loads(base64.b64decode(bkg_data['content']).decode('utf-8'))
        print(f"부킹 목록: {len(bookings)}건")
    except Exception as e:
        print(f"❌ bookings_for_vss.json 읽기 실패: {e}")
        sys.exit(1)

    # 2. vessel_actual.json 읽기
    try:
        actual_data = github_get('vessel_actual.json')
        actual_map = json.loads(base64.b64decode(actual_data['content']).decode('utf-8'))
        actual_sha = actual_data['sha']
        print(f"기존 actual: {len(actual_map)}건")
    except Exception as e:
        actual_map = {}
        actual_sha = None
        print(f"vessel_actual.json 신규 생성")

    # 3. 선사+POL별로 페이지 그룹핑
    pages = {}
    for b in bookings:
        carrier = b.get('carrier', '').upper()
        pol = b.get('pol', '').upper()
        vessel = b.get('vessel_name', '')
        etd = b.get('etd', '')
        bkg_no = b.get('bkg_no', '')

        # 대응 선사 찾기
        cfg_key = None
        for key in VSS_CONFIG:
            if key.upper() in carrier or carrier in key.upper():
                cfg_key = key
                break
        if not cfg_key:
            continue

        cfg = VSS_CONFIG[cfg_key]
        port_code = cfg['ports'].get(pol)
        if not port_code:
            print(f"  ⚠ 포트 없음: {carrier}/{pol}")
            continue

        page_key = f"{cfg_key}__{pol}"
        if page_key not in pages:
            pages[page_key] = {'base': cfg['base'], 'port': port_code, 'bookings': []}
        pages[page_key]['bookings'].append({'bkg_no': bkg_no, 'vessel': vessel, 'etd': etd, 'carrier': b.get('carrier',''), 'pol': b.get('pol','')})

    print(f"스크래핑 대상: {len(pages)}페이지")

    # 4. 각 페이지 스크래핑
    results = {}
    for page_key, page in pages.items():
        print(f"\n[{page_key}]")
        vessel_map = {}
        for week in [1, 2, 3, 4]:
            url = f"{page['base']}?port={page['port']}&week={week}"
            html = fetch_vss(url)
            if html:
                parsed = parse_vessels(html)
                vessel_map.update(parsed)
            time.sleep(0.5)

        print(f"  수집 본선: {len(vessel_map)}건")

        for bkg in page['bookings']:
            matched = match_vessel(bkg['vessel'], vessel_map)
            bkg_no = bkg['bkg_no']
            if matched and (matched['sailing'] or matched['omit']):
                actual_etd = matched['sailing'] if not matched['omit'] else bkg['etd']
                note = 'OMIT' if matched['omit'] else ''
                changed = actual_etd != bkg['etd']
                status = f"⚠ {bkg['etd']}→{actual_etd}" if changed else f"✅ {actual_etd}"
                print(f"  {bkg_no}: {bkg['vessel'][:25]} {status}")
                results[bkg_no] = {
                    "actual_etd": actual_etd,
                    "vessel_name": bkg['vessel'],
                    "carrier": bkg['carrier'],
                    "pol": bkg['pol'],
                    "scheduled_etd": bkg['etd'],
                    "confirmed": False,
                    "updated_at": now
                }
                if note:
                    results[bkg_no]["note"] = note
            else:
                print(f"  {bkg_no}: {bkg['vessel'][:25]} ❓ 미매칭")

    # 5. 기존 actual_map에 병합 (새로 매칭된 것만 업데이트)
    actual_map.update(results)
    print(f"\n최종: {len(actual_map)}건 ({len(results)}건 업데이트)")

    # 6. vessel_actual.json 저장
    content = json.dumps(actual_map, ensure_ascii=False, indent=2)
    result = github_put(
        'vessel_actual.json', content,
        f"Auto update vessel actual ETD - {now} ({len(results)}건 갱신)",
        actual_sha
    )
    print(f"✅ 저장 완료: {result['commit']['sha']}")

if __name__ == '__main__':
    main()
