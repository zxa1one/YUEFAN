import concurrent.futures,json,tempfile,threading,unittest
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from unittest.mock import patch
import server

class EarlyFinishTests(unittest.TestCase):
    def test_early_finish_and_member_states(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server,'DB',Path(tmp)/'test.db'), patch.object(server,'ALLOW_DEMO',True):
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            worker=threading.Thread(target=http.serve_forever,daemon=True);worker.start()
            def api(path,body=None,token=None,account=None):
                headers={'Content-Type':'application/json'}
                if token:headers['X-Member-Token']=token
                if account:headers['X-Account-Token']=account
                with urlopen(Request(f'http://127.0.0.1:{http.server_port}/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers),timeout=5) as f:return json.load(f)
            try:
                acc=api('register',{'name':'Host','password':'test-password'})['token']
                def room(count=6):
                    a=api('create',{'count':count,'demo':True},account=acc);return a['id'],a['token']
                rid,h=room(3);d={'id':rid};g=api('join',d)['token'];g2=api('join',d)['token'];api('rename',{**d,'name':'小王'},g)
                with self.assertRaises(HTTPError):api('finish',d,h)
                api('generate',d,h)
                with self.assertRaises(HTTPError):api('finish',d,h)
                api('vote',{**d,'restaurant':'demo-0'},h)
                s=api('room?id='+rid,token=g);self.assertEqual(s['stage'],'voting');self.assertEqual(len(s['members']),3);self.assertEqual(sum(m['submitted'] for m in s['members']),1);self.assertEqual(s['members'][1]['name'],'小王');self.assertNotIn('votes',s['restaurants'][0]);self.assertNotIn('voters',s['restaurants'][0]);self.assertIsNone(s['finishReason'])
                with self.assertRaises(HTTPError):api('finish',d,g)
                api('vote',{**d,'restaurant':'demo-1'},g);api('finish',d,h)
                for t in [h,g,g2]:
                    s=api('room?id='+rid,token=t);self.assertEqual(s['stage'],'done');self.assertEqual(s['finishReason'],'early');self.assertEqual(sum(a['votes'] for a in s['restaurants']),2);self.assertEqual(sum(len(a['voters']) for a in s['restaurants']),2)
                with self.assertRaises(HTTPError):api('vote',{**d,'restaurant':'demo-0'},g2)
                with self.assertRaises(HTTPError):api('vote',{**d,'restaurant':'demo-1'},h)
                with self.assertRaises(HTTPError):api('join',d)
                api('finish',d,h);api('reset',d,h);self.assertIsNone(api('room?id='+rid,token=h)['finishReason'])
                # Concurrent last vote and early finish: either order must produce a consistent frozen result.
                rid,h=room(2);d={'id':rid};g=api('join',d)['token'];api('generate',d,h);api('vote',{**d,'restaurant':'demo-0'},h)
                def last_vote():
                    try:api('vote',{**d,'restaurant':'demo-1'},g)
                    except HTTPError:return False
                    return True
                with concurrent.futures.ThreadPoolExecutor(2) as pool:
                    v=pool.submit(last_vote);f=pool.submit(api,'finish',d,h);voted=v.result();f.result()
                s=api('room?id='+rid,token=g);self.assertEqual(s['stage'],'done');self.assertEqual(sum(a['votes'] for a in s['restaurants']),1+voted);self.assertEqual(s['finishReason'],'all_voted' if voted else 'early')
            finally:http.shutdown();http.server_close();worker.join()
