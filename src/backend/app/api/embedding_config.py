"""Teacher-only embedding settings; plaintext keys never appear in responses."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from app.api.dependencies import teacher_account
from app.api.model_config import _plain, _invalid, _disabled
from app.repositories.accounts import AccountRecord
from app.schemas.contracts import EmbeddingConfig, EmbeddingConfigUpdate, ModelConfigTestResult, ModelDiscoveryRequest, ModelDiscoveryResult
from app.services import embedding_configs as service, model_configs
from app.services.ai.outbound import EndpointBlocked, build_transport
from app.services.credentials import CredentialError

router=APIRouter(prefix='/api/v1/me/embedding-config',tags=['settings'])

def _transport(request):
    return getattr(request.app.state,'embedding_transport',None) or build_transport(request.app.state.settings)

def _run(action):
    try: return JSONResponse(content=action())
    except EndpointBlocked as e: return _invalid('base_url',e.reason)
    except model_configs.KeyRequired: return _invalid('api_key','required_when_endpoint_changes')
    except model_configs.InvalidKey: return _invalid('api_key','invalid_characters')
    except model_configs.InvalidModel as e: return _invalid('model',e.reason)
    except (model_configs.CredentialStoreDisabled,CredentialError): return _disabled()
    except service.EmbeddingConfigBusy:
        return JSONResponse(status_code=409,content={'code':'COURSE_BUSY','message':'课程正在处理或配置发生变化，请稍后重试'})
    except service.EmbeddingConfigFailure:
        return JSONResponse(status_code=422,content={'code':'VALIDATION_ERROR','message':'向量连接测试或课程重建失败，原配置保持生效；请检查模型、密钥与维度'})
    except Exception:
        return JSONResponse(status_code=503,content={'code':'STORAGE_UNAVAILABLE','message':'向量配置暂时无法保存或读取，请稍后重试；原配置保持生效'})

def _values(payload):
    return {'base_url':payload.base_url,'model':payload.model,'dimensions':payload.dimensions,'api_key':_plain(payload.api_key)}

def _limited(request,user,suffix):
    wait=request.app.state.config_test_limiter.acquire('embedding:'+suffix+':'+user.id)
    if wait: return JSONResponse(status_code=429,content={'code':'RATE_LIMITED','message':'操作过于频繁，请稍后再试'},headers={'Retry-After':str(wait)})

@router.get('',operation_id='getEmbeddingConfig',response_model=EmbeddingConfig)
def get_embedding_config(request:Request,user:AccountRecord=Depends(teacher_account)):
    return _run(lambda:service.public(request.app.state.settings,user.id))

@router.put('',operation_id='saveEmbeddingConfig',response_model=EmbeddingConfig)
def save_embedding_config(payload:EmbeddingConfigUpdate,request:Request,user:AccountRecord=Depends(teacher_account)):
    limit=_limited(request,user,'save')
    if limit is not None: return limit
    return _run(lambda:service.save(request.app.state.settings,user.id,transport=_transport(request),
                rebuilder=getattr(request.app.state,'embedding_rebuilder',None),**_values(payload)))

@router.post('/test',operation_id='testEmbeddingConfig',response_model=ModelConfigTestResult)
def test_embedding_config(payload:EmbeddingConfigUpdate,request:Request,user:AccountRecord=Depends(teacher_account)):
    limit=_limited(request,user,'test')
    if limit is not None:return limit
    return _run(lambda:service.test(request.app.state.settings,user.id,transport=_transport(request),**_values(payload)))

@router.post('/models',operation_id='discoverEmbeddingModels',response_model=ModelDiscoveryResult)
def discover_embedding_models(payload:ModelDiscoveryRequest,request:Request,user:AccountRecord=Depends(teacher_account)):
    limit=_limited(request,user,'models')
    if limit is not None:return limit
    def action():
        old=service.rows.get_config(request.app.state.settings.SQLITE_URL,user.id)
        base=(payload.base_url or '').strip().rstrip('/')
        key=_plain(payload.api_key)
        if not key:
            if old is None or base!=old.base_url: raise model_configs.KeyRequired()
            key=service._cipher(request.app.state.settings).open(service.domain(user.id),old.sealed)
        outcome=model_configs.discover_models(request.app.state.settings,user.id,base_url=base,api_key=key,
            transport=getattr(request.app.state,'model_discovery_transport',None) or build_transport(request.app.state.settings))
        return {'ok':outcome.ok,'models':outcome.models,**({'error_class':outcome.error_class} if outcome.error_class else {})}
    return _run(action)
