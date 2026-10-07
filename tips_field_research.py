"""Archive Bloomberg field definitions for the TIPS input investigation."""
import json
from datetime import datetime, timezone
from pathlib import Path
from cma_curve.bloomberg_fields import FieldService
from cma_curve.asset_analytics import flatten_fields
import pandas as pd

root = Path('data') / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '_tips_research')
root.mkdir(parents=True)
responses = {}
rows = []
service = FieldService()
for query in ['real yield', 'real duration', 'index inflation', 'index isma']:
    print('Searching:', query, flush=True)
    responses[query] = service.search(query)
    rows.extend(flatten_fields(responses[query], query))
(root / 'field_responses.json').write_text(json.dumps(responses, indent=2, default=str), encoding='utf-8')
frame = pd.DataFrame(rows)
frame.to_csv(root / 'field_candidates.csv', index=False)
print(root, flush=True)
print(frame.to_string(index=False), flush=True)
