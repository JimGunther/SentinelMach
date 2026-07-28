#from array import *
from datetime import datetime, timedelta
import os
import time
import sys
import subprocess
import config
from theDB import theDB
from qutie import Qutie

#*********************************************************************************************************************************
# GtHouseM.py: main Python file for Sentinel project. Acts as intermediary between Sentry RFID terminals (using Wifi/MQTT) and the
# Sentinel database, running on the same RPi on the MariaDB database server: now with added support for machines!
#
# Version 0.2
# Last updated 28/07/2026 09:16
# Author: Jim Gunther
#*********************************************************************************************************************************

config.init()
qt = Qutie()
prevHour = datetime.now().hour
fireTimeout = datetime.now() + timedelta(days=99)
prevDay = 0
prevCommands = []
prevMessages = []
machPerms = []
machNos = {}
dtPerms = datetime.now() - timedelta(days=99)

def handleIncomingTouch() -> None:
    '''handleIncomingTouch(): method called every time a fob touches the RFID screen - via MQTT from a Sentry
    parameters: none
    returns none, but publishes a reply on MQTT 
    '''
    global fireTimeout
    if not config.touchReceived:    # do nothing
        return
    
    config.touchReceived = False    # reply only once
    icMess = config.icBuffer
    sender = config.sender
    if config.mach:
        fobuid = icMess[0:8]    ## ASSUMES UID IS 8 CHARACTERS LONG
        machNo = int(icMess[9:])    ## ASSUMES UID IS 8 CHARACTERS LONG FOLLOWED BY 'M' and number
        matched = matchBoth(fobuid, machNo)
        yn = matched ? ':Y' : ':N'
        reply = icMess + yn
        qt.postStuff(sender + "/OUT", reply)
        return
    else:
        fobUID = icMess # only item in payload from Sentry
    
    try:
        hexcheck = int(fobUID, 16)  # to check fobID format only
    except:
        theDB.logMessage("Invalid fob UID format" + fobUID)
        return
    theDB.logTouch(fobUID)
    
    if fobUID == theDB.getEMF(1) or fobUID == theDB.getEMF(2):
        #print("Send email") # TEMP
        # Line below is my best guess at syntax
        subprocess.run(["sh","/home/MIS/Sentinel/bin/InNow.sh"])
        qt.messageAllSentries("Fire alarm from " + sender)
        theDB.logMessage("Fire alarm from " + sender)
        fireTimeout = datetime.now() + timedelta(hours=3)
        return
    
    result = theDB.matchShedder(fobUID)
    if result is not None:  # matching fob in database: must be visit (in or out)
        shedderID, dummy, givenName = result # unpack tuple
        if theDB.isInShed(shedderID):   # must be exit
            theDB.addExit(shedderID)
            reply = fobUID + ":B:" + givenName
        else:
            theDB.addVisit(shedderID)
            reply = fobUID + ":W:" + givenName
    else: # no match: add to Fob Store unless already in use
        reply = fobUID + ":N"
        if not theDB.isAPerm(fobUID):
            ok = theDB.addFob(fobUID) #false if already in fob store
            if not ok:
                theDB.logMessage(fobUID + " is already in Fob Store")
        else:
            theDB.logMessage(fobUID + " is already in use")

    qt.postStuff(sender + "/OUT", reply) # always reply to RFID (even if adding to fob store)

def onTimeout() -> None:
    global fireTimeout
    fireTimeout = datetime.now() + timedelta(days=99)
    qt.messageAllSentries("MiS Tag Identity" )
    theDB.logMessage("MiS Tag Identity")

def forcees() -> None:   # runs dailyReport()
    '''forceExits(): now just runs daily report
    parameters: none
    returns: none, but calls dailyReport method just before return
    '''
    global prevHour
    currHour = datetime.now().hour
    if (currHour != prevHour) and (currHour == config.forceeHour):
        dailyReport()
        readPermissions()
    prevHour = currHour

def dailyReport() -> None:
    '''dailyReport(): creates text file of daily visitors and those who didn't log out
    parameters: none
    returns: none
    '''
    
    # First, construct name of file to create
    dir = "/home/MIS/Reports/Sentinel/"
    dt = datetime.now().strftime("%Y-%m-%d")
    fName = dir + "D" + dt + ".txt" 

    # Now, open new file and write to it
    f = open(fName, 'wt')
    print("Men In Sheds Bedford: Daily Report for " + dt, file=f)
    print("================================================\n\n", file=f)
    print("Visitors Today:", file=f)
    print("Name------------ID-In----Out--------------------\n", file=f)
    visitors = theDB.listTodaysAll()
    for v in visitors:
        fullName = v[0] + " " + v[1]
        inTime = v[3].strftime("%H:%M")
        if (v[4] is None):
            outTime = "-----"
        else:
            outTime = v[4].strftime("%H:%M")
        print(f'{fullName:<16} {v[2]:>3} {inTime:<6}{outTime:>6}', file=f)
    print("\n\n", file=f)
    print("Auto Checkouts Today:", file=f)
    print("Name--------------------------------------------\n", file=f)
    forcees = theDB.listTodaysForcees()
    for fe in forcees:
        print(fe[0] + " " + fe[1], file=f)
    print("\n\n", file=f)
    print("People with Day Fobs:", file=f)
    print("FobID--Name--------------------------------------\n", file=f)
    dayFobbers = theDB.dayFobbers()
    for df in dayFobbers:
        print(df[1] + " " + df[0], file=f)
    print("\n\n", file=f)
    print("Report created " + datetime.now().strftime("%A, %d %B %Y %H:%M"), file=f)
    f.close()

def monthlyReport() -> None:
    '''monthlyReport(): creates a report as CSV file of daily attenders in calendar format
    parameters: none (but code assumes it is run on 1st of each month)
    returns: none
    '''
    assert datetime.now().day == 1, "Today is not 1st of Month"
    
    # First, construct name of file to create
    dir = "/home/MIS/Reports/Sentinel/"
    td = timedelta(days=-7) # report runs on 1st of next month, so any day "safely" last month
    dt = (datetime.now() + td).strftime("%Y-%m")
    fName = dir + "M" + dt + ".csv"
    
    tbl = [[0]*7 for i in range(6)] ## initialize 2-d array

    # calculate offset in first row from day of week for 1st of last month
    first = datetime.fromisoformat(dt + "-01")
    wd = first.weekday()
    adjust = (wd + 6) % 7
    dtMon = first + timedelta(days=-wd)

    visits = theDB.monthlyVisits()
    
    # populate tbl calendar-fashion
    for v in visits:
        n = v[1] + adjust   # n is absolute position in table; convert to x,y
        y = (int)(n / 7)
        x = n % 7
        tbl[y][x] = v[0]

    # Now write to csv file
    f = open(fName, 'wt')
    print(dt, file=f)
    print("w/c,Mon,Tue,Wed,Thu,Fri,Sat,Sun,Ave", file=f)  #header row
    for y in range(0, 6):
        line = ""
        if dtMon < datetime.today():    # don't print 6th row if not needed
            print(dtMon.strftime("%d/%m"), file=f, end="")
            count = 0
            sum = 0
            for x in range(0, 7):
                print(", " + str(tbl[y][x]), file=f, end="")
                if tbl[y][x] > 0:
                    count += 1
                sum += tbl[y][x]
            if count == 0:
                ave = 0.0
            else:
                ave = sum / count
            line += ",{:.1f}".format(ave)
            print(line, file=f)   # row average
        dtMon = dtMon + timedelta(days=7) # move on one week
    line="Ave"
    count2 = 0
    sum2 = 0
    for x in range(0, 7):   # column averages
        count = 0
        sum = 0
        for y in range(0, 6): # 6th row may be all zeros (ok)
            if tbl[y][x] > 0:
                count += 1
                count2 += 1
            sum += tbl[y][x]
            sum2 += tbl[y][x]
        if count == 0:
            ave = 0.0
        else:
            ave = sum / count
        line += ",{:.1f}".format(ave)
    if count2 == 0:
        ave2 = 0.0
    else:
        ave2 = sum2 / count2
    line += ",{:.1f}".format(ave2) + "\n"
    print(line, file=f)
    f.close()

def monthlyVisitors() -> None:
    '''monthlyVisitors(): creates a report as CSV file of daily attenders in list format, including names
    parameters: none (but code assumes it is run on 1st of each month)
    returns: none
    '''
    assert datetime.now().day == 1, "Today is not 1st of Month"
    
    # First, construct name of file to create
    dir = "/home/MIS/Reports/Sentinel/"
    td = timedelta(days=-7) # report runs on 1st of next month, so any day "safely" last month
    dt = (datetime.now() + td).strftime("%Y-%m")
    fName = dir + "V" + dt + ".csv"    

    visitors = theDB.monthVisitors()

    # Now write to csv file
    f = open(fName, 'wt')
    print (fName[27:39], file=f)
    print ("Name, ID, fobUID, Date", file=f)
    for vis in visitors:
        line = vis[0] + "," + str(vis[1]) + "," + vis[2] + "," + vis[3].strftime("%d-%m-%Y")
        print (line, file=f)
    f.close()


# creates monthly report file on 1st day of month at midnight
def checkMonthly() -> None:
    ''' checkMonthly(): method to run monthly report at midnight on 1st day of month (checks for this)
    parameters: none
    returns: none
    '''
    global prevDay
    dt = datetime.now().day
    if dt != prevDay:
        if dt == 1:
            monthlyReport()
            monthlyVisitors()
    prevDay = dt
# =================================================================================================================

def readNumbers() -> bool:
    '''readNumbers(): reads CSV lookup table matching machine names and numbers
    parameters: nonereturns: bool TRue if read successfully, otherwise False
    '''
    global machNos
    fNos = open('MacNos.csv', 'rt')
    comma = ','
    mn = {}
    try:
        while True:
            line = fNos.readline()
            if not line:
                break
            ix = line.find(comma)
            mnm = line[0:ix]
            mno = line[ix + 1:]           
            if mno.isdecimal(): # checks mch is a valid decimal number
                mNo = int(mno)
            mn[mnm] = mNo
        fNos.close()
        machNos = mn.copy() # copy to global variable dictionary
        return True
    except:
        return False
    
def readPermissions() -> bool:
    '''readPermissions(): provisional method to read the machine permissions file and store the results in an array of tuples (int, str)
        This function checks first if the file has been changed since last read.
    parameters: nonereturns: bool: True if successfully read and updated
    '''
    global machPerms
    dtSaved = os.path.getmtime('Permissions.csv')
    if dtPerms < dtSaved:
        # read file with machine permissions
        fPerms = open('Permissions.csv', 'rt')
        comma = ','
        mp = []
        try:
            while True:
                line = fPerms.readline()
                if not line:
                    break
                ix = line.find(comma)
                mch = line[0:ix]
                if mch.isdecimal(): # checks mch is a valid decimal number
                    mNo = int(mch)
                    uid = line[ix + 1:]
                    if all(c in string.hexdigits for c in uid): # checks uid is a valid hexadecimal string
                        mp.append((mNo, uid))
            fPerms.close()
            machPerms.clear() # empty the permanent (global) list
            for p in mp:
                machPerms.append(p)
            dtPerms = datetime.now()
        return True
        except:
            return False
    else:
           return False
    
def setupCommands() -> None:
    global prevCommands
    results = theDB.listTerminals()
    for row in results:
        prevCommands.append('ZZZ') # start with a dummy value

def setupMessages() -> None:
    global prevMessages
    results = theDB.listTerminals()
    for row in results:
        prevMessages.append(row[1]) # current LCDTexts stored on database at startup
    
def checkForCommands() -> None:
    '''checkForCommands: handles commands from administrator to be carried out by Sentry terminals
        parameters: none
        returns: none
    '''
    global prevCommands
    results = theDB.listTerminals()
    i = 0
    for row in results:
        cmd = row[2]
        if not (cmd == prevCommands[i]):
            #print(cmd)
            prevCommands[i] = cmd
            target = row[0]
            if cmd == "RST":
                qt.rebootSentry(target)
            if cmd == "LCD":
                qt.switchLCD(cmd)
            if (cmd[0:3] == "RED") or (cmd[0:3] == "GRN"):
                qt.setIntvl(cmd)
        i = i + 1
    theDB.resetCommand()

def checkForMessages() -> None:
    '''checkForMessages: handles admin messages from website to be passed on to Sentry terminals
        parameters: none
        returns: none
    '''
    global prevMessages
    results = theDB.listTerminals()
    i = 0
    for row in results:
        mess = row[1]
        if not (mess == prevMessages[i]):
            prevMessages[i] = mess

            target = row[0]
            if target == "ALL":
                qt.messageAllSentries(mess)
                return
            qt.messageSentry(target, mess)
        i = i + 1

def matchBoth(uid: str, mNo: int) -> bool:
    matched = False
    for mp in machPerms:
        if (mp[0] == mNo) and (mp[1] == uid):
            matched = True
            break
    return matched
    
# ====================================================================================

def setup():
    ok = readNumbers()
    ok &= readPermissions()
    if not ok:
        print ("Setup failed: reading CSV files" )
        return
    qt.client.loop_start()  # starts MQTT client looping
    setupMessages()
    setupCommands()
    print ("Setup done")

def loopGH():
    global fireTimeout
    while True:
        try:
            handleIncomingTouch()
            forcees()    # runs at set time: currently 18:00: now includes readPermissions() if file changed
            checkMonthly()
            checkForCommands()
            checkForMessages()
            if datetime.now() > fireTimeout:
                onTimeout()
            time.sleep(0.2)
        except KeyboardInterrupt:
            print("Program interrupted by user(Ctrl+C)")
            sys.exit()
        #except Exception as err:
         #   theDB.logMessage(str(err))
          #  sys.exit()

setup()
loopGH()
        