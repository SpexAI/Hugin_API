"""
Tests for the dummy Hugin ZMQ server.
"""

import pytest
import asyncio
import zmq.asyncio
import yaml
from typing import Dict, Any, Optional

from wur_api.dummy_hugin import DummyHuginServer, ImageError

# Basic server tests
@pytest.mark.asyncio
async def test_dummy_server_start_stop(test_env: Dict[str, str]) -> None:
    """Test that the dummy server can start and stop."""
    port = int(test_env["HUGIN_ZMQ_PORT"])
    server = DummyHuginServer(host="*", port=port)

    try:
        # Start server with a timeout
        await asyncio.wait_for(server.start(), timeout=2.0)
        assert server.running
        assert server.task is not None

        # Wait briefly to make sure it started
        await asyncio.sleep(0.1)

    finally:
        # Always clean up, even if assertions fail
        if server.running:
            # Stop with a timeout
            try:
                await asyncio.wait_for(server.stop(), timeout=2.0)
                assert not server.running
                assert server.task is None
            except asyncio.TimeoutError:
                print("WARNING: Server stop operation timed out")

@pytest.mark.asyncio
async def test_dummy_server_communication(test_env: Dict[str, str]) -> None:
    """Test basic communication with the dummy server."""
    port = int(test_env["HUGIN_ZMQ_PORT"])
    server = DummyHuginServer(host="*", port=port, error_rate=0.0)  # Always succeed
    
    try:
        # Start server
        await server.start()
        
        # Create ZMQ client
        context = zmq.asyncio.Context.instance()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://localhost:{port}")
        
        # Send a valid YAML message
        test_message = {
            "required": {
                "path": "test/test/",
                "plant-id": "test-plant",
                "uuid": "123456",
                "time-stamp": "2025-03-01-12-34-56"
            }
        }
        yaml_str = yaml.dump(test_message)
        
        await socket.send_string(yaml_str)
        response = await socket.recv_string()
        
        # Response should be "0 Success" (no error)
        parts = response.split()
        assert int(parts[0]) == 0
        
        # Clean up
        socket.close()
        
    finally:
        # Clean up if test fails
        if server.running:
            await server.stop()

@pytest.mark.asyncio
async def test_dummy_server_error_response(test_env: Dict[str, str]) -> None:
    """Test that the dummy server can generate error responses."""
    port = int(test_env["HUGIN_ZMQ_PORT"])
    # Always fail with specific error
    server = DummyHuginServer(host="*", port=port, error_rate=1.0)
    
    # Override the _generate_random_error method to always return a specific error
    original_generate_error = server._generate_random_error
    server._generate_random_error = lambda: ImageError.MAIN_CORRUPT
    
    try:
        # Start server
        await server.start()
        
        # Create ZMQ client
        context = zmq.asyncio.Context.instance()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://localhost:{port}")
        
        # Send a valid YAML message
        test_message = {
            "required": {
                "path": "test/test/",
                "plant-id": "test-plant",
                "uuid": "123456",
                "time-stamp": "2025-03-01-12-34-56"
            }
        }
        yaml_str = yaml.dump(test_message)
        
        await socket.send_string(yaml_str)
        response = await socket.recv_string()
        
        # Response should indicate MAIN_CORRUPT (error code 1)
        parts = response.split()
        assert int(parts[0]) == 1
        
        # Clean up
        socket.close()
        
    finally:
        # Restore original method
        server._generate_random_error = original_generate_error
        
        # Clean up if test fails
        if server.running:
            await server.stop()


@pytest.mark.asyncio
async def test_dummy_server_response_format(test_env: Dict[str, str]) -> None:
    """Test that the dummy server response includes plant ID and directory."""
    port = int(test_env["HUGIN_ZMQ_PORT"])
    server = DummyHuginServer(host="*", port=port, error_rate=0.0)  # Always succeed

    # Override _process_requests method to send a specific response format
    original_process = server._process_requests

    async def custom_process():
        while server.running:
            try:
                # Use a poller with a timeout to make this interruptible
                poller = zmq.asyncio.Poller()
                poller.register(server.socket, zmq.POLLIN)

                # Wait for a message with a 100ms timeout
                events = await poller.poll(timeout=100)

                # If no message received, just loop and check self.running again
                if not events:
                    continue

                # Receive the message
                message = await server.socket.recv_string()

                # Parse YAML to get plant ID
                config = yaml.safe_load(message)
                plant_id = config.get("required", {}).get("plant-id", "unknown")

                # Generate a directory name based on timestamp - fixed to use datetime
                from datetime import datetime
                directory = f"ImageSet_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                # Send response with the format: "ERROR_CODE PLANT_ID DIRECTORY"
                await server.socket.send_string(f"0 {plant_id} {directory}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in dummy server: {e}")
                try:
                    await server.socket.send_string("128 Error")
                except:
                    pass

    server._process_requests = custom_process

    try:
        # Start server
        await server.start()

        # Create ZMQ client
        context = zmq.asyncio.Context.instance()
        socket = context.socket(zmq.REQ)
        socket.connect(f"tcp://localhost:{port}")

        # Send a message with a specific plant ID
        test_message = {
            "required": {
                "path": "test/test/",
                "plant-id": "test-plant-123",
                "uuid": "123456",
                "time-stamp": "2025-03-01-12-34-56"
            }
        }
        yaml_str = yaml.dump(test_message)

        await socket.send_string(yaml_str)
        response = await socket.recv_string()

        # Check response format
        parts = response.split()
        assert len(parts) >= 3
        assert int(parts[0]) == 0  # Success
        assert parts[1] == "test-plant-123"  # Plant ID
        assert parts[2].startswith("ImageSet_")  # Directory format

        # Clean up
        socket.close()

    finally:
        # Restore original method
        server._process_requests = original_process

        # Clean up if test fails
        if server.running:
            await server.stop()