import json, tempfile, threading, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import server

class ReleaseSafety(unittest.TestCase):
    def test_default_rejects_demo_and_missing_map(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(server,'DB',Path(tmp)/'test.db'), patch.object(server,'ALLOW_DEMO',False), patch.object(server,'provider',return_value='demo'):
            http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
            t=threading.Thread(target=http.serve_forever,daemon=True);t.start()
            def api(action,body,token=None):
                headers={'Content-Type':'application/json'}
                if token:headers['X-Account-Token']=token
                with urlopen(Request(f'http://127.0.0.1:{http.server_port}/api/{action}',data=json.dumps(body).encode(),headers=headers),timeout=5) as f:return json.load(f)
            try:
                token=api('register',{'name':'Test Host','password':'test-password'})['token']
                for d in ({'count':2,'demo':True},{'count':2,'demo':False,'location':[114.3,35.7]},{'count':2}):
                    with self.assertRaises(HTTPError) as error:api('create',d,token)
                    self.assertEqual(error.exception.code,400)
            finally:
                http.shutdown();http.server_close();t.join()
