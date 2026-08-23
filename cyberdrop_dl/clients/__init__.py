import logging
from typing import Literal

from cyberdrop_dl import signature
from cyberdrop_dl.logs import LOG_HTTP_TRAFFIC

HttpMethod = Literal["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"]


class TrafficLogger(logging.LoggerAdapter[logging.Logger]):
    @signature.copy(logging.LoggerAdapter.info)
    def traffic(self, msg, *args, **kwargs) -> None:
        if LOG_HTTP_TRAFFIC.get():
            self.log(logging.INFO, msg, *args, **kwargs)


def get_logger(name: str) -> TrafficLogger:
    return TrafficLogger(logging.getLogger(name))
