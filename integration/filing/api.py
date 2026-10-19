"""Optional synthetic intake/read adapter; no worker or schema startup side effects."""
import base64
import binascii
import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .adapters import Conflict


class Intake(BaseModel):
    model_config = ConfigDict(extra='forbid')
    spec: dict
    document_base64: str | None = Field(default=None, max_length=12*1024*1024)


def create_app(service, objects, *, token):
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError('Independent strong synthetic test token required')
    app = FastAPI(title='Test-only filing adapter', docs_url=None, redoc_url=None, openapi_url=None)

    def owner(authorization: str | None = Header(default=None)):
        if not authorization or not hmac.compare_digest(authorization, 'Bearer '+token):
            raise HTTPException(401, 'Unauthorised')
        return 'synthetic-owner'

    @app.post('/v1/filing-test/jobs', status_code=202)
    def submit(body: Intake, requester=Depends(owner)):
        try:
            data = base64.b64decode(body.document_base64, validate=True) if body.document_base64 is not None else None
            job = service.submit(body.spec, data, objects)
            return service.status(job, requester, body.spec['conversation_id'])
        except PermissionError:
            raise HTTPException(403, 'Outside synthetic scope')
        except Conflict:
            raise HTTPException(409, 'Immutable submission conflict')
        except (ValueError,KeyError,TypeError,binascii.Error):
            raise HTTPException(422, 'Invalid synthetic filing package')

    @app.get('/v1/filing-test/conversations/{conversation_id}/jobs')
    def origin(conversation_id: str, requester=Depends(owner)):
        return service.outcomes_for_origin(requester, conversation_id)

    @app.get('/v1/filing-test/jobs/{job_id}')
    def status(job_id: str, conversation_id: str, requester=Depends(owner)):
        try:
            return service.status(job_id, requester, conversation_id)
        except PermissionError:
            raise HTTPException(404, 'Synthetic job not found')

    return app
