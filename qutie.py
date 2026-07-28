import paho.mqtt.client as qt
import time
import config
from theDB import theDB

#*********************************************************************************************************************************
# qutie.py: support Python file for Sentinel project. Handles MQTT functionality, using the paho.mqtt.client library
#
# Version 1.2
# Last updated 23/07/20265 09:03
# 
# Author: Jim Gunther
#*********************************************************************************************************************************

#global variables
sents = []

msgWaiting = False

# global MQTT callback functions here --------------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc):
    '''on_connect(): sets up n MQTT subscriptions, where n = number of Sentry terminals (in database)
    parameters:
        client: MQTT client object
        [other parameters not used]
    returns: none: it's an ISR!
    '''
    for s in sents:
        client.subscribe("MiS/" + s + "/IN")

def on_icMessage(client, userdata, msg):
    '''on_icMessage(): places incoming MQTT message in icBuffer and sets config.touchReceived flag
    parameters:
        client, userdata: [not used]
        msg: string, payload text of incoming message
    returns: none
    '''
    if (msg.topic[0:9] == "MiS/RFID_") or (msg.topic[0:8] == "MiS/MACH"):
        config.mach = True
        if msg.topic[0:9] == MiS/RFID":
            config.sender = msg.topic[4:10] # works only for single digit after RFID_
            config.mach = False
        config.icBuffer = msg.payload.decode("utf-8")
        config.touchReceived = True
        #handle fob touches, otherwise ignore
    
        
   
# -----------------------------End of MQTT callbacks -----------------------------------
    
# Qutie class starts here...
class Qutie:
    def __init__(self) -> None: 
        '''__init__(): class initiations: sets up MQTT client connection
        parameters:
            self: this instance
        returns: none
        '''
        self.client = qt.Client()
        self.client.on_connect = on_connect
        self.client.on_message = on_icMessage
        global sents
        terms = theDB.listTerminals()
        sents = []
        for t in terms:
            sents.append(t[0])
    
        self.client.connect("localhost", 1883, 60)

        print("mqtt started")

    def postStuff(self, topic : str, payload : str) -> None :
        time.sleep(1.0)
        self.client.publish("MiS/" + topic, payload, 1)
        print(topic + "::" + payload)
    
    def messageSentry(self, rfid : str, msg : str) -> None: #currently not in use: use and format to be agreed
        tpc = rfid + "/MSG"
        self.postStuff(tpc, msg)

    def messageAllSentries(self, msg : str) -> None:
        for s in sents:
            tpc = "MSG" 
            self.postStuff(tpc, msg) 

    def rebootSentry(self, rfid : str) -> None:
        tpc = rfid + "/RST"
        self.postStuff(tpc, "-")

    def switchLCD(self, msg :str) -> None:
        tpc = "LCD"
        self.postStuff(tpc, msg)

    def setIntvl(self, msg : str) -> None:
        tpc = "DELAY"
        self.postStuff(tpc, msg)
