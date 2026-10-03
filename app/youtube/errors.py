"""YouTube integration errors."""


class YouTubeError(RuntimeError):
    pass


class YouTubeQuotaExceededError(YouTubeError):
    pass


class YouTubePermissionError(YouTubeError):
    pass


class YouTubeTransientError(YouTubeError):
    pass
