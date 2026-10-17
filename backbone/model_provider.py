"""Model-neutral interface. Routing permissions remain outside any language model."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class ModelRequest:
    policy_version: str
    instructions: str
    text: str
    # Sensitive originals are referenced only through authorised backend access.

@dataclass(frozen=True)
class ModelResponse:
    provider_id: str
    model_id: str
    content: str

class ModelProvider(Protocol):
    provider_id: str
    model_id: str
    def complete(self, request: ModelRequest) -> ModelResponse: ...

class DisabledProvider:
    """No external dependency; useful for offline testing and safe fallback."""
    provider_id = 'disabled'
    model_id = 'none'
    def complete(self, request: ModelRequest) -> ModelResponse:
        raise RuntimeError('Model execution disabled; no provider configured')

class StaticTestProvider:
    """Synthetic deterministic fixture, NEVER a production classifier."""
    provider_id = 'fixture'
    model_id = 'fixed-response'
    def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(self.provider_id,self.model_id,
                             '{"classification":"REVIEW_REQUIRED"}')

def classify_for_review(provider: ModelProvider, request: ModelRequest) -> dict:
    """Untrusted model output is not an authorisation or an action."""
    import json
    response = provider.complete(request)
    result = json.loads(response.content)
    if not isinstance(result,dict) or result.get('classification') not in {
        'REVIEW_REQUIRED','RECEIPT','FOOD','MARINE','OTHER'}:
        raise ValueError('Invalid model classification')
    return {'provider_id':response.provider_id,'model_id':response.model_id,
            'classification':result['classification'],'action_authorised':False}
