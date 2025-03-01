"""
Pytest configuration for Hugin API tests.
"""

import os
import pytest
import asyncio
import socket
from typing import Dict, Any, Generator
from contextlib import closing
from fastapi.testclient import TestClient

from wur_api.api_server import app, state
from wur_api.dummy_hugin import DummyHuginServer

# Utility functions for tests
def find_free_port() -> int:
    """Find an available port on localhost."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('localhost', 0))
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return s.getsockname()[1]

# FastAPI test client fixture
@pytest.fixture
def api_client() -> Generator[TestClient, None, None]:
    """Create a FastAPI test client."""
    client = TestClient(app)
    yield client

# Environment variables fixture for testing
@pytest.fixture
def test_env() -> Dict[str, str]:
    """Return test environment variables."""
    return {
        "HUGIN_ZMQ_HOST": "localhost",
        "HUGIN_ZMQ_PORT": str(find_free_port()),
        "HUGIN_ZMQ_TIMEOUT": "2.0",  # Short timeout for quicker tests
        "HUGIN_S3_BUCKET": "test-bucket",
        "HUGIN_S3_BASE_PATH": "test-path",
        "WUR_API_HOST": "127.0.0.1",
        "WUR_API_PORT": str(find_free_port()),
        "LOG_LEVEL": "DEBUG"
    }

# Set environment variables for tests
@pytest.fixture(autouse=True)
def set_test_env(test_env: Dict[str, str]) -> Generator[None, None, None]:
    """Set environment variables for testing."""
    # Save original environment
    original_env = {}
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value
        
    yield
    
    # Restore original environment
    for key, value in original_env.items():
        if value is None:
            if key in os.environ:
                del os.environ[key]
        else:
            os.environ[key] = value

# Dummy Hugin server fixture
@pytest.fixture
async def dummy_hugin(test_env: Dict[str, str]) -> Generator[DummyHuginServer, None, None]:
    """Start dummy Hugin server for testing."""
    port = int(test_env["HUGIN_ZMQ_PORT"])
    server = DummyHuginServer(host="*", port=port, error_rate=0.2, delay_min=0.1, delay_max=0.3)
    
    # Start server in background
    await server.start()
    
    yield server
    
    # Clean up
    await server.stop()

# Event loop fixture for async tests
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()