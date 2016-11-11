#!/usr/bin/python3.5
# -*- coding: utf-8 -*-

# 並列において以下のパッチが必要
# https://github.com/pexpect/pexpect/pull/376/files#r78765769

# Ubuntuの場合、以下のようにすること
# sudo add-apt-repository ppa:fkrull/deadsnakes
# sudo apt-get update
# sudo apt-get install python3.5
# wget https://bootstrap.pypa.io/get-pip.py -O /tmp/get-pip.py
# sudo python3.5 /tmp/get-pip.py
# sudo pip3.5 install pexpect
# sudo pip3.5 install PyYAML

import asyncio
import time
import pexpect
import sys
import yaml

sample_yaml="""
global:
 tftpserver: "192.168.196.99"
nodes:
 - name: "crs1k-1"
   type: "iosxe"
   spawn: "telnet 192.168.196.100"
   loginuser: "name"
   loginpass: "pass"
 - name: "crs1k-1-clone"
   type: "iosxe"
   spawn: "telnet 192.168.196.100"
   loginuser: "name"
   loginpass: "pass"
"""

class AuthError(Exception):
     def __init__(self, value):
         self.value = value
     def __str__(self):
         return repr(self.value)


class CiscoIOSXE:
    p = None
    name = ""
    is_enable = False
    loginuser = None
    loginpass = None
    enablepass = None
    def __init__(self, spawn, name = "", loginuser =None,
                 loginpass =None, enablepass=None, type = ""):
        self.p = pexpect.spawn(spawn, encoding="utf-8")
        self.p.logfile = sys.stdout
        self.name = name
        self.loginuser = loginuser
        self.loginpass = loginpass
        self.enablepass = loginpass
        if enablepass != None:
            self.enablepass = enablepass
        self.msg("INIT")

    @asyncio.coroutine
    def login(self):
        yield from self.p.expect("name: ", async=True)
        self.p.sendline(self.loginuser)
        yield from self.p.expect("word: ", async=True)
        self.p.sendline(self.loginpass)
        i = yield from self.p.expect([r">", r"#", r"Authentication failed"],
                                 async=True)
        if i == 0:
            self.setPrompt(self.p.before.split("\n")[-1])
        elif i == 1:
            self.setPrompt(self.p.before.split("\n")[-1])
            self.is_enable = True
        elif i == 2:
            raise AuthError("login")

    @asyncio.coroutine
    def enable(self):
        self.msg("enable P:")
        if self.is_enable:
            return
        self.p.sendline("enable")
        i = yield from self.p.expect([self.prompt + "#", r"word: "], async = True)
        if i == 0:
            self.msg("already enable")
            self.is_enable = True
            return
        self.p.sendline(self.enablepass)
        i = yield from self.p.expect([self.prompt + "#", r"Access denied"], async = True)
        if i == 1:
            raise AuthError("enable")
        self.msg("enable ok")

    def setPrompt(self, prompt):
        self.msg("set PROMPT: {0}".format(prompt))
        self.prompt = prompt

    def msg(self, msg):
        print("[{0}]: {1}".format(self.name, msg))

    @asyncio.coroutine
    def tftpbackup(self, path):
        try:
            yield from self.login()
        except AuthError as e:
            return({"name": self.name, "status": "AuthError: " + e.value , "res": "", })
        except pexpect.exceptions.EOF as e:
            return({"name": self.name, "status": "Timeout"  , "res": "", })

        try: 
            yield from self.enable()
        except AuthError as e:
            return({"name": self.name, "status": "AuthError: " + e.value , "res": "", })
        except pexpect.exceptions.EOF as e:
            return({"name": self.name, "status": "Timeout"  , "res": "", })

        self.p.sendline("copy running-config {0}".format(path))
        try:
            yield from self.p.expect("remote host", async = True)
        except pexpect.exceptions.EOF as e:
            return({"name": self.name, "status": "Timeout"  , "res": "", })
        self.p.sendline("")

        try:
            yield from self.p.expect("filename", async = True)
        except pexpect.exceptions.EOF as e:
            return({"name": self.name, "status": "Timeout"  , "res": "", })
        self.p.sendline("")

        try:
            i = yield from self.p.expect([self.prompt + "#", r"Permission denied", "Timed out"], async = True, timeout = 40)
        except pexpect.exceptions.EOF as e:
            return({"name": self.name, "status": "Timeout"  , "res": "", })
        if i == 1:
            return({"name": self.name, "status": "TFTPServer: Permission denied"  , "res": "", })
        elif i == 2:
            return({"name": self.name, "status": "TFTPServer: Timeout"  , "res": "", })

        self.p.sendline("logout")
        return({"name": self.name, "status": "ok", "res": "", })


if __name__ == "__main__":
    dat = yaml.load(sample_yaml)
    argv = sys.argv
    argc = len(argv)
    if argc == 2:
        fr = open(argv[1], "r")
        y = fr.read()
        dat = yaml.load(y)
    cors = []
    g = dat["global"]
    for e in dat["nodes"]:
        if e["type"] == "iosxe":
            o = CiscoIOSXE(**e)
        else:
            continue
        cors.append(o.tftpbackup("tftp://" + g["tftpserver"] + "/" + e["name"]))
    loop = asyncio.get_event_loop()
    r = loop.run_until_complete(asyncio.gather(*cors))
    print(r)