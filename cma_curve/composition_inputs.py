"""Current Bloomberg membership/metadata acquisition with completeness controls."""
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import numpy as np
from .analysis import sha256, markdown_table
from .asset_analytics import flatten_fields
from .bloomberg_fields import FieldService
from .bond_inputs import load_assets
from .data import save_bundle

FIELDS = ['ID_CUSIP','RTG_SP','INDUSTRY_SECTOR','CRNCY']


def fetch_composition_inputs(catalog_path, output, client, progress=print):
    catalog = load_assets(catalog_path)
    assets = [a for a in catalog['assets'] if a['key'] != 'inflation_linked']
    if not all(a['verified'] for a in assets):
        raise ValueError('Benchmark identities must be approved before composition acquisition.')
    definitions = FieldService(client.host,client.port).info(['INDX_MWEIGHT',*FIELDS])
    backend = client._blp()
    options = client._options(backend.bds)
    options.pop('format',None)
    members, coverage, raw_bulk, errors = [], [], {}, []
    for asset in assets:
        if progress:
            progress(f'Fetching current index weights: {asset["ticker"]}')
        try:
            frame = backend.bds(tickers=asset['ticker'],flds='INDX_MWEIGHT',**options)
            raw_bulk[asset['key']] = frame
            if frame.empty:
                coverage.append({'key':asset['key'],'members':0,'weight_sum':None,'status':'complete_weighted_export_required'})
                continue
            frame=frame.copy()
            frame['key']=asset['key']
            frame['security']='/cusip/'+frame['Member Ticker and Exchange Code'].astype(str)
            frame['weight_decimal']=pd.to_numeric(frame['Percentage Weight'],errors='raise')/100
            total=frame.weight_decimal.sum()
            valid=(np.isfinite(frame.weight_decimal).all() and (frame.weight_decimal>=0).all()
                   and not frame.security.duplicated().any() and np.isclose(total,1,atol=1e-5,rtol=0))
            coverage.append({'key':asset['key'],'members':len(frame),'weight_sum':total,
                             'status':'complete_weight_sum_unverified_current_composition' if valid else 'incomplete_or_invalid_do_not_use'})
            if valid:
                members.append(frame)
        except (RuntimeError,ValueError,OSError) as exc:
            errors.append({'key':asset['key'],'error':str(exc)})
    if not members:
        raise ValueError('No complete weighted lists returned. Export index composition manually.')
    members=pd.concat(members,ignore_index=True)
    securities=members.security.drop_duplicates().tolist()
    references=[]
    for offset in range(0,len(securities),200):
        if progress:
            progress(f'Fetching current constituent metadata: {offset}/{len(securities)}')
        references.append(client.reference(securities[offset:offset+200],FIELDS))
    reference=pd.concat(references,ignore_index=True)
    coverage=pd.DataFrame(coverage)
    folder=save_bundle(reference,coverage,output,{'kind':'constituent-review',
        'status':'current_vintage_not_historical_or_approved','point_in_time_eligible':False,
        'asset_config':catalog,'asset_config_sha256':sha256(catalog_path),'code_sha256':sha256(__file__),
        'composition_asof_is':'retrieval time, NOT requested history end date','errors':errors,
        'unavailable_weights_not_rescaled':True})
    members.to_csv(folder/'members.csv',index=False)
    reference.to_csv(folder/'reference.csv',index=False)
    pd.DataFrame(flatten_fields(definitions,'composition')).to_csv(folder/'definitions.csv',index=False)
    (folder/'definitions.json').write_text(json.dumps(definitions,indent=2,default=str),encoding='utf-8')
    for key,frame in raw_bulk.items():
        frame.to_csv(folder/(key+'_raw_weights.csv'),index=False)
    (folder/'run_summary.md').write_text('# Current Index Composition\n\n'+markdown_table(coverage)+
        '\n\nWeights are current-vintage candidates, not historical September month-end weights. '
        'Missing weighted lists are not filled from partial/unweighted member lists. '
        'Issue ratings and coarse industry classification require separate review.\n',encoding='utf-8')
    manifest=folder/'manifest.json'
    info=json.loads(manifest.read_text())
    info['output_sha256']={p.name:sha256(p) for p in folder.iterdir() if p.name!='manifest.json'}
    manifest.write_text(json.dumps(info,indent=2),encoding='utf-8')
    if progress:
        progress(f'Saved current composition candidates: {folder}')
    return folder
