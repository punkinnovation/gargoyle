#!/usr/bin/env python3
# bt106c - CommonHandler class

import datetime
import paramiko
import subprocess
import shlex
import requests
import sys
import os

class CommonHandler:

    def __init__(self, username):

        self.username = username

        self.apiUser = os.environ['API_USER']
        self.apiPassword = os.environ['API_PW']
        self.apiHost = os.environ['API_HOST']
        self.apiBackport = os.environ['API_BACKPORT']

        self.gargoyleLogPath = '/var/log/gargoyle'

        self.checkLogFile = '%s/%s' % (self.gargoyleLogPath, 'compliance.log')
        self.errorLogFile = '%s/%s' % (self.gargoyleLogPath, 'error_log.txt')

        self.sudoWhitelistCommands = [
            '/usr/bin/stat',
            '/bin/grep',
            ]

        self.whitelistCommands = [
            '/bin/uname',
            '/bin/netstat',
            '/usr/bin/curl'
            ]

        self.charBlacklist = [
            "'",
            '|',
            ';',
            '&',
            '$',
            '>',
            '<',
            '`',
            '!',
            '>>',
            ' sudo',
            'sudo '
            ]

        return


    def getChecks(self, tblField, tblValue):
        response = requests.get(f'https://{self.apiHost}:{self.apiBackport}/v2/{tblField}/{tblValue}',
                                auth=(self.apiUser, self.apiPassword),
                                verify='/etc/ssl/certs')
        data = response.json()
        checks = data['payload']
        return checks


    def getCheck(self, rowId):
        response = requests.get(f'https://{self.apiHost}:{self.apiBackport}/v2/checks/{rowId}',
                                auth=(self.apiUser, self.apiPassword),
                                verify='/etc/ssl/certs')

        data = response.json()
        payload = []
        payload.append(data['payload'])
        data['payload'] = payload
        checks = data['payload']
        return checks


    def getPatterns(self):
        response = requests.get(f'https://{self.apiHost}:{self.apiBackport}/v2/patterns', auth=(self.apiUser,self.apiPassword), verify='/etc/ssl/certs')
        data = response.json()
        patterns = data['payload']
        return patterns



    def getHostname(self, host):
        '''
        Split an FQDN on the '.' and return the first element.

        :param str host: Full FQDN.
        :return: Return just the hostname sans domain.
        :rtype: str
        '''
        p = host.split('.')
        hostname = p[0] # keep it short
        return hostname


    def getResourceExists(self, host, resource):
        resourceFound = False
        existsCmdString = '/usr/bin/stat -t %s' % (resource)
        checkExistsCommand = self.getSshCommand(True, existsCmdString)
        resourceExists = self.getRemoteOutput(host, checkExistsCommand)
        if resourceExists:
            resourceFound = True
        return resourceFound


    def isAllowed(self, command):
        # Default no
        whitelistOK = False
        isAllowed = False

        # First arg should match allowed
        cmdParts = command.split()
        shellCmd = '%s' % (cmdParts[0].strip())

        for cmd in self.whitelistCommands:
            if cmd == shellCmd:
                whitelistOK = True

        for cmd in self.sudoWhitelistCommands:
            if cmd == shellCmd:
                whitelistOK = True

        if whitelistOK:
            isAllowed = True
        else:
            timeStamp = datetime.datetime.utcnow().isoformat() + 'Z'
            errorMsg = '%s gargoyle ERROR Whitelist violation detected: %s' % (timeStamp, command)
            errorLogger = open(self.errorLogFile, 'a')
            errorLogger.write(errorMsg + '\n')
            errorLogger.close()
            print('ERROR - Check %s' % (self.errorLogFile))
            isAllowed = False

        return isAllowed


    def isSudoWhitelist(self, command):
        # Default low priv
        runElevated = False

        # First arg should match allowed sudo, code change required for new sudo
        cmdParts = command.split()
        shellCmd = '%s' % (cmdParts[0].strip())

        for sudoCommand in self.sudoWhitelistCommands:
            if shellCmd == sudoCommand:
                runElevated = True

        return runElevated


    def areFieldsBlacklistSafe(self, fieldList):
        '''
        Check field for bad characters.

        :param list fieldList:
        :return: blacklistSafe
        :rtype: boolean:

        '''

        # Fail closed
        badFieldFound = False
        blacklistSafe = False

        #for stringField in stringList:
            # blacklisted characters from ANY string field
        for field in fieldList:
            for char in self.charBlacklist:
                if char in field:
                    badFieldFound = True
                    badField = field

        # Evaluate expectation and if count unsuccessful or fail
        if badFieldFound:
            timeStamp = datetime.datetime.utcnow().isoformat() + 'Z'
            errorMsg = '%s gargoyle ERROR Injection attempt detected: %s' % (timeStamp, badField)
            errorLogger = open(self.errorLogFile, 'a')
            errorLogger.write(errorMsg + '\n')
            errorLogger.close()
            print('ERROR - Check %s' % (self.errorLogFile))
            blacklistSafe = False
        else:
            blacklistSafe = True

        return blacklistSafe


    def getSshCommand(self, runElevated, remoteCommand):
        if runElevated:
            sshCommand = '/bin/echo "' + remoteCommand + '" | sudo /bin/bash -s'
        else:
            sshCommand = '/bin/echo "' + remoteCommand + '" | /bin/bash -s'
        return sshCommand


    def getRemoteOutput(self, host, sshCommand):
        lines = []
        host = host.strip()

        s = paramiko.SSHClient()
        s.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        s.load_system_host_keys()

        try:
            s.connect(host, username=self.username, timeout=5)
            (stdin, stdout, stderr) = s.exec_command(sshCommand) # nosec
            lines = stdout.readlines()
        except Exception as e:
            timeStamp = datetime.datetime.utcnow().isoformat() + 'Z'
            errorMsg = '%s %s ERROR %s' % (timeStamp, host, e)
            errorLogger = open(self.errorLogFile, 'a')
            errorLogger.write(errorMsg + '\n')
            errorLogger.close()
        finally:
            if s:
                s.close()

        return lines
