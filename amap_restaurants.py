"""Amap POI 2.0 restaurant discovery with real business fields."""
import re, math
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from algorithm import haversine,budget_info,rank
from tencent import dining_tier
from commercial import catalog,merge

def text(v):return v.strip() if isinstance(v,str) else ''
def number(v):
    try:
        n=float(v);return n if math.isfinite(n) and n>0 else None
    except (TypeError,ValueError):return None

def photos(p):
    out=[]
    for item in p.get('photos') or []:
        if not isinstance(item,dict):continue
        u=text(item.get('url'))
        try:
            parsed=urlsplit(u);host=parsed.hostname or ''
            if parsed.scheme=='http' and (host.endswith('.autonavi.com') or host.endswith('.amap.com')):u='https'+u[4:];parsed=urlsplit(u)
            if parsed.scheme=='https' and not parsed.username and not parsed.password and u not in out:out.append(u)
        except ValueError:continue
    return out[:3]

def parse(p,center,radius,records):
    pid=text(p.get('id'));name=text(p.get('name'));category=text(p.get('type'))
    if not pid or not name or not text(p.get('typecode')).startswith('05') or dining_tier(name,category) is None:return None
    try:
        loc=list(map(float,text(p.get('location')).split(',')))
        if len(loc)!=2 or not(-180<=loc[0]<=180 and -90<=loc[1]<=90) or haversine(center,loc)*1000>radius:return None
    except (ValueError,TypeError):return None
    b=p.get('business');b=b if isinstance(b,dict) else {}
    hours=text(b.get('opentime_today'));week=text(b.get('opentime_week'))
    if '永久停业' in name+hours+week:return None
    rating=number(b.get('rating'));price=number(b.get('cost'))
    tel=b.get('tel');tel=';'.join(str(x) for x in tel) if isinstance(tel,list) else text(tel)
    row=dict(id=pid,name=name,address=text(p.get('address')),location=loc,category=category,rating=rating if rating and rating<=5 else None,price=price if price and price<=10000 else None,sales=None,status='unknown',hours=hours,weekly_hours=week,hours_date=datetime.now(timezone(timedelta(hours=8))).date().isoformat(),tel=tel,citycode=text(p.get('citycode')),photos=photos(p),source='高德地图',routes={})
    return merge(row,records,'amap')

def search(request,center,radius,budget,status,limit=60,members=None):
    radius=min(20000,max(500,int(radius)));records=catalog();pool={};errors=[];ok=0
    queries=[('',3),('火锅',2),('烤肉',2),('自助餐',2),('中餐厅',2),('烧烤',2),('西餐',1),('地方菜',1)]
    for keyword,pages in queries:
        for page in range(1,pages+1):
            args={'location':','.join(str(round(x,6)) for x in center),'radius':radius,'types':'050000','show_fields':'business,photos','page_size':25,'page_num':page,'sortrule':'weight'}
            if keyword:args['keywords']=keyword
            try:d=request('v5/place/around',args);ok+=1
            except ValueError as e:errors.append(str(e));break
            rows=d.get('pois') or []
            for p in rows:
                if not isinstance(p,dict):continue
                row=parse(p,center,radius,records)
                if row:
                    old=pool.get(row['id'])
                    if old:
                        for k,v in row.items():
                            if not old.get(k) and v:old[k]=v
                    else:pool[row['id']]=row
            if len(rows)<25:break
        if not ok and errors:raise ValueError(errors[0])
    def order(a):
        state={'open':0,'unknown':1,'closed':2}.get(status(a),1)
        b,delta=budget_info(a['price'],budget)
        return (state,{'near':0,'outside':1,'unknown':2,None:0}[b],dining_tier(a['name'],a['category']),a['rating'] is None,-(a['rating'] or 0),delta if delta is not None else 0,haversine(center,a['location']),a['id'])
    if members:
        # Score the entire retrieved pool before the display cap, not only the first 60 POIs.
        rows=list(pool.values())
        for a in rows:
            a['status']=status(a)
            a['routes']={m['id']:{'km':round(haversine(m['location'],a['location']),2)} for m in members}
        ranked,_=rank(rows,members,budget=budget)
        result=ranked[:limit]
    else:
        result=sorted(pool.values(),key=order)[:limit]
    for a in result:a['searchPartial']=bool(errors)
    if not result and errors:raise ValueError(errors[0])
    return result
