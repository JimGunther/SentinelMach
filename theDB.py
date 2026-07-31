import MySQLdb
from dotenv import load_dotenv, find_dotenv, dotenv_values 
import os

#*********************************************************************************************************************************
# theDB.py: support Python file for Sentinel project. Handles the Functionality of data transfer using SQL between the code and
# the Sentinel database
#
# Version 1.5
# Last updated 30/07/2025 15:58
#
# Author: Jim Gunther
#*********************************************************************************************************************************

# class to handle all communication with MySQL database server
class theDB:

    global user_id
    global passwd
    global dbase

    load_dotenv(find_dotenv())
    user_id = os.getenv("DB_USER")
    passwd = os.getenv("PASSWORD")
    dbase = os.getenv("DBASE")

    # e-mail fob
    @classmethod
    def getEMF(cls, numFob: int) -> str | None:
        if numFob == 1:
            return os.getenv("EMFOB1")
        else:
            return os.getenv("EMFOB2")

    # Reusable helper methods
    @classmethod
    def openDB(cls, sql : str) -> tuple:
        global user_id, passwd, dbase
        db = MySQLdb.connect(host="localhost", user=user_id, password=passwd, db=dbase)
        curs = db.cursor()
        curs.execute(sql)
        return (db, curs)
    
    @classmethod
    def fetchOne(cls, sql: str) -> tuple | None:
        db, curs = cls.openDB(sql)
        result = curs.fetchone()
        db.close()
        return result

    @classmethod
    def fetchAll(cls, sql : str) -> list | None:
        db, curs = cls.openDB(sql)
        results = curs.fetchall()
        db.close()
        return results
    
    @classmethod
    def changeData(cls, sql : str) -> bool:
        db, curs = cls.openDB(sql)
        b = True
        try:
            db.commit()
        except Exception as ex:
            db.rollback()
            print(str(ex))
            b = False
        db.close()
        return b

    # Methods for writing to / reading from data tables

    # 0. Log all fob touches
    @classmethod
    def logTouch(cls, fobUID: str) -> bool:
        '''logTouch(): method to log every fob touch
        parameter: fobUID: string : UID of fob just touched
        returns: bool: True if successful'''
        sql = "INSERT INTO TouchLog (dtLog, FobUID) VALUES (NOW(), " + fobUID + ")"
        return cls.changeData(sql)

    # 1. Read IDs from Shedders table to validate fob and get given name
    @classmethod
    def matchShedder(cls, fobUIDString : str) -> tuple | None:
        '''matchShedder(): finds a shedder whose fob UID matches
        parameter: fobUIDString: string representation of fon hexadecimal UID number
        returns: tuple(ID, fobUID, given name) if match found, None otherwise
        '''
        sql = "SELECT ID, FobUID, GivenName FROM Shedders WHERE EndDate IS NULL AND FobUID = '" + fobUIDString + "'"
        return cls.fetchOne(sql)
        
    # 1A. Get fobuid from membership number
    @classmethod
    def fobFromNo(cls, memNo: int) -> str:
        '''fobFromNo(): gets a shedder's fobUID from their membership ID
        parameter: memNo: int: shedder's unique membership number
        returns: str: the matching fob UID string
        '''
        sql = "SELECT FobUID FROM Shedders WHERE ID = " + str(memNo)
        result = cls.fetchOne(sql)
        if result is None:
            return "none"
        else:
            return result[0] # result is a tuple with one member

    # 2. Is person in or out of shed?
    @classmethod
    def isInShed(cls, id : int) -> bool:
        '''isInShed(): checks whether shedder is currently signed in
        parameter: id: int: unique id for shedder
        returns: bool: True if signed in, False otherwise
        '''
        sql = "SELECT ShedderID FROM Visits WHERE EndTime IS NULL AND ShedderID = " + str(id)
        result = cls.fetchOne(sql)
        return result is not None
   
    # 3. Add entry to Visits table
    @classmethod
    def addVisit(cls, shedderID : int) -> bool:
        '''addVisit(): adds a visit record, start time now, for given user
        parameter: shedder ID : int
        returns: bool: True if successfully added, else False
        '''
        sql = "INSERT INTO Visits (StartTime, ShedderID) VALUES (NOW(), " + str(shedderID) + ")"
        return cls.changeData(sql)

    # 4. Modify visits table on exit
    # returns True if succeeded
    @classmethod
    def addExit(cls, shedderID : int) -> bool:
        '''addExit(): adds an exit time to shedder visit record
        parameters:
            shedderID: int; shedder's unique ID (NOT fob UID)
        returns: bool: True if successfully updated, False otherwise
        '''
        sql = "UPDATE Visits SET EndTime = NOW() WHERE ShedderID = " + str(shedderID) + " AND EndTime IS NULL"
        return cls.changeData(sql)

    # 5. Add to message log: WE NEED TO DISCUSS WHAT GETS LOGGED!
    # returns: none
    @classmethod
    def logMessage(cls, text : str) -> bool:
        '''logMessage: adds a message to log table
        parameter: text: string: message text
        returns: bool
        '''
        sql = "INSERT INTO MessageLog (dtMessage, MessageText) VALUES (NOW(), '" + text + "')"
        return cls.changeData(sql)

    # 6. List today's visitors for report
    @classmethod
    def listTodaysAll(cls) -> list:
        '''listTodaysAll(): returns list (by name) of shedders in today
        parameters: none
        returns: list of tuples: (given name, surname)
        '''
        visitors = []
        sql = "SELECT GivenName, Surname, Id, Visits.StartTime, Visits.EndTime FROM Shedders INNER JOIN Visits On Shedders.Id = Visits.ShedderID WHERE Visits.StartTime > DATE_SUB(NOW(), INTERVAL 16 HOUR) ORDER BY Surname, GivenName"
        results = cls.fetchAll(sql)
        if results is not None:
            for result in results:
                visitors.append(result)
        return visitors
    
    # 7. List today's forced exits for report
    @classmethod
    def listTodaysForcees(cls) -> list:
        '''listTodaysForcees(): lists those still not logged out today
        parameters: none
        returns: list of tuples(given name, surname)
        '''
        forcees = []
        sql = "SELECT GivenName, Surname FROM Shedders INNER JOIN Visits on Shedders.ID = Visits.ShedderID WHERE (Visits.StartTime > DATE_SUB(NOW(), INTERVAL 16 HOUR)) AND (Visits.EndTime IS NULL) ORDER BY Surname, GivenName"
        results = cls.fetchAll(sql)
        if results is not None:
            for result in results:
                forcees.append(result)
        return forcees
    
    # 8. Add a newly detected Fob (for assignment by administrator)
    @classmethod
    def addFob(cls, uid : str) -> bool:
        '''addFob(): adds a new fob's UID to the "fob store" table
        parameter: uid: string: new fob's UID
        returns: boolean: True if successfully added, otherwise False
        '''
        # Check not in Fob Store
        sql = "SELECT FobUID FROM NewFobs WHERE FobUID = '" + uid + "'"
        row = cls.fetchOne(sql)
        if row is not None:
            return False
        
        # Check not already assigned to Shedder
        sql = "SELECT ID FROM Shedders WHERE FobUID = '" + uid + "'"
        row = cls.fetchOne(sql)
        if row is None:
            sql = "INSERT INTO NewFobs (FobUID) VALUES('" + uid + "')"
            return cls.changeData(sql)
        else:
            return False

    # 9. procedure for generating data for monthly report (count of visits by day) : runs on 1st of month only!
    @classmethod
    def monthlyVisits(cls) -> list:
        '''monthlyVisits(): produces monthly stats in a list for conversion to CSV data
        parameters: none
        returns: list of tuples (visitor count, date)
        '''
        sql = "SELECT COUNT(StartTime), DAY(StartTime) as DoM FROM Visits WHERE StartTime > DATE_SUB(NOW(), INTERVAL 1 MONTH) GROUP BY DoM"
        results = cls.fetchAll(sql)
        if results is None:
            return []   # empty list
        else:
            return results
        
    #10. procedure for listing terminals recognised
    @classmethod
    def listTerminals(cls) -> list:
        '''listTerminals(): produces list of terminal names as two-item tuples (name, LCDtext)
        parameters: none
        returns: list of tuples (terminal names)
        '''
        sql = "SELECT TerminalName, LCDText, Commd FROM Terminals ORDER BY TerminalName"
        terms = cls.fetchAll(sql)
        if terms is not None:
            return terms
        else:
            return []   # empty list
    
    #11. procedure to reset the Commd field in Terminals table
    @classmethod
    def resetCommand(cls) -> bool:
        '''resetCommand(): resets Terminal command after notifying RFID
        parameters: none
        returns: bool: True if OK
        '''
        sql = "UPDATE Terminals SET Commd = 'XXX' WHERE Commd != 'XXX' "
        return cls.changeData(sql)
    
    #12. procedure for checking if fob UID is in use
    @classmethod
    def isAPerm(cls, uid: str) -> bool:
        '''isAPerm: checks if uid is in use in PrmUID column of Shedders table
        parameters: uid: str: fobUID to check
        returns: bool: True if found
        '''
        sql = "SELECT PrmUID FROM Shedders WHERE (EndDate IS NULL) AND (PrmUID IS NOT NULL) AND (PrmUID = '" + uid + "')"
        result = cls.fetchAll(sql)
        if result is None:
            return False
        else:
            return (len(result) > 0)

    #13. procedure to list "DayFobbers" for daily report
    @classmethod
    def dayFobbers(cls) -> list:   
        '''dayFobbers(): list those who forgot their fobs and use a "day fob"
        parameters: none
        returns: list of tuples'''
        sql = "SELECT CONCAT(GivenName, ' ', Surname) AS FullName, FobUID FROM Shedders WHERE PrmUID IS NOT NULL ORDER BY Surname, GivenName"
        df = cls.fetchAll(sql)
        if df is None:
            return []   # empty list
        else:
            return df
        
    #14. procedure to get monthly visitors data
    @classmethod
    def monthVisitors(cls) -> list:
        '''monthVisitors() list with names of all visitors in the past month
        parameters: none
        returns: list of tuples
        '''
        sql = "SELECT CONCAT(Shedders.GivenName, ' ', Shedders.Surname) AS FullName, Shedders.ID, Shedders.FobUID, Visits.StartTime "
        sql += "FROM Shedders INNER JOIN Visits ON Shedders.ID = Visits.ShedderID "
        sql += "WHERE Visits.StartTime > DATE_SUB(NOW(), INTERVAL 1 MONTH) ORDER BY Visits.StartTime"
        print (sql)
        mv = cls.fetchAll(sql)
        if mv is None:
            return []
        else:
            return mv