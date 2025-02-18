"""
ZMQ Client for handling image acquisition and error responses.

This module implements a ZMQ REQ-REP pattern client that:
1. Sends YAML configuration for image acquisition
2. Receives and processes response codes for various camera states
3. Handles error conditions with appropriate logging and status reporting

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
from enum import IntFlag, auto
from typing import Optional, Union

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
        """Parse the binary response into an ImageError flag."""
        try:
            error_code = int(response.split()[0])
            return cls(error_code)
        except (ValueError, IndexError) as e:
            logger.error(f"Failed to parse response: {response}", exc_info=True)
            return cls.FATAL_UNKNOWN

class ZMQClient:
    """Client for handling ZMQ communication and image acquisition."""
    
    def __init__(self, host: str = "localhost", port: int = 5555):
        self.host = host
        self.port = port
        self.context = zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.REQ)
        self._connect()

    def _connect(self) -> None:
        """Establish connection to ZMQ server."""
        try:
            self.socket.connect(f"tcp://{self.host}:{self.port}")
            logger.info(f"Connected to ZMQ server at {self.host}:{self.port}")
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
            logger.error(f"Failed to send message: {e}", exc_info=True)
            raise

    def process_error_code(self, error: ImageError) -> None:
        """
        Process and log the error state based on the response code.
        
        Args:
            error: ImageError flag to process
        """
        if error == ImageError.SUCCESS:
            logger.info("Image acquisition successful")
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
                logger.error(f"Error {err_flag.value}: {message}")

        # Check for common combinations
        if error.value == 14:  # 2 + 4 + 8
            logger.error("All 3D cameras are missing")
        elif error.value == 15:  # 1 + 2 + 4 + 8
            logger.error("Only thermal camera is present")

async def main():
    """Main execution function."""
    client = ZMQClient()
    
    try:
        # Load and send YAML configuration
        with open('../yaml/guideline.yaml') as stream:
            try:
                message = yaml.safe_load(stream)
                yaml_str = yaml.dump(message, default_flow_style=False, allow_unicode=True)
                await client.send(yaml_str)
                
                # Receive and process response
                response = await client.receive()
                error = ImageError.parse_response(response)
                client.process_error_code(error)
                
                # Exit with error code if not successful
                if error != ImageError.SUCCESS:
                    sys.exit(error.value)
                    
                await asyncio.sleep(1)
                
            except yaml.YAMLError as e:
                logger.error(f"Error parsing YAML file: {e}", exc_info=True)
                sys.exit(1)
    except FileNotFoundError as e:
        logger.error(f"YAML configuration file not found: {e}", exc_info=True)
        sys.exit(1)
    except zmq.ZMQError as e:
        logger.error(f"ZMQ communication error: {e}", exc_info=True)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        client.socket.close()
        client.context.term()

if __name__ == "__main__":
    asyncio.run(main())