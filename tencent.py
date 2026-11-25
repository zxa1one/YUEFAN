"""Tencent WebService adapter. Coordinates internally [longitude, latitude]."""
import os,json,hashlib,time,threading,math
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen
from urllib.error import HTTPError,URLError
from algorithm import haversine
BASE=Path(__file__).resolve().parent
FILE=BASE/'.tencent_credentials.json'
try: saved=json.loads(FILE.read_text(encoding='utf-8')) if FILE.is_file() else {}
except (ValueError,OSError): saved={}
KEY=os.getenv('TENCENT_MAP_KEY','').strip() or saved.get('key','')
SK=os.getenv('TENCENT_MAP_SK','').strip() or saved.get('sk','')
PACE=threading.Lock(); LAST=0.0

def configured():return bool(KEY and SK)
def signed_url(path,params,key,sk):
    p={**params,'key':key}; raw='&'.join(f'{k}={p[k]}' for k in sorted(p))
    sig=hashlib.md5((path+'?'+raw+sk).encode('utf-8')).hexdigest()
    return 'https://apis.map.qq.com'+path+'?'+urlencode(dict(p,sig=sig))
def request(path,params):
    global LAST
    if not configured():raise ValueError('请先配置腾讯地图 Key 和 SK')
    # Conservative shared rate cap for local development.
    with PACE:
        time.sleep(max(0,.26-(time.monotonic()-LAST))); LAST=time.monotonic()
    try:
        with urlopen(signed_url(path,params,KEY,SK),timeout=12) as f:d=json.load(f)
    except HTTPError as e:raise ValueError('腾讯地图 HTTP 错误：'+str(e.code)) from None
    except (URLError,TimeoutError,OSError,ValueError):raise ValueError('腾讯地图连接失败，请检查网络') from None
    if str(d.get('status'))!='0':
        code=str(d.get('status','未知')); msg={'111':'签名校验失败，请核对 Key 与 SK','110':'请求来源未授权','112':'IP 未授权','113':'接口未授权','120':'请求频率超限','121':'每日配额已用尽'}.get(code,'请检查接口参数、权限及配额')
        raise ValueError('腾讯地图 '+code+'：'+msg)
    return d

def latlng(p):return f'{p[1]:.6f},{p[0]:.6f}'
def point(p):
    x,y=float(p['lng']),float(p['lat'])
    if not (-180<=x<=180 and -90<=y<=90):raise ValueError('腾讯地图坐标无效')
    return [x,y]
def convert(p):return point(request('/ws/coord/v1/translate',{'locations':latlng(p),'type':1})['locations'][0])
def geocode(city,address):
    a=request('/ws/geocoder/v1/',{'address':city+address,'region':city})['result']
    return {'location':point(a['location']),'address':city+' '+address+'（请核对地址）'}
def reverse(p):
    d=request('/ws/geocoder/v1/',{'location':latlng(p),'get_poi':0})['result']
    return str(d.get('address') or (d.get('formatted_addresses') or {}).get('recommend') or '')

# These are dining suitability heuristics, not Dianping listings or deal verification.
EXCLUDED=('食堂','员工餐厅','职工餐厅','内部餐厅','外卖档口','纯外卖','奶茶','茶饮','咖啡','甜品','蛋糕','面包','冰淇淋','饮品','熟食店','生鲜','餐饮管理','餐饮公司','食品公司','永久停业','已关闭','已停业')
DINING=('美食','餐饮','餐厅','餐馆','饭店','小吃','快餐','火锅','烧烤','烤肉','料理','中餐','西餐','自助','面馆')
SITDOWN=('火锅','烧烤','烤肉','自助','中餐','西餐','料理','川菜','湘菜','粤菜','家常菜','地方菜','餐馆','饭店','餐厅','酒楼','菜馆','海鲜','融合菜')
def dining_tier(name,category):
    text=name+' '+category
    if any(x in text for x in EXCLUDED) or not any(x in category for x in DINING):return None
    if any(x in text for x in ('快餐','小吃','面馆','汉堡','粉面','包子','饺子','米线')):return 1
    return 0 if any(x in text for x in SITDOWN) else 1

RICH_PARAMS={'get_rich':1,'added_fields':'star_level,avg_price,opening_hours'}
RICH_UNAVAILABLE=False

def search_page(params):
    global RICH_UNAVAILABLE
    if not RICH_UNAVAILABLE:
        try:return request('/ws/place/v1/search',{**params,**RICH_PARAMS})
        except ValueError as e:
            # Permission denial only: normal search can still be available.
            if '腾讯地图 113：' not in str(e):raise
            RICH_UNAVAILABLE=True
    return request('/ws/place/v1/search',params)

def rich_value(p,key):
    for source in (p,p.get('rich'),p.get('added_fields'),p.get('rich_info')):
        if isinstance(source,dict) and source.get(key) not in (None,'',[]):return source[key]
    return None

def verified_catalog():
    # Optional locally verified merchant records, matched by exact Tencent POI ID.
    try:
        data=json.loads((BASE/'verified_merchants.json').read_text(encoding='utf-8'))
        return data if isinstance(data,dict) else {}
    except (OSError,ValueError):return {}

def deal_url(v,platform):
    if not isinstance(v,str):return None
    try:u=urlsplit(v);host=u.hostname or ''
    except ValueError:return None
    domains={'meituan':('meituan.com','dianping.com','meituan.net'),'douyin':('douyin.com',)}[platform]
    return v if u.scheme=='https' and not u.username and not u.password and any(host==d or host.endswith('.'+d) for d in domains) else None

def enrich(p,loc,category,catalog):
    pid=str(p['id']); rating=number(rich_value(p,'star_level')); price=number(rich_value(p,'avg_price')); hours=rich_value(p,'opening_hours')
    row=dict(id=pid,name=str(p['title']).strip(),address=str(p.get('address') or ''),location=loc,rating=rating if rating and rating<=5 else None,price=price if price and price<=10000 else None,sales=None,status='unknown',hours=hours if isinstance(hours,str) else '',tel=str(p.get('tel') or ''),category=category,routes={})
    extra=catalog.get(pid,{})
    # A matching name is required in addition to the stable POI id.
    if isinstance(extra,dict) and extra.get('name')==row['name']:
        for platform in ('douyin','meituan'):
            row[platform+'_deal_url']=deal_url(extra.get(platform+'_deal_url'),platform)
        if isinstance(extra.get('tel'),str) and not row['tel']:row['tel']=extra['tel']
    return row

def search(center,radius=20000,limit=60):
    radius=min(20000,max(10,int(radius)))
    x,y=center; dy=radius/110500;dx=dy/max(.01,math.cos(math.radians(y)))
    def rect(x1,y1,x2,y2):
        return f'rectangle({max(-90,y1):.6f},{max(-180,x1):.6f},{min(90,y2):.6f},{min(180,x2):.6f})'
    near=f'nearby({latlng(center)},{min(1000,radius)},0)'
    queries=[('餐厅',near,2),('火锅',near,1),('烤肉',near,1),('中餐厅',near,1)]
    if radius>1000:
        # Four sectors plus a central search and category searches. All results are clipped to the actual circle.
        boxes=[rect(a,b,c,d) for a,c in ((x-dx,x),(x,x+dx)) for b,d in ((y-dy,y),(y,y+dy))]
        queries += [('餐厅',box,2) for box in boxes]
        inner=rect(x-dx/2,y-dy/2,x+dx/2,y+dy/2)
        queries += [('餐厅',inner,2),('火锅',inner,1),('烤肉',inner,1),('自助餐',inner,1)]
        full=rect(x-dx,y-dy,x+dx,y+dy)
        queries += [(k,full,1) for k in ('火锅','烤肉','自助餐','中餐厅','西餐厅','烧烤','地方菜','家常菜')]
    else:queries.append(('美食',near,2))
    groups=[]; errors=[]; successful=0; catalog=verified_catalog()
    for keyword,boundary,pages in queries:
        rows=[]; seen=set()
        for page in range(1,pages+1):
            try:d=search_page({'keyword':keyword,'boundary':boundary,'page_size':20,'page_index':page});successful+=1
            except ValueError as e:
                # Do not hide credential and quota failures, or pretend failed searches returned no restaurants.
                if any('腾讯地图 '+code+'：' in str(e) for code in ('110','111','112','113','120','121')):raise
                errors.append(str(e));break
            data=d.get('data') or []
            for p in data:
                name=str(p.get('title','')).strip();category=str(p.get('category',''));pid=str(p.get('id') or '')
                tier=dining_tier(name,category)
                if not pid or pid in seen or not name or tier is None or p.get('type',0)!=0:continue
                try:loc=point(p['location'])
                except (ValueError,KeyError,TypeError):continue
                if haversine(center,loc)*1000>radius:continue
                seen.add(pid)
                row=enrich(p,loc,category,catalog)
                if '永久停业' in row['hours']:continue
                rows.append((tier,row))
            if len(data)<20 or (d.get('count') is not None and page*20>=int(d['count'])):break
        groups.append(rows)
    if not successful and errors:raise ValueError(errors[0])
    # Merge duplicate POIs before truncation. Prefer verified deal links, then
    # usable quality metadata, then nearer sit-down restaurants; no invented popularity.
    pool={}
    for g in groups:
        for tier,row in g:
            pid=row['id']
            if pid not in pool:pool[pid]=(tier,row)
            else:
                oldtier,old=pool[pid]
                for k in ('rating','price','hours','tel','douyin_deal_url','meituan_deal_url'):
                    if not old.get(k) and row.get(k):old[k]=row[k]
                pool[pid]=(min(tier,oldtier),old)
    def quality(item):
        tier,row=item; rating=row.get('rating'); deal=bool(row.get('douyin_deal_url') or row.get('meituan_deal_url'))
        return (tier,not deal,rating is None,-(rating or 0),not bool(row.get('hours')),haversine(center,row['location']),row['id'])
    ordered=sorted(pool.values(),key=quality)
    # Keep a small share of simple meals only when available.
    main=[row for tier,row in ordered if tier==0]; quick=[row for tier,row in ordered if tier==1]
    chosen=main[:limit-max(1,limit//10)]+quick[:max(1,limit//10)]
    chosen+=(main[limit-max(1,limit//10):]+quick[max(1,limit//10):])[:max(0,limit-len(chosen))]
    out={row['id']:row for row in chosen[:limit]}
    if not out and errors:raise ValueError('部分地图搜索失败：'+errors[0])
    for row in out.values():row['searchPartial']=bool(errors)
    return list(out.values())
def number(v):
    try:
        v=float(v);return v if math.isfinite(v) and v>=0 else None
    except (ValueError,TypeError):return None

def route(m,r):
    mode={'walk':'walking','bike':'bicycling','drive':'driving','transit':'transit'}[m['mode']]
    d=request('/ws/direction/v1/'+mode+'/',{'from':latlng(m['location']),'to':latlng(r['location'])})
    arr=d.get('result',{}).get('routes',[])
    if not arr:raise ValueError('腾讯地图未返回路线')
    a=arr[0];km=number(a.get('distance'));minutes=number(a.get('duration'))
    return {'km':round(km/1000,2) if km is not None else None,'minutes':math.ceil(minutes) if minutes is not None else None,'source':'腾讯路线规划'}
