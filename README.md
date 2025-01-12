# Glucose level monitor for M5Stack Core2 device

With this application you can visualize on M5Stack Core2 devices glucose level readings stored in Nightscout API cloud database.

In order to run this application you must first copy [main.py](main.py), [ap.py](app.py), config.html and success.html to the M5Stack Core2 device.

When you boot the device for the first time it will open wifi named AP-M5DiabConf. Connect to it and open in web browser url http://192.168.4.1. Enter all mandatory configuration parameters: ssid, wifi_password, api_endpoint, api_token. When you are done click on "Save Configuration' button at the bottom and wait until M5Stack Core2 device reboots, connects to your wifi and starts downloading glucose level readings from Nightscout API endpoint.

This application has been tested with xDrip+ application installed od Android mobile phone as source of glucose level readings from CGM system.

If you are interested in using my managed Nightscout cloud database instance to store glucose level readings from your GCM device or if you have any other questions related to this project please contact me at support@gms-world.net. 