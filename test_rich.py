import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import tencent,server
class RichTests(unittest.TestCase):
    def test_rich_and_verified_links(self):
        p={'id':'x','title':'测试火锅','rich':{'star_level':'4.8','avg_price':'68','opening_hours':'全天营业'},'tel':'12345678'}
        catalog={'x':{'name':'测试火锅','douyin_deal_url':'https://www.douyin.com/example','meituan_deal_url':'https://not-meituan.com/example'}}
        a=tencent.enrich(p,[116,39],'美食:火锅',catalog)
        self.assertEqual(a['rating'],4.8);self.assertEqual(a['price'],68);self.assertIsNone(a['sales']);self.assertIsNone(a['meituan_deal_url'])
        self.assertTrue(a['douyin_deal_url'].startswith('https://www.douyin.com/'))
        a['hours_date']=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        self.assertEqual(server.restaurant_status({'demo':False,'provider':'tencent'},a),'open')
        a['hours']='周一至周五 10:00-22:00';self.assertEqual(server.restaurant_status({'demo':False,'provider':'tencent'},a),'unknown')
    def test_rich_permission_fallback(self):
        with patch.object(tencent,'RICH_UNAVAILABLE',False),patch('tencent.request',side_effect=[ValueError('腾讯地图 113：接口未授权'),{'data':[]}]) as f:
            self.assertEqual(tencent.search_page({'keyword':'火锅'}),{'data':[]});self.assertIn('get_rich',f.call_args_list[0].args[1]);self.assertNotIn('get_rich',f.call_args_list[1].args[1])
    def test_rating_before_candidate_cutoff(self):
        def fake(path,params):
            return {'data':[{'id':'a','title':'普通火锅','category':'美食:火锅','location':{'lat':39.9,'lng':116.4}}, {'id':'b','title':'评分火锅','category':'美食:火锅','location':{'lat':39.91,'lng':116.4},'star_level':4.9}]}
        with patch('tencent.request',side_effect=fake):
            rows=tencent.search([116.4,39.9],3000,1)
        self.assertEqual(rows[0]['id'],'b')
