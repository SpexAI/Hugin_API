# Hugin_API
 
 Documentation on how to interact with Hugin

 ## Prerequistes 

 Interaction with Hugin will happen over [ZeroMq ](https://zeromq.org/get-started/)

 # Trigger of the Image accquistion 

 Send the **guidline.yaml** file over **tcp:TBD** to Hugin using **ZeroMQ:TBD**. 

# Stream 3D Distance

See *TBD* example on how to trigger the avg. distance stream to bring the sensor into position. 

# Stream LiveView

Send the **live-stream.yaml** file over **tcp:TBD** to Hugin using **ZeroMQ:TBD** to trigger the live stream feed of any camera. 
The response wil be the **live-stream-response.yaml** which contains the local Ip and **udp** ports for the gstreamer sink. example client `gst-launch-1.0 udpsrc port=5000 ! application/x-rtp, payload=26 ! rtpjpegdepay ! jpegdec ! videoconvert ! autovideosink`

# Overview of the whole pipeline 

![Flow Diagram](Data_Flow_Client_side_v0.drawio.svg?raw=true&sanitize=true "Flow Diagram")
