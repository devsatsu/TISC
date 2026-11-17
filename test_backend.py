import json, unittest, threading
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from bill_backend import merge, explain
from backend_server import Handler
class BackendTests(unittest.TestCase):
 def test_merge(self):
  lookup={'fields':[{'id':'net_payable','type':'decimal'}]}
  def report(v,status='extracted'):
   return {'photo_id':str(v),'fields':{'net_payable':{'value':v,'status':status}}}
  self.assertEqual(merge([report('1'),report('1.0')],lookup)['net_payable']['status'],'extracted')
  conflict=merge([report('1'),report('2')],lookup)
  self.assertIsNone(conflict['net_payable']['value'])
  self.assertEqual(conflict['net_payable']['status'],'conflict')
  self.assertTrue(explain(conflict)['sections'][0]['requires_review'])
  self.assertIsNone(merge([report('1'),report(None,'ambiguous_match')],lookup)['net_payable']['value'])
 def test_api(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
  thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
  try:
   base=f'http://127.0.0.1:{server.server_port}'
   self.assertEqual(json.load(urlopen(base+'/health'))['status'],'ok')
   with self.assertRaises(HTTPError) as error:
    urlopen(Request(base+'/bills',data=b'{"photos":[]}',headers={'Content-Type':'application/json'}))
   self.assertEqual(error.exception.code,400)
  finally:
   server.shutdown();server.server_close();thread.join()
if __name__=='__main__': unittest.main()
