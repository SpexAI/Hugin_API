 ![oben2_color_c0016](https://user-images.githubusercontent.com/52712273/194772406-301799a8-56ae-4c6d-ab00-7fc085bcd007.jpg)


 # Hugin API Client

A Python client for interacting with SpexAI's [Hugin](https://spexai.com/hugin/) image acquisition system. This client enables automated control and monitoring of Hugin's multi-sensor imaging system.

![Flow Diagram](Data_Flow_Client_side_v0.drawio.svg?raw=true&sanitize=true "Flow Diagram")

## Overview

The Hugin API client provides a robust interface for:
- Configuring image acquisition parameters
- Triggering synchronized multi-sensor captures
- Monitoring system status and error conditions
- Managing data collection workflows

The client uses ZMQ (ZeroMQ) for reliable communication with the Hugin system, supporting both synchronous and asynchronous operations.

## Installation

```bash
# Clone the repository
git clone https://github.com/SpexAI/Hugin_API.git

# Install dependencies
pip install -r python_examples/requirements.txt

# For WUR API server additional dependencies
pip install fastapi uvicorn aiohttp python-dotenv
```

## Usage

### Basic Example

```python
import asyncio
from hugin_client import ZMQClient

async def main():
    # Initialize client
    client = ZMQClient(host="localhost", port=5555)
    
    # Send trigger command
    await client.send_trigger()
    
    # Get response
    response = await client.receive()
    
    # Process error codes
    client.process_error_code(response)

if __name__ == "__main__":
    asyncio.run(main())
```

### YAML Configuration

The client uses YAML configuration files to specify image acquisition parameters. Here's an example configuration:

```yaml
required:
  path: 'test/test/'             # Path to the bucket
  plant-id: 'plant-id'           # Plant ID as used by client
  uuid: 'uuid'                   # UUID given by the system
  time-stamp: 'yy-mm-dd-hh-mm-ss'# UTC always
  position:
    greenhouse: 'greenhouse-name' # As it appears in the front end
    is-fixed: true               # false if one fixed position or table
    fixed:
      x: 1.2                     # Position x on the greenhouse grid
      y: 1.6                     # Position y on the greenhouse grid
    table:
      table-id: 'table-id'       # ID of the table
      row: 0                     # Row position on the table
      col: 0                     # Col position on the table
  sensors:
    spectral:
      in-use: true
      default-settings: true
    thermal:
      in-use: true
      default-settings: true
    3D:
      in-use: true
      default-settings: true
      settings:
        preset: 'day'            # The D415 can be configured through a config.json
```

### Error Code Handling

The client includes comprehensive error code handling for various system states:

| Code | Description | Details |
|------|-------------|---------|
| 0    | SUCCESS     | ≥ 1 main, ≥ 2 3ds, ≥ thermal images captured |
| 1    | MAIN_CORRUPT| No or corrupt main image |
| 2    | 3D0_CORRUPT | No or corrupt 3D camera 0 |
| 4    | 3D1_CORRUPT | No or corrupt 3D camera 1 |
| 8    | 3D2_CORRUPT | No or corrupt 3D camera 2 |
| 16   | THERMAL_CORRUPT | No or corrupt thermal image |
| 32   | RESET_TIMEOUT  | Timeout for reset (30s) |
| 64   | REBOOT_TIMEOUT | Timeout for reboot (1m) |
| 128  | FATAL_UNKNOWN  | Fatal unknown error |

Common combinations:
- 14: All 3D cameras missing (2 + 4 + 8)
- 15: Only thermal present (1 + 2 + 4 + 8)

### Test Client Usage

The test client includes a command-line interface for system testing:

```bash
python test_client.py --host 192.168.1.100 --port 5555 --config config.yaml --debug
```

Options:
- `--host`: Hugin system hostname/IP (default: localhost)
- `--port`: ZMQ port number (default: 5555)
- `--config`: Path to YAML config file
- `--debug`: Enable debug logging

The test client provides:
- Detailed error logging and reporting
- Connection status monitoring
- Configuration validation
- System state verification

### Error Handling Example

```python
from hugin_client import ImageError, ZMQClient

async def handle_acquisition():
    client = ZMQClient()
    response = await client.receive()
    error = ImageError.parse_response(response)
    
    if error == ImageError.SUCCESS:
        logger.info("Acquisition successful")
        return True
        
    if error & ImageError.THREE_D0_CORRUPT:
        logger.error("3D camera 0 failed")
    
    if error.value == 14:
        logger.error("All 3D cameras missing")
        
    return False
```

### WUR API

# Remote Imaging Interface API Documentation

## Overview

The Remote Imaging Interface API enables interaction with cameras via a remote plugin mechanism. This API allows users to control camera settings, trigger imaging tasks, monitor status, and retrieve image data.

## API Workflow

The WIWAM software uses this API in the following sequence:

1. Check camera status using `/status`
2. Get available settings files using `/settings`
3. Select a settings file using `/settings/{settingsName}`
4. Provide metadata for the imaging task using `/metadata`
5. Trigger an imaging task using `/trigger/{plantId}`
6. Poll the status of the trigger using `/status/{triggerId}`
7. Retrieve the image location using `/getimageid/{triggerId}` (after successful completion)
8. Return to step 1

## Base URLs

- `http://localhost/RemoteImagingInterface`
- `https://localhost/RemoteImagingInterface`

## Running the WUR API Server

The WUR API server implements the Remote Imaging Interface defined in the OpenAPI specification. It acts as a bridge between REST clients and the Hugin ZMQ interface.

```bash
# Start the server
python -m wur_api.api_server

# Server will be available at http://localhost:8000
```

## Testing with the Dummy Hugin Server

For development and testing without a physical Hugin system, use the dummy Hugin server:

```bash
# Start the dummy Hugin ZMQ server
python -m wur_api.dummy_hugin --port 5555 --error-rate 0.2

# In another terminal, start the WUR API server
python -m wur_api.api_server
```

The dummy server simulates the behavior of a real Hugin system, including occasional errors, to test the API's error handling capabilities.

## Endpoints

### Check Camera Status

```
GET /status
```

Gets the overall status of the imaging system.

**Response Types:** Error, Message

**Possible Status Values:**
- `idle`: No action is ongoing, system is ready for a new imaging task
- `busy`: An imaging task is ongoing (triggerId is provided in the output)
- `error`: System is in error state, manual intervention required

**Example Response:**
```json
{
  "Values": [],
  "Message": {
    "MessageText": "idle",
    "Type": "Message"
  }
}
```

### List Available Settings

```
GET /settings
```

Gets a list of available settings files.

**Response Types:** None, Error, Message

**Example Response:**
```json
{
  "Values": ["setting1", "setting2"],
  "Message": {
    "MessageText": "",
    "Type": "None"
  }
}
```

### Apply Settings

```
PUT /settings/{settingsName}
```

Applies a settings file for the next imaging task.

**Parameters:**
- `settingsName` (path): Name/identifier of a group of settings

**Response Types:** Error, Success

**Example Response:**
```json
{
  "Values": [],
  "Message": {
    "MessageText": "",
    "Type": "Success"
  }
}
```

### Set Metadata

```
POST /metadata
```

Sets new metadata for the next imaging task.

**Request Body:** `ImagingMetaData` object

**Response Types:** Error, Success

**Example Response (Error):**
```json
{
  "Values": [],
  "Message": {
    "MessageText": "Received metadata is null",
    "Type": "Error"
  }
}
```

### Trigger Imaging Task

```
PUT /trigger/{plantId}
```

Triggers a new imaging task.

**Parameters:**
- `plantId` (path): ID of the plant to be imaged (should match ID provided via metadata)

**Response Types:** Error, Warning, Success

**Example Response (Success):**
```json
{
  "Values": ["triggerId"],
  "Message": {
    "MessageText": "",
    "Type": "Success"
  }
}
```

### Check Trigger Status

```
GET /status/{triggerId}
```

Gets status information for a previously triggered plant.

**Parameters:**
- `triggerId` (path): ID provided by the Trigger call

**Response Type:** Message

**Possible Status Values:**
- `finished`: Imaging task completed
- `busy`: Imaging task in progress
- `invalid`: Invalid trigger ID
- `error`: Error occurred during imaging

**Example Response:**
```json
{
  "Values": [],
  "Message": {
    "MessageText": "finished",
    "Type": "Message"
  }
}
```

### Get Image ID

```
GET /getimageid/{triggerId}
```

Gets information about the captured image.

**Parameters:**
- `triggerId` (path): ID provided by the Trigger call

**Response Types:** Error, Message

**Example Response (Error):**
```json
{
  "Values": [],
  "Message": {
    "MessageText": "Camera is in error",
    "Type": "Error"
  }
}
```

### Register for Notifications

```
POST /register
```

Registers the client to receive notifications when images are taken.

**Request Body:** `CallBackRegistrationData` object

**Response Types:** Success, Error

**Example Response:**
```json
{
  "Values": [],
  "Message": {
    "MessageText": "",
    "Type": "Success"
  }
}
```

### Unregister from Notifications

```
POST /unregister
```

Unregisters a client from receiving notifications.

**Parameters:**
- `ClientName` (query): Client identifier

**Response Types:** Success, Error

**Example Response:**
```json
{
  "Values": [],
  "Message": {
    "MessageText": "",
    "Type": "Success"
  }
}
```

## Data Models

### ImagingMetaData

```json
{
  "PlantId": "string",        // Plant identifier, unique within experiment
  "ExperimentId": "string",   // Experiment identifier
  "TreatmentId": "string",    // Treatment identifier
  "Height": 0.0,              // Height at which the plant is elevated
  "Angle": 0.0                // Angle at which the plant is rotated for imaging
}
```

### CallBackRegistrationData

```json
{
  "ClientName": "string",     // Name to identify a registered client
  "Uri": "string",            // URI where notifications should be sent
  "SendPathInfo": true,       // Whether to send the path where an image is stored
  "SendData": true,           // Whether to send the image data as binary blob
  "HeartBeatInterval": 0      // Interval in ms for heartbeat (0 = no heartbeat)
}
```

### Response

```json
{
  "Values": ["string"],       // Values returned, if any
  "Message": {
    "MessageText": "string",  // Extra info about the status of the call
    "Type": "string"          // Type: None, Error, Warning, Message, Success
  }
}
```


## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Create a Pull Request

## License

This project is licensed under the [MIT License](LICENSE).

## Support

For support and questions about the Hugin system, please contact SpexAI support or visit [spexai.com/hugin](https://spexai.com/hugin/).


