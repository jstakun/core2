from m5stack import *
from m5stack_ui import *
from uiflow import *
import math
import time
import ujson
import network
import sys
import deviceCfg
import wifiCfg
import machine
import ubinascii
import urequests
import _thread
import utime
from machine import Pin, PWM
from collections import OrderedDict
from imu import IMU

EMERGENCY_PAUSE_INTERVAL = 1800  #sec = 30 mins
MODES = ["full_elapsed", "full_date", "full_battery", "basic", "flip_full_elapsed", "flip_full_date", "flip_full_battery", "chart", "flip_chart"]

def getBatteryLevel():
  volt = power.getBatVoltage()
  if volt < 3.20: return -1
  if volt < 3.27: return 0
  if volt < 3.61: return 5
  if volt < 3.69: return 10
  if volt < 3.71: return 15
  if volt < 3.73: return 20
  if volt < 3.75: return 25
  if volt < 3.77: return 30
  if volt < 3.79: return 35
  if volt < 3.80: return 40
  if volt < 3.82: return 45
  if volt < 3.84: return 50
  if volt < 3.85: return 55
  if volt < 3.87: return 60
  if volt < 3.91: return 65
  if volt < 3.95: return 70
  if volt < 3.98: return 75
  if volt < 4.02: return 80
  if volt < 4.08: return 85
  if volt < 4.11: return 90
  if volt < 4.15: return 95
  if volt < 4.20: return 100
  if volt >= 4.20: return 101

def isOlderThan(date_str, mins): 
  the_date = getDateTuple(date_str)
  #TODO check TIMEZONE and add correct number of hours
  the_date_seconds = utime.mktime(the_date) #UTC+1
  #UTC
  now = utime.mktime((rtc.datetime()[0],rtc.datetime()[1],rtc.datetime()[2],rtc.datetime()[4],rtc.datetime()[5],rtc.datetime()[6],0,0))
  #print(str(the_date) + ":" + str(seconds) + " " + str(rtc.datetime()) + ":" + str(now))
  diff = (now - the_date_seconds + 3600)
  printTime(diff, prefix='Entry read', suffix='ago')
  return diff > (60 * mins)   

def getDateTuple(date_str):
  [yyyy, mm, dd] = [int(i) for i in date_str.split('T')[0].split('-')]
  [HH, MM, SS] = [int(i) for i in date_str.split('T')[1].split(':')]
  return (yyyy, mm, dd, HH, MM, SS, 0, 0, 0)    

def printTime(seconds, prefix='', suffix=''):
  m, s = divmod(seconds, 60)
  h, m = divmod(m, 60)
  print(prefix + ' {:02d}:{:02d}:{:02d} '.format(h, m, s) + suffix)  

def saveSgvFile(sgvdict):
  sgvfile = open('sgvdict.txt', 'w')
  for key in sgvdict:
    sgvfile.write(str(key) + ':' + str(sgvdict[key]) + '\n')
  sgvfile.close()  

def readSgvFile():
  d = OrderedDict()
  try: 
    sgvfile = open('sgvdict.txt', 'r')
    entries = sgvfile.read().split('\n')
    for entry in entries:
      if ":" in entry:
        [s, v] = [int(i) for i in entry.split(':')]
        d.update({s: v})
  except Exception as e:
    sys.print_exception(e)
  return d 

def checkBeeper():
  global USE_BEEPER, BEEPER_START_TIME, BEEPER_END_TIME 
  try:   
    if USE_BEEPER == 1:
      #TODO add to tm timezone
      d = utime.localtime(0)
      #UTC
      now = rtc.datetime() #utime.localtime(utime.time())
    
      c = list(d)
      c[3] = now[4]
      c[4] = now[5]
      c[5] = now[6]

      d1 = list(d)
      [HH, MM, SS] = [int(i) for i in BEEPER_START_TIME.split(':')]
      d1[3] = HH
      d1[4] = MM
      d1[5] = SS

      d2 = list(d)
      [HH, MM, SS] = [int(i) for i in BEEPER_END_TIME.split(':')]
      d2[3] = HH
      d2[4] = MM
      d2[5] = SS

      #print("Compare d1: " + str(d1) + ", d2: " + str(d2) + ", c: " + str(c))
      
      if tuple(d1) < tuple(d2):
         return tuple(c) > tuple(d1) and tuple(c) < tuple(d2)
      else:
         return tuple(c) > tuple(d1) or tuple(c) < tuple(d2)
    else:
      return False 
  except Exception as e:
    sys.print_exception(e)
    return True   

def printCenteredText(msg, font=lcd.FONT_DejaVu24, backgroundColor=lcd.BLACK, textColor=lcd.WHITE, clear=False):
  lcd.font(font)
  if clear == True:
     lcd.clear(backgroundColor)
  lcd.setTextColor(textColor)
  w = lcd.textWidth(msg)
  f = lcd.fontSize()
  lcd.fillRect(0, (int)(120-f[1]/2), 320, (int)(f[1]), backgroundColor)
  lcd.print(msg, (int)((320-w)/2), (int)((240-f[1])/2))

def printText(msg, x, y, cleanupMsg, font=lcd.FONT_DejaVu24, backgroundColor=lcd.BLACK, textColor=lcd.WHITE, clear=False, rotate=0):
  lcd.font(font, rotate=rotate)
  if clear == True:
     #lcd.clear(backgroundColor)
     lcd.fillRect(x, (int)(y), (int)(w), (int)(f[1]), backgroundColor)
  lcd.setTextColor(textColor)
  w = lcd.textWidth(cleanupMsg)
  f = lcd.fontSize()
  lcd.print(msg, x, y)

def printDirection(x, y, xshift=0, yshift=0, rotateAngle=0, arrowColor=lcd.WHITE, fillColor=lcd.WHITE):
  lcd.circle(x, y, 40, fillcolor=fillColor, color=fillColor)
  r = drawTriangle(x+xshift, y+yshift, arrowColor, rotateAngle)
  #lcd.circle(int(r[0]), int(r[1]), 4, fillcolor=arrowColor, color=arrowColor)

def printDoubleDirection(x, y, ytop=0, ybottom=0, rotateAngle=0, arrowColor=lcd.WHITE, fillColor=lcd.WHITE):
  lcd.circle(x, y, 40, fillcolor=fillColor, color=fillColor)
  drawTriangle(x, y+ytop, arrowColor, rotateAngle)
  r = drawTriangle(x, y+ybottom, arrowColor, rotateAngle) 
  #lcd.circle(int(r[0]), int(r[1]), 4, fillcolor=arrowColor, color=arrowColor)

def drawTriangle(centerX, centerY, arrowColor, rotateAngle=90, width=44, height=44):
  angle = math.radians(rotateAngle) # Angle to rotate

  # Vertex's coordinates before rotating
  x1 = centerX + width / 2
  y1 = centerY
  x2 = centerX - width / 2
  y2 = centerY + height / 2
  x3 = centerX - width / 2
  y3 = centerY - height / 2

  # Rotating
  x1r = ((x1 - centerX) * math.cos(angle) - (y1 - centerY) * math.sin(angle) + centerX)
  y1r = ((x1 - centerX) * math.sin(angle) + (y1 - centerY) * math.cos(angle) + centerY)
  x2r = ((x2 - centerX) * math.cos(angle) - (y2 - centerY) * math.sin(angle) + centerX)
  y2r = ((x2 - centerX) * math.sin(angle) + (y2 - centerY) * math.cos(angle) + centerY)
  x3r = ((x3 - centerX) * math.cos(angle) - (y3 - centerY) * math.sin(angle) + centerX)
  y3r = ((x3 - centerX) * math.sin(angle) + (y3 - centerY) * math.cos(angle) + centerY)

  lcd.fillTriangle(int(x1r), int(y1r), int(x2r), int(y2r), int(x3r), int(y3r), arrowColor)
  #lcd.triangle(int(x1r), int(y1r), int(x2r), int(y2r), int(x3r), int(y3r), fillcolor=arrowColor, color=arrowColor)
  return x1r, y1r, x2r, y2r, x3r, y3r 

def printScreen(clear=False, expiredData=False):
  global response, mode, brightness, emergency, emergencyPause, MIN, MAX, EMERGENCY_MIN, EMERGENCY_MAX, currentBackgroudColor, screenDrawing, startTime
  #320*240

  print('Printing screen in ' + MODES[mode] + ' mode')
  waitTime = 0.0
  while screenDrawing == True:
    time.sleep(0.1)
    waitTime += 0.1
    print(".", end="")

  if waitTime > 0: 
    print('Finished in ' + str(waitTime) + ' seconds')
  screenDrawing = True   

  newest = response[0]
  sgv = newest['sgv']
  sgvStr = str(sgv)
  #if sgv < 100: sgvStr = " " + sgvStr

  directionStr = newest['direction']
  
  tooOld = expiredData
  if tooOld == False:
   try:
     tooOld = isOlderThan(newest['date'], 30)
   except Exception as e:
     sys.print_exception(e)
  
  led = 0
  if tooOld: backgroundColor=lcd.DARKGREY; led = 1; emergency=False
  elif sgv <= EMERGENCY_MIN: backgroundColor=lcd.RED; led = 1; emergency=(utime.time() > emergencyPause and not tooOld)  
  elif sgv >= (MIN-10) and sgv < MIN and directionStr.endswith("Up"): backgroundColor=lcd.DARKGREEN; emergency=False; led = 0
  elif sgv > EMERGENCY_MIN and sgv <= MIN: backgroundColor=lcd.RED; led = 1; emergency=False
  elif sgv > MIN and sgv <= MAX: backgroundColor=lcd.DARKGREEN; emergency=False; led = 0 
  elif sgv > MAX and sgv <= (MAX+10) and directionStr.endswith("Down"): backgroundColor=lcd.DARKGREEN; emergency=False; led = 0
  elif sgv > MAX and sgv <= EMERGENCY_MAX: backgroundColor=lcd.ORANGE; led = 1; emergency=False
  elif sgv > EMERGENCY_MAX: backgroundColor=lcd.ORANGE; led = 1; emergency=(utime.time() > emergencyPause and not tooOld)  

  ledDevice = M5Led()
  if led == 1: ledDevice.set_on()
  else: ledDevice.set_off()
  
  #if emergency change to one of full modes 
  currentMode = mode
  if emergency == True and (mode == 3 or mode == 7): currentMode = 0
  
  #battery level emergency
  batteryLevel = getBatteryLevel()
  uptime = utime.time() - startTime  
  if (batteryLevel < 20 and batteryLevel > 0 and uptime > 300) and (utime.time() > emergencyPause) and not axp.getChargeState(): 
    emergency = True
    if currentMode < 4 or currentMode == 7: currentMode = 2
    else: currentMode = 6
    clear = True

  if "ago" in newest and (currentMode == 0 or currentMode == 4): 
    dateStr = newest['ago']
  elif currentMode == 2 or currentMode == 6:
    batteryLevel = getBatteryLevel()
    if batteryLevel >= 0:
       dateStr = "Battery: " + str(getBatteryLevel()) + "%"
    else: 
       dateStr = "Battery level unknown"
  else:   
    dateStr = newest['date'].replace("T", " ")[:-3] #remove seconds
  
  if clear or currentBackgroudColor != backgroundColor:
     lcd.clear(backgroundColor)
     currentBackgroudColor = backgroundColor
  else:
     print("Skip background clearing")

  h = str(rtc.datetime()[4])
  if (rtc.datetime()[4] < 10): h = "0" + h   
  m = str(rtc.datetime()[5])
  if (rtc.datetime()[5] < 10): m = "0" + m
  #s = str(rtc.datetime()[6])
  #if (rtc.datetime()[6] < 10): s = "0" + s
  timeStr = h + ":" + m

  if not tooOld and directionStr == 'DoubleUp' and sgv+20>=MAX: arrowColor = lcd.RED
  elif not tooOld and directionStr == 'DoubleDown' and sgv-20<=MIN: arrowColor = lcd.RED
  elif not tooOld and directionStr == 'SingleUp' and sgv+10>=MAX: arrowColor = lcd.ORANGE
  elif not tooOld and directionStr == 'SingleDown' and sgv-10<=MIN: arrowColor = lcd.ORANGE
  else: arrowColor = backgroundColor  

  batteryStr = str(getBatteryLevel()) + '%'

  sgvDiff = sgv-response[1]['sgv']
  sgvDiffStr = str(sgvDiff)
  if sgvDiff > 0: sgvDiffStr = "+" + sgvDiffStr
  #if sgvDiff < 10 and sgvDiff > -10: sgvDiffStr = "  " + sgvDiffStr
  
  #draw screen
  
  if currentMode in range (0,3):  

    lcd.fillRect(0, 0, 360, 180, backgroundColor)   

    #sgv 
    lcd.font(lcd.FONT_DejaVu72)
    w = lcd.textWidth(sgvStr)
    x = (int)((320 - w - 20 - 80) / 2)
    y = 120 - 36 - 8
    printText(sgvStr, x, y, "888", font=lcd.FONT_DejaVu72, backgroundColor=backgroundColor)

    #arrow
    x += w + 20 + 40
    y = 115 - 10
    
    if directionStr == 'DoubleUp': printDoubleDirection(x, y, ytop=-12, ybottom=4, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'DoubleDown': printDoubleDirection(x, y, ytop=-4, ybottom=12, rotateAngle=90, arrowColor=arrowColor) 
    elif directionStr == 'SingleUp': printDirection(x, y, xshift=0, yshift=-4, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'SingleDown': printDirection(x, y, xshift=0, yshift=4, rotateAngle=90, arrowColor=arrowColor)
    elif directionStr == 'Flat': printDirection(x, y, xshift=4, rotateAngle=0, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveUp': printDirection(x, y, xshift=4, yshift=-4, rotateAngle=-45, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveDown': printDirection(x, y, xshift=4, yshift=4, rotateAngle=45, arrowColor=arrowColor)

    #current time
    printText(timeStr, 10, 10, "88888", font=lcd.FONT_DejaVu18, backgroundColor=backgroundColor)  
  
    #battery
    w = lcd.textWidth(batteryStr)
    printText(batteryStr, (int)(320-5-w), 10, "88888", font=lcd.FONT_DejaVu18, backgroundColor=backgroundColor) 

    #sgv diff
    w = lcd.textWidth(sgvDiffStr)
    x = (int)((320-w)/2)
    printText(sgvDiffStr, x, 10, "888", font=lcd.FONT_DejaVu18, backgroundColor=backgroundColor)
  
    #dateStr
    lcd.font(lcd.FONT_DejaVu24)
    w = lcd.textWidth(dateStr)
    x = (int)((320-w)/2)
    y = 240-24-5
    lcd.fillRect(0, y-5, 360, 46, lcd.DARKGREY)
    printText(dateStr, x, y, "8888888888888", font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY)
  
  elif currentMode in range(4,7):
    #flip mode
    lcd.fillRect(0, 34, 360, 180, backgroundColor)   

    #sgv 
    lcd.font(lcd.FONT_DejaVu72)
    w = lcd.textWidth(sgvStr)
    x = (int)(320 - (320 - w - 20 - 80) / 2)
    if x > 275: x = 275
    y = 120 + 36
    printText(sgvStr, x, y, "888", font=lcd.FONT_DejaVu72, backgroundColor=backgroundColor, rotate=180)
    
    #arrow
    x -= (60 + w)
    y -= 30
    
    if directionStr == 'DoubleUp': printDoubleDirection(x, y, ytop=-4, ybottom=12, rotateAngle=90, arrowColor=arrowColor)
    elif directionStr == 'DoubleDown': printDoubleDirection(x, y, ytop=-12, ybottom=4, rotateAngle=-90, arrowColor=arrowColor) 
    elif directionStr == 'SingleUp': printDirection(x, y, xshift=0, yshift=4, rotateAngle=90, arrowColor=arrowColor)
    elif directionStr == 'SingleDown': printDirection(x, y, xshift=0, yshift=-4, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'Flat': printDirection(x, y, xshift=-4, rotateAngle=180, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveUp': printDirection(x, y, xshift=-4, yshift=4, rotateAngle=135, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveDown': printDirection(x, y, xshift=-4, yshift=-4, rotateAngle=-135, arrowColor=arrowColor)

    #current time
    printText(timeStr, 307, 222, "88888", font=lcd.FONT_DejaVu18, backgroundColor=backgroundColor, rotate=180)  
  
    #battery
    w = lcd.textWidth(batteryStr)
    printText(batteryStr, (int)(w+5), 222, "88888", font=lcd.FONT_DejaVu18, backgroundColor=backgroundColor, rotate=180) 

    #sgv diff
    w = lcd.textWidth(sgvDiffStr)
    x = (int)(w+(320-w)/2)
    printText(sgvDiffStr, x, 222, "888", font=lcd.FONT_DejaVu18, backgroundColor=backgroundColor, rotate=180)

    #dateStr
    lcd.font(lcd.FONT_DejaVu24)
    w = lcd.textWidth(dateStr)
    x = (int)(320-(320-w)/2)
    y = 24 + 5
    lcd.fillRect(0, 0, 360, 38, lcd.DARKGREY)
    printText(dateStr, x, y, "8888888888888", font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, rotate=180)  

  print("----------------------------")
  screenDrawing = False 

def backendMonitor():
  global response, INTERVAL, API_ENDPOINT, API_TOKEN, LOCALE, TIMEZONE, startTime, sgvDict
  backendRetry = (int)(INTERVAL/4)
  while True:
    try:
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Free memory: ' + str(gc.mem_free()) + ' bytes')
      printTime((utime.time() - startTime), prefix='Uptime is')
      print('Calling backend ...')
      s = utime.time()
      response = urequests.get(API_ENDPOINT + "/entries.json?count=10",headers={'api-secret': API_TOKEN,'accept-language': LOCALE,'accept-charset': 'ascii', 'x-gms-tz': TIMEZONE}).json()
      printTime((utime.time() - s), prefix='Response received in')
      print('Sgv:', response[0]['sgv'])
      print('Direction:', response[0]['direction'])
      print('Read: ' + response[0]['date'] + ' (' + TIMEZONE + ')')
      sgvDiff = response[0]['sgv'] - response[1]['sgv']
      print('Sgv diff from previous read:', sgvDiff)

      d = OrderedDict()
      seconds = -1
      for index, entry in enumerate(response):
        the_date = getDateTuple(entry['date'])  
        seconds = utime.mktime(the_date)
        d.update({seconds: entry['sgv']})

      dictLen = len(d)  
      for key in sgvDict:
        if key < seconds and dictLen < 50:
          d.update({key: sgvDict[key]})
        elif dictLen >= 50:
          break  
        dictLen = len(d)

      sgvDict = d
      saveSgvFile(d)
      print('Cached ' + str(dictLen) + " sgv entries")
      #print(sgvDict)  
      
      printScreen()
      time.sleep(INTERVAL)
    except Exception as e:
      sys.print_exception(e)
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      print('Network error. Retry in ' + str(backendRetry) + ' sec...')
      printScreen(expiredData=True)
      time.sleep(backendRetry)

def emergencyMonitor():
  global emergency, response
  while True:
    #print('Emergency monitor checking status')
    useBeeper = checkBeeper()
    if emergency == True:
      batteryLevel = getBatteryLevel()
      if batteryLevel < 20:
        print('Low battery level ' + str(batteryLevel) + "%!!!")
      else:
        print('Emergency glucose level ' + str(response[0]['sgv']) + '!!!')
      ledDevice = M5Led()
      ledDevice.set_on()
      if useBeeper == True:
        speaker.playTone(523, 2, volume=2)
      time.sleep(0.5)
      ledDevice.set_off()
      if useBeeper == True:
        speaker.playTone(523, 2, volume=2)
      time.sleep(0.5)
    else:
      #print('No emergency')
      time.sleep(2)

def mpuMonitor():
  global mpu, mode, response
  while True:
    acceleration = mpu.acceleration
    hasResponse = (response != '{}')
    if hasResponse and acceleration[1] < -0.1 and mode in range(0,3): mode += 4; printScreen(clear=True) #change to 'Flip mode' #4,5,6
    elif hasResponse and acceleration[1] > 0.1 and mode in range(4,7): mode -= 4; printScreen(clear=True) #change to 'Normal mode' #0,1,2
    elif hasResponse and acceleration[1] < -0.1 and mode == 7: mode = 8; printScreen(clear=True)
    elif hasResponse and acceleration[1] > 0.1 and mode == 8: mode = 7; printScreen(clear=True)
    #print("Acc:", str(acceleration))
    time.sleep(0.5)

def onBtnPressed():
  global emergency, emergencyPause
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + EMERGENCY_PAUSE_INTERVAL
  else:   
    global brightness
    brightness += 32
    if brightness > 128: brightness = 32
    screen = M5Screen()
    screen.set_screen_brightness(brightness)

# ------------------------------------------------------------------------------     

print('Starting...')
print('APIKEY: ' + deviceCfg.get_apikey())
macaddr=wifiCfg.wlan_sta.config('mac')
macaddr='{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}'.format(*macaddr)
print('MAC Adddress: ' + macaddr)
print('Free memory: ' + str(gc.mem_free()) + ' bytes')
machine_id = binascii.hexlify(machine.unique_id())
print('Machine unique id: ' + machine_id.decode())

response = '{}'
brightness = 32
emergency = False
emergencyPause = 0
currentBackgroudColor = -1
screenDrawing = False

screen = M5Screen()
screen.set_screen_brightness(brightness)

try: 
  confFile = open('config.json', 'r')
  config = ujson.loads(confFile.read())

  WIFI = config["wifi"]
  API_ENDPOINT = config["api-endpoint"]
  API_TOKEN = config["api-token"]
  LOCALE = config["locale"]
  INTERVAL = config["interval"]
  MIN = config["min"]
  MAX = config["max"]
  EMERGENCY_MIN = config["emergencyMin"]
  EMERGENCY_MAX = config["emergencyMax"] 
  TIMEZONE = config["timezone"]
  USE_BEEPER = config["beeper"]
  BEEPER_START_TIME = config["beeperStartTime"]
  BEEPER_END_TIME = config["beeperEndTime"]

  if INTERVAL<30: INTERVAL=30
  if MIN<30: MIN=30
  if MAX<100: MAX=100
  if EMERGENCY_MIN<30 or MIN<=EMERGENCY_MIN: EMERGENCY_MIN=MIN-10
  if EMERGENCY_MAX<100 or MAX>=EMERGENCY_MAX: EMERGENCY_MAX=MAX+10  
  if len(API_ENDPOINT)==0: raise Exception("Empty api-endpoint parameter")
  if len(WIFI)==0: raise Exception("Empty wifi parameter") 
  if USE_BEEPER != 1 and USE_BEEPER != 0: USE_BEEPER=1
  #TODO add TIMEZONE validation format GMT+/-10

  mpu = IMU()
  mode = 0
  if mpu.acceleration[1] < 0: mode = 4 #flip

  lcd.clear(lcd.DARKGREY)
except Exception as e:
  sys.print_exception(e)
  while True:
    printCenteredText("Fix config.json!", backgroundColor=lcd.RED, clear=True)
    time.sleep(2)
    printCenteredText("Restart required!", backgroundColor=lcd.RED, clear=True)
    time.sleep(2)  

nic = network.WLAN(network.STA_IF)
nic.active(True)

printCenteredText("Scanning wifi...", backgroundColor=lcd.DARKGREY)

found = False
while not found:
  try: 
    nets = nic.scan()
    for result in nets:
      ssid = result[0].decode() 
      if ssid in WIFI: found = True; SSID=ssid; WIFI_PASSWORD=WIFI[ssid]; break
  except Exception as e:
      sys.print_exception(e)
      printCenteredText("Wifi not found!", backgroundColor=lcd.RED, clear=True)  
  if not found: time.sleep(1)

printCenteredText("Connecting wifi...", backgroundColor=lcd.DARKGREY) #lcd.OLIVE)
nic.connect(SSID, WIFI_PASSWORD)
print('Connecting wifi ' + SSID)
while not nic.isconnected():
  print(".", end="")
  time.sleep(0.25)
print("")  

printCenteredText("Setting time...", backgroundColor=lcd.DARKGREY) #lcd.GREENYELLOW)

rtc.settime('ntp', host='pool.ntp.org', tzone=1)
print("Current UTC datetime " +  str(rtc.datetime()))
startTime = utime.time()

printCenteredText("Loading data...", backgroundColor=lcd.DARKGREY) #lcd.DARKGREEN)

sgvDict = readSgvFile()
dictLen = len(sgvDict)
print('Loaded ' + str(dictLen) + " sgv entries")

_thread.start_new_thread(backendMonitor, ())
_thread.start_new_thread(emergencyMonitor, ())
_thread.start_new_thread(mpuMonitor, ())

btnA.wasPressed(onBtnPressed)
btnB.wasPressed(onBtnPressed)
btnC.wasPressed(onBtnPressed)
