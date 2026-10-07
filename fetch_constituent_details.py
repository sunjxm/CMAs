"""Bounded current-vintage constituent review; not historical weights."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from cma_curve.bloomberg import BloombergClient
from cma_curve.bloomberg_fields import FieldService
from cma_curve.asset_analytics import flatten_fields
from cma_curve.analysis import sha256

source = Path('data/20261007T052559_composition-probe')
root = Path('data') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_constituent-review')
root.mkdir()
fields = ['ID_CUSIP', 'RTG_SP', 'INDUSTRY_SECTOR', 'LEHMAN_ISSUER_CLASS', 'LEHMAN_SECTOR', 'CRNCY']
definitions = FieldService().info(fields)
(root / 'definitions.json').write_text(json.dumps(definitions, indent=2, default=str), encoding='utf-8')
pd.DataFrame(flatten_fields(definitions, 'constituent candidates')).to_csv(root / 'definitions.csv', index=False)
members = []
for key, ticker in [('short_term_bond','LGC3TRUU'),('high_yield','LF98TRUU'),('em_debt','EMUSTRUU')]:
    f = pd.read_csv(source / (ticker + '_INDX_MWEIGHT.csv'))
    f['key'], f['security'] = key, '/cusip/' + f['Member Ticker and Exchange Code'].astype(str)
    f['weight_decimal'] = f['Percentage Weight'] / 100
    members.append(f)
members = pd.concat(members, ignore_index=True)
members.to_csv(root / 'members.csv', index=False)
securities = members.security.drop_duplicates().tolist()
client = BloombergClient()
frames = []
for offset in range(0, len(securities), 200):
    print(f'Constituent metadata: {offset}/{len(securities)}', flush=True)
    frame = client.reference(securities[offset:offset+200], fields)
    frames.append(frame)
    pd.concat(frames, ignore_index=True).to_csv(root / 'reference.csv', index=False)
manifest = {'kind':'constituent-review', 'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
            'status':'current_vintage_not_historical_or_approved', 'source':str(source.resolve()),
            'source_manifest_sha256':sha256(source / 'manifest.json'),
            'output_sha256':{p.name:sha256(p) for p in root.iterdir()}}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print(root, flush=True)
