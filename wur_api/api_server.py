#!/usr/bin/env python3
"""
WUR API Server implementation for Hugin imaging system.

This server implements the Remote Imaging Interface API specified in 
RemoteImagingInterface_openapi_v3.yaml and translates REST requests to 
ZMQ messages for the Hugin system.
"""

import asyncio
import logging
import os
import uuid
import yaml
import time
import aiohttp
import socket
import dotenv
from datetime import datetime
from enum import IntFlag, auto
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Set, Tuple
from urllib.parse import urlparse
from contextlib import asynccontextmanager
import zmq.asyncio
from fastapi import FastAPI, HTTPException, Path as PathParam, Query, Body, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# Load environment variables
dotenv.load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f'wur_api_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    ]
)
logger = logging.getLogger(__name__)

# Get configuration from environment
HUGIN_ZMQ_HOST = os.getenv("HUGIN_ZMQ_HOST", "localhost")
HUGIN_ZMQ_PORT = int(os.getenv("HUGIN_ZMQ_PORT", "5555"))
HUGIN_ZMQ_TIMEOUT = float(os.getenv("HUGIN_ZMQ_TIMEOUT", "20.0"))
HUGIN_S3_BUCKET = os.getenv("HUGIN_S3_BUCKET", "hugin-images")
HUGIN_S3_BASE_PATH = os.getenv("HUGIN_S3_BASE_PATH", "images")
WUR_API_HOST = os.getenv("WUR_API_HOST", "0.0.0.0")
WUR_API_PORT = int(os.getenv("WUR_API_PORT", "8000"))

# Define ImageError enum (similar to trigger_image_acquisition.py)
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
    def parse_response(cls, response: bytes) -> Tuple['ImageError', Optional[str], Optional[str]]:
        """
        Parse the binary response from Hugin ZMQ server.
        
        Response format: "ERROR_CODE PLANT_ID IMAGE_DIRECTORY"
        
        Args:
            response: Raw ZMQ response bytes
            
        Returns:
            Tuple containing:
            - ImageError flag representing the error state
            - Plant ID (or None if not present/parseable)
            - Image directory (or None if not present/parseable)
        """
        try:
            # Convert to string and split by whitespace
            parts = response.decode('utf-8').strip().split()
            
            # Parse error code
            error_code = int(parts[0])
            error = cls(error_code)
            
            # Parse plant ID if present
            plant_id = parts[1] if len(parts) > 1 else None
            
            # Parse image directory if present
            image_dir = parts[2] if len(parts) > 2 else None
            
            logger.debug(f"Parsed ZMQ response: error={error}, plant_id={plant_id}, image_dir={image_dir}")
            return error, plant_id, image_dir
            
        except (ValueError, IndexError, UnicodeDecodeError) as e:
            logger.error(f"Failed to parse ZMQ response: {response}", exc_info=True)
            return cls.FATAL_UNKNOWN, None, None

# Pydantic models for API
class Message(BaseModel):
    """Message object returned by API"""
    MessageText: str = Field(description="Extra info about the status of the call")
    Type: str = Field(description="Type of message, possible values: 'None', 'Error', 'Warning', 'Message', 'Success'")
    
    @classmethod
    def none(cls, text: str = "") -> 'Message':
        """Create a 'None' type message."""
        return cls(MessageText=text, Type="None")
        
    @classmethod
    def error(cls, text: str) -> 'Message':
        """Create an 'Error' type message."""
        return cls(MessageText=text, Type="Error")
        
    @classmethod
    def warning(cls, text: str) -> 'Message':
        """Create a 'Warning' type message."""
        return cls(MessageText=text, Type="Warning")
        
    @classmethod
    def message(cls, text: str) -> 'Message':
        """Create a 'Message' type message."""
        return cls(MessageText=text, Type="Message")
        
    @classmethod
    def success(cls, text: str = "") -> 'Message':
        """Create a 'Success' type message."""
        return cls(MessageText=text, Type="Success")

class Response(BaseModel):
    """Response object describing status of the call"""
    Values: List[str] = Field(description="Values returned if any", default=[])
    Message: Message

class ImagingMetaData(BaseModel):
    """Group metadata of a plant"""
    PlantId: str = Field(description="Plant identifier, eg. QR code, datamatrix,... should be unique within experiment")
    ExperimentId: str = Field(description="Experiment identifier")
    TreatmentId: str = Field(description="Treatment identifier")
    Height: float = Field(description="Height at which the plant is elevated")
    Angle: float = Field(description="Angle at which the plant is rotated for imaging")

class CallBackRegistrationData(BaseModel):
    """Information required to register for notifications upon imaging events"""
    ClientName: str = Field(description="Name to identify a registered client")
    Uri: str = Field(description="Uri where notifications should be sent")
    SendPathInfo: bool = Field(description="Indicates whether to send the path where an image is stored in the notifications")
    SendData: bool = Field(description="Indicates whether to send the image data as binary blob in the notifications")
    HeartBeatInterval: int = Field(description="Interval in ms for heartbeat (0 = no heartbeat)")

# ZMQ Client for communicating with Hugin
class ZMQClient:
    """Async ZMQ client for communicating with Hugin."""
    
    def __init__(self, host: str = "localhost", port: int = 5555, timeout: float = 20.0):
        """Initialize ZMQ client."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.context = zmq.asyncio.Context.instance()
        self.socket = None
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.last_activity = time.time()
        self.create_socket()
        
    def create_socket(self) -> None:
        """Create a new ZMQ socket."""
        if self.socket:
            self.socket.close()
            
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.RCVTIMEO, int(self.timeout * 1000))
        self.socket.setsockopt(zmq.SNDTIMEO, int(self.timeout * 1000))
        self.socket.setsockopt(zmq.LINGER, 0)  # Don't wait for unsent messages when closing
        
    def _connect(self) -> bool:
        """
        Establish connection to ZMQ server.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            endpoint = f"tcp://{self.host}:{self.port}"
            self.socket.connect(endpoint)
            logger.info(f"Connected to ZMQ server at {endpoint}")
            self.connected = True
            self.reconnect_attempts = 0
            self.last_activity = time.time()
            return True
        except zmq.ZMQError as e:
            logger.error(f"Failed to connect to ZMQ server: {e}", exc_info=True)
            self.connected = False
            return False
    
    async def ensure_connection(self) -> bool:
        """
        Ensure that we have a valid connection to the ZMQ server.
        
        Returns:
            bool: True if connection is valid, False otherwise
        """
        # If we've never connected or if it's been too long since last activity
        if not self.connected or (time.time() - self.last_activity) > 300:  # 5 minutes
            self.create_socket()
            return self._connect()
            
        return self.connected
    
    async def reconnect(self) -> bool:
        """
        Attempt to reconnect to the ZMQ server.
        
        Returns:
            bool: True if reconnection successful, False otherwise
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Maximum reconnection attempts ({self.max_reconnect_attempts}) reached")
            return False
            
        self.reconnect_attempts += 1
        logger.warning(f"Attempting to reconnect to ZMQ server (attempt {self.reconnect_attempts})")
        
        # Create a new socket
        self.create_socket()
        
        # Try to connect
        if self._connect():
            logger.info("Successfully reconnected to ZMQ server")
            return True
        
        # Back off with increasing delay
        backoff_time = min(2 ** self.reconnect_attempts, 30)
        logger.info(f"Reconnection failed, waiting {backoff_time} seconds before next attempt")
        await asyncio.sleep(backoff_time)
        return False
            
    async def send(self, message: str) -> None:
        """Send message to the server."""
        try:
            # Ensure connection is valid
            if not await self.ensure_connection():
                if not await self.reconnect():
                    raise zmq.ZMQError(zmq.ENOTCONN, "Not connected to ZMQ server")
            
            logger.debug(f"Sending message: {message}")
            await self.socket.send_string(message)
            self.last_activity = time.time()
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                logger.error(f"Timeout sending message after {self.timeout}s")
            else:
                logger.error(f"Failed to send message: {e}", exc_info=True)
                
            # Try to reconnect
            await self.reconnect()
            raise
            
    async def receive(self) -> bytes:
        """Receive and process response from the server."""
        try:
            message = await self.socket.recv()
            logger.debug(f"Received raw response: {message}")
            self.last_activity = time.time()
            return message
        except zmq.ZMQError as e:
            if e.errno == zmq.EAGAIN:
                logger.error(f"Timeout waiting for response after {self.timeout}s")
            else:
                logger.error(f"Failed to receive message: {e}", exc_info=True)
                
            # Try to reconnect
            await self.reconnect()
            raise
            
    def close(self) -> None:
        """Close the socket."""
        if self.socket:
            self.socket.close()
            self.socket = None
        self.connected = False

# NotificationClient for sending notifications to registered clients
class NotificationClient:
    """Client for sending notifications to registered clients."""
    
    def __init__(self):
        """Initialize notification client."""
        self.session: Optional[aiohttp.ClientSession] = None
        self.http_timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout for HTTP requests
        
    async def ensure_session(self) -> aiohttp.ClientSession:
        """Ensure an aiohttp session is available."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.http_timeout)
        return self.session
        
    async def close(self):
        """Close the aiohttp session."""
        if self.session and not self.session.closed:
            await self.session.close()
            
    async def send_notification(self, uri: str, payload: Dict[str, Any]) -> bool:
        """
        Send a notification to a registered client.
        
        Args:
            uri: URI where to send the notification
            payload: Notification payload
            
        Returns:
            bool: True if notification was sent successfully, False otherwise
        """
        if not uri:
            logger.error("Cannot send notification: URI is empty")
            return False
            
        try:
            # Validate URI
            parsed_uri = urlparse(uri)
            if not parsed_uri.scheme or not parsed_uri.netloc:
                logger.error(f"Invalid URI for notification: {uri}")
                return False
                
            # Ensure session is available
            session = await self.ensure_session()
            
            # Send notification
            async with session.post(uri, json=payload) as response:
                if response.status < 200 or response.status >= 300:
                    logger.error(f"Notification to {uri} failed with status {response.status}")
                    return False
                    
                logger.info(f"Notification sent to {uri} successfully")
                return True
                
        except aiohttp.ClientError as e:
            logger.error(f"Error sending notification to {uri}: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending notification to {uri}: {e}", exc_info=True)
            return False
            
    async def send_heartbeat(self, uri: str) -> bool:
        """
        Send a heartbeat notification to a registered client.
        
        Args:
            uri: URI where to send the heartbeat
            
        Returns:
            bool: True if heartbeat was sent successfully, False otherwise
        """
        payload = {
            "Type": "Heartbeat",
            "Timestamp": datetime.now().isoformat(),
            "Status": "alive"
        }
        
        return await self.send_notification(uri, payload)
            
# API State - in memory for now, could be moved to a database
class APIState:
    """Manages state for the WUR API."""
    
    def __init__(self):
        self.zmq_client: Optional[ZMQClient] = None
        self.notification_client: NotificationClient = NotificationClient()
        self.current_metadata: Optional[Dict[str, Any]] = None
        self.current_settings: Optional[str] = None
        self.triggers: Dict[str, Dict[str, Any]] = {}  # Map trigger IDs to their status
        self.settings_files: List[str] = []
        self.registered_clients: Dict[str, CallBackRegistrationData] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}  # Map client name to heartbeat task
        
    def init_zmq_client(self, host: str = HUGIN_ZMQ_HOST, port: int = HUGIN_ZMQ_PORT, timeout: float = HUGIN_ZMQ_TIMEOUT):
        """Initialize ZMQ client."""
        if self.zmq_client:
            self.zmq_client.close()
        self.zmq_client = ZMQClient(host, port, timeout)
        logger.info(f"Initialized ZMQ client with host={host}, port={port}, timeout={timeout}s")
        
    def load_settings_files(self, settings_dir: str = "yaml"):
        """Load available settings files."""
        path = Path(settings_dir)
        if path.is_dir():
            self.settings_files = [f.stem for f in path.glob("*.yaml") if f.is_file()]
            logger.info(f"Loaded {len(self.settings_files)} settings files from {settings_dir}")
        else:
            logger.warning(f"Settings directory {settings_dir} not found")
            self.settings_files = []
            
    async def close(self):
        """Close all resources."""
        # Stop all heartbeat tasks
        for task in self.heartbeat_tasks.values():
            task.cancel()
            
        try:
            # Wait for all heartbeat tasks to complete
            await asyncio.gather(*self.heartbeat_tasks.values(), return_exceptions=True)
        except asyncio.CancelledError:
            pass
            
        # Close ZMQ client
        if self.zmq_client:
            self.zmq_client.close()
            
        # Close notification client
        await self.notification_client.close()
        
    def start_heartbeat_task(self, client_name: str, client_data: CallBackRegistrationData):
        """
        Start a heartbeat task for a client.
        
        Args:
            client_name: Name of the client
            client_data: Client registration data
        """
        # Cancel existing task if any
        if client_name in self.heartbeat_tasks and not self.heartbeat_tasks[client_name].done():
            self.heartbeat_tasks[client_name].cancel()
            
        # If heartbeat interval is 0, don't start a task
        if client_data.HeartBeatInterval <= 0:
            return
            
        # Start a new heartbeat task
        self.heartbeat_tasks[client_name] = asyncio.create_task(
            self._heartbeat_loop(client_name, client_data.Uri, client_data.HeartBeatInterval)
        )
        
    async def _heartbeat_loop(self, client_name: str, uri: str, interval_ms: int):
        """
        Heartbeat loop for a client.
        
        Args:
            client_name: Name of the client
            uri: URI where to send heartbeats
            interval_ms: Interval in milliseconds between heartbeats
        """
        interval_sec = max(interval_ms / 1000.0, 1.0)  # Ensure at least 1 second
        logger.info(f"Starting heartbeat loop for client {client_name} with interval {interval_sec:.1f}s")
        
        try:
            while True:
                # Send heartbeat
                success = await self.notification_client.send_heartbeat(uri)
                if not success:
                    logger.warning(f"Failed to send heartbeat to client {client_name}")
                    
                # Wait for next heartbeat
                await asyncio.sleep(interval_sec)
                
        except asyncio.CancelledError:
            logger.info(f"Heartbeat loop for client {client_name} cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in heartbeat loop for client {client_name}: {e}", exc_info=True)
            
    async def notify_image_acquisition(self, trigger_id: str, plant_id: str, image_dir: Optional[str] = None):
        """
        Notify registered clients about a new image acquisition.
        
        Args:
            trigger_id: ID of the trigger
            plant_id: ID of the plant
            image_dir: Directory where the image is stored (optional)
        """
        # If no clients are registered, do nothing
        if not self.registered_clients:
            return
            
        # Get trigger data
        trigger_data = self.triggers.get(trigger_id)
        if not trigger_data:
            logger.error(f"Cannot notify: trigger {trigger_id} not found")
            return
            
        # Prepare base notification payload
        payload = {
            "Type": "ImageAcquisition",
            "Timestamp": datetime.now().isoformat(),
            "TriggerId": trigger_id,
            "PlantId": plant_id,
            "Status": "success" if trigger_data.get("status") == "finished" else "error"
        }
        
        # Add image directory path info if available
        if image_dir and trigger_data.get("status") == "finished":
            # Construct path to the image in S3 bucket
            s3_path = f"{HUGIN_S3_BUCKET}/{HUGIN_S3_BASE_PATH}/{image_dir}"
            payload["ImagePath"] = s3_path
            payload["ImageId"] = f"{plant_id}_{image_dir}"
            
        # Add error info if available
        if "error" in trigger_data and trigger_data["error"] is not None:
            payload["Error"] = {
                "Code": trigger_data["error"],
                "Message": f"Error code: {trigger_data['error']}"
            }
            
        # Send notification to each registered client
        for client_name, client_data in self.registered_clients.items():
            logger.info(f"Sending image acquisition notification to {client_name}")
            
            # Determine what to include in the notification
            client_payload = payload.copy()
            
            # Include path info if requested
            if not client_data.SendPathInfo and "ImagePath" in client_payload:
                del client_payload["ImagePath"]
                
            # Include image data if requested (not implemented yet)
            if client_data.SendData:
                logger.warning(f"SendData option not implemented yet - client {client_name} requested image data")
                
            # Send notification
            success = await self.notification_client.send_notification(client_data.Uri, client_payload)
            if not success:
                logger.error(f"Failed to send notification to client {client_name}")
                
            # Log notification payload for debugging
            logger.debug(f"Notification payload for {client_name}: {client_payload}")

# Create FastAPI app
app = FastAPI(
    title="RemoteImagingInterface",
    description="REST API for the SMO WIWAM remote imaging interface",
    version="1.0.15.0",
    root_path="/RemoteImagingInterface"  # Match OpenAPI specification base path
)

# Create API state
state = APIState()

@asynccontextmanager
async def lifespan(app: FastAPI):
    state.init_zmq_client()
    state.load_settings_files()
    logger.info(f"WUR API server started on {WUR_API_HOST}:{WUR_API_PORT}")

    yield  # This separates startup from shutdown code

    await state.close()
    logger.info("WUR API server shut down")

app = FastAPI(
    title="RemoteImagingInterface",
    description="REST API for the SMO WIWAM remote imaging interface",
    version="1.0.15.0",
    root_path="/RemoteImagingInterface",  # Match OpenAPI specification base path
    lifespan=lifespan  # Add this line to use the lifespan context manager
)
# API endpoints
@app.get("/status", response_model=Response)
async def get_status():
    """Get overall status information."""
    try:
        # Check if any triggers are in 'busy' state
        busy_triggers = {tid: data for tid, data in state.triggers.items() 
                         if data.get("status") == "busy"}
        
        if busy_triggers:
            # Return the first busy trigger ID
            trigger_id = next(iter(busy_triggers.keys()))
            return Response(
                Values=[trigger_id],
                Message=Message.message("busy")
            )
        
        # Simple status check via ZMQ could be implemented here
        # For now, assume idle if no busy triggers
        return Response(
            Values=[],
            Message=Message.message("idle")
        )
    except Exception as e:
        logger.error(f"Error getting status: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message.error(f"Error getting status: {str(e)}")
        )

@app.get("/settings", response_model=Response)
async def get_settings():
    """Get a list of available settings files."""
    try:
        return Response(
            Values=state.settings_files,
            Message=Message.none()
        )
    except Exception as e:
        logger.error(f"Error getting settings list: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message.error(f"Error getting settings: {str(e)}")
        )

@app.put("/settings/{settings_name}", response_model=Response)
async def set_settings(settings_name: str = PathParam(..., description="Name of settings file")):
    """Apply a settings file for the next imaging task."""
    try:
        # Check if settings file exists
        if settings_name not in state.settings_files:
            return Response(
                Values=[],
                Message=Message(MessageText=f"Settings file '{settings_name}' not found", Type="Error")
            )
        
        # Store selected settings for later use
        state.current_settings = settings_name
        
        return Response(
            Values=[],
            Message=Message(MessageText="", Type="Success")
        )
    except Exception as e:
        logger.error(f"Error setting settings: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message(MessageText=f"Error setting settings: {str(e)}", Type="Error")
        )

@app.post("/metadata", response_model=Response)
async def set_metadata(metadata: ImagingMetaData = Body(...)):
    """Set new metadata for the next imaging task."""
    try:
        if not metadata:
            return Response(
                Values=[],
                Message=Message(MessageText="Received metadata is null", Type="Error")
            )
        
        # Store metadata for next imaging task
        state.current_metadata = metadata.model_dump()
        
        return Response(
            Values=[],
            Message=Message(MessageText="", Type="Success")
        )
    except Exception as e:
        logger.error(f"Error setting metadata: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message(MessageText=f"Error setting metadata: {str(e)}", Type="Error")
        )

@app.put("/trigger/{plant_id}", response_model=Response)
async def trigger(
    background_tasks: BackgroundTasks,
    plant_id: str = PathParam(..., description="ID of the plant to be imaged")
):
    """Trigger a new imaging task."""
    try:
        # Check if metadata is set
        if not state.current_metadata:
            return Response(
                Values=[],
                Message=Message(MessageText="No metadata provided before trigger", Type="Error")
            )
            
        # Check if plant ID matches metadata
        if plant_id != state.current_metadata.get("PlantId"):
            return Response(
                Values=[],
                Message=Message(
                    MessageText=f"Plant ID mismatch: {plant_id} != {state.current_metadata.get('PlantId')}",
                    Type="Warning"
                )
            )
        
        # Generate trigger ID
        trigger_id = str(uuid.uuid4())
        
        # Prepare ZMQ message based on current settings and metadata
        zmq_message = prepare_zmq_message(state.current_metadata, state.current_settings)
        
        # Store trigger information
        state.triggers[trigger_id] = {
            "status": "busy",
            "plant_id": plant_id,
            "timestamp": datetime.now().isoformat(),
            "settings": state.current_settings,
            "metadata": state.current_metadata,
            "image_id": None
        }
        
        # Send ZMQ message in background task
        background_tasks.add_task(
            process_trigger,
            trigger_id=trigger_id,
            zmq_message=zmq_message
        )
        
        return Response(
            Values=[trigger_id],
            Message=Message(MessageText="", Type="Success")
        )
    except Exception as e:
        logger.error(f"Error triggering image acquisition: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message(MessageText=f"Error triggering: {str(e)}", Type="Error")
        )

@app.get("/status/{trigger_id}", response_model=Response)
async def get_status_for_id(
    trigger_id: str = PathParam(..., description="ID provided by the Trigger call")
):
    """Get status information from a previously triggered plant."""
    try:
        # Check if trigger ID exists
        if trigger_id not in state.triggers:
            return Response(
                Values=[],
                Message=Message(MessageText="invalid", Type="Message")
            )
        
        # Return status
        status = state.triggers[trigger_id]["status"]
        return Response(
            Values=[],
            Message=Message(MessageText=status, Type="Message")
        )
    except Exception as e:
        logger.error(f"Error getting trigger status: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message(MessageText="error", Type="Message")
        )

@app.get("/getimageid/{trigger_id}", response_model=Response)
async def get_image_id(
    trigger_id: str = PathParam(..., description="ID provided by the Trigger call")
):
    """Get information of the taken image."""
    try:
        # Check if trigger ID exists
        if trigger_id not in state.triggers:
            return Response(
                Values=[],
                Message=Message(MessageText="Invalid trigger ID", Type="Error")
            )
        
        # Check if image is available
        trigger_data = state.triggers[trigger_id]
        if trigger_data["status"] != "finished":
            return Response(
                Values=[],
                Message=Message(
                    MessageText=f"Image not available, status: {trigger_data['status']}", 
                    Type="Error"
                )
            )
        
        # Return image ID if available
        image_id = trigger_data.get("image_id")
        if not image_id:
            return Response(
                Values=[],
                Message=Message(MessageText="Image ID not available", Type="Error")
            )
        
        return Response(
            Values=[image_id],
            Message=Message(MessageText="", Type="Success")
        )
    except Exception as e:
        logger.error(f"Error getting image ID: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message(MessageText=f"Error getting image ID: {str(e)}", Type="Error")
        )

@app.post("/register", response_model=Response)
async def register(registration_data: CallBackRegistrationData = Body(...)):
    """Register for notifications when images are taken."""
    try:
        # Validate registration data
        if not registration_data.ClientName:
            return Response(
                Values=[],
                Message=Message(MessageText="Client name is required", Type="Error")
            )
            
        if not registration_data.Uri:
            return Response(
                Values=[],
                Message=Message(MessageText="URI is required", Type="Error")
            )
            
        # Check if URI is valid
        try:
            parsed_uri = urlparse(registration_data.Uri)
            if not parsed_uri.scheme or not parsed_uri.netloc:
                return Response(
                    Values=[],
                    Message=Message(MessageText=f"Invalid URI: {registration_data.Uri}", Type="Error")
                )
        except Exception:
            return Response(
                Values=[],
                Message=Message(MessageText=f"Invalid URI: {registration_data.Uri}", Type="Error")
            )
            
        # Store registration data
        state.registered_clients[registration_data.ClientName] = registration_data
        
        # Start heartbeat task if requested
        if registration_data.HeartBeatInterval > 0:
            state.start_heartbeat_task(registration_data.ClientName, registration_data)
            logger.info(f"Started heartbeat for client {registration_data.ClientName} with interval {registration_data.HeartBeatInterval}ms")
        
        logger.info(f"Client {registration_data.ClientName} registered for notifications at {registration_data.Uri}")
        return Response(
            Values=[],
            Message=Message(MessageText="", Type="Success")
        )
    except Exception as e:
        logger.error(f"Error registering client: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message(MessageText=f"Error registering: {str(e)}", Type="Error")
        )

@app.post("/unregister", response_model=Response)
async def unregister(client_name: str = Query(..., alias="ClientName")):
    """Unregister a client from receiving notifications."""
    try:
        # Remove client from registered clients
        if client_name in state.registered_clients:
            # Stop heartbeat task if exists
            if client_name in state.heartbeat_tasks and not state.heartbeat_tasks[client_name].done():
                state.heartbeat_tasks[client_name].cancel()
                
            # Remove client from registered clients
            del state.registered_clients[client_name]
            logger.info(f"Client {client_name} unregistered")
            
            return Response(
                Values=[],
                Message=Message(MessageText="", Type="Success")
            )
        else:
            logger.warning(f"Attempted to unregister non-existent client: {client_name}")
            return Response(
                Values=[],
                Message=Message(MessageText=f"Client '{client_name}' not registered", Type="Error")
            )
    except Exception as e:
        logger.error(f"Error unregistering client: {e}", exc_info=True)
        return Response(
            Values=[],
            Message=Message(MessageText=f"Error unregistering: {str(e)}", Type="Error")
        )

# Helper functions
def prepare_zmq_message(metadata: Dict[str, Any], settings_name: Optional[str]) -> str:
    """Prepare ZMQ message from metadata and settings."""
    # Load settings file if specified
    settings = {}
    if settings_name:
        settings_path = Path(f"yaml/{settings_name}.yaml")
        if settings_path.exists():
            try:
                with open(settings_path) as f:
                    settings = yaml.safe_load(f)
            except Exception as e:
                logger.error(f"Error loading settings file: {e}", exc_info=True)
    
    # Combine metadata with settings
    message = {
        "required": {
            "path": settings.get("path", "test/test/"),
            "plant-id": metadata.get("PlantId", ""),
            "uuid": str(uuid.uuid4()),
            "time-stamp": datetime.now().strftime("%Y-%m-%d-%H-%M-%S"),
            "position": {
                "greenhouse": settings.get("greenhouse", "default"),
                "is-fixed": True,
                "fixed": {
                    "x": 1.0,
                    "y": 1.0
                }
            },
            "sensors": settings.get("sensors", {
                "spectral": {"in-use": True, "default-settings": True},
                "thermal": {"in-use": True, "default-settings": True},
                "3D": {"in-use": True, "default-settings": True}
            })
        }
    }
    
    # Add metadata-specific fields
    if "Height" in metadata:
        message["required"]["height"] = metadata["Height"]
    if "Angle" in metadata:
        message["required"]["angle"] = metadata["Angle"]
    if "ExperimentId" in metadata:
        message["required"]["experiment-id"] = metadata["ExperimentId"]
    if "TreatmentId" in metadata:
        message["required"]["treatment-id"] = metadata["TreatmentId"]
    
    return yaml.dump(message, default_flow_style=False, allow_unicode=True)

async def process_trigger(trigger_id: str, zmq_message: str):
    """Process a trigger request asynchronously."""
    try:
        # Send ZMQ message
        await state.zmq_client.send(zmq_message)
        
        # Receive response
        response = await state.zmq_client.receive()
        
        # Parse response - get error code, plant_id, and image_dir
        error, plant_id, image_dir = ImageError.parse_response(response)
        
        # Get plant ID from trigger data if not in response
        if not plant_id and trigger_id in state.triggers:
            plant_id = state.triggers[trigger_id].get("plant_id")
        
        # Update trigger status
        if error == ImageError.SUCCESS:
            # Generate image ID using plant ID and directory
            image_id = f"{plant_id}_{image_dir}" if plant_id and image_dir else f"img_{trigger_id}"
            
            # Update trigger data
            state.triggers[trigger_id].update({
                "status": "finished",
                "image_id": image_id,
                "image_dir": image_dir,
                "error": None,
                "completed_at": datetime.now().isoformat()
            })
            
            logger.info(f"Trigger {trigger_id} completed successfully: image_id={image_id}, image_dir={image_dir}")
            
            # Notify registered clients
            await state.notify_image_acquisition(trigger_id, plant_id, image_dir)
            
        else:
            # Handle error case
            error_value = error.value
            state.triggers[trigger_id].update({
                "status": "error",
                "error": error_value,
                "error_at": datetime.now().isoformat()
            })
            
            # Log specific errors
            logger.error(f"Image acquisition error for trigger {trigger_id}: {error}")
            
            # Notify registered clients of error
            await state.notify_image_acquisition(trigger_id, plant_id, None)
            
    except asyncio.CancelledError:
        logger.warning(f"Trigger {trigger_id} processing cancelled")
        raise
        
    except Exception as e:
        logger.error(f"Error processing trigger {trigger_id}: {e}", exc_info=True)
        
        # Update trigger status
        if trigger_id in state.triggers:
            state.triggers[trigger_id].update({
                "status": "error",
                "error": str(e),
                "error_at": datetime.now().isoformat()
            })
            
            # Try to notify registered clients of error
            try:
                plant_id = state.triggers[trigger_id].get("plant_id")
                await state.notify_image_acquisition(trigger_id, plant_id, None)
            except Exception as notify_error:
                logger.error(f"Error sending error notification for trigger {trigger_id}: {notify_error}")
                
    finally:
        # Make sure we don't leave the trigger in "busy" state indefinitely
        if trigger_id in state.triggers and state.triggers[trigger_id].get("status") == "busy":
            logger.warning(f"Trigger {trigger_id} left in busy state, setting to error")
            state.triggers[trigger_id]["status"] = "error"
            state.triggers[trigger_id]["error"] = "Unexpected state"

# Run the server with uvicorn if script is executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WUR_API_HOST, port=WUR_API_PORT, log_level=log_level.lower())