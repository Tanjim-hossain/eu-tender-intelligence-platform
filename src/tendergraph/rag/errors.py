class GenerationUnavailable(RuntimeError):
    """The configured generator failed; never fall back to a paid provider."""


class InvalidGeneratedAnswer(RuntimeError):
    """Generated output failed the citation contract."""
