class MarketplaceBudgetExceededError(RuntimeError):
    """Raised before an Apify run when the marketplace budget is exhausted."""


class MarketplaceTransientError(RuntimeError):
    """Raised when an Apify marketplace run cannot be completed safely."""


class MarketplacePermissionError(MarketplaceTransientError):
    pass


class MarketplaceBadRequestError(MarketplaceTransientError):
    pass
