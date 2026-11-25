"""Configure a local Web Service key without exposing it in browser or chat."""
from getpass import getpass
from pathlib import Path
import server

def main():
    key=getpass('粘贴高德 Web 服务 Key（输入不显示），回车：').strip()
    if not key or any(c.isspace() for c in key):raise ValueError('Key 不能为空或包含空格')
    server.KEY=key
    print('正在测试鹤壁餐厅商业数据…',flush=True)
    rows=server.amap('v5/place/text',{'keywords':'火锅','region':'鹤壁市','city_limit':'true','show_fields':'business,photos','page_size':25,'page_num':1}).get('pois') or []
    if not rows:raise ValueError('测试区域未返回餐厅，请检查服务权限')
    path=Path(__file__).resolve().parent/'.amap_key'
    import os
    fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:f.write(key+'\n')
    os.chmod(path,0o600)
    print('验证成功，已在本地保存 Key。请运行 python3 server.py。')
    print('返回餐厅：'+str(len(rows))+' 家；有评分：'+str(sum(bool((p.get('business') or {}).get('rating')) for p in rows if isinstance(p.get('business'),dict))))

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print('配置失败：'+str(e));raise SystemExit(1)
    except KeyboardInterrupt:print('\n已取消');raise SystemExit(1)
