#*********************************************************************************************************************************
# config.py: support Python file for Sentinel project. Mainly used for gathering global variables used in other Python files
#
# Version 1.0
# Last updated 30/04/2025 20:58
# Author: Jim Gunther
#*********************************************************************************************************************************

#globals shared between modules

def init():
    global sender
    sender = "none"
    global icBuffer
    icBuffer = "(empty)"
    global ogBuffer
    ogBuffer = "(empty)"
    global touchReceived
    touchReceived = False
    global forceeHour
    forceeHour = 18