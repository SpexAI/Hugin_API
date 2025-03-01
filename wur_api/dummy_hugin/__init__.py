#!/usr/bin/env python3
"""
Dummy Hugin ZMQ server implementation for testing purposes.

This module provides a simple ZMQ server that simulates Hugin image acquisition
responses for testing the WUR API implementation without an actual Hugin system.
"""

import asyncio
import logging
import random
import yaml
import zmq.asyncio
from datetime import datetime
from enum import IntFlag, auto
from pathlib import Path
from typing import Optional, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'dummy_hugin_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
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

class DummyHuginServer:
    """
    Dummy ZMQ server that simulates Hugin image acquisition system.
    
    This server responds to ZMQ REQ/REP messages with simulated responses,
    optionally introducing random failures for testing error handling.
    """
    
    def __init__(
        self, 
        host: str = "*", 
        port: int = 5555, 
        error_rate: float = 0.2,
        delay_min: float = 0.5,
        delay_max: float = 2.0
    ):
        """
        Initialize the dummy server.
        
        Args:
            host: Host to bind to (default: "*" - all interfaces)
            port: Port to bind to
            error_rate: Probability of generating an error response (0.0-1.0)
            delay_min: Minimum delay in seconds before responding
            delay_max: Maximum delay in seconds before responding
        """
        self.host = host
        self.port = port
        self.error_rate = error_rate
        self.delay_min = delay_min
        self.delay_max = delay_max
        self.context = zmq.asyncio.Context.instance()
        self.socket = self.context.socket(zmq.REP)
        self.running = False
        self.task: Optional[asyncio.Task] = None
        
    def bind(self) -> None:
        """Bind the socket to the host and port."""
        try:
            endpoint = f"tcp://{self.host}:{self.port}"
            self.socket.bind(endpoint)
            logger.info(f"Dummy Hugin server bound to {endpoint}")
        except zmq.ZMQError as e:
            logger.error(f"Failed to bind socket: {e}", exc_info=True)
            raise
            
    async def start(self) -> None:
        """Start the server and begin processing requests."""
        self.bind()
        self.running = True
        self.task = asyncio.create_task(self._process_requests())
        logger.info("Dummy Hugin server started")
        
    async def stop(self) -> None:
        """Stop the server."""
        self.running = False
        if self.task:
            await self.task
        self.socket.close()
        logger.info("Dummy Hugin server stopped")
        
    async def _process_requests(self) -> None:
        """Process incoming ZMQ requests."""
        while self.running:
            try:
                # Wait for request
                message = await self.socket.recv_string()
                logger.info(f"Received request: {message[:100]}...")
                
                # Parse YAML
                try:
                    config = yaml.safe_load(message)
                    logger.debug(f"Parsed config: {config}")
                except yaml.YAMLError as e:
                    logger.error(f"Failed to parse YAML: {e}", exc_info=True)
                    await self.socket.send_string(f"{ImageError.FATAL_UNKNOWN.value} Invalid YAML")
                    continue
                
                # Simulate processing time
                delay = random.uniform(self.delay_min, self.delay_max)
                logger.debug(f"Simulating processing delay of {delay:.2f}s")
                await asyncio.sleep(delay)
                
                # Determine response based on error rate
                if random.random() < self.error_rate:
                    # Generate a random error response
                    error = self._generate_random_error()
                    logger.warning(f"Simulating error response: {error}")
                    await self.socket.send_string(f"{error.value} Error")
                else:
                    # Success response
                    logger.info("Simulating successful image acquisition")
                    await self.socket.send_string(f"{ImageError.SUCCESS.value} Success")
                    
            except asyncio.CancelledError:
                logger.info("Server task cancelled")
                break
            except Exception as e:
                logger.error(f"Error processing request: {e}", exc_info=True)
                # Try to send an error response
                try:
                    await self.socket.send_string(f"{ImageError.FATAL_UNKNOWN.value} Internal error")
                except Exception:
                    pass
                
    def _generate_random_error(self) -> ImageError:
        """Generate a random error for testing purposes."""
        # Define possible errors and their weights
        errors = [
            (ImageError.MAIN_CORRUPT, 0.2),
            (ImageError.THREE_D0_CORRUPT, 0.2),
            (ImageError.THREE_D1_CORRUPT, 0.1),
            (ImageError.THREE_D2_CORRUPT, 0.1),
            (ImageError.THERMAL_CORRUPT, 0.2),
            (ImageError.RESET_TIMEOUT, 0.1),
            (ImageError.REBOOT_TIMEOUT, 0.05),
            (ImageError.FATAL_UNKNOWN, 0.05)
        ]
        
        # Sometimes return a combination of errors
        if random.random() < 0.3:
            # Return all 3D camera errors (common case from example)
            return ImageError.THREE_D0_CORRUPT | ImageError.THREE_D1_CORRUPT | ImageError.THREE_D2_CORRUPT
            
        # Otherwise return a single error based on weights
        total = sum(weight for _, weight in errors)
        r = random.uniform(0, total)
        upto = 0
        for error, weight in errors:
            upto += weight
            if upto >= r:
                return error
                
        # Fallback
        return ImageError.FATAL_UNKNOWN

async def run_server(
    host: str = "*", 
    port: int = 5555, 
    error_rate: float = 0.2,
    delay_min: float = 0.5,
    delay_max: float = 2.0
) -> None:
    """
    Run the dummy Hugin server.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        error_rate: Probability of generating an error response
        delay_min: Minimum delay before responding
        delay_max: Maximum delay before responding
    """
    server = DummyHuginServer(host, port, error_rate, delay_min, delay_max)
    try:
        await server.start()
        # Keep server running until interrupted
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Server interrupted, shutting down...")
    finally:
        await server.stop()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run a dummy Hugin ZMQ server for testing")
    parser.add_argument("--host", default="*", help="Host to bind to")
    parser.add_argument("--port", type=int, default=5555, help="Port to bind to")
    parser.add_argument("--error-rate", type=float, default=0.2, 
                      help="Probability of generating an error response (0.0-1.0)")
    parser.add_argument("--delay-min", type=float, default=0.5,
                      help="Minimum delay in seconds before responding")
    parser.add_argument("--delay-max", type=float, default=2.0,
                      help="Maximum delay in seconds before responding")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    
    asyncio.run(run_server(
        host=args.host,
        port=args.port,
        error_rate=args.error_rate,
        delay_min=args.delay_min,
        delay_max=args.delay_max
    ))