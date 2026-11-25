import unittest,hashlib,time
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
import tencent,server
class TencentTests(unittest.TestCase):
    def test_signature(self):
        url=tencent.signed_url('/ws/place/v1/search',{'keyword':'美食','boundary':'nearby(39,116,1000,0)'},'TESTKEY','TESTSK')
        q=parse_qs(urlsplit(url).query)
        expected=hashlib.md5('/ws/place/v1/search?boundary=nearby(39,116,1000,0)&key=TESTKEY&keyword=美食TESTSK'.encode()).hexdigest()
        self.assertEqual(q['sig'],[expected]);self.assertNotIn('TESTSK',url)
    def test_coordinates(self):
        with patch('tencent.request',return_value={'locations':[{'lat':39.9,'lng':116.4}]}) as f:
            self.assertEqual(tencent.convert([116.39,39.89]),[116.4,39.9]);self.assertEqual(f.call_args.args[1],{'locations':'39.890000,116.390000','type':1})
    def test_provider(self):
        def fake(path,params):
            if path=='/ws/place/v1/search':
                self.assertTrue(params['boundary'].startswith(('nearby(','rectangle(')))
                return {'data':[{'id':'a','title':'测试餐厅','category':'美食:中餐厅','location':{'lat':39.901,'lng':116.401},'tel':'123'},{'id':'b','title':'永久停业餐厅','location':{'lat':39.901,'lng':116.401}}]}
            if path=='/ws/direction/v1/walking/':return {'result':{'routes':[{'distance':1200,'duration':17}]}}
            raise AssertionError(path)
        r={'provider':'tencent','demo':False,'radius':3000,'members':[{'id':'m','location':[116.4,39.9],'mode':'walk'}]}
        with patch('tencent.request',side_effect=fake):rows=server.candidates(r)
        self.assertEqual(len(rows),1);a=rows[0];self.assertEqual(a['status'],'unknown');self.assertIsNone(a['sales']);self.assertIsNone(a['rating']);self.assertNotIn('minutes',a['routes']['m']);self.assertAlmostEqual(a['routes']['m']['km'],.14,places=2)
    def test_search_pages_and_radius(self):
        calls=[]
        def fake(path,params):
            calls.append(params)
            if params['page_index']==1:
                return {'count':21,'data':[{'id':str(i),'title':'餐厅'+str(i),'category':'美食:中餐厅','location':{'lat':39.901,'lng':116.401}} for i in range(20)]}
            return {'count':21,'data':[{'id':'far','title':'远处餐厅','category':'美食','location':{'lat':39.916,'lng':116.4}}]}
        with patch('tencent.request',side_effect=fake):rows=tencent.search([116.4,39.9],3000)
        self.assertEqual(len(rows),21)
        self.assertTrue(any(c['page_index']==2 for c in calls))
        self.assertTrue(any(c['boundary'].startswith('rectangle(') for c in calls))
        self.assertTrue(all('orderby' not in c for c in calls))
    def test_dining_20km_and_exclusions(self):
        calls=[]
        def fake(path,params):
            calls.append(params)
            def poi(id,name,cat,lat):
                return {'id':id,'title':name,'category':cat,'location':{'lat':lat,'lng':116.4}}
            return {'data':[poi('a','聚餐火锅','美食:火锅',40.05),poi('b','超范围餐厅','美食:中餐厅',40.09),poi('c','大学食堂','美食:餐厅',39.9),poi('d','某奶茶','美食:饮品',39.9),poi('e','某面馆','美食:快餐',39.9),poi('f','某自助餐','美食:自助餐',39.9)]}
        with patch('tencent.request',side_effect=fake):rows=tencent.search([116.4,39.9],20000)
        self.assertEqual({r['id'] for r in rows},{'a','e','f'})
        self.assertGreater(len({c['boundary'] for c in calls}),4)
        self.assertIn('烤肉',{c['keyword'] for c in calls})
        self.assertTrue(all(r['rating'] is None and r['sales'] is None and r['status']=='unknown' for r in rows))
    def test_partial_search(self):
        def fake(path,params):
            if params['keyword']=='火锅':raise ValueError('连接失败')
            return {'data':[{'id':'a','title':'某餐厅','category':'美食:中餐厅','location':{'lat':39.9,'lng':116.4}}]}
        with patch('tencent.request',side_effect=fake):rows=tencent.search([116.4,39.9],20000)
        self.assertTrue(rows[0]['searchPartial'])
    def test_quota_error_visible(self):
        with patch('tencent.request',side_effect=ValueError('腾讯地图 121：每日配额已用尽')):
            with self.assertRaisesRegex(ValueError,'121'):tencent.search([116.4,39.9],20000)
    def test_verification_expiry(self):
        r={'demo':False,'provider':'tencent'}
        self.assertEqual(server.restaurant_status(r,{}),'unknown');self.assertEqual(server.restaurant_status(r,{'verified_at':time.time(),'verified_status':'open'}),'open');self.assertEqual(server.restaurant_status(r,{'verified_at':time.time()-7300,'verified_status':'open'}),'unknown')
    def test_no_route(self):
        with patch('tencent.request',return_value={'result':{'routes':[]}}):
            with self.assertRaises(ValueError):tencent.route({'mode':'walk','location':[116,39]},{'location':[116,39]})
if __name__=='__main__':unittest.main()
