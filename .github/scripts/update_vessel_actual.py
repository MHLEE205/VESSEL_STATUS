#!/usr/bin/env python3
"""
VESSEL STATUS - Actual ETD Auto Update v4.1
- toyoshingo.com: urllib 직접 스크래핑 (기존 방식)
- jinjiangshipping.jp: Playwright 브라우저로 스크래핑 (신규)
- VOYAGE 번호 기반 정확 매칭
"""
import json, re, sys, time, urllib.request, os, base64
from datetime import datetime

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = 'MHLEE205/VESSEL_STATUS'
API  = 'https://api.github.com'

# ── VSS 선사별 URL + 포트 매핑 (toyoshingo.com) ──
VSS_CONFIG = {
    "SINOKOR": {
        "base": "https://www.toyoshingo.com/sinokor/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41,
            "SENDAI":19, "AKITA":17, "KANAZAWA":33, "NIIGATA":24,
            "YOKOHAMA":13, "ISHIKARI":7, "MIZUSHIMA":50, "HIROSHIMA":51,
        }
    },
    "HEUNG A": {
        "base": "https://www.toyoshingo.com/heunga/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41, "SENDAI":19, "AKITA":17, "YOKOHAMA":13, "ISHIKARI":7}
    },
    "HEUNG-A": {
        "base": "https://www.toyoshingo.com/heunga/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41, "SENDAI":19, "AKITA":17, "YOKOHAMA":13, "ISHIKARI":7}
    },
    "NAMSUNG": {
        "base": "https://www.toyoshingo.com/namsung/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":30, "SENDAI":19, "YOKOHAMA":13}
    },
    "KMTC": {
        "base": "https://www.toyoshingo.com/kmtc/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41, "SENDAI":19, "YOKOHAMA":13}
    },
    "DONG YOUNG": {
        "base": "https://www.toyoshingo.com/dongjin/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":35, "HAKATA":41, "YOKOHAMA":13}
    },
    "YANGMING": {
        "base": "https://www.toyoshingo.com/yangming/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41, "YOKOHAMA":11, "KOBE":41}
    },
    "PAN OCEAN": {
        "base": "https://www.toyoshingo.com/sinokor/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41, "SENDAI":19, "AKITA":17, "YOKOHAMA":13, "ISHIKARI":7, "KOBE":41, "MIZUSHIMA":50}
    },
    "PAN OCEAN_NAMSUNG": {
        "base": "https://www.toyoshingo.com/namsung/index.php",
        "ports": {"TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41, "SENDAI":19, "YOKOHAMA":13, "KOBE":11}
    },
    "CNC": {
        "base": "https://www.toyoshingo.com/cmacgm/index.php",
        "ports": {"TOKYO":13, "YOKOHAMA":11, "NAGOYA":35, "KOBE":41}
    },
}

# ── JIN JIANG 컬럼 매핑 ──
JJ_COL_SHANGHAI = {'TOKYO':3,'YOKOHAMA':4,'NAGOYA':5,'SHIMIZU':6,'OSAKA':7,'KOBE':8,'HAKATA':9,'MOJI':10,'NAHA':11}
JJ_COL_QINGDAO  = {'MOJI':3,'HAKATA':4,'OSAKA':5,'KOBE':6,'NAGOYA':7,'TOKYO':8,'YOKOHAMA':9}

# ── VOYAGE 번호 추출 ──
def extract_voyage(vessel_name):
    m = re.search(r'(\d{3,4})[EWNS](?:\s|$)', vessel_name.upper())
    if m: return m.group(1)
    m = re.search(r'[SN](\d{3})', vessel_name.upper())
    if m: return m.group(1).lstrip('0') or '0'
    m = re.search(r'0([A-Z]{4,6})\b', vessel_name.upper())
    if m: return m.group(1)
    return None

def voyage_matches(bkg_voyage, vss_voyage):
    if not bkg_voyage or not vss_voyage: return False
    return bkg_voyage in vss_voyage

# ── toyoshingo.com 스크래핑 ──
def fetch_vss(url):
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.read().decode('shift-jis', errors='replace')
    except Exception as e:
        print(f"  Fetch error {url}: {e}")
        return None

def parse_vessels_with_voyage(html):
    results = {}
    if not html: return results
    pattern = re.compile(
        r'Vessel\s*Name\s*\n\s*:\s*(.+?)\n.*?'
        r'Voyage\s*\n\s*:\s*(.+?)\n.*?'
        r'Sailing\s*\n\s*:\s*(.+?)(?:\n|$)',
        re.DOTALL
    )
    for m in pattern.finditer(html):
        vname   = re.sub(r'\s*\([^)]+\)\s*$', '', m.group(1).strip()).strip()
        voyage  = m.group(2).strip()
        sailing = m.group(3).strip()
        omit    = '--OMIT--' in sailing
        date    = sailing[:10].replace('/', '-') if re.match(r'\d{4}/\d{2}/\d{2}', sailing) else ''
        key     = f"{vname.upper()}__{voyage}"
        results[key] = {'vessel': vname, 'voyage': voyage, 'sailing': date, 'omit': omit}
    return results

# ── JIN JIANG Playwright 스크래핑 ──
def fetch_jinjiang_playwright():
    """Playwright로 jinjiangshipping.jp 3페이지 스크래핑"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ⚠ Playwright 미설치 → JIN JIANG 스킵")
        return {}

    def parse_dep(cell_text):
        lines = [l.strip() for l in cell_text.split('\n') if l.strip() and l.strip() != '-']
        dates = [l for l in lines if re.match(r'^\*?\d{1,2}/\d{1,2}', l)]
        if not dates: return None
        dep = dates[1] if len(dates) >= 2 else dates[0]
        m = re.match(r'\*?(\d{1,2})/(\d{1,2})', dep)
        return f"2026-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}" if m else None

    def parse_table(page, col_map):
        vessels = []
        rows = page.query_selector_all('tr')
        for row in rows:
            cells = row.query_selector_all('td, th')
            if len(cells) < 6: continue
            c0 = cells[0].inner_text().strip()
            if not re.search(r'\d{4}[EWNS]', c0): continue
            lines = [l.strip() for l in c0.split('\n') if l.strip()]
            vessel_name, voyage = '', ''
            for j, line in enumerate(lines):
                if re.search(r'\d{4}[EWNS]', line):
                    voyage = line
                    vessel_name = ' '.join(lines[:j])
                    break
            if not vessel_name: continue
            port_dates = {}
            for port, idx in col_map.items():
                if idx < len(cells):
                    d = parse_dep(cells[idx].inner_text())
                    if d: port_dates[port] = d
            vessels.append({'vesselName': vessel_name.strip(), 'voyage': voyage, 'portDates': port_dates})
        return vessels

    def parse_sea(page):
        vessels, current = [], None
        for row in page.query_selector_all('tr'):
            cells = row.query_selector_all('td, th')
            if not cells: continue
            c0 = cells[0].inner_text().strip()
            if len(cells) >= 5 and re.search(r'\d{4}[EWNS]', c0):
                lines = [l.strip() for l in c0.split('\n') if l.strip()]
                vn, voy = '', ''
                for j, line in enumerate(lines):
                    if re.search(r'\d{4}[EWNS]', line):
                        voy = line; vn = ' '.join(lines[:j]); break
                current = {'vesselName': vn.strip(), 'voyage': voy, 'portDates': {}}
                vessels.append(current)
            elif current and len(cells) >= 4:
                port_txt = cells[0].inner_text().strip().upper()
                dep_txt  = cells[3].inner_text().strip() if len(cells) > 3 else ''
                for p in ['TOKYO','YOKOHAMA','NAGOYA','OSAKA','KOBE','HAKATA','NAHA','SHIMIZU']:
                    if p in port_txt and re.search(r'\d{1,2}/\d{1,2}', dep_txt):
                        m = re.search(r'(\d{1,2})/(\d{1,2})', dep_txt)
                        if m: current['portDates'][p] = f"2026-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
        return vessels

    all_vessels = []
    print("  Playwright 기동 중...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({'Accept-Language': 'ja-JP,ja;q=0.9'})

        # 上海航路
        try:
            page.goto('https://www.jinjiangshipping.jp/vmi/daily2.php', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            all_vessels += parse_table(page, JJ_COL_SHANGHAI)
            print(f"  上海航路: {len(all_vessels)}件")
        except Exception as e:
            print(f"  上海航路 error: {e}")

        # 青島大連航路
        try:
            page.goto('https://www.jinjiangshipping.jp/vmi/daily_q2.php', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            q_vessels = parse_table(page, JJ_COL_QINGDAO)
            all_vessels += q_vessels
            print(f"  青島大連航路: {len(q_vessels)}件")
        except Exception as e:
            print(f"  青島大連航路 error: {e}")

        # 東南アジア航路
        try:
            page.goto('https://www.jinjiangshipping.jp/vmi/dailysea2.php', timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            s_vessels = parse_sea(page)
            all_vessels += s_vessels
            print(f"  東南アジア航路: {len(s_vessels)}件")
        except Exception as e:
            print(f"  東南アジア航路 error: {e}")

        browser.close()

    print(f"  JIN JIANG 전체 수집: {len(all_vessels)}件")
    return all_vessels

def match_jinjiang(bookings, all_vessels, actual_map, now):
    """JIN JIANG 부킹 매칭 및 업데이트"""
    results = {}
    jj_bookings = [b for b in bookings if b.get('carrier', '') == 'JIN JIANG']

    for bkg in jj_bookings:
        vname = bkg.get('vessel_name', '').upper().strip()
        # 인코딩 깨진 문자 정규화
        vname = re.sub(r'[^\x20-\x7E]', ' ', vname)
        vname = re.sub(r'\s+', ' ', vname).strip()
        bkg_voyage = extract_voyage(vname)
        if not bkg_voyage: continue
        pol = bkg.get('pol', '').upper()
        # 본선명 핵심단어 (숫자+방향 제거)
        base_name = re.sub(r'\s*\d{4}[EWNS]\s*$', '', vname).strip()
        base_words = [w for w in base_name.split() if len(w) > 1]

        matched = None
        for v in all_vessels:
            if bkg_voyage not in v['voyage']: continue
            vn = v['vesselName'].upper()
            if all(w in vn for w in base_words):
                matched = v
                break

        if not matched: continue
        etd = matched['portDates'].get(pol)
        if not etd: continue

        existing = actual_map.get(bkg['bkg_no'], {})
        changed = existing.get('actual_etd') != etd
        results[bkg['bkg_no']] = {
            **existing,
            'actual_etd': etd,
            'vessel_name': bkg.get('vessel_name', ''),
            'carrier': 'JIN JIANG',
            'pol': bkg.get('pol', ''),
            'scheduled_etd': existing.get('scheduled_etd') or bkg.get('etd', etd),
            'confirmed': True,
            'voyage': matched['voyage'],
            'note': f"jinjiangshipping.jp auto-confirmed{' (ETD changed)' if changed else ''}",
            'updated_at': now,
        }
        status = f"⚠ ETD変更 {existing.get('actual_etd')}→{etd}" if changed else f"✅ {etd}"
        print(f"  {bkg['bkg_no']:<25} {matched['vesselName']:<20} {pol}:{etd} {status}")

    return results

# ── EHIME OCEAN Playwright 스크래핑 ──
# 항로구조: Naha① → PUSAN/LAT KRABANG행 / Naha② → TAICHUNG행 (귀항)
EHIME_VESSELS = {
    '512': 'ITX EHIME',
    '519': 'ITX HIGO',
}

def fetch_ehime_playwright():
    """Playwright로 ehime-ocean.co.jp 스케줄 스크래핑"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ⚠ Playwright 미설치 → EHIME OCEAN 스킵")
        return {}

    def parse_schedule(page, vessel_name):
        """페이지에서 Voyage + Naha ETD 파싱"""
        results = []
        # Current Voyage 번호 추출
        voyage_text = ''
        for el in page.query_selector_all('p, h2, h3, span, div'):
            t = el.inner_text().strip()
            m = re.search(r'(\d{3}N\s*/\s*\d{3}S)', t)
            if m:
                voyage_text = m.group(1).replace(' ', '')
                break

        # 테이블 행 파싱
        naha_idx = 0
        rows = page.query_selector_all('tr')
        for row in rows:
            cells = row.query_selector_all('td')
            if not cells: continue
            port = cells[0].inner_text().strip()
            if port != 'Naha': continue
            naha_idx += 1

            # Departure Date 셀(index 3) - OMIT 또는 날짜
            if len(cells) < 4: continue
            dep_cell = cells[3].inner_text().strip()
            is_omit = 'OMIT' in dep_cell

            if is_omit:
                results.append({
                    'vessel': vessel_name, 'voyage': voyage_text,
                    'naha_idx': naha_idx, 'omit': True, 'etd': None
                })
            else:
                # 날짜 추출: Estimated(2번째) 우선, 없으면 Original(1번째)
                dates = re.findall(r'(\d{4}-\d{2}-\d{2})', dep_cell)
                etd = dates[1] if len(dates) >= 2 else (dates[0] if dates else None)
                results.append({
                    'vessel': vessel_name, 'voyage': voyage_text,
                    'naha_idx': naha_idx, 'omit': False, 'etd': etd
                })
        return results

    all_results = {}  # vessel_value → [naha_schedule]
    print("  Playwright 기동 (EHIME OCEAN)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for vessel_value, vessel_name in EHIME_VESSELS.items():
            try:
                page.goto('https://ehime-ocean.co.jp/service/schedule/', timeout=30000)
                page.wait_for_load_state('networkidle', timeout=15000)
                # 드롭다운 선택
                page.select_option('select', vessel_value)
                page.wait_for_timeout(2000)
                schedules = parse_schedule(page, vessel_name)
                all_results[vessel_name] = schedules
                print(f"  {vessel_name}: Naha {len(schedules)}행 확인")
            except Exception as e:
                print(f"  {vessel_name} error: {e}")

        browser.close()

    return all_results


def match_ehime(bookings, ehime_data, actual_map, now):
    """EHIME OCEAN 부킹 매칭 - POD로 Naha① or ② 판정"""
    results = {}
    # POD → Naha 인덱스 매핑
    # Naha①: PUSAN, LAT KRABANG, BUSAN 등 북행 POD
    # Naha②: TAICHUNG, KEELUNG, KAOHSIUNG 등 남행 POD
    NAHA1_PODS = {'PUSAN', 'BUSAN', 'LAT KRABANG', 'BANGKOK', 'LAEM CHABANG'}
    NAHA2_PODS = {'TAICHUNG', 'KEELUNG', 'KAOHSIUNG', 'TAOYUAN'}

    ehime_bookings = [b for b in bookings if b.get('carrier') in ('EHIME OCEAN', 'ONE')
                      and b.get('pol', '').upper() == 'NAHA'
                      and 'ITX' in b.get('vessel_name', '').upper()]

    for bkg in ehime_bookings:
        vessel_name = bkg.get('vessel_name', '')
        # ITX EHIME / ITX HIGO 판별
        vessel_key = None
        if 'EHIME' in vessel_name.upper():
            vessel_key = 'ITX EHIME'
        elif 'HIGO' in vessel_name.upper():
            vessel_key = 'ITX HIGO'
        if not vessel_key: continue

        # VOYAGE 번호 추출 (예: ITX HIGO 265S → 265)
        vm = re.search(r'(\d{3})[NS]', vessel_name.upper())
        if not vm: continue
        voy_num = vm.group(1)

        # POD 확인 (vessel_actual.json의 기존 데이터 또는 bookings에서)
        existing = actual_map.get(bkg['bkg_no'], {})
        pod = existing.get('pod', '').upper()
        # bookings_for_vss에 pod가 없으므로 기존 note나 vessel_actual에서 추론
        # 일단 naha_idx로 판별: Naha① = PUSAN계, Naha② = TAICHUNG계
        # POD 정보가 없으면 기존 confirmed 데이터 유지
        if not pod:
            # vessel_name의 S/N 방향으로 추정: S=남행(TAICHUNG), N=북행(PUSAN)
            direction = 'S' if re.search(r'\d{3}S', vessel_name.upper()) else 'N'
            # S항차 = TAICHUNG행 = Naha②, N항차는 스킵(출항전)
            if direction == 'S':
                pod = 'TAICHUNG'  # 기본값
            else:
                continue

        # Naha 인덱스 결정
        if any(p in pod for p in NAHA1_PODS):
            target_naha_idx = 1
        elif any(p in pod for p in NAHA2_PODS):
            target_naha_idx = 2
        else:
            continue

        # ehime_data에서 해당 vessel + voyage + naha_idx 찾기
        vessel_schedules = ehime_data.get(vessel_key, [])
        matched = None
        for s in vessel_schedules:
            if voy_num in s.get('voyage', '').replace(' ', '') and s.get('naha_idx') == target_naha_idx:
                matched = s
                break

        if not matched: continue

        if matched['omit']:
            etd = existing.get('scheduled_etd') or bkg.get('etd', '')
            note = 'EHIME OCEAN NAHA OMIT'
        else:
            etd = matched['etd']
            note = f"ehime-ocean.co.jp {vessel_key} {matched['voyage']} NAHA{target_naha_idx} auto-confirmed"

        if not etd: continue

        changed = existing.get('actual_etd') != etd
        results[bkg['bkg_no']] = {
            **existing,
            'actual_etd': etd,
            'vessel_name': vessel_name,
            'carrier': bkg.get('carrier'),
            'pol': 'NAHA',
            'scheduled_etd': existing.get('scheduled_etd') or bkg.get('etd', etd),
            'confirmed': not matched['omit'],
            'voyage': matched['voyage'],
            'note': note + (' (ETD changed)' if changed else ''),
            'updated_at': now,
        }
        status = f"OMIT" if matched['omit'] else f"ETD:{etd}{' changed' if changed else ''}"
        print(f"  {bkg['bkg_no']:<25} {vessel_key} {matched['voyage']} NAHA{target_naha_idx} POD:{pod} → {status}")

    return results


# ── GitHub API ──
def github_get(path):
    req = urllib.request.Request(f"{API}/repos/{REPO}/contents/{path}")
    req.add_header('Authorization', f'token {GITHUB_TOKEN}')
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.load(res)

def github_put(path, content_str, message, sha=None):
    payload = {"message": message, "content": base64.b64encode(content_str.encode('utf-8')).decode('utf-8')}
    if sha: payload["sha"] = sha
    req = urllib.request.Request(f"{API}/repos/{REPO}/contents/{path}", data=json.dumps(payload).encode('utf-8'), method='PUT')
    req.add_header('Authorization', f'token {GITHUB_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.load(res)

def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"=== Vessel Actual ETD Update v4.0 - {now} ===")

    bkg_data = github_get('bookings_for_vss.json')
    bookings = json.loads(base64.b64decode(bkg_data['content']).decode('utf-8'))
    print(f"부킹 목록: {len(bookings)}건")

    actual_data = github_get('vessel_actual.json')
    actual_map  = json.loads(base64.b64decode(actual_data['content']).decode('utf-8'))
    actual_sha  = actual_data['sha']
    print(f"기존 actual: {len(actual_map)}건")

    # ── toyoshingo.com 스크래핑 (기존) ──
    print("\n[1/2] toyoshingo.com 스크래핑...")
    all_vessel_map = {}
    scraped_pages  = set()
    for bkg in bookings:
        carrier = bkg.get('carrier', '').upper()
        pol     = bkg.get('pol', '').upper()
        cfg_key = None
        for key in VSS_CONFIG:
            if key.upper() in carrier or carrier in key.upper():
                cfg_key = key; break
        if not cfg_key: continue
        cfg       = VSS_CONFIG[cfg_key]
        port_code = cfg['ports'].get(pol)
        if not port_code: continue
        page_key = f"{cfg_key}__{pol}"
        if page_key in scraped_pages: continue
        scraped_pages.add(page_key)
        for week in [1, 2, 3, 4]:
            url  = f"{cfg['base']}?port={port_code}&week={week}"
            html = fetch_vss(url)
            if html:
                all_vessel_map.update(parse_vessels_with_voyage(html))
            time.sleep(0.4)

    print(f"toyoshingo 수집: {len(all_vessel_map)}건")

    # toyoshingo 매칭
    tyo_results = {}
    for bkg in bookings:
        bkg_no  = bkg.get('bkg_no', '')
        vessel  = bkg.get('vessel_name', '')
        carrier = bkg.get('carrier', '')
        pol     = bkg.get('pol', '')
        etd     = bkg.get('etd', '')
        if carrier == 'JIN JIANG': continue  # JIN JIANG은 별도 처리
        cfg_key = None
        for key in VSS_CONFIG:
            if key.upper() in carrier.upper() or carrier.upper() in key.upper():
                cfg_key = key; break
        if not cfg_key: continue
        bkg_voyage  = extract_voyage(vessel)
        vessel_base = re.sub(r'\s+\S+\s*$', '', vessel).strip().upper()
        best = None
        for key, data in all_vessel_map.items():
            v   = data['vessel'].upper()
            voy = data['voyage']
            name_ok = (vessel_base[:10] in v or v[:10] in vessel_base or vessel_base == v)
            if name_ok and bkg_voyage and voyage_matches(bkg_voyage, voy):
                best = data; break
        if best and (best['sailing'] or best['omit']):
            actual = best['sailing'] if not best['omit'] else etd
            changed = actual != etd
            status  = f"⚠ {etd}→{actual}" if changed else f"✅ {actual}"
            if best['omit']: status = "❌ OMIT"
            print(f"  {bkg_no:<25} VOY:{bkg_voyage:<6} → {best['voyage']:<15} {status}")
            tyo_results[bkg_no] = {
                "actual_etd": actual, "vessel_name": vessel,
                "carrier": carrier, "pol": pol,
                "scheduled_etd": etd, "confirmed": False,
                "updated_at": now, "voyage": best['voyage'],
            }
            if best['omit']: tyo_results[bkg_no]["note"] = "OMIT"

    # ── JIN JIANG Playwright 스크래핑 ──
    print("\n[2/3] JIN JIANG jinjiangshipping.jp 스크래핑...")
    jj_vessels = fetch_jinjiang_playwright()
    jj_results = match_jinjiang(bookings, jj_vessels, actual_map, now) if jj_vessels else {}
    print(f"JIN JIANG 매칭: {len(jj_results)}건")

    # ── EHIME OCEAN Playwright 스크래핑 ──
    print("\n[3/3] EHIME OCEAN ehime-ocean.co.jp 스크래핑...")
    ehime_data = fetch_ehime_playwright()
    ehime_results = match_ehime(bookings, ehime_data, actual_map, now) if ehime_data else {}
    print(f"EHIME OCEAN 매칭: {len(ehime_results)}건")

    # 병합 후 저장
    actual_map.update(tyo_results)
    actual_map.update(jj_results)
    actual_map.update(ehime_results)
    total = len(tyo_results) + len(jj_results) + len(ehime_results)
    print(f"\n✅ 전체 갱신: {total}건 (toyoshingo:{len(tyo_results)}, JIN JIANG:{len(jj_results)}, EHIME:{len(ehime_results)})")

    content = json.dumps(actual_map, ensure_ascii=False, indent=2)
    r = github_put('vessel_actual.json', content,
        f"Auto update v4.1 - {now} (tyo:{len(tyo_results)}, jj:{len(jj_results)}, ehime:{len(ehime_results)})", actual_sha)
    print(f"✅ 저장 완료: {r['commit']['sha'][:7]}")

if __name__ == '__main__':
    main()
