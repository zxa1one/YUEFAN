import unittest
from datetime import datetime, timezone,timedelta
from unittest.mock import patch
import server,amap_restaurants,commercial

def poi(id='one',name='测试火锅',location='114.3,35.7'):
    return {'id':id,'name':name,'location':location,'address':'测试路1号','type':'餐饮服务;中餐厅;火锅店','typecode':'050117','business':{'rating':'4.6','cost':'59','opentime_today':'10:00-14:00 17:30-22:30','tel':'0392-1234567'},'photos':[{'url':'http://store.is.autonavi.com/showpic/abc'}]}

class HybridTests(unittest.TestCase):
    def test_provider(self):
        with patch.object(server,'KEY','test'),patch('tencent.configured',return_value=True): self.assertEqual(server.provider(),'hybrid')
    def test_parse(self):
        row=amap_restaurants.parse(poi(),[114.3,35.7],20000,{})
        self.assertEqual(row['rating'],4.6);self.assertEqual(row['price'],59);self.assertIsNone(row['sales']);self.assertEqual(row['hours'],'10:00-14:00 17:30-22:30');self.assertTrue(row['photos'][0].startswith('https://'))
        self.assertIsNone(amap_restaurants.parse(poi(location='115.3,35.7'),[114.3,35.7],20000,{}))
        self.assertIsNone(amap_restaurants.parse(poi(name='永久停业火锅'),[114.3,35.7],20000,{}))
    def test_hybrid_distance_without_route_request(self):
        r={'demo':False,'provider':'hybrid','radius':20000,'budget':60,'members':[{'id':'a','location':[114.3,35.7],'mode':'walk'}]}
        with patch('server.amap',return_value={'pois':[poi()]}),patch('tencent.search',side_effect=AssertionError('wrong candidate provider')),patch('tencent.route',return_value={'km':2,'minutes':25,'source':'腾讯路线规划'}) as route:
            rows=server.candidates(r)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['routes']['a']['km'],0);self.assertNotIn('minutes',rows[0]['routes']['a']);route.assert_not_called()
    def test_pagination_radius(self):
        calls=[]
        def req(path,args):
            calls.append(args)
            return {'pois':[poi(str(i)) for i in range(25)] if args['page_num']==1 else [poi('last')]}
        result=amap_restaurants.search(req,[114.3,35.7],20000,60,lambda a:'open')
        self.assertEqual(len(result),26);self.assertTrue(any(x['page_num']==2 for x in calls));self.assertTrue(all(x['radius']==20000 for x in calls))
    def test_commercial_data(self):
        now=datetime.now(timezone.utc);future=(now+timedelta(days=1)).isoformat();past=(now-timedelta(days=1)).isoformat()
        extra={'name':'测试火锅','address':'测试路1号','monthly_sales':{'value':234,'metric':'restaurant_monthly_sales','source':'测试授权数据','as_of':past},'douyin':{'url':'https://v.douyin.com/example','expires_at':future},'meituan':{'url':'https://www.meituan.com/example','expires_at':past}}
        row=amap_restaurants.parse(poi(),[114.3,35.7],20000,{'amap:one':extra})
        self.assertEqual(row['sales'],234);self.assertIn('douyin_deal_url',row);self.assertNotIn('meituan_deal_url',row)
        extra['monthly_sales']['metric']='deal_total';self.assertIsNone(amap_restaurants.parse(poi(),[114.3,35.7],20000,{'amap:one':extra})['sales'])
        extra['address']='不同地址';self.assertNotIn('douyin_deal_url',amap_restaurants.parse(poi(),[114.3,35.7],20000,{'amap:one':extra}))
    def test_status(self):
        row=amap_restaurants.parse(poi(),[114.3,35.7],20000,{})
        with patch('server.status_today',return_value='open') as f:
            self.assertEqual(server.restaurant_status({'demo':False,'provider':'hybrid'},row),'open');f.assert_called_once_with(row['hours'])
