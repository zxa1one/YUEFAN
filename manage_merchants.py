"""Local operator tool: attach verified branch-specific commercial data, not a crawler."""
import json, sqlite3, os
from pathlib import Path
from datetime import datetime,timezone,timedelta
from tencent import deal_url
BASE=Path(__file__).resolve().parent

def main():
    db=Path(os.getenv('FANJU_DB',str(BASE/'rooms.sqlite3')))
    if not db.is_file():return print('请先启动网站并生成一个真实餐厅列表。')
    with sqlite3.connect(db) as c:
        rooms=c.execute('SELECT body FROM rooms ORDER BY rowid DESC').fetchall()
    rows={}
    for (body,) in rooms:
        r=json.loads(body)
        if r.get('demo') or r.get('provider') not in ('amap','hybrid'):continue
        for a in r.get('restaurants',[]):rows.setdefault(a['id'],a)
    if not rows:return print('暂无高德真实餐厅，请先创建房间并搜索。')
    term=input('输入餐厅名称关键词：').strip()
    options=[a for a in rows.values() if term in a['name']]
    if not options:return print('未找到匹配餐厅。')
    for i,a in enumerate(options,1):print(f"{i}. {a['name']} | {a['address']}")
    try:
        n=int(input('选择编号：'));assert 1<=n<=len(options);a=options[n-1]
    except (ValueError,AssertionError):return print('编号无效。')
    path=BASE/'verified_merchants.json'; data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    k='amap:'+a['id']; extra=data.get(k,{})
    if extra.get('name')!=a['name'] or extra.get('address')!=a['address']:extra={'name':a['name'],'address':a['address']}
    print('只录入已核实、获准使用的本分店团购链接及真实统计。空白保留现有值。')
    for platform,label in [('meituan','美团'),('douyin','抖音')]:
        url=input(label+'团购链接（- 删除）：').strip()
        if url=='-':extra.pop(platform,None);continue
        if not url:continue
        if not deal_url(url,platform):print('仅接受对应平台 HTTPS 链接，未保存。');continue
        expiry=input('实际有效截止日期 YYYY-MM-DD（北京时间，当天结束）：').strip()
        try:
            end=datetime.strptime(expiry,'%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=8)))+timedelta(days=1)
            if end<=datetime.now(timezone.utc):raise ValueError()
        except ValueError:print('日期无效或已过期，未保存。');continue
        extra[platform]={'url':url,'expires_at':end.isoformat()}
    source=input('人气统计来源（例如获授权的同一平台；回车跳过）：').strip()
    if source:
        counts={}
        for field,label in [('comments','评论数'),('favorites','收藏数'),('checkins','签到数'),('deals','在售团购商品数')]:
            v=input(label+'（未知留空）：').strip()
            if v:
                if not v.isdecimal():return print('数量须为非负整数，未保存本次修改。')
                counts[field]=int(v)
        if counts:extra['popularity']={'source':source,'counts':counts,'as_of':datetime.now(timezone.utc).isoformat()}
    data[k]=extra
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)
    print('保存完成。刷新网页即可加载更新（已有房间无需重新选餐）。')
if __name__=='__main__':main()
