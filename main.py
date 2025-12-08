#UiFlow2 https://uiflow-micropython.readthedocs.io/en/develop/

import M5
import ntptime
from hardware import WDT, I2C, Pin
import machine
import requests2
import math
import os
import time
import network
import sys
import _thread
import utime
from collections import OrderedDict
import re
import ap
import ujson
from unit import ENVUnit, RGBUnit

EMERGENCY_PAUSE_INTERVAL = 1800  #sec = 30 mins
MODES = ["full_elapsed", "full_date", "full_battery", "basic", "flip_full_elapsed", "flip_full_date", "flip_full_battery", "chart", "flip_chart"]
SGVDICT_FILE = 'sgvdict.txt'
RESPONSE_FILE = 'response.json'
BACKEND_TIMEOUT_MS = 30000 #max 60000
MAX_SAVED_ENTRIES = 10
YEAR = 2025

BLACK = 0x000000
WHITE = 0xFFFFFF
RED = 0xFF0000
GREEN = 0x00FF00
BLUE = 0x0000FF
ORANGE = 0xFFA500
DARKGREY = 0x404040
DARKGREEN = 0x006400

drawScreenLock = _thread.allocate_lock()

def getBatteryLevel():
  return M5.Power.getBatteryLevel() 

def isOlderThan(date_str, mins, now_seconds, print_time=False): 
  the_date = getDateTuple(date_str)
  the_date_seconds = utime.mktime(the_date)
  #print("Date: " + str(the_date) + " - " + str(the_date_seconds) + ", Now: " + str(now_seconds))
  diff = (now_seconds - the_date_seconds)
  if print_time == True:
     printTime(diff, prefix='Entry read', suffix='ago')
  return (diff > (60 * mins) and getBatteryLevel() >= 5)  

def getDateTuple(date_str):
  [yyyy, mm, dd] = [int(i) for i in date_str.split('T')[0].split('-')]
  [HH, MM, SS] = [int(i) for i in date_str.split('T')[1].split(':')]
  return (yyyy, mm, dd, HH, MM, SS, 0, 0)    

def printTime(seconds, prefix='', suffix=''):
  m, s = divmod(seconds, 60)
  h, m = divmod(m, 60)
  print(prefix + ' {:02d}:{:02d}:{:02d} '.format(h, m, s) + suffix)  

def saveConfigFile():
  global config
  try:
    with open(ap.CONFIG_FILE, 'w') as confFile:
      ujson.dump(config, confFile) 
    print("Successfully saved config file")
  except Exception as e:
    sys.print_exception(e) 
    saveError(e)
 
def saveResponseFile():
  global response
  with open(RESPONSE_FILE, 'w') as responseFile:
    ujson.dump(response, responseFile) 
 
def readResponseFile():
  global response
  try:
    with open(RESPONSE_FILE, 'r') as responseFile:
      response = ujson.loads(responseFile.read())
  except Exception as e:
    sys.print_exception(e)
    saveError(e)
    response = None
    
def saveSgvFile(sgvdict):
  items = []
  for key in sgvdict:
    items.append(str(key) + ':' + str(sgvdict[key]))
  content = '\n'.join(items)
  with open(SGVDICT_FILE, 'w') as file:
    file.write(content)

def readSgvFile():
  d = OrderedDict()
  try: 
    with open(SGVDICT_FILE, 'r') as f:
      sgvFile = f.read()
    if sgvFile != None:
      entries = sgvFile.split('\n')
      for entry in entries:
        if ":" in entry:
          [s, v] = [int(i) for i in entry.split(':')]
          d.update({s: v})   
  except Exception as e:
    sys.print_exception(e)
    saveError(e)
  return d 

def saveError(e):
  now = utime.ticks_cpu()
  filename = "error" + str(now) + ".txt"
  with open(filename, 'w') as file:
    sys.print_exception(e, file)

def persistEntries():
  global response, sgvDict
  saveResponseFile()
  d = OrderedDict()
  seconds = -1
  for index, entry in enumerate(response):
    the_date = getDateTuple(entry['date'])  
    seconds = utime.mktime(the_date)
    d.update({seconds: entry['sgv']})
  
  dictLen = len(d)  
  for key in sgvDict:
    if key < seconds and dictLen < MAX_SAVED_ENTRIES:
       d.update({key: sgvDict[key]})
    elif dictLen >= MAX_SAVED_ENTRIES:
      break  
    dictLen = len(d)

  sgvDict = d
  saveSgvFile(d)
  print('\nPersisted ' + str(dictLen) + " sgv entries")

def checkBeeper():
  global USE_BEEPER, BEEPER_START_TIME, BEEPER_END_TIME, secondsDiff
  try:   
    if (USE_BEEPER == 1 and getBatteryLevel() >= 5):
      d = utime.localtime(0)
      now_datetime = utime.localtime(utime.time()) 
      if now_datetime[0] < YEAR:
        raise ValueError('Invalid datetime: ' + str(now_datetime))
      now = utime.mktime((now_datetime[0], now_datetime[1], now_datetime[2], now_datetime[3], now_datetime[4], now_datetime[5],0,0))
      localtime = utime.localtime(now + secondsDiff)
      
      c = list(d)
      c[3] = localtime[3]
      c[4] = localtime[4]
      c[5] = localtime[5]

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

      #print("Compare start: " + str(d1) + ", end: " + str(d2) + ", current: " + str(c))
      
      if tuple(d1) < tuple(d2):
         #d1 start | current | d2 end 
         return tuple(c) > tuple(d1) and tuple(c) < tuple(d2)
      else:
         # current | d2 end | or | d1 start | current 
         return tuple(c) > tuple(d1) or tuple(c) < tuple(d2)
    else:
      return False 
  except Exception as e:
    sys.print_exception(e)
    saveError(e)
    return False   

def getRtcDatetime():
  now_datetime = None
  for i in range(3):
    now_datetime = utime.localtime(utime.time())
    if now_datetime[0] >= YEAR:
      return now_datetime
  raise ValueError('Invalid datetime: ' + str(now_datetime))

# gui methods ----

def printCenteredText(msg, mode, font=M5.Display.FONTS.DejaVu24, backgroundColor=BLACK, textColor=WHITE, clear=True):  
  if mode >= 4:
    M5.Display.setRotation(3)
  else:        
    M5.Display.setRotation(1)
    
  if clear:
    M5.Display.clear(backgroundColor)
        
  M5.Display.setFont(font)
    
  M5.Display.setTextColor(textColor, backgroundColor)
    
  w = M5.Display.textWidth(msg)
  f = M5.Display.fontHeight()
  x = math.ceil((320-w)/2)
  y = math.ceil((240-f)/2)

  M5.Display.drawString(msg, x, y)

def printText(msg, x, y, font=M5.Display.FONTS.DejaVu24, backgroundColor=BLACK, textColor=WHITE, clear=False, rotate=1, silent=False):
  M5.Display.setRotation(rotate)  
    
  if clear:
    M5.Display.clear(backgroundColor)
        
  M5.Display.setFont(font)
    
  M5.Display.setTextColor(textColor, backgroundColor)
    
  M5.Display.drawString(msg, x, y)
  
  if silent == False:
    print("Printing " + msg)

def drawDirection(x, y, xshift=0, yshift=0, rotateAngle=0, arrowColor=WHITE, fillColor=WHITE):
  M5.Lcd.fillCircle(x, y, 40, fillColor)
  print("Printing Direction: " + str(x) + ',' + str(y))
  drawTriangle(x+xshift, y+yshift, arrowColor, rotateAngle)

def drawDoubleDirection(x, y, ytop=0, ybottom=0, rotateAngle=0, arrowColor=WHITE, fillColor=WHITE):
  M5.Lcd.fillCircle(x, y, 40, fillColor)
  print("Printing DoubleDirection: " + str(x) + ',' + str(y))
  drawTriangle(x, y+ytop, arrowColor, rotateAngle)
  drawTriangle(x, y+ybottom, arrowColor, rotateAngle) 
  
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

  M5.Display.fillTriangle(int(x1r), int(y1r), int(x2r), int(y2r), int(x3r), int(y3r), arrowColor)
  return x1r, y1r, x2r, y2r, x3r, y3r 

def printLocaltime(mode, secondsDiff, localtime=None, useLock=False, silent=False):
  try: 
    if localtime == None:
      now_datetime = getRtcDatetime()
      now = utime.mktime((now_datetime[0], now_datetime[1], now_datetime[2], now_datetime[3], now_datetime[4], now_datetime[5],0,0))  + secondsDiff
      localtime = utime.localtime(now)
    h = str(localtime[3])
    if (localtime[3] < 10): h = "0" + h   
    m = str(localtime[4])
    if (localtime[4] < 10): m = "0" + m
    s = str(localtime[5])
    if (localtime[5] < 10): s = "0" + s
    timeStr = h + ":" + m + ":" + s
    locked = False 
    if useLock == False and drawScreenLock.locked() == False:
      locked = drawScreenLock.acquire()
    if locked == True or useLock == True:
      rotate = 1
      if mode >= 4:
        rotate = 3
      printText(timeStr, 10, 12, backgroundColor=DARKGREY, silent=silent, rotate=rotate)  
      if useLock == False and locked == True:
        drawScreenLock.release()
  except Exception as e:
    sys.print_exception(e)
    saveError(e)

def drawScreen(newestEntry, noNetwork=False):
  global response, mode, brightness, emergency, emergencyPause, MIN, MAX, EMERGENCY_MIN, EMERGENCY_MAX, startTime, rgbUnit, secondsDiff, OLD_DATA, OLD_DATA_EMERGENCY, batteryStrIndex, envUnit, secondsDiff 
  #320*240
  
  now_datetime = getRtcDatetime()
    
  locked = drawScreenLock.acquire()

  if locked == True: 

    currentMode = mode

    s = utime.time()
    print('Printing screen in ' + MODES[currentMode] + ' mode')
  
    sgv = newestEntry['sgv']
    sgvStr = str(sgv)
  
    directionStr = newestEntry['direction']
    sgvDateStr = newestEntry['date']
  
    now = utime.mktime((now_datetime[0], now_datetime[1], now_datetime[2], now_datetime[3], now_datetime[4], now_datetime[5],0,0))  + secondsDiff
    
    tooOld = False
    try:
      tooOld = isOlderThan(sgvDateStr, OLD_DATA, now, print_time=True)
    except Exception as e:
      sys.print_exception(e)
      saveError(e)
    #print("Is sgv data older than " + str(OLD_DATA) + " minutes?", tooOld)  

    emergencyNew = None
  
    if tooOld: backgroundColor=DARKGREY; emergencyNew=False
    elif sgv <= EMERGENCY_MIN: backgroundColor=RED; emergencyNew=(utime.time() > emergencyPause and not tooOld)  
    elif sgv >= (MIN-10) and sgv < MIN and directionStr.endswith("Up"): backgroundColor=DARKGREEN; emergencyNew=False
    elif sgv > EMERGENCY_MIN and sgv < MIN: backgroundColor=RED; emergencyNew=False
    elif sgv >= MIN and sgv <= MAX: backgroundColor=DARKGREEN; emergencyNew=False 
    elif sgv > MAX and sgv <= (MAX+10) and directionStr.endswith("Down"): backgroundColor=DARKGREEN; emergencyNew=False
    elif sgv > MAX and sgv <= EMERGENCY_MAX: backgroundColor=ORANGE; emergencyNew=False
    elif sgv > EMERGENCY_MAX: backgroundColor=ORANGE; emergencyNew=(utime.time() > emergencyPause and not tooOld)  
  
    #battery level emergency
    batteryLevel = getBatteryLevel()
    uptime = utime.time() - startTime  
    if (batteryLevel < 10 and batteryLevel > 0 and uptime > 300) and (utime.time() > emergencyPause) and not M5.Power.isCharging(): 
      emergencyNew = True
      if currentMode < 4 or currentMode == 7: currentMode = 2
      else: currentMode = 6
      clear = True

    #old data emergency
    if utime.time() > emergencyPause and isOlderThan(sgvDateStr, OLD_DATA_EMERGENCY, now):
      emergencyNew = True
      clear = True   

    emergency = emergencyNew  

    if emergency == False and rgbUnit != None:
      rgbUnit.set_color(0, BLACK)
      rgbUnit.set_color(1, backgroundColor)
      rgbUnit.set_color(2, BLACK)

    #if emergency change to one of full modes 
    if emergency == True and (currentMode == 3 or currentMode == 7): currentMode = 0
  
    if noNetwork == False and "ago" in newestEntry and (currentMode == 0 or currentMode == 4): 
      dateStr = newestEntry['ago']
    elif currentMode == 2 or currentMode == 6:
      if batteryLevel >= 0:
       dateStr = "Battery: " + str(batteryLevel) + "%"
      else: 
       dateStr = "Battery level unknown"
    else:   
      dateStr = sgvDateStr.replace("T", " ")[:-3] #remove seconds
  
    if not tooOld and directionStr == 'DoubleUp' and sgv+20>=MAX and sgv<MAX: arrowColor = ORANGE
    elif not tooOld and directionStr == 'DoubleUp' and sgv>=MAX: arrowColor = RED
    elif not tooOld and directionStr == 'DoubleDown' and sgv-20<=MIN: arrowColor = RED
    elif not tooOld and directionStr.endswith('Up') and sgv+10>=MAX and sgv<MAX: arrowColor = ORANGE
    elif not tooOld and directionStr.endswith('Down') and sgv-10<=MIN: arrowColor = RED
    else: arrowColor = backgroundColor  

    batteryStr = str(batteryLevel) + '%'
    batteryTextColor = WHITE
    if batteryLevel < 20: batteryTextColor = RED
    try:
      if envUnit != None and batteryLevel > 20:
        if batteryStrIndex == 1: 
          batteryStr = "%.0fC" % envUnit.read_temperature()
          if envUnit.read_temperature() > 25 or envUnit.read_temperature() < 18: batteryTextColor = RED
          batteryStrIndex = 2
        elif batteryStrIndex == 2:
          batteryStr = 'p'+ "%.0f" % envUnit.read_pressure()
          if envUnit.read_pressure() > 1050 or envUnit.read_pressure() < 950: batteryTextColor = RED
          batteryStrIndex = 3
        elif batteryStrIndex == 3:
          batteryStr = 'h' + "%.0f" % envUnit.read_humidity() + '%'
          if envUnit.read_humidity() < 40 or envUnit.read_humidity() > 60: batteryTextColor = RED
          batteryStrIndex = 0  
        else:
          batteryStrIndex = 1  
    except Exception as e:
      sys.print_exception(e)
      #saveError(e)

    sgvDiff = 0
    if len(response) > 1: sgvDiff = sgv - response[1]['sgv']
    sgvDiffStr = str(sgvDiff)
    if sgvDiff > 0: sgvDiffStr = "+" + sgvDiffStr
     
    rotate = 1
    if mode >= 4:
      rotate = 3
    
    M5.Display.setRotation(rotate)  

    M5.Display.fillRect(0, 0, 360, 44, DARKGREY)
    M5.Display.fillRect(0, 44, 360, 158, backgroundColor)
    M5.Display.fillRect(0, 196, 360, 44, DARKGREY)

    #draw current time
    printLocaltime(mode, secondsDiff, useLock=True)  
 
    #draw sgv
    M5.Display.setFont(M5.Display.FONTS.DejaVu72) 
    w = M5.Display.textWidth(sgvStr)
    x = math.ceil((320 - w - 30 - 80) / 2)
    y = 120 - 36
    printText(sgvStr, x, y, font=M5.Display.FONTS.DejaVu72, backgroundColor=backgroundColor, rotate=rotate)
    
    #draw arrow
    x += w + 70
    y = 113
    
    if directionStr == 'DoubleUp': drawDoubleDirection(x, y, ytop=-12, ybottom=4, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'DoubleDown': drawDoubleDirection(x, y, ytop=-4, ybottom=12, rotateAngle=90, arrowColor=arrowColor) 
    elif directionStr == 'SingleUp': drawDirection(x, y, xshift=0, yshift=-4, rotateAngle=-90, arrowColor=arrowColor)
    elif directionStr == 'SingleDown': drawDirection(x, y, xshift=0, yshift=4, rotateAngle=90, arrowColor=arrowColor)
    elif directionStr == 'Flat': drawDirection(x, y, xshift=4, rotateAngle=0, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveUp': drawDirection(x, y, xshift=4, yshift=-4, rotateAngle=-45, arrowColor=arrowColor)
    elif directionStr == 'FortyFiveDown': drawDirection(x, y, xshift=4, yshift=4, rotateAngle=45, arrowColor=arrowColor)
    
    #draw battery
    M5.Display.setFont(M5.Display.FONTS.DejaVu24)
    textColor = batteryTextColor
    w = M5.Display.textWidth(batteryStr)
    printText(batteryStr, math.ceil(315 - w), 12, font=M5.Display.FONTS.DejaVu24, backgroundColor=DARKGREY, textColor=textColor, rotate=rotate) 
    
    #draw sgv diff
    textColor = WHITE
    if math.fabs(sgvDiff) >= 10 and backgroundColor != RED and not tooOld: textColor = RED
    w = M5.Display.textWidth(sgvDiffStr)
    x = math.ceil(25 + (320 - w) / 2)
    printText(sgvDiffStr, x, 12, font=M5.Display.FONTS.DejaVu24, backgroundColor=DARKGREY, textColor=textColor, rotate=rotate)
    
    #draw dateStr
    M5.Display.setFont(M5.Display.FONTS.DejaVu24)
    textColor = WHITE
    if isOlderThan(sgvDateStr, 10, now): 
      textColor = RED
    w = M5.Display.textWidth(dateStr)
    x = math.ceil((320 - w) / 2)
    y = 240-24-5
    printText(dateStr, x, y, font=M5.Display.FONTS.DejaVu24, backgroundColor=DARKGREY, textColor=textColor, rotate=rotate)  
    
    drawScreenLock.release()
    print("Printing screen finished in " + str((utime.time() - s)) + " secs ...")  
  else:    
    print("Printing locked!")

# ------

def backendMonitor():
  global response, API_ENDPOINT, API_TOKEN, LOCALE, TIMEZONE, startTime, sgvDict, secondsDiff, backendResponseTimer, backendResponse, mode
  lastid = -1
  while True:
    try:
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      printTime((utime.time() - startTime), prefix='Uptime is')
      print("Calling backend with timeout " + str(BACKEND_TIMEOUT_MS) + " ms ...")
      s = utime.time()
      backendResponseTimer.init(mode=machine.Timer.ONE_SHOT, period=BACKEND_TIMEOUT_MS+10000, callback=watchdogCallback)
      backendResponse = requests2.get(API_ENDPOINT + "/entries.json?count=10&waitfornextid=" + str(lastid) + "&timeout=" + str(BACKEND_TIMEOUT_MS), headers={'api-secret': API_TOKEN,'accept-language': LOCALE,'accept-charset': 'ascii', 'x-gms-tz': TIMEZONE})
      backendResponseTimer.deinit()
      response = backendResponse.json()
      backendResponse.close()
      printTime((utime.time() - s), prefix='Response received in')
      sgv = response[0]['sgv']
      sgvDate = response[0]['date']
      lastid = response[0]['id']
      print('Sgv:', sgv)
      print('Direction:', response[0]['direction'])
      print('Read: ' + sgvDate + ' (' + TIMEZONE + ')')
      sgvDiff = 0
      if len(response) > 1: sgvDiff = sgv - response[1]['sgv']
      print('Sgv diff from previous read:', sgvDiff)
      drawScreen(response[0])
      _thread.start_new_thread(persistEntries, ())
      #persistEntries() 
    except Exception as e:
      backendResponseTimer.deinit()
      if backendResponse != None: backendResponse.close()
      lastid = -1
      sys.print_exception(e)
      #saveError(e)
      print('Battery level: ' + str(getBatteryLevel()) + '%')
      if response == None: readResponseFile()
      try: 
        if response != None and len(response) >= 1: 
          drawScreen(response[0], noNetwork=True)
        else:
          printCenteredText("Network error! Please wait.", mode, backgroundColor=RED, clear=True)
      except Exception as e:
        sys.print_exception(e)
        saveError(e)
      print('Backend call error. Retry in 5 secs ...')
      time.sleep(5)
    print('---------------------------')

def setEmergencyrgbUnitColor(setBeepColorIndex, beepColor):
  setBlackColorIndex = setBeepColorIndex-1
  if setBlackColorIndex == -1: setBlackColorIndex = 2
  #print('Colors: ' + str(setBlackColorIndex) + ' ' + str(setBeepColorIndex))
  if rgbUnit != None:
    rgbUnit.set_color(setBlackColorIndex, BLACK)
    rgbUnit.set_color(setBeepColorIndex, beepColor)
        
def emergencyMonitor():
  global emergency, response, rgbUnit, beeperExecuted, EMERGENCY_MAX, EMERGENCY_MIN, OLD_DATA_EMERGENCY
  useBeeper = False
  set_colorIndex = 1
  
  while True:
    #print('Emergency monitor checking status')
    if emergency == True:
      batteryLevel = getBatteryLevel()
      sgv = response[0]['sgv']
      if batteryLevel < 10:
        print('Low battery level ' + str(batteryLevel) + "%!!!")
      elif sgv > EMERGENCY_MAX or sgv <= EMERGENCY_MIN:
        print('Emergency glucose level ' + str(sgv) + '!!!')
      else:
        print('SGV data is older than ' + str(OLD_DATA_EMERGENCY) + ' minutes!!!')  
      
      beepColor = RED
      if sgv > EMERGENCY_MAX: beepColor = ORANGE  

      setEmergencyrgbUnitColor(set_colorIndex, beepColor)
      set_colorIndex += 1
      if set_colorIndex > 2: set_colorIndex = 0 
      if beeperExecuted == False:
        useBeeper = checkBeeper()
      if useBeeper == True:
        M5.Power.setVibration(128) #Max 255
        time.sleep(1)
        M5.Power.setVibration(0)
        beeperExecuted = True   
        useBeeper = False 
      else:
        time.sleep(1)
      print("beeperExecuted=" + str(beeperExecuted) + ", useBeeper=" + str(useBeeper))              
    else:
      #print('No Emergency')
      beeperExecuted = False
      useBeeper = False
      set_colorIndex = 0
      time.sleep(1)

#accelerator
def accelMonitor():
  while True:
    accelAction()
    time.sleep(0.5)

def accelAction():
  global mode, response
  acceleration = M5.Imu.getAccel()
  hasResponse = (response != None)
  if hasResponse and acceleration[1] < -0.1 and mode in range(0,3): mode += 4; drawScreen(response[0]) #change to 'Flip mode' #4,5,6
  elif hasResponse and acceleration[1] > 0.1 and mode in range(4,7): mode -= 4; drawScreen(response[0]) #change to 'Normal mode' #0,1,2
  elif hasResponse and acceleration[1] < -0.1 and mode == 7: mode = 8; drawScreen(response[0])
  elif hasResponse and acceleration[1] > 0.1 and mode == 8: mode = 7; drawScreen(response[0])

def touchPadCallback(t):
  M5.update()
  if M5.Touch.getCount() > 0:
    tx = M5.Touch.getX()
    ty = M5.Touch.getY()
    print("Touch screen pressed at " + str(tx) + "," + str(ty))
    if tx >= 120 and tx <= 160 and ty >= 240 and ty <= 280:
      onBtnBPressed(t)
    elif tx >= 240 and tx <= 280 and ty >= 240 and ty <= 280:
      onBtnCPressed(t)  
    else:
      onBtnPressed(t)

def watchdogCallback(t):
  global shuttingDown, backendResponse, rgbUnit, response, mode

  print('Restarting due to backend communication failure ...')
  if rgbUnit != None:
    rgbUnit.set_color(0, BLACK)
    rgbUnit.set_color(1, DARKGREY)
    rgbUnit.set_color(2, BLACK)
  if backendResponse != None: backendResponse.close()
  WDT(timeout=1000)   
  shuttingDown = True
  printCenteredText("Restarting...", mode, backgroundColor=RED, clear=True)

def localtimeCallback(t):
  global shuttingDown, mode, secondsDiff 
  if shuttingDown == False:
    printLocaltime(mode, secondsDiff, silent=True)

def onBtnPressed(t):
  print('Button pressed')
  global emergency, emergencyPause
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + EMERGENCY_PAUSE_INTERVAL
  else:   
    global brightness, config
    brightness += 32
    if brightness > 255: brightness = 32
    M5.Widgets.setBrightness(brightness)
    config["brightness"] = brightness
    saveConfigFile()

def onBtnBPressed(t):
  global shuttingDown, mode, config
  print('Button B pressed')
  config[ap.CONFIG] = 0
  saveConfigFile()
  WDT(timeout=1000)
  shuttingDown = True
  printCenteredText("Restarting...", mode, backgroundColor=RED, clear=True)  

def onBtnCPressed(t):
  onBtnPressed(t)

# main app code -------------------------------------------------------------------     

config = None

try:
   os.stat(ap.CONFIG_FILE)
   confFile = open(ap.CONFIG_FILE, 'r')
   config = ujson.loads(confFile.read())
except Exception as e:
   sys.print_exception(e)

mode = 0
if M5.Imu.getAccel()[1] < 0: mode = 4 #flip

M5.begin()

brightness = 32
if config != None: brightness = config["brightness"]
M5.Widgets.setBrightness(brightness)

printCenteredText("Starting...", mode, backgroundColor=DARKGREY, clear=True)  

envUnit = None
try: 
   i2c0 = I2C(0, scl=Pin(33), sda=Pin(32), freq=40000)
   envUnit = ENVUnit(i2c=i2c0, type=3) 
   print('Temperature:',str(envUnit.read_temperature()) + " C")
   print('Humidity:',str(envUnit.read_humidity()) + " %")
   print('Pressure:',str(envUnit.read_pressure()) + " hPa")
except Exception as e:
   print('Weather Monitoring Unit not found')
   sys.print_exception(e)

rgbUnit = None
try: 
   rgbUnit = RGBUnit((36, 26), 3)
   rgbUnit.set_color(0, BLACK)     
   rgbUnit.set_color(1, DARKGREY)
   rgbUnit.set_color(2, BLACK)
except Exception as e:
   print('RGB Unit not found')
   sys.print_exception(e)

print('Starting ...')
print('System:', sys.implementation)

response = None
emergency = False
emergencyPause = 0
shuttingDown = False
backendResponse = None
beeperExecuted = False
  
batteryStrIndex = 0

if config == None or config[ap.CONFIG] == 0:
   printCenteredText("Connect AP ...", mode, backgroundColor=RED, clear=True)
   print("Connect wifi " + ap.SSID)
   def reboot():
      global shuttingDown 
      print('Restarting after configuration change...')
      WDT(timeout=1000)   
      shuttingDown = True
      printCenteredText("Restarting...", mode, backgroundColor=RED, clear=True)   
   ap.open_access_point(reboot)  
else:
   try: 
     API_ENDPOINT = config["api-endpoint"]
     API_TOKEN = config["api-token"]
     LOCALE = config["locale"]
     MIN = config["min"]
     MAX = config["max"]
     EMERGENCY_MIN = config["emergencyMin"]
     EMERGENCY_MAX = config["emergencyMax"] 
     TIMEZONE = "GMT" + config["timezone"]
     USE_BEEPER = config["beeper"]
     BEEPER_START_TIME = config["beeperStartTime"]
     BEEPER_END_TIME = config["beeperEndTime"]
     OLD_DATA = config["oldData"]
     OLD_DATA_EMERGENCY = config["oldDataEmergenc"]

     if MIN < 30: MIN=30
     if MAX < 100: MAX=100
     if EMERGENCY_MIN < 30 or MIN <= EMERGENCY_MIN: EMERGENCY_MIN=MIN-10
     if EMERGENCY_MAX < 100 or MAX >= EMERGENCY_MAX: EMERGENCY_MAX=MAX+10  
     if len(API_ENDPOINT) == 0: raise Exception("Empty api-endpoint parameter")
     if USE_BEEPER != 1 and USE_BEEPER != 0: USE_BEEPER=1
     if re.search("^GMT[+-]((0?[0-9]|1[0-1]):([0-5][0-9])|12:00)$",TIMEZONE) == None: TIMEZONE="GMT+0:00"
     if OLD_DATA < 10: OLD_DATA=10
     if OLD_DATA_EMERGENCY < 15: OLD_DATA_EMERGENCY=15

     timeStr = TIMEZONE[4:]
     [HH, MM] = [int(i) for i in timeStr.split(':')]
     secondsDiff = HH * 3600 + MM * 60
     if TIMEZONE[3] == "-": secondsDiff = secondsDiff * -1
     print('Setting local time seconds diff from UTC:', secondsDiff) 
   except Exception as e:
     sys.print_exception(e)
     saveError(e)
     config[ap.CONFIG] = 0
     saveConfigFile()
     printCenteredText("Fix config!", mode, backgroundColor=RED, clear=True)
     time.sleep(2)
     WDT(timeout=1000)
     shuttingDown = True
     printCenteredText("Restarting...", mode, backgroundColor=RED, clear=True)

# activate buttons to enable configuration changes     

M5.BtnA.setCallback(type=M5.BtnA.CB_TYPE.WAS_PRESSED, cb=onBtnPressed)
M5.BtnB.setCallback(type=M5.BtnB.CB_TYPE.WAS_PRESSED, cb=onBtnBPressed)
M5.BtnC.setCallback(type=M5.BtnC.CB_TYPE.WAS_PRESSED, cb=onBtnCPressed)

touchPadTimer = machine.Timer(0)
touchPadTimer.init(period=100, callback=touchPadCallback)

# from here code runs only if application is properly configured

try:
  nic = network.WLAN(network.STA_IF)
  nic.active(True)

  printCenteredText("Scanning wifi ...", mode, backgroundColor=DARKGREY)

  wifi_password = None
  wifi_ssid = None  
  while wifi_password == None:
    try: 
      nets = nic.scan()
      for result in nets:
        wifi_ssid = result[0].decode() 
        if wifi_ssid in config: 
          wifi_password = config[wifi_ssid]
        else:
          print('No password for wifi ' + wifi_ssid + ' found')  
        if wifi_password != None: break
    except Exception as e:
      sys.print_exception(e)
      saveError(e)
      printCenteredText("Wifi not found!", mode, backgroundColor=RED, clear=True)  
    if wifi_password == None: time.sleep(1)

  printCenteredText("Connecting wifi...", mode, backgroundColor=DARKGREY) 
  nic.connect(wifi_ssid, wifi_password)
  print('Connecting wifi ' + wifi_ssid)
  while not nic.isconnected():
    print(".", end="")
    time.sleep(0.25)
  print("")  

  time_server = 'pool.ntp.org'
  printCenteredText("Setting time...", mode, backgroundColor=DARKGREY) 
  print('Connecting time server ' + time_server)
  now_datetime = None
  while now_datetime is None:
    try:
      print(".", end="")
      #TODO use 0.pool.ntp.org, 1.pool.ntp.org, 2.pool.ntp.org, 3.pool.ntp.org
      ntptime.host = "pool.ntp.org" 
      ntptime.settime()
      now_datetime = getRtcDatetime()
      startTime = utime.time()
    except Exception as e:
      sys.print_exception(e)
      #saveError(e)
      time.sleep(2)
  print("\nCurrent UTC datetime " +  str(now_datetime))

  printCenteredText("Loading data...", mode, backgroundColor=DARKGREY) 

  sgvDict = readSgvFile()
  dictLen = len(sgvDict)
  print("Loaded " + str(dictLen) + " sgv entries")

  #max 4 timers 0-3

  backendResponseTimer = machine.Timer(1)
  
  localtimeTimer = machine.Timer(2)
  localtimeTimer.init(period=1000, callback=localtimeCallback)

  #main method and threads

  _thread.start_new_thread(emergencyMonitor, ())
  _thread.start_new_thread(accelMonitor, ())
  _thread.start_new_thread(backendMonitor(), ())
except:
  sys.print_exception(e)
  #saveError(e)
  printCenteredText("Fix config!", mode, backgroundColor=RED, clear=True)
