#!/usr/bin/env python3
"""
Test script for ZMQ-based image acquisition system.

This script tests the ZMQ image acquisition service by:
1. Connecting to the specified ZMQ endpoint
2. Sending a YAML configuration
3. Receiving and parsing response codes
4. Providing detailed error reporting

Usage:
    python test_zmq_acquisition.py --host <ip> --port <port> --config <yaml_path>

Error codes (zmq.results):
    0: SUCCESS (≥ 1 main, ≥ 2 3ds, ≥ thermal)
    1: No or corrupt main image
    2: No or corrupt 3d0 image
    4: No or corrupt 3d1 image
    8: No or corrupt 3d2 image
    16: No or corrupt thermal image
    32: Timeout for reset (30s)
    64: Timeout for reboot (1m)
    128: Fatal unknown error

Common combinations:
    14: All 3D cameras missing (2 + 4 + 8)
    15: Only thermal camera present (1 + 2 + 4 + 8)
"""

import asyncio
import logging
import zmq.asyncio
import yaml
import sys
import argparse
from enum import IntFlag, auto
from typing import Optional, Union, Dict, Any
from pathlib import Path
import socket
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'zmq_test_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

class ImageError(IntFlag):
    """Enum representing possible error states in the image acquisition process."""
    SUCCESS = 0
    MAIN_CORRUPT = auto()
    THREE_D0_CORRUPT = auto()
    THREE_D1_CORRUPT = auto()
    THREE_D2_CORRUPT = auto()
    THERMAL_CORRUPT = auto()
    RESET_TIMEOUT = auto()
    REBOOT_TIMEOUT = auto()
    FATAL_UNKNOWN = auto()

    @classmethod
    def parse_response(cls, response: bytes) -> 'ImageError':
        """
        Parse the binary response into an ImageError flag.

        Args:
            response: Raw ZMQ response

        Returns:
            ImageError flag representing the error state
        """
        try:
            error_code = int(response.split()[0])
            return cls(error_code)
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse response: {response}", exc_info=True)
            return cls.FATAL_UNKNOWN

class ZMQTestClient:
    """Test client for ZMQ image acquisition system."""

    def __init__(self, host: str = "localhost", port: int = 5555, timeout: float = 30.0):
        """
        Initialize ZMQ test client.

        Args:
            host: Server hostname or IP
            port: Server port
            timeout: Connection timeout in seconds
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))
        self.socket.setsockopt(zmq.SNDTIMEO, int(timeout * 1000))
        self._connect()

    def _connect(self) -> None:
        """
        Establish connection to ZMQ server.

        Raises:
            zmq.ZMQError: If connection fails
        """
        try:
            # Try to resolve hostname first
            try:
                ip = socket.gethostbyname(self.host)
                logger.debug(f"Resolved {self.host} to {ip}")
            except socket.gaierror as e:
                logger.warning(f"Could not resolve hostname {self.host}, using as-is")
                ip = self.host

            endpoint = f"tcp://{ip}:{self.port}"
            self.socket.connect(endpoint)
            logger.info(f"Connected to ZMQ server at {endpoint}")

        except zmq.ZMQError as e:
            logger.error(f"Failed to connect to ZMQ server: {e}", exc_info=True)
            raise

    async def receive(self) -> bytes:
        """
        Receive and process response from the server.

        Returns:
            bytes: Raw server response

        Raises:
            zmq.ZMQError: If communication fails
        """
        try:
            message = await self.socket.recv()
            logger.debug(f"Received raw response: {message}")
            return message
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                logger.error(f"Timeout waiting for response after {self.timeout}s")
            else:
                logger.error(f"Failed to receive message: {e}", exc_info=True)
            raise

    async def send(self, message: str) -> None:
        """
        Send message to the server.

        Args:
            message: YAML string to send

        Raises:
            zmq.ZMQError: If communication fails
        """
        try:
            logger.debug(f"Sending message: {message}")
            await self.socket.send_string(message)
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                logger.error(f"Timeout sending message after {self.timeout}s")
            else:
                logger.error(f"Failed to send message: {e}", exc_info=True)
            raise

    def process_error_code(self, error: ImageError) -> None:
        """
        Process and log the error state based on the response code.

        Args:
            error: ImageError flag to process
        """
        if error == ImageError.SUCCESS:
            logger.info("✓ Image acquisition successful")
            return

        # Log specific error conditions
        error_messages = {
            ImageError.MAIN_CORRUPT: "Main image corrupt or missing",
            ImageError.THREE_D0_CORRUPT: "3D camera 0 image corrupt or missing",
            ImageError.THREE_D1_CORRUPT: "3D camera 1 image corrupt or missing",
            ImageError.THREE_D2_CORRUPT: "3D camera 2 image corrupt or missing",
            ImageError.THERMAL_CORRUPT: "Thermal image corrupt or missing",
            ImageError.RESET_TIMEOUT: "Reset timeout (30s) occurred",
            ImageError.REBOOT_TIMEOUT: "Reboot timeout (1m) occurred",
            ImageError.FATAL_UNKNOWN: "Fatal unknown error occurred"
        }

        # Check each error flag and log accordingly
        for err_flag, message in error_messages.items():
            if error & err_flag:
                logger.error(f"✗ Error {err_flag.value}: {message}")

        # Check for common combinations
        if error.value == 14:  # 2 + 4 + 8
            logger.error("✗ All 3D cameras are missing")
        elif error.value == 15:  # 1 + 2 + 4 + 8
            logger.error("✗ Only thermal camera is present")

async def run_test(host: str, port: int, config_path: str, timeout: float = 30.0) -> int:
    """
    Run the ZMQ client test with specified configuration.

    Args:
        host: ZMQ server hostname or IP
        port: ZMQ server port
        config_path: Path to YAML configuration file
        timeout: Connection and operation timeout in seconds

    Returns:
        int: Exit code (0 for success, error code for failure)
    """
    client = ZMQTestClient(host, port, timeout)

    try:
        # Verify config file exists
        config_file = Path(config_path)
        if not config_file.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return 1

        # Load and validate YAML configuration
        with open(config_file) as stream:
            try:
                message = yaml.safe_load(stream)
                if not isinstance(message, dict):
                    logger.error("YAML configuration must be a dictionary")
                    return 1

                yaml_str = yaml.dump(message, default_flow_style=False, allow_unicode=True)
                await client.send(yaml_str)

                # Receive and process response
                response = await client.receive()
                error = ImageError.parse_response(response)
                client.process_error_code(error)

                # Return error code if not successful
                return error.value if error != ImageError.SUCCESS else 0

            except yaml.YAMLError as e:
                logger.error(f"Error parsing YAML file: {e}", exc_info=True)
                return 1
    except zmq.ZMQError as e:
        logger.error(f"ZMQ communication error: {e}", exc_info=True)
        return 1
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        return 130  # Standard Unix practice
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1
    finally:
        client.socket.close()
        client.context.term()

def parse_args() -> argparse.Namespace:
    """Parse and validate command line arguments."""
    parser = argparse.ArgumentParser(
        description="Test ZMQ image acquisition system",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--host",
        default="localhost",
        help="ZMQ server hostname or IP address"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5555,
        help="ZMQ server port"
    )
    parser.add_argument(
        "--config",
        default="../yaml/guideline.yaml",
        help="Path to YAML configuration file"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Connection and operation timeout in seconds"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Basic argument validation
    if args.port < 1 or args.port > 65535:
        parser.error("Port must be between 1 and 65535")
    if args.timeout <= 0:
        parser.error("Timeout must be positive")

    return args

def main() -> int:
    """Main entry point for the test script."""
    args = parse_args()

    # Set debug logging if requested
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Print test configuration
    logger.info("Starting ZMQ acquisition test with configuration:")
    logger.info(f"  Host: {args.host}")
    logger.info(f"  Port: {args.port}")
    logger.info(f"  Config: {args.config}")
    logger.info(f"  Timeout: {args.timeout}s")
    logger.info(f"  Debug: {'enabled' if args.debug else 'disabled'}")

    # Run the test
    try:
        return asyncio.run(run_test(
            args.host,
            args.port,
            args.config,
            args.timeout
        ))
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
        return 130

if __name__ == "__main__":
    sys.exit(main())