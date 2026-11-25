import unittest
from algorithm import rank
from datetime import datetime,timezone,timedelta
from commercial import merge,expire

def row(id,rating=4.5,km=1,counts=None,source='test',status='open'):
    return dict(id=id,name=id,address='test',rating=rating,status=status,price=50,routes={'m':{'km':km}},popularity_counts=counts or {},popularity_source=source)
M=[{'id':'m','vote':None}]
class PopularityTests(unittest.TestCase):
    def test_weights(self):
        r,w=rank([row('a',4.9,3,{'comments':1}),row('b',4.8,1,{'comments':999999})],M)
        self.assertAlmostEqual(sum(w.values()),1)
        self.assertAlmostEqual(w['rating'],48.89/51.11)
        self.assertNotIn('popularity',w)
        self.assertTrue(all('popularity_counts' not in x for x in r))
    def test_missing_rating_does_not_disable_all(self):
        r,w=rank([row('a',4.9,3),row('b',4.0,1),row('missing',None,.1)],M)
        self.assertIn('rating',w);self.assertIsNone(r[-1]['score']);self.assertAlmostEqual(w['rating'],48.89/51.11)
    def test_distance_only_when_rating_missing(self):
        r,w=rank([row('a',None,2),row('b',None,1)],M)
        self.assertEqual(w,{'distance':1});self.assertEqual(r[0]['id'],'b')
    def test_verified_and_expiry(self):
        now=datetime.now(timezone.utc);a=row('a');a.pop('popularity_counts');a.pop('popularity_source')
        d={'name':'a','address':'test','popularity':{'source':'test','counts':{'comments':12,'deals':-1,'favorites':True},'as_of':now.isoformat()}}
        merge(a,{'amap:a':d},'amap');self.assertEqual(a['popularity_counts'],{'comments':12})
        a['popularity_as_of']=(now-timedelta(days=32)).isoformat();expire(a);self.assertNotIn('popularity_counts',a)
    def test_open_first(self):
        r,_=rank([row('a',5,1,status='closed'),row('b',3,5)],M,'composite');self.assertEqual(r[0]['id'],'b')
    def test_rank_before_cutoff(self):
        import amap_restaurants
        from test_hybrid import poi
        a=poi('a','测试火锅A','114.31,35.7');b=poi('b','测试火锅B','114.301,35.7')
        a['business']['rating']='4.9';b['business']['rating']='4.8'
        result=amap_restaurants.search(lambda path,args:{'pois':[a,b]},[114.3,35.7],20000,59,lambda a:'open',limit=1,members=[{'id':'m','location':[114.3,35.7]}])
        self.assertEqual(result[0]['id'],'b')
    def test_existing_room_refreshes_links(self):
        import server
        from unittest.mock import patch
        now=datetime.now(timezone.utc)
        a=row('a');a.update(location=[114.3,35.7],hours='全天营业',hours_date=datetime.now(timezone(timedelta(hours=8))).date().isoformat())
        a['meituan_deal_url']='https://www.meituan.com/old'
        room={'id':'r','title':'r','count':2,'radius':20000,'provider':'hybrid','demo':False,'stage':'voting','host':'m','members':[{'id':'m','token':'token','name':'m','location':[114.3,35.7],'vote':None}],'restaurants':[a]}
        records={'amap:a':{'name':'a','address':'test','douyin':{'url':'https://v.douyin.com/example','expires_at':(now+timedelta(days=1)).isoformat()}}}
        with patch('commercial.catalog',return_value=records):
            out=server.public(room,'token')['restaurants'][0]
        self.assertNotIn('meituan_deal_url',out);self.assertEqual(out['douyin_deal_url'],'https://v.douyin.com/example')
