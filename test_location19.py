import json,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import server

class LocationGate(unittest.TestCase):
    def test_real_mode_location_gate(self):
        # Mock map provider only; real room HTTP handlers, SQLite and readiness logic.
        with tempfile.TemporaryDirectory() as tmp, patch.object(server,'DB',Path(tmp)/'test.db'), patch.object(server,'provider',return_value='amap'), patch.object(server,'convert',side_effect=lambda p:p), patch.object(server,'candidates',return_value=[{'id':'a','name':'A','rating':4.8,'price':60,'status':'open','location':[114.3,35.7],'routes':{}}]) as candidates:
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
            def api(path,body=None,token=None,account=None):
                headers={'Content-Type':'application/json'}
                if token:headers['X-Member-Token']=token
                if account:headers['X-Account-Token']=account
                with urlopen(Request(f'http://127.0.0.1:{http.server_port}/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5) as f:return json.load(f)
            try:
                acc=api('register',{'name':'Host','password':'test-password'})['token']
                r=api('create',{'count':3,'demo':False,'location':[114.3,35.7],'coordType':'gps'},account=acc);d={'id':r['id']};h=r['token'];path='room?id='+r['id']
                with self.assertRaises(HTTPError):api('generate',d,h)
                g=api('join',d)['token'];j=api('join',d)['token']
                api('location_status',{**d,'status':'locating'},g)
                self.assertEqual(api(path,token=h)['members'][1]['locationStatus'],'locating')
                with self.assertRaises(HTTPError):api('generate',d,h)
                api('location_status',{**d,'status':'denied'},g)
                self.assertEqual(api(path,token=h)['members'][1]['locationStatus'],'denied')
                with self.assertRaises(HTTPError):api('skip_location',d,g)
                with self.assertRaises(HTTPError):api('location',{**d,'location':[500,35]},g)
                with self.assertRaises(HTTPError):api('generate',d,h)
                api('location',{**d,'location':[114.31,35.7],'coordType':'gps'},g)
                api('location_status',{**d,'status':'failed'},g)
                self.assertEqual(api(path,token=h)['members'][1]['locationStatus'],'located')
                with self.assertRaises(HTTPError):api('generate',d,h)
                self.assertEqual(candidates.call_count,0)
                api('location',{**d,'location':[114.32,35.7],'coordType':'gps'},j)
                self.assertTrue(all(m['located'] for m in api(path,token=h)['members']))
                with self.assertRaises(HTTPError):api('generate',d,g)
                api('generate',d,h);self.assertEqual(candidates.call_count,1)
                for t in (h,g,j):self.assertEqual(api(path,token=t)['stage'],'voting')
                self.assertNotIn('location',api(path,token=h)['members'][1])
            finally:http.shutdown();http.server_close();worker.join()
