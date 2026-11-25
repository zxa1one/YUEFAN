"""Local, verified commercial records. No scraping or fabricated data.
Future authorized integrations can provide this same schema.
"""
import json, math
from pathlib import Path
from datetime import datetime, timedelta, timezone
from tencent import deal_url
BASE=Path(__file__).resolve().parent

def catalog():
    try:
        data=json.loads((BASE/'verified_merchants.json').read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def merge(row, records, provider):
    extra=records.get(provider+':'+row['id'], {})
    if not isinstance(extra,dict) or extra.get('name')!=row['name'] or extra.get('address')!=row['address']:return row
    now=datetime.now(timezone.utc)
    for platform in ('meituan','douyin'):
        value=extra.get(platform)
        if not isinstance(value,dict):continue
        try: expires=datetime.fromisoformat(value['expires_at'].replace('Z','+00:00'))
        except (KeyError,ValueError,TypeError,AttributeError):continue
        if expires.tzinfo is None or expires<=now:continue
        url=deal_url(value.get('url'),platform)
        if url:row[platform+'_deal_url']=url;row[platform+'_deal_expires']=expires.isoformat()
    popularity=extra.get('popularity')
    if isinstance(popularity,dict):
        try:
            date=datetime.fromisoformat(popularity['as_of'].replace('Z','+00:00'))
            source=popularity['source']
            counts=popularity['counts']
            if date.tzinfo is not None and now-timedelta(days=31)<=date<=now and isinstance(source,str) and source.strip() and isinstance(counts,dict):
                clean={k:v for k,v in counts.items() if k in ('comments','favorites','checkins','deals') and type(v) is int and v>=0}
                if clean:row.update(popularity_counts=clean,popularity_source=source.strip(),popularity_as_of=date.isoformat())
        except (KeyError,ValueError,TypeError,AttributeError):pass
    sales=extra.get('monthly_sales')
    if isinstance(sales,dict) and sales.get('metric')=='restaurant_monthly_sales' and sales.get('source'):
        try:
            date=datetime.fromisoformat(sales['as_of'].replace('Z','+00:00'));v=sales['value']
            if date.tzinfo is not None and now-timedelta(days=31)<=date<=now and type(v) is int and v>=0:
                row.update(sales=v,sales_source=str(sales['source']),sales_as_of=date.isoformat())
        except (KeyError,ValueError,TypeError,AttributeError):pass
    return row

def expire(row):
    now=datetime.now(timezone.utc)
    for p in ('douyin','meituan'):
        if row.get(p+'_deal_expires') and datetime.fromisoformat(row[p+'_deal_expires'])<=now:row[p+'_deal_url']=None
    if row.get('sales_as_of') and datetime.fromisoformat(row['sales_as_of'])<now-timedelta(days=31):row['sales']=None

    if row.get('popularity_as_of') and datetime.fromisoformat(row['popularity_as_of'])<now-timedelta(days=31):
        row.pop('popularity_counts',None);row.pop('popularity_source',None);row.pop('popularity_as_of',None)
