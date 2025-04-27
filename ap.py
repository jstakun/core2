try:
  import usocket as socket
except:
  import socket
import network
import esp
esp.osdebug(None)
import nvs
import uos

SSID = 'AP-M5DiabConf'
PASSWORD = '123456789'
CONFIG = 'config'

ipconfig = None

def randstr(length=20):
    source = 'abcdefghijklmnopqrstuvwxyz1234567890'
    return ''.join([source[x] for x in [(uos.urandom(1)[0] % len(source)) for _ in range(length)]])

def readHtmlFile(filename):
    htmlFile = open(filename, 'r')
    html = htmlFile.read()
    htmlFile.close()
    return html

def unquote(string):
    if not string:
        return b''

    if isinstance(string, str):
        string = string.encode('utf-8')

    bits = string.split(b'%')
    if len(bits) == 1:
        return string

    res = bytearray(bits[0])
    append = res.append
    extend = res.extend

    for item in bits[1:]:
        try:
            append(int(item[:2], 16))
            extend(item[2:])
        except KeyError:
            append(b'%')
            extend(item)

    return bytes(res)

def open_access_point(successCallback):

  ap = network.WLAN(network.AP_IF)
  ap.active(True)
  ssid = SSID + "-" + randstr(5)
  ap.config(essid=ssid, password=PASSWORD)
  ap.config(max_clients=1) 

  while ap.active() == False:
    pass
  
  ipconfig = ap.ifconfig()

  print('AP config: ' + str(ipconfig))

  s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  s.bind(('', 80))
  s.listen(5)

  configHtml = readHtmlFile('config.html')
  successHtml = readHtmlFile('success.html')

  print('Web server is running on port 80')

  while True:
    conn, addr = s.accept()
    print('Got a connection from %s' % str(addr))
    request = conn.recv(1024)
    contentStr = request.decode()
    print('Content = %s' % contentStr)
    splittedRequest = contentStr.split()
    #rmethod = splittedRequest[0]
    rurl = splittedRequest[1]
  
    conn.send('HTTP/1.1 200 OK\n')
    conn.send('Content-Type: text/html\n')
    conn.send('Connection: close\n\n')

    if rurl.find("/config") != -1:
      splittedRequest = contentStr.split('\r\n')
      configParams = splittedRequest[len(splittedRequest)-1]
      print('Config params: ' + configParams) 
      entries = configParams.split('&') 
      wifi_ssid = None
      wifi_password = None
      for entry in entries:
        [k,v] = entry.split('=')
        #max nvs key length = 15
        if len(k) > 15: k = k[0:15]
        value = unquote(v).decode()
        if k == 'ssid': wifi_ssid = value
        elif k == 'wifi_password': wifi_password = value  
        elif value.isdigit(): value = int(value) 
        if k != 'ssid' and k != 'wifi_password':
          nvs.write(k, value)
          print("Saved config parameter " + k)
      if len(wifi_ssid) > 15: wifi_ssid = wifi_ssid[0:15]    
      nvs.write(wifi_ssid, wifi_password)
      print("Saved config parameter " + wifi_ssid)
      nvs.write(CONFIG, 1)  
      successCallback()
      conn.send(successHtml)   
    else: 
      conn.send(configHtml)
      
    conn.close()