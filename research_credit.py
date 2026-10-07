"""Archive candidate index composition fields without approving mappings."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from cma_curve.bloomberg_fields import FieldService
from cma_curve.asset_analytics import flatten_fields
from cma_curve.bloomberg import BloombergClient
from cma_curve.analysis import sha256

root = Path('data') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_composition-research')
root.mkdir()
responses, rows = {}, []
service = FieldService()
for query in ['index rating', 'index sector weight', 'index currency weight', 'index coupon', 'index maturity']:
    print('Searching', query, flush=True)
    responses[query] = service.search(query)
    rows.extend(flatten_fields(responses[query], query))
frame = pd.DataFrame(rows)
frame.to_csv(root / 'definitions.csv', index=False)
(root / 'responses.json').write_text(json.dumps(responses, indent=2, default=str), encoding='utf-8')
candidates = frame[frame.mnemonic.fillna('').str.contains('INDEX|WEIGHTED_AVERAGE', regex=True)]
print(candidates[['mnemonic', 'description']].drop_duplicates().to_string(index=False), flush=True)
manifest = {'kind': 'composition-research', 'retrieved_at_utc': datetime.now(timezone.utc).isoformat(),
            'status': 'candidate_fields_not_verified', 'output_sha256': {p.name:sha256(p) for p in root.iterdir()}}
(root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Archive', root, flush=True)
