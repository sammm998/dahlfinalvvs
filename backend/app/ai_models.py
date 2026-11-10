"""The language models a reading may ask for the final pipe assignment - or none, the sheet's own evidence alone.

Chosen per analysis, so the same drawing can be read once with each and the answers, tokens and cost compared.
"""
import os

NONE = 'none'
ASTRA = 'gpt-6-astra'
SOL = 'gpt-6.1-sol'
OPUS = 'claude-opus-5-5'
FABLE = 'claude-fable-5-2'
GEMINI = 'gemini-pro'
CHOICES = (NONE, ASTRA, SOL, OPUS, FABLE, GEMINI)
LABELS = {NONE: 'Utan AI', ASTRA: 'GPT-6 Astra', SOL: 'GPT-6.1 Sol', OPUS: 'Claude Opus 5.5', FABLE: 'Claude Fable 5.2', GEMINI: 'Gemini Pro'}


def model_id(choice):
    """The provider's model id for a choice; the OpenAI and Google ids can be set by the operator."""
    if choice == SOL:
        return os.environ.get('VVS_SOL_MODEL', SOL)
    if choice == GEMINI:
        from .gemini_model import GEMINI_MODEL
        return GEMINI_MODEL
    return choice


def default():
    """What a reading uses when nobody chose: GPT-6 Astra whenever the server holds an OpenAI key, the rules alone
    when it does not. The operator can turn the default off with VVS_ASSIGNMENT_MODEL=0; the person starting an
    analysis can always pick another model or none."""
    if os.environ.get('VVS_ASSIGNMENT_MODEL') == '0':
        return NONE
    from .source_model import configured as openai_ready
    if not openai_ready():
        return NONE
    from . import api_budget
    return NONE if api_budget.blocked(model_id(ASTRA)) else ASTRA


def available():
    from .source_model import configured as openai_ready
    from .claude_model import configured as claude_ready
    from .gemini_model import configured as gemini_ready
    openai = openai_ready()
    return {NONE: True, ASTRA: openai, SOL: openai, OPUS: claude_ready(), FABLE: claude_ready(), GEMINI: gemini_ready()}


def transport(choice):
    """The connection that answers the assignment for `choice`; None reads by the rules."""
    if choice in (ASTRA, SOL):
        from .source_model import transport as openai_transport
        return openai_transport(model_id(choice))
    if choice in (OPUS, FABLE):
        from .claude_model import transport as claude_transport
        return claude_transport(choice)
    if choice == GEMINI:
        from .gemini_model import transport as gemini_transport
        return gemini_transport(model_id(choice))
    return None
