"""Policy for model requests that include source records or images."""
import os

from api.app.agents.errors import ProviderError


def record_provider():
    from api.app.agents.provider import ChatProvider
    provider = ChatProvider()
    # The free Gemini profile permits provider data use. For a separately
    # configured private provider the operator must attest to cost and terms.
    if (provider.profile != 'compatible'
            or os.environ.get('SAFELEDGER_RECORD_PROVIDER_NO_TRAINING') != '1'
            or os.environ.get('SAFELEDGER_LLM_FREE_TIER_CONFIRMED') != '1'):
        raise ProviderError('PRIVATE_RECORD_PROVIDER_REQUIRED')
    return provider
