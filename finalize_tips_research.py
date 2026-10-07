"""Seal investigation evidence without changing the archived source responses."""
import json
from pathlib import Path
from datetime import datetime, timezone
from cma_curve.analysis import sha256

for name in ['20261007T050208_tips_research', '20261007T050254_tips_probe']:
    root = Path('data') / name
    manifest = {'kind': 'tips-field-investigation',
                'retrieved_at_utc': datetime.strptime(root.name[:15], '%Y%m%dT%H%M%S').replace(tzinfo=timezone.utc).isoformat(),
                'manifest_created_at_utc': datetime.now(timezone.utc).isoformat(),
                'status': 'research_not_approved_index_analytics',
                'output_sha256': {p.name: sha256(p) for p in root.iterdir() if p.name != 'manifest.json'}}
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
