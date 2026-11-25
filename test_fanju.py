import unittest, subprocess, sys, tempfile, os, json, time, socket
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from algorithm import distance_cost,rank
from server import status_today
from unittest.mock import patch
import server
from datetime import datetime
class Tests(unittest.TestCase):
    def test_distance(self):self.assertAlmostEqual(distance_cost([1,2,3,4]),2.95)
    def test_budget_priority(self):
        rs=[dict(id=i,status=st,price=p,rating=rating,sales=100,popularity_source='test',popularity_counts={'comments':100},routes={'m':{'km':1}}) for i,st,p,rating in [('far','open',150,5),('near','open',80,4),('boundary','open',96,4.5),('unknown','open',None,5),('closed','closed',80,5),('close_out','open',100,4)]]
        members=[{'id':'m','vote':'far'}]
        ordered,w=rank(rs,members,'composite',80)
        self.assertEqual([r['id'] for r in ordered],['boundary','near','close_out','far','unknown','closed'])
        self.assertEqual(ordered[0]['budgetMatch'],'near');self.assertEqual(ordered[4]['budgetMatch'],'unknown')
        scores={r['id']:r['score'] for r in ordered}
        ordered,_=rank(rs,members,'price_desc',80)
        self.assertEqual(ordered[0]['id'],'far')
        self.assertEqual(scores,{r['id']:r['score'] for r in ordered})
        ordered,_=rank(rs,members,'results',80)
        self.assertEqual(ordered[0]['id'],'far')
        self.assertEqual(w,{'rating':48.89/51.11,'distance':2.22/51.11})
    def test_final_order_votes_then_name(self):
        rows=[dict(id=i,name=n,status=st,rating=rating,routes={}) for i,n,st,rating in [('z','Zebra','open',5),('s','山野火锅','open',5),('a','Apple','closed',1),('l','老街川菜馆','unknown',2),('b','banana','closed',1),('q','四季烤肉','open',5)]]
        votes=[{'id':str(i),'vote':v} for i,v in enumerate(['z','z','q','s','a','b','l'])]
        ordered,_=rank(rows,votes,'results');self.assertEqual([r['id'] for r in ordered],['z','a','b','l','s','q'])
    def test_hours(self):
        self.assertEqual(status_today('09:00-13:00 17:00-22:00',datetime(2026,11,24,14,0)),'closed')
        self.assertEqual(status_today('22:00-02:00',datetime(2026,11,24,1,0)),'open')
        self.assertEqual(status_today('',datetime(2026,11,24,1,0)),'unknown')
    def test_missing(self):
        r=[dict(id='a',status='open',rating=4,price=10,sales=None,routes={'m':{'km':1}}),dict(id='b',status='open',rating=5,price=20,sales=300,routes={'m':{'km':2}})]
        _,w=rank(r,[{'id':'m','vote':None}]);self.assertNotIn('popularity',w);self.assertAlmostEqual(sum(w.values()),1)
    def test_live_provider_contract(self):
        def provider(path,params):
            if path=='v5/place/around':
                self.assertEqual(params['show_fields'],'business,photos')
                return {'pois':[{'id':'x','name':'测试餐厅','type':'餐饮服务;中餐厅','typecode':'050101','location':'116.4,39.91','citycode':'010','business':{'rating':'4.8','cost':'52','opentime_today':'全天营业'}},{'id':'closed','name':'永久停业餐厅','type':'餐饮服务;中餐厅','typecode':'050101','location':'116.4,39.91','business':{}}]}
            if path=='v5/direction/walking':
                self.assertEqual(params['show_fields'],'cost')
                return {'route':{'paths':[{'distance':'1200','cost':{'duration':'601'}}]}}
            raise AssertionError(path)
        room={'demo':False,'radius':3000,'members':[{'id':'a','location':[116.39,39.9],'mode':'walk'}]}
        with patch('server.amap',side_effect=provider):
            rows=server.candidates(room)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['rating'],4.8);self.assertEqual(rows[0]['price'],52);self.assertIsNone(rows[0].get('sales'));self.assertEqual(rows[0]['status'],'open');self.assertAlmostEqual(rows[0]['routes']['a']['km'],1.4,places=2);self.assertNotIn('minutes',rows[0]['routes']['a'])
    def test_live_route_failure(self):
        with patch('server.amap',return_value={'route':{'paths':[{'distance':'500','cost':None}]}}):
            r=server.live_route({'location':[116.39,39.9],'mode':'walk'},{'location':[116.4,39.91]})
        self.assertEqual(r['km'],.5);self.assertIsNone(r['minutes'])
        self.assertEqual(status_today('今日休息 09:00-22:00'),'closed')
    def test_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            p=subprocess.Popen([sys.executable,'server.py'],env={**os.environ,'YUEFAN_ALLOW_DEMO':'1','PORT':str(port),'FANJU_DB':os.path.join(tmp,'rooms.db')},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            base=f'http://127.0.0.1:{port}'
            def api(path,body=None,token=None,account=None):
                req=Request(base+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json',**({'X-Member-Token':token} if token else {}),**({'X-Account-Token':account} if account else {})})
                with urlopen(req,timeout=5) as f:return json.load(f)
            try:
                for _ in range(50):
                    try:api('config');break
                    except Exception:time.sleep(.1)
                with self.assertRaises(HTTPError):api('create',{'count':4,'demo':True})
                acc=api('register',{'name':'King A','password':'test-password-1'})
                with self.assertRaises(HTTPError):api('register',{'name':'King A','password':'test-password-1'})
                with self.assertRaises(HTTPError):api('login',{'name':'King A','password':'wrong-password'})
                login=api('login',{'name':'King A','password':'test-password-1'})
                self.assertEqual(api('config',account=login['token'])['account'],'King A')
                with self.assertRaises(HTTPError):api('create',{'count':4,'demo':True,'budget':-1},account=login['token'])
                a=api('create',{'count':4,'demo':True,'budget':80},account=login['token']);rid=a['id'];tokens=[a['token']]
                self.assertEqual(api('room?id='+rid,token=tokens[0])['budget'],80)
                for n in 'BCD':tokens.append(api('join',{'id':rid,'name':n})['token'])
                with self.assertRaises(HTTPError):api('join',{'id':rid,'name':'E'})
                for t,mode in zip(tokens,['walk','bike','drive','transit']):api('location',{'id':rid,'mode':mode},t)
                with self.assertRaises(HTTPError):api('generate',{'id':rid},tokens[1])
                api('generate',{'id':rid},tokens[0])
                for sort in ['composite','price_asc','price_desc','distance_asc','distance_desc','rating']:
                    s=api('room?id='+rid+'&sort='+sort,token=tokens[0]);rs=s['restaurants'];self.assertEqual(rs[-1]['status'],'closed');self.assertEqual(rs[-2]['status'],'unknown');self.assertEqual(len(rs[0]['routes']),4);self.assertNotIn('votes',rs[0]);self.assertNotIn('location',s['members'][0]);self.assertNotIn('token',s['members'][0]);self.assertEqual(s['budget'],80);self.assertIn('budgetMatch',rs[0])
                self.assertFalse(api('room?id='+rid)['restaurants']);self.assertFalse(api('room?id='+rid)['members'])
                with self.assertRaises(HTTPError):api('vote',{'id':rid,'restaurant':'demo-3'},tokens[0])
                api('vote',{'id':rid,'restaurant':'demo-1'},tokens[0])
                for t,id in zip(tokens,['demo-0','demo-1','demo-0','demo-0']):api('vote',{'id':rid,'restaurant':id},t)
                s=api('room?id='+rid+'&sort=results',token=tokens[0]);self.assertEqual(s['stage'],'done');self.assertEqual(s['restaurants'][0]['id'],'demo-0');self.assertEqual(s['restaurants'][0]['votes'],3);self.assertEqual(sum(r['votes'] for r in s['restaurants']),4)
                with self.assertRaises(HTTPError):api('vote',{'id':rid,'restaurant':'demo-1'},tokens[0])
                api('reset',{'id':rid},tokens[0]);self.assertEqual(api('room?id='+rid,token=tokens[0])['stage'],'lobby')
                # Start waits for all planned participants.
                b=api('create',{'count':3,'demo':True},account=login['token']);rid=b['id'];h=b['token']
                with self.assertRaises(HTTPError):api('generate',{'id':rid},h)
                g=api('join',{'id':rid})['token']
                with self.assertRaises(HTTPError):api('generate',{'id':rid},h)
                j=api('join',{'id':rid})['token'];api('generate',{'id':rid},h)
                s=api('room?id='+rid,token=g);self.assertFalse(s['routesPending']);self.assertEqual(len(s['restaurants'][0]['routes']),3)
                api('vote',{'id':rid,'restaurant':'demo-0'},h)
                api('vote',{'id':rid,'restaurant':'demo-1'},g)
                api('vote',{'id':rid,'restaurant':'demo-0'},j)
                s=api('room?id='+rid+'&sort=results',token=h);self.assertEqual(s['stage'],'done');self.assertEqual(s['restaurants'][0]['votes'],2);self.assertEqual(len(s['restaurants'][0]['routes']),3)
                with self.assertRaises(HTTPError):api('join',{'id':rid})

                # Two independent client tokens, no guest registration, tie and final sync.
                pair=api('create',{'count':2,'demo':True,'budget':60},account=login['token']);rid=pair['id'];h=pair['token']
                g=api('join',{'id':rid})['token'];self.assertNotEqual(g,h)
                api('rename',{'id':rid,'name':'小明'},g)
                with self.assertRaises(HTTPError):api('rename',{'id':rid,'name':'King A'},g)
                api('generate',{'id':rid},h)
                api('vote',{'id':rid,'restaurant':'demo-1'},h)
                pending=api('room?id='+rid+'&sort=results',token=g)
                self.assertEqual(pending['stage'],'voting')
                self.assertTrue(all('votes' not in r and 'voters' not in r for r in pending['restaurants']))
                self.assertEqual([r['id'] for r in pending['restaurants']],[r['id'] for r in api('room?id='+rid,token=g)['restaurants']])
                api('vote',{'id':rid,'restaurant':'demo-0'},g)
                finals=[]
                for t in (h,g):
                    final=api('room?id='+rid+'&sort=price_desc',token=t)
                    self.assertEqual(final['stage'],'done');self.assertEqual(final['restaurants'][0]['votes'],1)
                    self.assertEqual([r['id'] for r in final['restaurants'][:2]],['demo-0','demo-1'])
                    self.assertEqual(final['restaurants'][0]['voters'],[{'id':next(m['id'] for m in final['members'] if m['name']=='小明'),'name':'小明'}])
                    self.assertEqual(final['restaurants'][1]['voters'][0]['name'],'King A')
                    self.assertNotIn('popularity',final['weights']);self.assertNotIn('sales',final['restaurants'][0]);finals.append(final['restaurants'])
                self.assertEqual(finals[0],finals[1])
                with self.assertRaises(HTTPError):api('rename',{'id':rid,'name':'New'},g)
                self.assertFalse(api('room?id='+rid)['restaurants']);self.assertFalse(api('room?id='+rid)['members'])
            finally:p.terminate();p.wait(timeout=5)
if __name__=='__main__':unittest.main(verbosity=2)
