#!/usr/bin/env python3
"""
VESSEL STATUS - Actual ETD Auto Update
VSS (toyoshingo.com) から実際の出港日を取得して vessel_actual.json を更新
"""
import json
import re
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
import os

# ── VSS 선사별 URL 매핑 ──
VSS_CONFIG = {
    "SINOKOR": {
        "base": "https://www.toyoshingo.com/sinokor/index.php",
        "area": "A",
        "ports": {
            "TOKYO": 13, "OSAKA": 11, "NAGOYA": 30, "HAKATA": 41,
            "SENDAI": 19, "AKITA": 17, "KANAZAWA": 33, "NIIGATA": 24,
            "YOKOHAMA": 13
        }
    },
    "HEUNG A": {
        "base": "https://www.toyoshingo.com/heunga/index.php",
        "area": "A",
        "ports": {
            "TOKYO": 13, "OSAKA": 11, "NAGOYA": 30, "HAKATA": 41,
            "SENDAI": 19, "AKITA": 17, "YOKOHAMA": 13
        }
    },
    "HEUNG-A": {
        "base": "https://www.toyoshingo.com/heunga/index.php", 
        "area": "A",
        "ports": {
            "TOKYO": 13, "OSAKA": 11, "NAGOYA": 30, "HAKATA": 41,
            "SENDAI": 19, "AKITA": 17, "YOKOHAMA": 13
        }
    },
    "NAMSUNG": {
        "base": "https://www.toyoshingo.com/namsung/index.php",
        "area": "A",
        "ports": {
            "TOKYO": 13, "OSAKA": 11, "NAGOYA": 30,
            "SENDAI": 19, "YOKOHAMA": 13
        }
    },
    "KMTC": {
        "base": "https://www.toyoshingo.com/kmtc/index.php",
        "area": "A", 
        "ports": {
            "TOKYO": 13, "OSAKA": 11, "NAGOYA": 30, "HAKATA": 41,
            "SENDAI": 19, "YOKOHAMA": 13
        }
    },
    "DONG YOUNG": {
        "base": "https://www.toyoshingo.com/dongjin/index.php",
        "area": "A",
        "ports": {
            "TOKYO": 13, "OSAKA": 11, "NAGOYA": 30,
            "YOKOHAMA": 13
        }
    },
    "INTERASIA": {
        "base": "https://www.toyoshingo.com/interasia/index.php",
        "area": "A",
        "ports": {
            "TOKYO": 13, "OSAKA": 11, "NAGOYA": 30, "HAKATA": 41,
            "YOKOHAMA": 13
        }
    }
}

def fetch_vss(url):
    """VSS 페이지 가져오기"""
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')
        req.add_header('Accept', 'text/html,application/xhtml+xml')
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.read().decode('shift-jis', errors='replace')
    except Exception as e:
        print(f"  Fetch error: {e}")
        return None

def parse_vessels(html):
    """HTML에서 본선명과 실제 Sailing 날짜 파싱"""
    vessels = {}
    if not html:
        return vessels
    
    # title 속성에서 vessel 데이터 추출
    # 형식: <dt>Vessel Name</dt><dd>: HEUNG-A XIAMEN</dd>...<dt>Sailing</dt><dd>: <span class='actual'>2026/06/05 16:56</span>
    entries = re.findall(
        r'Vessel Name.*?&lt;/dd&gt;(.*?)(?=Vessel Name|$)',
        html.replace('\n','').replace('\r',''),
        re.DOTALL
    )
    
    for entry in entries:
        # 본선명 추출
        vname_match = re.search(r'&lt;dd&gt;: (.*?)&lt;/dd&gt;', entry)
        if not vname_match:
            continue
        vname = vname_match.group(1).strip()
        
        # 실제 Sailing 날짜 추출 (actual class)
        sailing_match = re.search(
            r'Sailing.*?class=.actual.&gt;([\d/]+)',
            entry
        )
        if sailing_match:
            date_str = sailing_match.group(1).strip()
            # 2026/06/05 → 2026-06-05
            date_fmt = date_str.replace('/', '-').split(' ')[0]
            vessels[vname] = date_fmt
            
    return vessels

def get_actual_etd(carrier, pol, vessel_name):
    """특정 선사/항구/본선의 실제 ETD 조회"""
    carrier_upper = carrier.upper().strip()
    pol_upper = pol.upper().strip()
    
    config = None
    for key in VSS_CONFIG:
        if key in carrier_upper or carrier_upper in key:
            config = VSS_CONFIG[key]
            break
    
    if not config:
        return None
    
    port_code = config['ports'].get(pol_upper)
    if not port_code:
        return None
    
    # 현재 주 + 전후 2주 범위 확인
    for week in [1, 2, 3, 4]:
        url = f"{config['base']}?port={port_code}&week={week}&area={config['area']}"
        print(f"  Checking: {url}")
        html = fetch_vss(url)
        if not html:
            continue
            
        vessels = parse_vessels(html)
        
        # 본선명으로 매칭 (부분 매칭)
        vessel_upper = vessel_name.upper()
        for v, date in vessels.items():
            if vessel_upper in v.upper() or v.upper() in vessel_upper:
                print(f"  ✅ Found: {v} → {date}")
                return date
                
        time.sleep(0.5)
    
    return None

def main():
    print("=" * 50)
    print("VESSEL STATUS - Actual ETD Update")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 기존 vessel_actual.json 읽기
    try:
        with open('vessel_actual.json', 'r', encoding='utf-8') as f:
            actual_data = json.load(f)
    except:
        actual_data = {}
    
    # bookings.json 읽기 (GitHub Actions에서 생성)
    try:
        with open('bookings_for_vss.json', 'r', encoding='utf-8') as f:
            bookings = json.load(f)
    except Exception as e:
        print(f"bookings_for_vss.json not found: {e}")
        bookings = []
    
    updated = 0
    for booking in bookings:
        bkg_no      = booking.get('bkg_no', '')
        vessel_name = booking.get('vessel_name', '')
        carrier     = booking.get('carrier', '')
        pol         = booking.get('pol', '')
        etd         = booking.get('etd', '')
        
        if not all([bkg_no, vessel_name, carrier, pol]):
            continue
        
        # 이미 출항한 부킹은 스킵 (ETD가 오늘보다 7일 이상 과거)
        if etd:
            try:
                etd_date = datetime.strptime(etd[:10], '%Y-%m-%d')
                if etd_date < datetime.now() - timedelta(days=7):
                    continue
            except:
                pass
        
        print(f"\nChecking: {bkg_no} | {vessel_name} | {carrier} | {pol}")
        
        actual_etd = get_actual_etd(carrier, pol, vessel_name)
        
        if actual_etd:
            if bkg_no not in actual_data:
                actual_data[bkg_no] = {}
            actual_data[bkg_no]['actual_etd']    = actual_etd
            actual_data[bkg_no]['vessel_name']   = vessel_name
            actual_data[bkg_no]['carrier']       = carrier
            actual_data[bkg_no]['pol']           = pol
            actual_data[bkg_no]['scheduled_etd'] = etd
            actual_data[bkg_no]['updated_at']    = datetime.now().strftime('%Y-%m-%d %H:%M')
            updated += 1
        
        time.sleep(1)  # VSS 서버 부하 방지
    
    # vessel_actual.json 저장
    with open('vessel_actual.json', 'w', encoding='utf-8') as f:
        json.dump(actual_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 50}")
    print(f"✅ Updated: {updated} bookings")
    print(f"Total records: {len(actual_data)}")
    print("=" * 50)

if __name__ == '__main__':
    main()
