"""Discovery uses fake GET responses; never contacts real providers."""
import base64
import json
from types import SimpleNamespace
import pytest
from app.config import load_settings
from app.services import model_configs as service

KEY = 'fake-key-discovery'

def settings():
    return load_settings({'LLM_MODE':'personal','MODEL_CREDENTIAL_KEY':base64.urlsafe_b64encode(bytes(range(32))).decode()})

class Transport:
    def __init__(self, payload=None, status=200):
        self.payload = json.dumps(payload if payload is not None else {'data':[{'id':'z-model'},{'id':'a-model'},{'id':'z-model'}]}).encode()
        self.status = status
        self.calls = []
        self.closed = False
    def get(self, url, headers, timeout):
        self.calls.append((url,headers,timeout))
        self.remaining = self.payload
        def read(amount, timeout):
            chunk,self.remaining=self.remaining[:amount],self.remaining[amount:]
            return chunk
        return SimpleNamespace(status=self.status,read=read,close=lambda:setattr(self,'closed',True),header=lambda n:None)

def call(transport, base='https://provider.example/v1'):
    return service.discover_models(settings(),'fake-user',base_url=base,api_key=KEY,transport=transport)

def test_get_directory_deduplicates_without_saving_or_generating():
    transport=Transport();result=call(transport)
    assert result.ok and result.models == ['a-model','z-model']
    assert transport.calls[0][0]=='https://provider.example/v1/models'
    assert transport.calls[0][1]['Authorization']=='Bearer '+KEY
    assert transport.closed

@pytest.mark.parametrize('status,reason',[(401,'auth'),(403,'auth'),(404,'unsupported'),(405,'unsupported'),(429,'rate_limited'),(503,'server'),(302,'malformed_response')])
def test_upstream_errors_return_only_safe_class(status,reason):
    transport=Transport({'error':{'message':KEY}},status)
    result=call(transport)
    assert not result.ok and result.models==[] and result.error_class==reason
    assert KEY not in repr(result) and transport.closed

@pytest.mark.parametrize('payload',[{'data':[{'id':''}]},{'data':[{'id':'x'+KEY}]},{'data':[{'id':'a\nB'}]},{'error':{'message':KEY}}])
def test_invalid_directory_does_not_expose_provider_content(payload):
    result=call(Transport(payload))
    assert not result.ok and result.error_class=='malformed_response' and KEY not in repr(result)

def test_private_or_non_https_endpoint_does_not_get_key():
    transport=Transport();result=call(transport,'http://127.0.0.1:8321')
    assert not result.ok and result.error_class=='blocked_address' and transport.calls==[]

def test_oversized_body_is_bounded_and_closed():
    transport=Transport();transport.payload=b'x'*(1024*1024+1)
    result=call(transport)
    assert not result.ok and result.error_class=='malformed_response' and transport.closed

def test_guarded_get_blocks_private_resolution_before_connecting():
    from app.services.ai.outbound import GuardedTransport, EndpointBlocked
    transport=GuardedTransport(resolver=lambda h,p:['127.0.0.1'],connector=lambda *args:pytest.fail('must not connect'))
    with pytest.raises(EndpointBlocked):
        transport.get('https://provider.example/v1/models',{'Authorization':'Bearer '+KEY},1)


def test_guarded_get_pins_address_and_preserves_get_method():
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from app.services.ai.outbound import GuardedTransport
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path,self.headers.get('Host'),self.headers.get('Authorization')))
            self.send_response(200);self.end_headers();self.wfile.write(b'{"data":[]}')
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        response=GuardedTransport(allow_private=True,resolver=lambda h,p:['127.0.0.1']).get(f'http://provider.test:{server.server_port}/v1/models',{'Authorization':'Bearer '+KEY},2)
        assert response.status==200 and response.read(100,2)==b'{"data":[]}'
        response.close();assert calls==[('/v1/models',f'provider.test:{server.server_port}','Bearer '+KEY)]
    finally:
        server.shutdown();server.server_close();thread.join()


def test_saved_key_is_never_forwarded_to_changed_address(monkeypatch):
    monkeypatch.setattr(service.repo,'get_config',lambda *args:SimpleNamespace(base_url='https://original.example/v1',sealed='unused'))
    transport=Transport()
    with pytest.raises(service.KeyRequired):
        service.discover_models(settings(),'u',base_url='https://other.example/v1',api_key=None,transport=transport)
    assert not transport.calls


def test_no_root_key_does_not_send_unsaved_key():
    transport=Transport()
    with pytest.raises(service.CredentialStoreDisabled):
        service.discover_models(load_settings({'LLM_MODE':'demo'}),'u',base_url='https://provider.example',api_key=KEY,transport=transport)
    assert not transport.calls

def test_discovery_route_authentication_and_unsaved_request(tmp_path,monkeypatch):
    from test_n07_n08 import _client, BASE
    from fastapi.testclient import TestClient
    app,url,user,auth,_,_=_client(tmp_path,monkeypatch,mode='personal',root_key=True)
    transport=Transport();app.state.model_discovery_transport=transport
    with TestClient(app) as client:
        assert client.post(BASE+'/models').status_code==401
        assert client.post(BASE+'/models',headers=auth).status_code==409
        response=client.post(BASE+'/models',headers=auth,json={'base_url':'https://provider.example/v1','api_key':KEY})
        assert response.status_code==200 and response.json()=={'ok':True,'models':['a-model','z-model']}
        assert client.get(BASE,headers=auth).json()['configured'] is False
    assert len(transport.calls)==1


def test_discovery_route_saved_key_endpoint_and_test_state(tmp_path,monkeypatch):
    from test_n07_n08 import _client, BASE, ROOT_KEY
    from fastapi.testclient import TestClient
    from app.services.credentials import CredentialCipher
    app,url,user,auth,_,_=_client(tmp_path,monkeypatch,mode='personal',root_key=True)
    original=service.repo.save_config(url,user_id=user.id,base_url='https://provider.example/v1',model='manual-model',sealed=CredentialCipher(ROOT_KEY).seal(user.id,KEY),key_hint='fake')
    transport=Transport();app.state.model_discovery_transport=transport
    with TestClient(app) as client:
        assert client.post(BASE+'/models',headers=auth,json={'base_url':'https://other.example/v1'}).status_code==422
        assert not transport.calls
        assert client.post(BASE+'/models',headers=auth,json={'base_url':'https://provider.example/v1'}).json()['ok'] is True
    assert service.repo.get_config(url,user.id)==original
    assert transport.calls[0][1]['Authorization']=='Bearer '+KEY


def test_discovery_route_rate_limit_and_disabled_store(tmp_path,monkeypatch):
    from test_n07_n08 import _client, BASE
    from fastapi.testclient import TestClient
    app,_,_,auth,_,_=_client(tmp_path,monkeypatch,mode='demo',root_key=False)
    transport=Transport();app.state.model_discovery_transport=transport
    with TestClient(app) as client:
        response=client.post(BASE+'/models',headers=auth,json={'base_url':'https://provider.example/v1','api_key':KEY})
        assert response.status_code==503 and not transport.calls
        app.state.model_discovery_limiter=service.ConfigTestLimiter(limit=1)
        client.post(BASE+'/models',headers=auth)
        response=client.post(BASE+'/models',headers=auth)
        assert response.status_code==429 and response.headers.get('Retry-After')
