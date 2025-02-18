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
pip install zmq pyyaml asyncio
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


