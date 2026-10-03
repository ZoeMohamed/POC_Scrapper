"""Google Maps integration errors."""


class MapsError(RuntimeError):
    pass


class MapsBudgetExceededError(MapsError):
    pass


class MapsPermissionError(MapsError):
    pass


class MapsRateLimitedError(MapsError):
    pass


class MapsBadRequestError(MapsError):
    pass


class MapsTransientError(MapsError):
    pass
