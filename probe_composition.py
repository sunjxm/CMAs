"""Test composition bulk fields and archive unsupported responses."""
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from cma_curve.bloomberg import BloombergClient
from cma_curve.bloomberg_fields import FieldService
from cma_curve.asset_analytics import flatten_fields
from cma_curve.analysis import sha256

root = Path('data') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_composition-probe')
root.mkdir()
fields = ['INDX_MEMBERS', 'INDX_MWEIGHT', 'INDX_MWEIGHT_HIST', 'INDEX_COUPON', 'WEIGHTED_AVERAGE_MATURITY_YEARS']
definitions = FieldService().info(fields)
(root / 'definitions.json').write_text(json.dumps(definitions, indent=2, default=str), encoding='utf-8')
pd.DataFrame(flatten_fields(definitions, 'composition candidates')).to_csv(root / 'definitions.csv', index=False)
client = BloombergClient()
tickers = ['LGC3TRUU Index', 'LBUSTRUU Index', 'LF98TRUU Index', 'LG38TRUH Index', 'EMUSTRUU Index']
reference = client.reference(tickers, fields[-2:])
reference.to_csv(root / 'reference.csv', index=False)
print(reference.to_string(index=False), flush=True)
blp = client._blp()
errors = []
for ticker in tickers:
    for field in fields[:2]:
        print('Bulk probe', ticker, field, flush=True)
        try:
            options = client._options(blp.bds)
            options.pop('format', None)
            frame = blp.bds(tickers=ticker, flds=field, **options)
            frame.to_csv(root / (ticker.split()[0] + '_' + field + '.csv'), index=False)
            print('Rows:', len(frame), flush=True)
        except Exception as exc:
            errors.append({'ticker': ticker, 'field': field, 'error': str(exc)})
manifest = {'kind':'composition-probe', 'retrieved_at_utc':datetime.now(timezone.utc).isoformat(),
            'status':'raw_not_verified', 'errors':errors, 'output_sha256':{p.name:sha256(p) for p in root.iterdir()}}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Archive:', root, 'Errors:', errors, flush=True)
