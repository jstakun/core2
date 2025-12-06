from m5stack import lcd, machine, binascii, gc, M5Screen, rtc, touch, btnA, btnB, btnC 
import math
import os
import time
import network
import sys
import deviceCfg 
import wifiCfg 
import urequests 
import _thread
import utime
import unit
from collections import OrderedDict
from imu import IMU 
import re
import ap
import ujson

EMERGENCY_PAUSE_INTERVAL = 1800  #sec = 30 mins
MODES = ["full_elapsed", "full_date", "full_battery", "basic", "flip_full_elapsed", "flip_full_date", "flip_full_battery", "chart", "flip_chart"]
SGVDICT_FILE = 'sgvdict.txt'
RESPONSE_FILE = 'response.json'
BACKEND_TIMEOUT_MS = 30000 #max 60000
MAX_SAVED_ENTRIES = 10
YEAR = 2025

drawScreenLock = _thread.allocate_lock()

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
  gc.collect()  
  print('Persisted ' + str(dictLen) + " sgv entries")

def checkBeeper():
  global USE_BEEPER, BEEPER_START_TIME, BEEPER_END_TIME, secondsDiff 
  try:   
    if (USE_BEEPER == 1 and getBatteryLevel() >= 5):
      d = utime.localtime(0)
      now_datetime = rtc.datetime() 
      if now_datetime[0] < YEAR:
        raise ValueError('Invalid datetime: ' + str(now_datetime))
      now = utime.mktime((now_datetime[0], now_datetime[1], now_datetime[2], now_datetime[4], now_datetime[5], now_datetime[6],0,0))
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
    now_datetime = rtc.datetime()
    if now_datetime[0] >= YEAR:
      return now_datetime
  raise ValueError('Invalid datetime: ' + str(now_datetime))

# gui methods ----

def printCenteredText(msg, mode, font=lcd.FONT_DejaVu24, backgroundColor=lcd.BLACK, textColor=lcd.WHITE, clear=False):
  rotate = 0
  if mode >= 4: 
    rotate = 180
  lcd.font(font, rotate=rotate)
  if clear == True:
    lcd.clear(backgroundColor)
  lcd.setTextColor(textColor)
  w = lcd.textWidth(msg)
  f = lcd.fontSize()
  x = math.ceil((320-w)/2)
  y = math.ceil((240-f[1])/2)
  if rotate == 180:
    x = math.ceil(160+(w/2))
    y = math.ceil(120+(f[1]/2))
  lcd.fillRect(0, math.ceil(120-f[1]/2), 320, math.ceil(f[1]), backgroundColor)
  lcd.print(msg, x, y)

def printText(msg, x, y, cleanupMsg, font=lcd.FONT_DejaVu24, backgroundColor=lcd.BLACK, textColor=lcd.WHITE, clear=True, rotate=0, cleanupX=None, silent=False):
  lcd.font(font, rotate=rotate)
  if clear == True and cleanupMsg != None:
     if cleanupX == None: cleanupX = x
     w = lcd.textWidth(cleanupMsg)
     f = lcd.fontSize()
     if silent == False: 
       print("Clearing " + cleanupMsg + ": " + str(cleanupX) + "," + str(y))
     if rotate == 0:
       lcd.fillRect(cleanupX, math.ceil(y), math.ceil(w)+2, math.ceil(f[1]), backgroundColor)
     else:   
       lcd.fillRect(math.ceil(cleanupX-w), math.ceil(y-f[1]), math.ceil(w)+2, math.ceil(f[1]), backgroundColor)
  lcd.setTextColor(textColor)
  lcd.print(msg, x, y)
  if silent == False:
    print("Printing " + msg)

def drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=0, yshift=0, rotateAngle=0, arrowColor=lcd.WHITE, fillColor=lcd.WHITE, backgroundColor=lcd.BLACK):
  cleared = False
  if prevX != None and prevY != None and (prevX != x or prevY != y):
    print('Clearing: ' + str(prevX) + "," + str(prevY))
    lcd.circle(prevX, prevY, 40, fillcolor=backgroundColor, color=backgroundColor) 
    cleared = True 
  if cleared == True or directionStr != prevDirectionStr:
    lcd.circle(x, y, 40, fillcolor=fillColor, color=fillColor)
    print("Printing Direction: " + str(x) + ',' + str(y))
    drawTriangle(x+xshift, y+yshift, arrowColor, rotateAngle)

def drawDoubleDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, ytop=0, ybottom=0, rotateAngle=0, arrowColor=lcd.WHITE, fillColor=lcd.WHITE, backgroundColor=lcd.BLACK):
  cleared = False
  if prevX != None and prevY != None and (prevX != x or prevY != y):
    print('Clearing: ' + str(prevX) + "," + str(prevY))
    lcd.circle(prevX, prevY, 40, fillcolor=backgroundColor, color=backgroundColor)
    cleared = True  
  if cleared == True or directionStr != prevDirectionStr:
    lcd.circle(x, y, 40, fillcolor=fillColor, color=fillColor)
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

  lcd.fillTriangle(int(x1r), int(y1r), int(x2r), int(y2r), int(x3r), int(y3r), arrowColor)
  #lcd.triangle(int(x1r), int(y1r), int(x2r), int(y2r), int(x3r), int(y3r), fillcolor=arrowColor, color=arrowColor)
  return x1r, y1r, x2r, y2r, x3r, y3r 

def printLocaltime(prevTimeStr, mode, secondsDiff, localtime=None, useLock=False, silent=False):
  try: 
    if localtime == None:
      now_datetime = getRtcDatetime()
      now = utime.mktime((now_datetime[0], now_datetime[1], now_datetime[2], now_datetime[4], now_datetime[5], now_datetime[6],0,0))  + secondsDiff
      localtime = utime.localtime(now)
    h = str(localtime[3])
    if (localtime[3] < 10): h = "0" + h   
    m = str(localtime[4])
    if (localtime[4] < 10): m = "0" + m
    s = str(localtime[5])
    if (localtime[5] < 10): s = "0" + s
    timeStr = h + ":" + m + ":" + s
    if timeStr != prevTimeStr:
      locked = False 
      if useLock == False and drawScreenLock.locked() == False:
        locked = drawScreenLock.acquire()
      if locked == True or useLock == True:
        if mode in range (0,3):
          printText(timeStr, 10, 12, prevTimeStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, silent=silent)  
        elif mode in range (4,7):
          printText(timeStr, 304, 215, prevTimeStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, rotate=180, silent=silent)   
        if useLock == False and locked == True:
          drawScreenLock.release()
    return timeStr       
  except Exception as e:
    sys.print_exception(e)
    saveError(e)
    return None

def drawScreen(newestEntry, clear=False, noNetwork=False):
  global response, mode, brightness, emergency, emergencyPause, MIN, MAX, EMERGENCY_MIN, EMERGENCY_MAX, startTime, rgbUnit, secondsDiff, OLD_DATA, OLD_DATA_EMERGENCY, headerColor, middleColor, footerColor, prevDateStr, prevSgvDiffStr, prevBatteryStr, prevTimeStr, prevSgvStr, prevX, prevY, prevDirectionStr, batteryStrIndex, envUnit, secondsDiff 
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
  
    now = utime.mktime((now_datetime[0], now_datetime[1], now_datetime[2], now_datetime[4], now_datetime[5], now_datetime[6],0,0))  + secondsDiff
    #localtime = utime.localtime(now)
  
    tooOld = False
    try:
      tooOld = isOlderThan(sgvDateStr, OLD_DATA, now, print_time=True)
    except Exception as e:
      sys.print_exception(e)
      saveError(e)
    #print("Is sgv data older than " + str(OLD_DATA) + " minutes?", tooOld)  

    emergencyNew = None
  
    if tooOld: backgroundColor=lcd.DARKGREY; emergencyNew=False
    elif sgv <= EMERGENCY_MIN: backgroundColor=lcd.RED; emergencyNew=(utime.time() > emergencyPause and not tooOld)  
    elif sgv >= (MIN-10) and sgv < MIN and directionStr.endswith("Up"): backgroundColor=lcd.DARKGREEN; emergencyNew=False
    elif sgv > EMERGENCY_MIN and sgv < MIN: backgroundColor=lcd.RED; emergencyNew=False
    elif sgv >= MIN and sgv <= MAX: backgroundColor=lcd.DARKGREEN; emergencyNew=False 
    elif sgv > MAX and sgv <= (MAX+10) and directionStr.endswith("Down"): backgroundColor=lcd.DARKGREEN; emergencyNew=False
    elif sgv > MAX and sgv <= EMERGENCY_MAX: backgroundColor=lcd.ORANGE; emergencyNew=False
    elif sgv > EMERGENCY_MAX: backgroundColor=lcd.ORANGE; emergencyNew=(utime.time() > emergencyPause and not tooOld)  
  
    #battery level emergency
    batteryLevel = getBatteryLevel()
    uptime = utime.time() - startTime  
    if (batteryLevel < 10 and batteryLevel > 0 and uptime > 300) and (utime.time() > emergencyPause) and not power.getChargeState(): 
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
      rgbUnit.setColor(1, lcd.BLACK)
      rgbUnit.setColor(2, backgroundColor)
      rgbUnit.setColor(3, lcd.BLACK)

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
  
    if not tooOld and directionStr == 'DoubleUp' and sgv+20>=MAX and sgv<MAX: arrowColor = lcd.ORANGE
    elif not tooOld and directionStr == 'DoubleUp' and sgv>=MAX: arrowColor = lcd.RED
    elif not tooOld and directionStr == 'DoubleDown' and sgv-20<=MIN: arrowColor = lcd.RED
    elif not tooOld and directionStr.endswith('Up') and sgv+10>=MAX and sgv<MAX: arrowColor = lcd.ORANGE
    elif not tooOld and directionStr.endswith('Down') and sgv-10<=MIN: arrowColor = lcd.RED
    else: arrowColor = backgroundColor  

    batteryStr = str(batteryLevel) + '%'
    batteryTextColor = lcd.WHITE
    if batteryLevel < 20: batteryTextColor = lcd.RED
    try:
      if envUnit != None and batteryLevel > 20:
        if batteryStrIndex == 1: 
          batteryStr = "%.0fC" % envUnit.temperature
          if envUnit.temperature > 25 or envUnit.temperature < 18: batteryTextColor = lcd.RED
          batteryStrIndex = 2
        elif batteryStrIndex == 2:
          batteryStr = 'p'+ "%.0f" % envUnit.pressure
          if envUnit.pressure > 1050 or envUnit.pressure < 950: batteryTextColor = lcd.RED
          batteryStrIndex = 3
        elif batteryStrIndex == 3:
          batteryStr = 'h' + "%.0f" % envUnit.humidity + '%'
          if envUnit.humidity < 40 or envUnit.humidity > 60: batteryTextColor = lcd.RED
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
   
    if clear:
      headerColor = None
      middleColor = None
      footerColor = None
      prevX = None
      prevY = None
      prevDirectionStr = None
      prevDateStr = None 
      prevSgvDiffStr = None
      prevBatteryStr = None 
      prevTimeStr = None 
      prevSgvStr = None
    
    if headerColor != lcd.DARKGREY:
      headerColor = lcd.DARKGREY
      lcd.fillRect(0, 0, 360, 50, lcd.DARKGREY)

    if backgroundColor != middleColor:
      middleColor = backgroundColor 
      lcd.fillRect(0, 48, 360, 140, backgroundColor)
      prevDirectionStr = None
      prevSgvStr = None
    
    if footerColor != lcd.DARKGREY:
      footerColor = lcd.DARKGREY     
      lcd.fillRect(0, 192, 360, 50, lcd.DARKGREY)

    if currentMode in range (0,3):

      #draw current time
      prevTimeStr = printLocaltime(prevTimeStr, mode, secondsDiff, useLock=True)  
 
      #draw sgv 
      lcd.font(lcd.FONT_DejaVu72)
      w = lcd.textWidth(sgvStr)
      x = math.ceil((320 - w - 20 - 80) / 2)
      y = 120 - 36
      if sgvStr != prevSgvStr:
        if prevSgvStr != None: 
          cleanupX = math.ceil((320 - lcd.textWidth(prevSgvStr) - 20 - 80) / 2)
        else:
          cleanupX = None 
        printText(sgvStr, x, y, prevSgvStr, font=lcd.FONT_DejaVu72, backgroundColor=backgroundColor, cleanupX=cleanupX)
        prevSgvStr = sgvStr

      #draw arrow
      x += w + 60
      y = 113
    
      if directionStr == 'DoubleUp': drawDoubleDirection(x, y, directionStr, ytop=-12, ybottom=4, rotateAngle=-90, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'DoubleDown': drawDoubleDirection(x, y, directionStr, ytop=-4, ybottom=12, rotateAngle=90, arrowColor=arrowColor, backgroundColor=backgroundColor) 
      elif directionStr == 'SingleUp': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=0, yshift=-4, rotateAngle=-90, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'SingleDown': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=0, yshift=4, rotateAngle=90, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'Flat': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=4, rotateAngle=0, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'FortyFiveUp': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=4, yshift=-4, rotateAngle=-45, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'FortyFiveDown': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=4, yshift=4, rotateAngle=45, arrowColor=arrowColor, backgroundColor=backgroundColor)

      prevX = x, 
      prevY = y, 
      prevDirectionStr = directionStr
      
      #draw battery
      lcd.font(lcd.FONT_DejaVu24)
      if batteryStr != prevBatteryStr:
        textColor = batteryTextColor
        w = lcd.textWidth(batteryStr)
        if prevBatteryStr != None: 
          cleanupX = math.ceil(315 - lcd.textWidth(prevBatteryStr))
        else:
          cleanupX = None 
        printText(batteryStr, math.ceil(315 - w), 12, prevBatteryStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, textColor=textColor, cleanupX=cleanupX) 
        prevBatteryStr = batteryStr 

      #draw sgv diff
      if prevSgvDiffStr != sgvDiffStr:
        textColor = lcd.WHITE
        if math.fabs(sgvDiff) >= 10 and backgroundColor != lcd.RED and not tooOld: textColor = lcd.RED
        w = lcd.textWidth(sgvDiffStr)
        if prevSgvDiffStr != None: 
          cleanupX = math.ceil(30 + (320 - lcd.textWidth(prevSgvDiffStr)) / 2)
        else:
          cleanupX = None 
        x = math.ceil(30 + (320 - w) / 2)
        printText(sgvDiffStr, x, 12, prevSgvDiffStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, textColor=textColor, cleanupX=cleanupX)
        prevSgvDiffStr = sgvDiffStr
    
      #draw dateStr
      if dateStr != prevDateStr:
        lcd.font(lcd.FONT_DejaVu24)
        textColor = lcd.WHITE
        if isOlderThan(sgvDateStr, 10, now): 
          textColor = lcd.RED
        w = lcd.textWidth(dateStr)
        x = math.ceil((320 - w) / 2)
        y = 240-24-5
        if prevDateStr != None: 
          cleanupX = math.ceil((320 - lcd.textWidth(prevDateStr)) / 2)  
        else:
          cleanupX = None  
        printText(dateStr, x, y, prevDateStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, textColor=textColor, cleanupX=cleanupX)  
        prevDateStr = dateStr

    elif currentMode in range(4,7):
      #flip mode
    
      #draw current time
      prevTimeStr = printLocaltime(prevTimeStr, mode, secondsDiff, useLock=True)

      #draw sgv 
      lcd.font(lcd.FONT_DejaVu72)
      w = lcd.textWidth(sgvStr)
      x = math.ceil(320 - (320 - w - 20 - 80) / 2)
      if x > 275: x = 275 #fix to bug in micropyhton
      y = 148
      if sgvStr != prevSgvStr:
        if prevSgvStr != None: 
          cleanupX = math.ceil(320 - (320 - lcd.textWidth(prevSgvStr) - 20 - 80) / 2)  
        else:
          cleanupX = None  
        printText(sgvStr, x, y, prevSgvStr, font=lcd.FONT_DejaVu72, backgroundColor=backgroundColor, rotate=180, cleanupX=cleanupX)
        prevSgvStr = sgvStr
    
      #draw arrow
      x -= (60 + w)
      y -= 30
    
      if directionStr == 'DoubleUp': drawDoubleDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, ytop=-4, ybottom=12, rotateAngle=90, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'DoubleDown': drawDoubleDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, ytop=-12, ybottom=4, rotateAngle=-90, arrowColor=arrowColor, backgroundColor=backgroundColor) 
      elif directionStr == 'SingleUp': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=0, yshift=4, rotateAngle=90, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'SingleDown': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=0, yshift=-4, rotateAngle=-90, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'Flat': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=-4, rotateAngle=180, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'FortyFiveUp': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=-4, yshift=4, rotateAngle=135, arrowColor=arrowColor, backgroundColor=backgroundColor)
      elif directionStr == 'FortyFiveDown': drawDirection(x, y, directionStr, prevX, prevY, prevDirectionStr, xshift=-4, yshift=-4, rotateAngle=-135, arrowColor=arrowColor, backgroundColor=backgroundColor)
  
      prevX = x 
      prevY = y 
      prevDirectionStr = directionStr 

      #draw battery
      lcd.font(lcd.FONT_DejaVu24)
      if batteryStr != prevBatteryStr:
        textColor = batteryTextColor
        w = lcd.textWidth(batteryStr)
        if prevBatteryStr != None: 
          cleanupX = math.ceil(lcd.textWidth(prevBatteryStr)+5)
        else:
          cleanupX = None 
        printText(batteryStr, math.ceil(w+5), 215, prevBatteryStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, rotate=180, textColor=textColor, cleanupX=cleanupX) 
        prevBatteryStr = batteryStr

      #draw sgv diff
      if prevSgvDiffStr != sgvDiffStr:
        textColor = lcd.WHITE
        if math.fabs(sgvDiff) >= 10 and backgroundColor != lcd.RED and not tooOld: textColor = lcd.RED
        w = lcd.textWidth(sgvDiffStr)
        if prevSgvDiffStr != None: 
          wp = lcd.textWidth(prevSgvDiffStr)
          cleanupX = math.ceil(wp - 30 + (320 - wp) / 2)
        else:
          cleanupX = None 
        x = math.ceil(w - 30 + (320 - w) / 2)
        printText(sgvDiffStr, x, 215, prevSgvDiffStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, rotate=180, textColor=textColor, cleanupX=cleanupX)
        prevSgvDiffStr = sgvDiffStr
    
      #draw dateStr
      if dateStr != prevDateStr:
        lcd.font(lcd.FONT_DejaVu24)
        textColor = lcd.WHITE
        if isOlderThan(sgvDateStr, 10, now): textColor = lcd.RED
        w = lcd.textWidth(dateStr)
        x = math.ceil(320 - (320 - w) / 2)
        y = 24 + 5
        if prevDateStr != None: 
          cleanupX = math.ceil(320 - (320 - lcd.textWidth(prevDateStr)) / 2)  
        else:
          cleanupX = None  
        printText(dateStr, x, y, prevDateStr, font=lcd.FONT_DejaVu24, backgroundColor=lcd.DARKGREY, rotate=180, textColor=textColor, cleanupX=cleanupX)  
        prevDateStr = dateStr
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
      print('Free memory: ' + str(gc.mem_free()) + ' bytes')
      print('Allocated memory: ' + str(gc.mem_alloc()) + ' bytes')
      printTime((utime.time() - startTime), prefix='Uptime is')
      print("Calling backend with timeout " + str(BACKEND_TIMEOUT_MS) + " ms ...")
      s = utime.time()
      backendResponseTimer.init(mode=machine.Timer.ONE_SHOT, period=BACKEND_TIMEOUT_MS+10000, callback=watchdogCallback)
      backendResponse = urequests.get(API_ENDPOINT + "/entries.json?count=10&waitfornextid=" + str(lastid) + "&timeout=" + str(BACKEND_TIMEOUT_MS), headers={'api-secret': API_TOKEN,'accept-language': LOCALE,'accept-charset': 'ascii', 'x-gms-tz': TIMEZONE})
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
          printCenteredText("Network error! Please wait.", mode, backgroundColor=lcd.RED, clear=True)
      except Exception as e:
        sys.print_exception(e)
        saveError(e)
      print('Backend call error. Retry in 5 secs ...')
      time.sleep(5)
    print('---------------------------')

def setEmergencyrgbUnitColor(setBeepColorIndex, beepColor):
  setBlackColorIndex = setBeepColorIndex-1
  if setBlackColorIndex == 0: setBlackColorIndex = 3
  #print('Colors: ' + str(setBlackColorIndex) + ' ' + str(setBeepColorIndex))
  if rgbUnit != None:
    rgbUnit.setColor(setBlackColorIndex, lcd.BLACK)
    rgbUnit.setColor(setBeepColorIndex, beepColor)
        
def emergencyMonitor():
  global emergency, response, rgbUnit, beeperExecuted, EMERGENCY_MAX, EMERGENCY_MIN, OLD_DATA_EMERGENCY
  useBeeper = False
  setColorIndex = 2
  
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
      
      beepColor = lcd.RED
      if sgv > EMERGENCY_MAX: beepColor = lcd.ORANGE  

      setEmergencyrgbUnitColor(setColorIndex, beepColor)
      setColorIndex += 1
      if setColorIndex > 3: setColorIndex = 1 
      if beeperExecuted == False:
        useBeeper = checkBeeper()
      if useBeeper == True:
        power.setVibrationEnable(True) 
        power.setVibrationIntensity(50)
        time.sleep(1)
        power.setVibrationEnable(False)
        beeperExecuted = True   
        useBeeper = False 
      else:
        time.sleep(1)
      print("beeperExecuted=" + str(beeperExecuted) + ", useBeeper=" + str(useBeeper))              
    else:
      #print('No Emergency')
      beeperExecuted = False
      useBeeper = False
      setColorIndex = 2
      time.sleep(1)

#accelerator
def mpuMonitor():
  while True:
    mpuAction()
    time.sleep(0.5)

def mpuAction():
  global mpu, mode, response
  acceleration = mpu.acceleration
  hasResponse = (response != None)
  if hasResponse and acceleration[1] < -0.1 and mode in range(0,3): mode += 4; drawScreen(response[0], clear=True) #change to 'Flip mode' #4,5,6
  elif hasResponse and acceleration[1] > 0.1 and mode in range(4,7): mode -= 4; drawScreen(response[0], clear=True) #change to 'Normal mode' #0,1,2
  elif hasResponse and acceleration[1] < -0.1 and mode == 7: mode = 8; drawScreen(response[0], clear=True)
  elif hasResponse and acceleration[1] > 0.1 and mode == 8: mode = 7; drawScreen(response[0], clear=True)

def mpuCallback(t):
  mpuAction()

def touchPadCallback(t):
  if touch.status() == True:
    t = touch.read()
    tx = t[0]
    ty = t[1]
    print("Touch screen pressed at " + str(tx) + "," + str(ty))
    if tx >= 120 and tx <= 160 and ty >= 240 and ty <= 280:
      onBtnBPressed()
    elif tx >= 240 and tx <= 280 and ty >= 240 and ty <= 280:
      onBtnCPressed()  
    else:
      onBtnPressed()

def watchdogCallback(t):
  global shuttingDown, backendResponse, rgbUnit, response, mode

  print('Restarting due to backend communication failure ...')
  if rgbUnit != None:
    rgbUnit.setColor(1, lcd.BLACK)
    rgbUnit.setColor(2, lcd.DARKGREY)
    rgbUnit.setColor(3, lcd.BLACK)
  if backendResponse != None: backendResponse.close()
  machine.WDT(timeout=1000)   
  shuttingDown = True
  printCenteredText("Restarting...", mode, backgroundColor=lcd.RED, clear=True)

def locatimeCallback(t):
  global shuttingDown, prevTimeStr, mode, secondsDiff 
  if shuttingDown == False:
    prevTimeStr = printLocaltime(prevTimeStr, mode, secondsDiff, silent=True)

def onBtnPressed():
  print('Button pressed')
  global emergency, emergencyPause
  if emergency == True:
    emergency = False
    emergencyPause = utime.time() + EMERGENCY_PAUSE_INTERVAL
  else:   
    global brightness, config
    brightness += 32
    if brightness > 128: brightness = 32
    screen = M5Screen()
    screen.set_screen_brightness(brightness)
    config["brightness"] = brightness
    saveConfigFile()

def onBtnBPressed():
  global shuttingDown, mode, config
  print('Button B pressed')
  config[ap.CONFIG] = 0
  saveConfigFile()
  machine.WDT(timeout=1000)
  shuttingDown = True
  printCenteredText("Restarting...", mode, backgroundColor=lcd.RED, clear=True)  

def onBtnCPressed():
  onBtnPressed()

# main app code -------------------------------------------------------------------     

config = None

try:
   os.stat(ap.CONFIG_FILE)
   confFile = open(ap.CONFIG_FILE, 'r')
   config = ujson.loads(confFile.read())
except Exception as e:
   sys.print_exception(e)

mode = 0
mpu = IMU()
if mpu.acceleration[1] < 0: mode = 4 #flip

brightness = 32
if config != None: brightness = config["brightness"]
screen = M5Screen()
screen.set_screen_brightness(brightness)

lcd.clear(lcd.DARKGREY)
printCenteredText("Starting...", mode, backgroundColor=lcd.DARKGREY, clear=True)  

envUnit = None
try: 
  envUnit = unit.get(unit.ENV3, unit.PORTA)
  print('Temperature:',str(envUnit.temperature) + " C")
  print('Humidity:',str(envUnit.humidity) + " %")
  print('Pressure:',str(envUnit.pressure) + " hPa")
except Exception as e:
  print('Weather Monitoring Unit not found')
  #sys.print_exception(e)

rgbUnit = None
try: 
  rgbUnit = unit.get(unit.RGB, unit.PORTA)
  rgbUnit.setColor(1, lcd.BLACK)     
  rgbUnit.setColor(2, lcd.DARKGREY)
  rgbUnit.setColor(3, lcd.BLACK)
except Exception as e:
  print('RGB Unit not found')
  #sys.print_exception(e)

print('Starting ...')
print('APIKEY:', deviceCfg.get_apikey())
print('Board name:', deviceCfg.get_board_name())
print('System:', sys.implementation)
macaddr=wifiCfg.wlan_sta.config('mac')
macaddr='{:02x}:{:02x}:{:02x}:{:02x}:{:02x}:{:02x}'.format(*macaddr)
print('MAC Adddress:', macaddr)
print('Free memory:', str(gc.mem_free()) + ' bytes')
machine_id = binascii.hexlify(machine.unique_id())
print('Machine unique id:', machine_id.decode())

response = None
emergency = False
emergencyPause = 0
shuttingDown = False
backendResponse = None
beeperExecuted = False
  
headerColor = None
middleColor = None
footerColor = None
prevX = None
prevY = None
prevDirectionStr = None
prevDateStr = None 
prevSgvDiffStr = None
prevBatteryStr = None 
prevTimeStr = None 
prevSgvStr = None
batteryStrIndex = 0

if config == None or config[ap.CONFIG] == 0:
   printCenteredText("Connect AP ...", mode, backgroundColor=lcd.RED, clear=True)
   print("Connect wifi " + ap.SSID)
   def reboot():
      global shuttingDown 
      print('Restarting after configuration change...')
      machine.WDT(timeout=1000)   
      shuttingDown = True
      printCenteredText("Restarting...", mode, backgroundColor=lcd.RED, clear=True)   
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
     printCenteredText("Fix config!", mode, backgroundColor=lcd.RED, clear=True)
     time.sleep(2)
     machine.WDT(timeout=1000)
     shuttingDown = True
     printCenteredText("Restarting...", mode, backgroundColor=lcd.RED, clear=True)

# activate buttons to enable configuration changes     
  
btnA.wasPressed(onBtnPressed)
btnB.wasPressed(onBtnBPressed)
btnC.wasPressed(onBtnCPressed)

# from here code runs only if application is properly configured

nic = network.WLAN(network.STA_IF)
nic.active(True)

printCenteredText("Scanning wifi ...", mode, backgroundColor=lcd.DARKGREY)

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
      printCenteredText("Wifi not found!", mode, backgroundColor=lcd.RED, clear=True)  
  if wifi_password == None: time.sleep(1)

printCenteredText("Connecting wifi...", mode, backgroundColor=lcd.DARKGREY) #lcd.OLIVE)
nic.connect(wifi_ssid, wifi_password)
print('Connecting wifi ' + wifi_ssid)
while not nic.isconnected():
  print(".", end="")
  time.sleep(0.25)
print("")  

time_server = 'pool.ntp.org'
printCenteredText("Setting time...", mode, backgroundColor=lcd.DARKGREY) #lcd.GREENYELLOW)
print('Connecting time server ' + time_server)
now_datetime = None
while now_datetime is None:
  try:
    print(".", end="")
    #TODO use 0.pool.ntp.org, 1.pool.ntp.org, 2.pool.ntp.org, 3.pool.ntp.org
    rtc.settime('ntp', host=time_server, tzone=1) #UTC = GMT+0
    now_datetime = getRtcDatetime()
    startTime = utime.time()
  except Exception as e:
    sys.print_exception(e)
    #saveError(e)
    time.sleep(2)
print("\nCurrent UTC datetime " +  str(now_datetime))

printCenteredText("Loading data...", mode, backgroundColor=lcd.DARKGREY) #lcd.DARKGREEN)

sgvDict = readSgvFile()
dictLen = len(sgvDict)
print("Loaded " + str(dictLen) + " sgv entries")

#max 4 timers 0-3

touchPadTimer = machine.Timer(0)
touchPadTimer.init(period=100, callback=touchPadCallback)

backendResponseTimer = machine.Timer(1)
  
localtimeTimer = machine.Timer(2)
localtimeTimer.init(period=1000, callback=locatimeCallback)

#using mpuMonitor thread instead
#mpuTimer = machine.Timer(3)
#mpuTimer.init(period=500, callback=mpuCallback)

#main method and threads

#_thread.start_new_thread(backendMonitor, ())
_thread.start_new_thread(emergencyMonitor, ())
_thread.start_new_thread(mpuMonitor, ())

backendMonitor()