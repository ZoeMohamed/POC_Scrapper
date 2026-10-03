"""Social collection errors safe to expose as short status messages."""


class SocialError(RuntimeError):
    pass


class SocialBudgetExceededError(SocialError):
    pass


class SocialPermissionError(SocialError):
    pass


class SocialRateLimitedError(SocialError):
    pass


class SocialBadRequestError(SocialError):
    pass


class SocialTransientError(SocialError):
    pass
