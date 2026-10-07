"""Probe direct TIPS analytics and retain definitions and raw responses."""
import json
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from cma_curve.bloomberg import BloombergClient
from cma_curve.bloomberg_fields import FieldService
from cma_curve.asset_analytics import flatten_fields

fields = ['YLD_WITHOUT_INFLATION_MID', 'YLD_WITHOUT_INFLATION_BID',
          'INFLATION_ADJ_DUR_MID', 'INDEX_ISMA_YIELD', 'INDEX_ISMA_DURATION',
          'INDEX_YTM_FLAT', 'INDEX_YTM_CURVE', 'INDEX_REAL_YIELD',
          'INDEX_REAL_DURATION', 'WEIGHTED_AVERAGE_MATURITY_YEARS']
root = Path('data') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_tips_probe')
root.mkdir(parents=True)
definitions = FieldService().info(fields)
(root / 'definitions.json').write_text(json.dumps(definitions, indent=2, default=str), encoding='utf-8')
df = pd.DataFrame(flatten_fields(definitions, 'explicit candidates'))
df.to_csv(root / 'definitions.csv', index=False)
print(df[['mnemonic', 'documentation']].to_string(index=False), flush=True)
client = BloombergClient()
current = client.reference(['LTI1TRUU Index'], fields)
current.to_csv(root / 'current_reference.csv', index=False)
print(current.to_string(index=False), flush=True)
histories = []
for field in fields:
    print('History:', field, flush=True)
    frame = client.history(['LTI1TRUU Index'], [field], '1996-10-01', '2026-09-30', frequency='monthly')
    if not frame.empty:
        histories.append(frame)
        print(frame.tail(1).to_string(index=False), flush=True)
if histories:
    pd.concat(histories, ignore_index=True).to_csv(root / 'history.csv', index=False)
print('Archive:', root, flush=True)
