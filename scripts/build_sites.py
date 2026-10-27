"""Build an offline-capable Sites snapshot from the unmodified source databases.

No remote writes or deployment. APPLYHOME_SERVICE_KEY is optional, server-side only.
Run: python scripts/build_sites.py --output /workspace/sites/jeonguk-ipju-db/dist --refresh
"""
import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from db_common import KIC_COLUMNS, normalize_sido
from streamlit_app import (fetch_lh, fetch_applyhome, get_api_key, load_supplement,
                           normalize_broker_df, dedup, clean_apt_name, naver_apt_url)


def records(frame):
    return json.loads(frame.to_json(orient='records', force_ascii=False))


def build(output, refresh=False):
    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / 'sites_app', output, dirs_exist_ok=True)
    data_dir = output / 'data'
    data_dir.mkdir(exist_ok=True)
    now = datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds')
    warnings, frames = [], []
    if not get_api_key():
        warnings.append('청약홈 API 키 미설정 · 청약홈 신규 자료는 미수집입니다.')
    snapshot = ROOT / 'apartment_snapshot.csv'
    if refresh:
        try:
            frames.append(fetch_lh())
        except Exception:
            warnings.append('LH 공급계획 연결 실패 · 저장 자료를 표시합니다.')
        key = get_api_key()
        if key:
            try:
                frames.append(fetch_applyhome(key))
            except Exception:
                warnings.append('청약홈 API 연결 실패 · 저장 자료를 표시합니다.')
    if snapshot.exists():
        frames.append(pd.read_csv(snapshot, encoding='utf-8-sig').fillna(''))
    frames.append(load_supplement())
    apartments = pd.concat([f for f in frames if not f.empty], ignore_index=True).fillna('')
    apartments['시도'] = apartments['시도'].map(normalize_sido)
    apartments = dedup(apartments)
    apartments['세대수'] = pd.to_numeric(apartments['세대수'], errors='coerce').fillna(0).astype(int)
    apartments = apartments[apartments['입주예정월'].ge('2025-01')]
    previous_names = apartments.get('원공고단지명', pd.Series('', index=apartments.index)).fillna('')
    apartments['원공고단지명'] = previous_names.where(previous_names.ne(''), apartments['단지명'])
    apartments['단지명'] = apartments['단지명'].map(clean_apt_name)
    apartments['_naver_url'] = apartments.apply(naver_apt_url, axis=1)
    apartments = apartments.sort_values(['입주예정월', '시도', '단지명'])
    apartments.to_csv(snapshot, index=False, encoding='utf-8-sig')
    raw_brokers = pd.read_csv(ROOT / 'broker_offices.csv.gz', dtype=str, encoding='utf-8-sig').fillna('')
    brokers = normalize_broker_df(raw_brokers).drop(columns=['개설등록일자_dt'])
    kic = pd.read_csv(ROOT / 'knowledge_industry_centers.csv', dtype=str, encoding='utf-8-sig').fillna('')
    if list(kic.columns) != KIC_COLUMNS:
        raise ValueError('KIC 17-column schema mismatch')
    offices = pd.read_csv(ROOT / 'managed_offices.csv', sep='|', encoding='utf-8-sig').fillna('')
    snap = json.loads((ROOT / 'naver_rankings.json').read_text())
    proofs = {o['name']: o for o in snap['offices']}
    for extra_path in sorted(ROOT.glob('naver_rank_extension_*.json')):
        extra = json.loads(extra_path.read_text())
        snap['queries'].update(extra.get('queries', {}))
        proofs.update({o['name']: o for o in extra.get('offices', [])})
    snap['offices'] = list(proofs.values())
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
              [ROOT / 'managed_offices.csv', ROOT / 'knowledge_industry_centers.csv', ROOT / 'broker_offices.csv.gz', ROOT / 'supplemental_verified.csv']}
    meta = {'builtAt': now, 'sourceCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'warnings': warnings, 'sourceHashes': hashes, 'apartmentCount': len(apartments),
            'brokerCount': len(brokers), 'managedCount': len(offices), 'kicCount': len(kic),
            'brokerSource': json.loads((ROOT / 'broker_source_meta.json').read_text()),
            'refreshMode': 'snapshot', 'nationwideKicComplete': False}
    for filename, value in [('apartments', records(apartments)), ('brokers', records(brokers)),
                            ('kic', records(kic)), ('managed', records(offices)), ('rankings', snap)]:
        raw = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
        with gzip.GzipFile(data_dir / (filename + '.json.gz'), 'wb', mtime=0) as stream:
            stream.write(raw)
    (data_dir / 'meta.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(json.dumps({k: meta[k] for k in ('builtAt', 'sourceCommit', 'warnings', 'apartmentCount', 'brokerCount', 'managedCount', 'kicCount')}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    build(args.output, args.refresh)
