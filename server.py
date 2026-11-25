import os,json,sqlite3,secrets,threading,copy,re,math,hashlib,time
from pathlib import Path
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs,urlencode
from urllib.request import urlopen
from urllib.error import URLError
from datetime import datetime,timezone,timedelta
from concurrent.futures import ThreadPoolExecutor
from algorithm import rank,haversine
import tencent
import amap_restaurants, commercial
BASE=Path(__file__).resolve().parent
DB=Path(os.getenv('FANJU_DB',str(BASE/'rooms.sqlite3')))
KEY_FILE=BASE/'.amap_key'
KEY=(os.getenv('AMAP_KEY','').strip() or (KEY_FILE.read_text(encoding='utf-8').strip() if KEY_FILE.is_file() else ''))
def provider():return "hybrid" if KEY and tencent.configured() else "amap" if KEY else "tencent" if tencent.configured() else "demo"
def is_configured():return provider()!="demo"
LOCK=threading.RLock()
GENERATING=set()
ROUTING=set()
MODES={'walk':'步行','bike':'骑行','drive':'驾车','transit':'公交'}
DEMO_CENTER=[113.242,35.19]
# Explicit opt-in for local development tests only.
ALLOW_DEMO=os.getenv('YUEFAN_ALLOW_DEMO','')=='1'
@contextmanager
def conn():
    c=sqlite3.connect(DB,timeout=10)
    try:
        with c:
            c.execute('CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY, salt TEXT NOT NULL, password TEXT NOT NULL)')
            c.execute('CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, name TEXT NOT NULL, expires INTEGER NOT NULL)')
            yield c
    finally:
        c.close()
def password_hash(password,salt):
    return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()
def account(token):
    if not token:return None
    digest=hashlib.sha256(token.encode()).hexdigest()
    with conn() as c:row=c.execute('SELECT name FROM sessions WHERE token=? AND expires>?',(digest,int(time.time()))).fetchone()
    return row[0] if row else None
def authenticate(d,register=False):
    name=str(d.get('name','')).strip();password=str(d.get('password',''))
    if not 2<=len(name)<=24 or not 8<=len(password)<=128:raise ValueError('昵称需2–24字，密码需8–128字符')
    with conn() as c:
        if register:
            salt=secrets.token_hex(16);hashed=password_hash(password,salt)
            try:c.execute('INSERT INTO accounts VALUES (?,?,?)',(name,salt,hashed))
            except sqlite3.IntegrityError:raise ValueError('昵称已被注册，请登录或更换昵称')
        else:
            row=c.execute('SELECT salt,password FROM accounts WHERE name=?',(name,)).fetchone()
            if not row or not secrets.compare_digest(password_hash(password,row[0]),row[1]):raise ValueError('昵称或密码错误')
        token=secrets.token_urlsafe(32);c.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),name,int(time.time())+30*86400))
    return {'name':name,'token':token}
def ready(m):return m['location'] is not None
def location_status(m):return 'located' if ready(m) else m.get('location_status','pending')
def all_located(r):return len(r['members'])==r['count'] and all(ready(m) for m in r['members'])
def load(rid):
    with conn() as c: row=c.execute('SELECT body FROM rooms WHERE id=?',(rid,)).fetchone()
    if not row: raise ValueError('房间不存在或链接无效')
    return json.loads(row[0])
def save(r):
    with conn() as c: c.execute('INSERT OR REPLACE INTO rooms VALUES (?,?)',(r['id'],json.dumps(r,ensure_ascii=False)))
def find_member(r,token):
    return next((m for m in r['members'] if secrets.compare_digest(m['token'],str(token or ''))),None)
def require(r,token):
    m=find_member(r,token)
    if not m: raise ValueError('请先加入房间')
    return m
def host(r,token):
    if require(r,token)['id']!=r['host']: raise ValueError('只有发起人可以执行此操作')
def new_member(name):
    name=str(name).strip()[:24]
    if not name: raise ValueError('请输入昵称')
    return {'id':secrets.token_hex(5),'token':secrets.token_urlsafe(24),'name':name,'location':None,'mode':'walk','vote':None}
def amap(path,params):
    if not KEY: raise ValueError('尚未配置高德 Web 服务 Key')
    try:
        with urlopen('https://restapi.amap.com/'+path+'?'+urlencode(dict(params,key=KEY)),timeout=12) as f: d=json.load(f)
    except (URLError,TimeoutError,OSError,ValueError): raise ValueError('无法连接高德服务，请检查网络后重试') from None
    if str(d.get('status'))!='1': raise ValueError('高德接口错误：'+str(d.get('info','未知'))+' ('+str(d.get('infocode','未知'))+')')
    return d
def num(v):
    try:
        x=float(v);return x if math.isfinite(x) and x>=0 else None
    except (ValueError,TypeError): return None
def coord(v):
    if not isinstance(v,list) or len(v)!=2: raise ValueError('经纬度格式错误')
    x,y=map(float,v)
    if not (-180<=x<=180 and -90<=y<=90): raise ValueError('经纬度超出范围')
    return [x,y]
def pair(x): return ','.join(str(round(v,6)) for v in x)
def convert(p):
    d=amap('v3/assistant/coordinate/convert',{'locations':pair(p),'coordsys':'gps'})
    return coord([float(x) for x in d['locations'].split(',')])
def status_today(t,now=None):
    if not isinstance(t,str) or not t.strip(): return 'unknown'
    t=t.replace('：',':')
    if any(x in t for x in ('暂停营业','暂不营业','今日休息','今日不营业','未营业','歇业','停业')): return 'closed'
    if '24小时' in t or '全天' in t: return 'open'
    now=now or datetime.now(timezone(timedelta(hours=8)))
    minute=now.hour*60+now.minute
    spans=re.findall(r'(\d{1,2}):(\d{2})\s*[-~—–－至]\s*(\d{1,2}):(\d{2})',t)
    if not spans: return 'unknown'
    for h,m,h2,m2 in spans:
        a=int(h)*60+int(m);b=int(h2)*60+int(m2)
        if not (0<=int(h)<24 and 0<=int(m)<60 and 0<=int(h2)<=24 and 0<=int(m2)<60 and (int(h2)!=24 or int(m2)==0)):return 'unknown'
        if a==b:return 'unknown'
        if (a<=minute<b if a<b else minute>=a or minute<b):return 'open'
    return 'closed'
def live_route(m,r):
    p={'origin':pair(m['location']),'destination':pair(r['location']),'show_fields':'cost'}
    mode=m['mode']; path={'walk':'walking','bike':'bicycling','drive':'driving','transit':'transit/integrated'}[mode]
    if mode=='transit':
        p.update(city1=r['citycode'],city2=r['citycode'])
        if not r['citycode']: raise ValueError('公交城市代码缺失')
    d=amap('v5/direction/'+path,p)['route']; arr=d.get('transits' if mode=='transit' else 'paths',[])
    if not arr: raise ValueError('无可用路线')
    a=arr[0]; distance=num(a.get('distance')); cost=a.get('cost') or {}; duration=num(cost.get('duration',a.get('duration')) if isinstance(cost,dict) else a.get('duration'))
    return {'km':round(distance/1000,2) if distance is not None else None,'minutes':math.ceil(duration/60) if duration is not None else None,'source':'高德路径规划' if distance is not None and duration is not None else '高德路线数据不完整'}
def geographic_distance(m,r):
    """Mode-independent distance; both positions use the mainland GCJ-02 coordinate system in live rooms."""
    if m.get('location') is None or r.get('location') is None:return {'km':None,'source':'距离暂无'}
    return {'km':round(haversine(m['location'],r['location']),2),'source':'直线距离'}

def restaurant_status(r,a):
    if r['demo']:return a['status']
    if a.get('verified_at',0)>time.time()-7200:return a.get('verified_status','unknown')
    if r.get('provider')=='tencent':
        # Only simple daily hours are interpreted; weekday-specific or complex schedules remain unknown.
        hours=a.get('hours','')
        if a.get('hours_date')==datetime.now(timezone(timedelta(hours=8))).date().isoformat() and isinstance(hours,str) and not re.search(r'周|星期|礼拜|节假|工作日|[一二三四五六日]至',hours):return status_today(hours)
        return 'unknown'
    return status_today(a.get('hours')) if a.get('hours_date')==datetime.now(timezone(timedelta(hours=8))).date().isoformat() else 'unknown'

def candidates(r):
    ms=[m for m in r['members'] if m['location'] is not None]; center=[sum(m['location'][i] for m in ms)/len(ms) for i in range(2)]
    if r['demo']:
        rows=[('老街川菜馆',4.8,45,3200,.004,.003,'open'),('四季烤肉',4.7,68,2800,-.009,.003,'open'),('山野火锅',4.9,89,2100,.012,-.005,'open'),('江南小馆',4.9,50,4200,-.003,-.001,'closed'),('邻里面馆',4.5,22,3800,.001,.009,'open'),('禾木茶餐厅',4.6,36,1900,-.006,-.008,'open'),('小城家常菜',4.6,32,1200,.007,-.009,'unknown')]
        out=[]
        for i,(name,rating,price,sales,x,y,st) in enumerate(rows):
            loc=[center[0]+x,center[1]+y]; routes={}
            for m in ms:
                routes[m['id']]=geographic_distance(m,{'location':loc})
            out.append(dict(id=f'demo-{i}',name=name,rating=rating,price=price,status=st,hours='17:00–22:00（模拟）' if st=='closed' else '',address='模拟餐厅 · 非真实商家',location=loc,routes=routes))
        return out
    # Amap supplies restaurant POIs; distance uses coordinates directly.
    if r.get('provider')=='tencent':
        out=tencent.search(center,r['radius'])
        for a in out:
            a['hours_date']=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
            a['status']=restaurant_status(r,a)
    else:
        out=amap_restaurants.search(amap,center,r['radius'],r.get('budget'),lambda a:restaurant_status(r,a),members=ms)
        for a in out:a['status']=restaurant_status(r,a)
    for a in out:
        a['routes']={m['id']:geographic_distance(m,a) for m in ms}
    return out

def public(r,token,sort='composite'):
    m=find_member(r,token); members=r['members']; rs=copy.deepcopy(r['restaurants']) if m else []
    if not r['demo']:
        records=commercial.catalog() if r.get('provider') in ('amap','hybrid') else None
        for a in rs:
            a['status']=restaurant_status(r,a)
            if records is not None:
                for key in ('popularity_counts','popularity_source','popularity_as_of','meituan_deal_url','meituan_deal_expires','douyin_deal_url','douyin_deal_expires'):
                    a.pop(key,None)
                commercial.merge(a,records,'amap')
            commercial.expire(a)
    for a in rs:
        a['routes']={x['id']:geographic_distance(x,a) for x in members if x.get('location') is not None}
    # Results are authoritative and use only votes, then alphabetical names.
    sort='results' if r['stage']=='done' else ('composite' if sort=='results' else sort)
    rs,e=rank(rs,members,sort,r.get('budget'))
    if not m: rs=[];e={}
    # Before completion, hide others' votes to avoid influence; never share precise member coordinates or tokens.
    for a in rs:
        if r['stage']!='done': a.pop('votes',None)
        else:
            a['voters']=[{'id':x['id'],'name':x['name']} for x in members if x.get('vote')==a['id']]
    return {'id':r['id'],'title':r['title'],'count':r['count'],'demo':r['demo'],'radius':r['radius'],'budget':r.get('budget'),'stage':r['stage'],'finishReason':r.get('finish_reason') if r['stage']=='done' else None,'host':r['host'],'members':[{'id':x['id'],'name':x['name'],'ready':ready(x),'located':x['location'] is not None,'locationStatus':location_status(x),'submitted':x['vote'] is not None} for x in members] if m else [],'me':{'id':m['id'],'vote':m['vote'],'ready':ready(m),'located':m['location'] is not None,'locationStatus':location_status(m)} if m else None,'restaurants':rs,'weights':e,'updated':r.get('updated'),'amapConfigured':is_configured(),'provider':r.get('provider','demo' if r['demo'] else 'amap'),'generationError':r.get('generation_error'),'generating':r['id'] in GENERATING,'routing':any(x[0]==r['id'] for x in ROUTING),'routesPending':bool(m and m['location'] is not None and any(m['id'] not in a.get('routes',{}) for a in r['restaurants']))}
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Request paths can contain invitation IDs. Avoid logging them by default.
        if os.getenv('YUEFAN_DEBUG_HTTP')=='1': super().log_message(format,*args)
    def send_json(self,d,code=200):
        b=json.dumps(d,ensure_ascii=False,allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(b)
    def do_GET(self):
        try:
            u=urlparse(self.path);q=parse_qs(u.query)
            if u.path=='/api/config':return self.send_json({'amapConfigured':is_configured(),'provider':provider(),'account':account(self.headers.get('X-Account-Token'))})
            if u.path=='/api/room':
                with LOCK:
                    r=load(q.get('id',[''])[0])
                    if r['demo'] and not ALLOW_DEMO:raise ValueError('演示模式未启用')
                    data=public(r,self.headers.get('X-Member-Token'),q.get('sort',['composite'])[0]);return self.send_json(data)
            name={'/':'index.html','/index.html':'index.html','/app.js':'app.js','/style.css':'style.css'}.get(u.path)
            if not name: return self.send_json({'error':'Not found'},404)
            b=(BASE/'public'/name).read_bytes();self.send_response(200);self.send_header('Content-Type',{'index.html':'text/html','app.js':'text/javascript','style.css':'text/css'}[name]+'; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.send_header('Referrer-Policy','no-referrer');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(b)
        except ValueError as e:self.send_json({'error':str(e)},400)
        except Exception as e:print(type(e).__name__);self.send_json({'error':'服务器异常'},500)
    def do_POST(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=20000:raise ValueError('请求过大')
            d=json.loads(self.rfile.read(size));act=urlparse(self.path).path.removeprefix('/api/');token=self.headers.get('X-Member-Token')
            if act in ('register','login'):return self.send_json(authenticate(d,act=='register'))
            if act=='logout':
                with conn() as c:c.execute('DELETE FROM sessions WHERE token=?',(hashlib.sha256((self.headers.get('X-Account-Token') or '').encode()).hexdigest(),))
                return self.send_json({'ok':True})
            if act=='reverse':
                if not account(self.headers.get('X-Account-Token')):raise ValueError('请先登录')
                p=coord(d.get('location'))
                if provider() in ('tencent','hybrid'):return self.send_json({'address':tencent.reverse(tencent.convert(p))})
                return self.send_json({'address':amap('v3/geocode/regeo',{'location':pair(convert(p))}).get('regeocode',{}).get('formatted_address','')}) if KEY else self.send_json({'address':''})
            if act=='geocode':
                if not account(self.headers.get('X-Account-Token')):raise ValueError('请先登录')
                address=str(d.get('address','')).strip();city=str(d.get('city','')).strip()
                if not 2<=len(address)<=120 or not 2<=len(city)<=40:raise ValueError('请输入城市与详细地址')
                if provider() in ('tencent','hybrid'):return self.send_json(tencent.geocode(city,address))
                found=amap('v3/geocode/geo',{'address':address,'city':city}).get('geocodes',[])
                if not found:raise ValueError('没有找到该地址，请填写更详细的位置')
                a=found[0];return self.send_json({'location':coord([float(x) for x in a['location'].split(',')]),'address':a.get('formatted_address',address)})
            if act=='create':
                name=account(self.headers.get('X-Account-Token'))
                if not name:raise ValueError('请先注册或登录')
                count=int(d.get('count',4));radius=int(d.get('radius',20000));demo=d.get('demo',False) is True
                if demo and not ALLOW_DEMO:raise ValueError('演示模式未启用')
                if not 2<=count<=12 or not 500<=radius<=20000:raise ValueError('人数或范围不合法')
                budget=None
                if d.get('budget') is not None:
                    budget=num(d['budget'])
                    if isinstance(d['budget'],bool) or budget is None or not 1<=budget<=10000 or not budget.is_integer():raise ValueError('请输入 1–10000 元的整数人均预算')
                    budget=int(budget)
                if not demo and not is_configured():raise ValueError('真实模式需要配置地图 Key')
                m=new_member(name);r={'id':secrets.token_urlsafe(9),'title':str(d.get('title','朋友约饭')).strip()[:48] or '朋友约饭','count':count,'radius':radius,'budget':budget,'provider':'demo' if demo else provider(),'demo':demo,'stage':'lobby','host':m['id'],'members':[m],'restaurants':[]}
                if demo:m['location']=DEMO_CENTER[:]
                else:
                    p=coord(d.get('location'));m['location']=(tencent.convert(p) if r.get('provider') in ('tencent','hybrid') else convert(p)) if d.get('coordType')=='gps' else p
                with LOCK:save(r)
                return self.send_json({'id':r['id'],'token':m['token']})
            # Expensive external requests run outside the lock; commit only if room is unchanged.
            if act=='generate':
                with LOCK:
                    r=load(d['id']);host(r,token)
                    if r['demo'] and not ALLOW_DEMO:raise ValueError('演示模式未启用')
                    if r['stage']!='lobby' or r['id'] in GENERATING:return self.send_json({'ok':True})
                    if not all_located(r):raise ValueError('请等待所有成员加入并完成定位后再开始')
                    r.pop('generation_error',None);save(r);snapshot=json.dumps(r,sort_keys=True);GENERATING.add(r['id'])
                try:
                    rs=candidates(r)
                    if not rs:raise ValueError('未找到候选餐厅，请重新创建或调整搜索范围')
                    with LOCK:
                        cur=load(r['id'])
                        if cur['stage']!='lobby' or not all_located(cur):raise ValueError('房间状态已变化，请重新生成')
                        stamp=datetime.now(timezone(timedelta(hours=8)))
                        for a in rs:a['hours_date']=stamp.date().isoformat()
                        cur['restaurants']=rs;cur['stage']='voting';cur['updated']=stamp.isoformat();cur.pop('generation_error',None);save(cur)
                except Exception as e:
                    with LOCK:
                        cur=load(r['id'])
                        if cur['stage']=='lobby':
                            cur['generation_error']=str(e) if isinstance(e,ValueError) else '餐厅查询失败，请检查地图服务后重试';save(cur)
                    raise
                finally:
                    with LOCK:GENERATING.discard(r['id'])
                return self.send_json({'ok':True})
            if act=='routes':
                with LOCK:
                    r=load(d['id']);m=require(r,token);job=(r['id'],m['id'])
                    missing=[a for a in r['restaurants'] if m['id'] not in a.get('routes',{})]
                    if not m['location'] or not missing or job in ROUTING:return self.send_json({'ok':True})
                    stamp=r.get('updated');ROUTING.add(job)
                try:
                    results={a['id']:geographic_distance(m,a) for a in missing}
                    with LOCK:
                        cur=load(r['id'])
                        if cur.get('updated')==stamp and cur['stage'] in ('voting','done'):
                            for a in cur['restaurants']:
                                if a['id'] in results:a.setdefault('routes',{})[m['id']]=results[a['id']]
                            save(cur)
                finally:
                    with LOCK:ROUTING.discard(job)
                return self.send_json({'ok':True})
            with LOCK:
                r=load(d['id']);m=find_member(r,token)
                if r['demo'] and not ALLOW_DEMO:raise ValueError('演示模式未启用')
                if act=='join':
                    if m:return self.send_json({'token':m['token']})
                    if r['stage']!='lobby' or len(r['members'])>=r['count']:raise ValueError('房间已满或选择已结束')
                    m=new_member('宾客 '+str(len(r['members'])));r['members'].append(m)
                    if r['demo']:
                        idx=r['members'].index(m);m['location']=[DEMO_CENTER[0]+.006*math.cos(idx*2.4),DEMO_CENTER[1]+.006*math.sin(idx*2.4)]
                    save(r);return self.send_json({'token':m['token']})
                m=require(r,token)
                if act=='location':
                    if r['id'] in GENERATING or r['stage']=='done' or (r['stage']=='voting' and ready(m)):raise ValueError('当前不能修改出发位置')
                    if r['demo']:
                        idx=r['members'].index(m);p=[DEMO_CENTER[0]+.006*math.cos(idx*2.4),DEMO_CENTER[1]+.006*math.sin(idx*2.4)]
                    else:
                        p=coord(d.get('location'));p=(tencent.convert(p) if r.get('provider') in ('tencent','hybrid') else convert(p)) if d.get('coordType')=='gps' else p
                    m.update(location=p,location_skipped=False,location_status='located')
                elif act=='location_status':
                    if r['stage']=='done' or ready(m):return self.send_json({'ok':True})
                    status=d.get('status')
                    if status not in ('locating','failed','denied'):raise ValueError('定位状态无效')
                    m['location_status']=status
                elif act=='skip_location':
                    raise ValueError('请先完成定位，不能跳过')
                elif act=='rename':
                    if r['stage']=='done' or m['id']==r['host']:raise ValueError('当前不能修改昵称')
                    name=str(d.get('name','')).strip()
                    if not 1<=len(name)<=24:raise ValueError('昵称需1–24字')
                    if any(x['id']!=m['id'] and x['name'].casefold()==name.casefold() for x in r['members']):raise ValueError('昵称已被房间内其他成员使用')
                    m['name']=name
                elif act=='verify_status':
                    host(r,token)
                    if r['stage']!='voting' or r['demo']:raise ValueError('当前不能核实营业状态')
                    a=next((a for a in r['restaurants'] if a['id']==d.get('restaurant')),None)
                    st=d.get('status')
                    if not a or st not in ('open','closed'):raise ValueError('餐厅或营业状态无效')
                    if st=='closed' and any(x['vote']==a['id'] for x in r['members']):raise ValueError('已有成员选择该餐厅，请重新生成餐厅再核实')
                    a.update(verified_status=st,verified_at=time.time())
                elif act=='verify_price':
                    host(r,token)
                    if r['stage']!='voting' or r['demo']:raise ValueError('当前不能补充人均价格')
                    a=next((a for a in r['restaurants'] if a['id']==d.get('restaurant')),None)
                    price=num(d.get('price'))
                    if not a or isinstance(d.get('price'),bool) or price is None or not 1<=price<=10000:raise ValueError('请输入 1–10000 元的有效人均价格')
                    a.update(price=round(price,2),price_source='host')
                elif act=='vote':
                    if r['stage']!='voting':raise ValueError('当前不能选择餐厅')
                    if not ready(m):raise ValueError('请先完成定位授权')
                    a=next((a for a in r['restaurants'] if a['id']==d.get('restaurant')),None)
                    if not a:raise ValueError('餐厅不存在')
                    st=restaurant_status(r,a)
                    if st!='open':raise ValueError('餐厅未确认营业，不能选择')
                    m['vote']=a['id']
                    if len(r['members'])==r['count'] and all(x['vote'] for x in r['members']):
                        r['stage']='done';r['finish_reason']='all_voted'
                elif act=='finish':
                    host(r,token)
                    if r['stage']=='done':return self.send_json({'ok':True})
                    if r['stage']!='voting':raise ValueError('当前不能结束投票')
                    if not any(x['vote'] is not None for x in r['members']):raise ValueError('至少需要一票才能提前结束')
                    r['stage']='done';r['finish_reason']='early'
                elif act=='reset':
                    host(r,token);
                    if r['id'] in GENERATING:raise ValueError('正在搜索，请稍后重试')
                    r['stage']='lobby';r['restaurants']=[];r.pop('generation_error',None);r.pop('finish_reason',None)
                    for x in r['members']:x['vote']=None
                else:raise ValueError('未知操作')
                save(r)
            self.send_json({'ok':True})
        except (ValueError,KeyError,TypeError) as e:self.send_json({'error':str(e)},400)
        except Exception as e:print(type(e).__name__);self.send_json({'error':'请求失败，请检查网络及 API 配置'},502)
if __name__=='__main__':
    port=int(os.getenv('PORT','8000'));print(f'约饭已启动：http://localhost:{port}（Ctrl+C 停止）',flush=True);print('地图数据源：'+provider(),flush=True);ThreadingHTTPServer((os.getenv('BIND_HOST','127.0.0.1'),port),Handler).serve_forever()
