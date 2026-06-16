#!/usr/bin/env python3
"""
VESSEL STATUS - Actual ETD Auto Update v3.0
- bookings_for_vss.json에서 부킹 목록 읽기
- VOYAGE 번호 기반 정확 매칭
- 공동운행 대응: 본선명이 같으면 다른 선사 사이트에서도 매칭
- 대응 선사: SINOKOR, HEUNG A, DONG YOUNG, YANGMING, NAMSUNG, KMTC, CNC(CMA CGM)
- 水島(port=50) 포트코드 추가
"""
import json, re, sys, time, urllib.request, os, base64
from datetime import datetime

GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = 'MHLEE205/VESSEL_STATUS'
API  = 'https://api.github.com'

# ── VSS 선사별 URL + 포트 매핑 ──
VSS_CONFIG = {
    "SINOKOR": {
        "base": "https://www.toyoshingo.com/sinokor/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41,
            "SENDAI":19, "AKITA":17, "KANAZAWA":33, "NIIGATA":24,
            "YOKOHAMA":13, "ISHIKARI":7,
            "MIZUSHIMA":50,   # 水島
            "HIROSHIMA":51,
        }
    },
    "HEUNG A": {
        "base": "https://www.toyoshingo.com/heunga/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41,
            "SENDAI":19, "AKITA":17, "YOKOHAMA":13, "ISHIKARI":7,
        }
    },
    "HEUNG-A": {
        "base": "https://www.toyoshingo.com/heunga/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41,
            "SENDAI":19, "AKITA":17, "YOKOHAMA":13, "ISHIKARI":7,
        }
    },
    "NAMSUNG": {
        "base": "https://www.toyoshingo.com/namsung/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":30, "SENDAI":19, "YOKOHAMA":13,
        }
    },
    "KMTC": {
        "base": "https://www.toyoshingo.com/kmtc/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41,
            "SENDAI":19, "YOKOHAMA":13,
        }
    },
    "DONG YOUNG": {
        "base": "https://www.toyoshingo.com/dongjin/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":35, "HAKATA":41, "YOKOHAMA":13,
        }
    },
    "YANGMING": {
        "base": "https://www.toyoshingo.com/yangming/index.php",
        "ports": {
            "TOKYO":13, "OSAKA":11, "NAGOYA":30, "HAKATA":41,
            "YOKOHAMA":11, "KOBE":41,
        }
    },
    "CNC": {
        "base": "https://www.toyoshingo.com/cmacgm/index.php",
        "ports": {
            "TOKYO":13, "YOKOHAMA":11, "NAGOYA":35, "KOBE":41,
        }
    },
}

# ── VOYAGE 번호 추출 ──
def extract_voyage(vessel_name):
    # 숫자 항차 (예: 2623W, 329S, 2621N)
    m = re.search(r'(\d{3,4})[EWNS](?:\s|$)', vessel_name.upper())
    if m:
        return m.group(1)
    # S/N+숫자 (예: S085, S068)
    m = re.search(r'[SN](\d{3})', vessel_name.upper())
    if m:
        return m.group(1).lstrip('0') or '0'
    # 영문 항차코드 (예: 0IZORS, 0CG7HS)
    m = re.search(r'0([A-Z]{4,6})\b', vessel_name.upper())
    if m:
        return m.group(1)
    return None

def voyage_matches(bkg_voyage, vss_voyage):
    if not bkg_voyage or not vss_voyage:
        return False
    return bkg_voyage in vss_voyage

# ── VSS 페이지 파싱 (VOYAGE 포함) ──
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
    if not html:
        return results
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

# ── GitHub API ──
def github_get(path):
    req = urllib.request.Request(f"{API}/repos/{REPO}/contents/{path}")
    req.add_header('Authorization', f'token {GITHUB_TOKEN}')
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.load(res)

def github_put(path, content_str, message, sha=None):
    payload = {
        "message": message,
        "content": base64.b64encode(content_str.encode('utf-8')).decode('utf-8')
    }
    if sha:
        payload["sha"] = sha
    req = urllib.request.Request(
        f"{API}/repos/{REPO}/contents/{path}",
        data=json.dumps(payload).encode('utf-8'), method='PUT'
    )
    req.add_header('Authorization', f'token {GITHUB_TOKEN}')
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=15) as res:
        return json.load(res)

def main():
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    print(f"=== Vessel Actual ETD Update v3.0 - {now} ===")

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
        actual_map  = json.loads(base64.b64decode(actual_data['content']).decode('utf-8'))
        actual_sha  = actual_data['sha']
        print(f"기존 actual: {len(actual_map)}건")
    except Exception:
        actual_map, actual_sha = {}, None

    # 3. 전체 VSS 페이지를 선사+POL별로 스크래핑
    # (공동운행 대응: 全 선사 사이트를 스캔해서 하나의 vessel_map에 합산)
    all_vessel_map = {}  # 본선명__항차 → {sailing, omit}
    scraped_pages  = set()

    for bkg in bookings:
        carrier = bkg.get('carrier', '').upper()
        pol     = bkg.get('pol', '').upper()

        cfg_key = None
        for key in VSS_CONFIG:
            if key.upper() in carrier or carrier in key.upper():
                cfg_key = key
                break
        if not cfg_key:
            continue

        cfg       = VSS_CONFIG[cfg_key]
        port_code = cfg['ports'].get(pol)
        if not port_code:
            continue

        page_key = f"{cfg_key}__{pol}"
        if page_key in scraped_pages:
            continue
        scraped_pages.add(page_key)

        print(f"\n[{page_key}] 스크래핑 중...")
        for week in [1, 2, 3, 4]:
            url  = f"{cfg['base']}?port={port_code}&week={week}"
            html = fetch_vss(url)
            if html:
                parsed = parse_vessels_with_voyage(html)
                all_vessel_map.update(parsed)
            time.sleep(0.4)

    print(f"\n전체 수집 본선: {len(all_vessel_map)}건")

    # 4. VOYAGE 기반 매칭
    results    = {}
    unmatched  = []

    for bkg in bookings:
        bkg_no  = bkg.get('bkg_no', '')
        vessel  = bkg.get('vessel_name', '')
        carrier = bkg.get('carrier', '')
        pol     = bkg.get('pol', '')
        etd     = bkg.get('etd', '')

        # VSS 대응 선사 확인
        cfg_key = None
        for key in VSS_CONFIG:
            if key.upper() in carrier.upper() or carrier.upper() in key.upper():
                cfg_key = key
                break
        if not cfg_key:
            continue

        bkg_voyage  = extract_voyage(vessel)
        vessel_base = re.sub(r'\s+\S+\s*$', '', vessel).strip().upper()

        best = None
        for key, data in all_vessel_map.items():
            v   = data['vessel'].upper()
            voy = data['voyage']
            name_ok = (vessel_base[:10] in v or v[:10] in vessel_base or vessel_base == v)
            if name_ok and bkg_voyage and voyage_matches(bkg_voyage, voy):
                best = data
                break

        if best and (best['sailing'] or best['omit']):
            actual = best['sailing'] if not best['omit'] else etd
            note   = 'OMIT' if best['omit'] else ''
            changed = actual != etd
            status  = f"⚠ {etd}→{actual}" if changed else f"✅ {actual}"
            if best['omit']:
                status = "❌ OMIT"
            print(f"  {bkg_no:<25} VOY:{bkg_voyage:<6} → {best['voyage']:<15} {status}")
            results[bkg_no] = {
                "actual_etd":    actual,
                "vessel_name":   vessel,
                "carrier":       carrier,
                "pol":           pol,
                "scheduled_etd": etd,
                "confirmed":     False,
                "updated_at":    now,
                "voyage":        best['voyage'],
            }
            if note:
                results[bkg_no]["note"] = note
        else:
            unmatched.append(bkg_no)

    print(f"\n✅ 매칭: {len(results)}건 / ❓ 미매칭: {len(unmatched)}건")
    if unmatched:
        print("미매칭:", unmatched)

    # 5. 기존 actual_map에 병합 후 저장
    actual_map.update(results)
    content = json.dumps(actual_map, ensure_ascii=False, indent=2)
    r = github_put(
        'vessel_actual.json', content,
        f"Auto update ETD v3.0 - {now} ({len(results)}건 갱신)",
        actual_sha
    )
    print(f"✅ vessel_actual.json 저장: {r['commit']['sha']}")

    # 6. bookings_for_vss.json은 그대로 유지
    print("완료！")

if __name__ == '__main__':
    main()
