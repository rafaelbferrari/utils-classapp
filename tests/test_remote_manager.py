"""Validate the optional private HTTPS proxy without exposing a listener."""
import json
import threading
import unittest
import urllib.request
import urllib.error
from manage_face_groups import serve


class FakeManager:
    mutex=threading.RLock()
    def groups(self):return {'groups':[],'can_undo':False}


class RemoteOriginTests(unittest.TestCase):
    def test_only_configured_private_host_is_allowed(self):
        server=serve(FakeManager(),external_origin='https://example.private.ts.net')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            url=f'http://127.0.0.1:{server.server_port}/api/groups'
            request=urllib.request.Request(url,headers={'Host':'example.private.ts.net'})
            with urllib.request.urlopen(request) as response:self.assertEqual(json.load(response)['groups'],[])
            for host in ['attacker.example','other.private.ts.net']:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(urllib.request.Request(url,headers={'Host':host}))
                self.assertEqual(error.exception.code,403)
            request=urllib.request.Request(url.replace('/api/groups','/api/name'),data=b'{}',headers={'Host':'example.private.ts.net','Origin':'https://attacker.example','X-Local-Token':'wrong'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
            self.assertEqual(error.exception.code,403)
        finally:server.shutdown();server.server_close();thread.join()

    def test_public_or_malformed_origins_rejected(self):
        for origin in ['http://example.ts.net','https://example.com','https://user@example.ts.net','https://example.ts.net/path']:
            with self.assertRaises(ValueError):serve(FakeManager(),external_origin=origin)


if __name__=='__main__':unittest.main()
