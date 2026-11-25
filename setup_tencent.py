from getpass import getpass
import json,os
import tencent

def main():
    key=input('请粘贴腾讯地图 API Key（明文显示），回车：').strip()
    sk=input('请粘贴腾讯地图 SK（明文显示），回车：').strip()
    if not key or not sk or any(c.isspace() for c in key+sk):raise ValueError('Key / SK 不能为空或包含空格')
    tencent.KEY,tencent.SK=key,sk
    print('正在检查签名、坐标转换、餐厅搜索、步行路线…',flush=True)
    center=tencent.convert([116.397,39.908])
    rows=tencent.search(center,1000)
    if not rows:raise ValueError('测试位置附近未返回餐厅，请检查搜索权限')
    route=tencent.route({'location':center,'mode':'walk'},rows[0])
    if route['km'] is None or route['minutes'] is None:raise ValueError('路线返回不完整')
    tmp=tencent.FILE.with_suffix('.json.tmp')
    fd=os.open(str(tmp),os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'key':key,'sk':sk},f)
    os.chmod(tmp,0o600);os.replace(tmp,tencent.FILE)
    print('腾讯地图接口验证成功！密钥已保存在本地，不要上传或提交 Git。')
    print('测试餐厅：'+rows[0]['name']+'；步行距离：'+str(route['km'])+' km；预计 '+str(route['minutes'])+' 分钟')
    print('请运行 python3 server.py')
if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:print('配置失败：'+str(e));raise SystemExit(1)
    except KeyboardInterrupt:print('\n已取消');raise SystemExit(1)
