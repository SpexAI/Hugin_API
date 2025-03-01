"""
Dummy Hugin ZMQ Server

This script simulates a Hugin imaging system ZMQ server for testing purposes.
It listens for ZMQ requests, parses YAML configurations, and returns configurable
response codes to simulate different scenarios.

Usage:
    python dummy_hugin_server.py [--port PORT] [--error ERROR_CODE] [--delay SECONDS]

Example:
    # Run server with success response
    python dummy_hugin_server.py --port 5555

    # Simulate main image corrupt error
    python dummy_hugin_server.py --error 1

    # Simulate all 3D cameras missing
    python dummy_hugin_server.py --error 14
"""

import asyncio
import argparse
import logging
import yaml
import zmq
import zmq.asyncio
import random
import signal
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'dummy_hugin_server_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)


class DummyHuginServer:
    """Simulated ZMQ server for the Hugin imaging system."""

    def __init__(self, port: int = 5555, error_code: int = 0, delay: float = 0.0):
        """
        Initialize the dummy Hugin server.

        Args:
            port: Port to listen on
            error_code: Error code to return (0 = success)
            delay: Simulated processing delay in seconds
        """
        self.port = port
        self.error_code = error_code
        self.delay = delay
        self.context = zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.REP)
        self.running = False

        # Error code descriptions for logging
        self.error_descriptions = {
            0: "SUCCESS",
            1: "MAIN_CORRUPT",
            2: "THREE_D0_CORRUPT",
            4: "THREE_D1_CORRUPT",
            8: "THREE_D2_CORRUPT",
            14: "ALL_3D_CAMERAS_MISSING",
            15: "ONLY_THERMAL_PRESENT",
            16: "THERMAL_CORRUPT",
            32: "RESET_TIMEOUT",
            64: "REBOOT_TIMEOUT",
            128: "FATAL_UNKNOWN"
        }

    async def start(self):
        """Start the ZMQ server and listen for requests."""
        try:
            endpoint = f"tcp://*:{self.port}"
            self.socket.bind(endpoint)
            logger.info(f"Dummy Hugin server listening on {endpoint}")
            logger.info(f"Configured to return error code: {self.error_code} "
                        f"({self.error_descriptions.get(self.error_code, 'Custom error')})")

            self.running = True
            while self.running:
                await self.handle_request()

        except zmq.ZMQError as e:
            logger.error(f"ZMQ error: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
        finally:
            self.socket.close()
            self.context.term()
            logger.info("Server stopped")

    async def handle_request(self):
        """Handle incoming ZMQ request."""
        try:
            # Wait for next request
            message = await self.socket.recv()
            logger.info("Received request")

            # Try to parse as YAML
            try:
                yaml_data = yaml.safe_load(message.decode('utf-8'))
                logger.info(f"Parsed YAML: {yaml_data}")

                # Extract some key information for logging
                plant_id = yaml_data.get('required', {}).get('plant-id', 'unknown')
                experiment = yaml_data.get('required', {}).get('experiment-id', 'unknown')
                logger.info(f"Processing request for plant: {plant_id}, experiment: {experiment}")

            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse YAML: {e}")

            # Simulate processing delay
            if self.delay > 0:
                logger.info(f"Simulating processing delay of {self.delay}s")
                await asyncio.sleep(self.delay)

            # Send response with configured error code
            await self.socket.send_string(f"{self.error_code} DUMMY_RESPONSE")
            logger.info(f"Sent response with error code: {self.error_code}")

        except zmq.ZMQError as e:
            logger.error(f"ZMQ error while handling request: {e}", exc_info=True)
            if self.running:  # Only try to respond if we're still running
                try:
                    await self.socket.send_string("128 SERVER_ERROR")
                except:
                    pass

    def stop(self):
        """Stop the server."""
        logger.info("Stopping server...")
        self.running = False


async def main():
    """Parse arguments and start the server."""
    parser = argparse.ArgumentParser(
        description="Dummy Hugin ZMQ server for testing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5555,
        help="Port to listen on"
    )
    parser.add_argument(
        "--error",
        type=int,
        default=0,
        help="Error code to return (0=success, 1=main corrupt, 14=all 3D missing, etc.)"
    )
    parser.add_argument(
        "--random-error",
        action="store_true",
        help="Return random error codes on each request"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Simulated processing delay in seconds"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Set up signal handlers for graceful shutdown
    server = DummyHuginServer(args.port, args.error, args.delay)

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        server.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Handle random error mode
    if args.random_error:
        # Error codes to cycle through
        error_codes = [0, 1, 2, 4, 8, 14, 15, 16, 32, 64, 128]

        async def random_error_task():
            while server.running:
                server.error_code = random.choice(error_codes)
                logger.info(f"Switched to random error code: {server.error_code}")
                await asyncio.sleep(5)  # Change every 5 seconds

        asyncio.create_task(random_error_task())

    # Start the server
    await server.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        sys.exit(1)