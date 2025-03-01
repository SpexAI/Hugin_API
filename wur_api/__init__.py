"""
WUR API implementation for Hugin imaging system.

This package provides a REST API server that implements the Remote Imaging Interface
as specified in the WUR API definition, translating REST requests to ZMQ messages
for the Hugin system.
"""

__version__ = "0.1.0"

from . import dummy_hugin
from .api_server import app, ImageError, APIState, ZMQClient

__all__ = ["app", "dummy_hugin", "ImageError", "APIState", "ZMQClient"]