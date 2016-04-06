#!/usr/bin/python

import os
import sys
import subprocess

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), ".."))
import build_support as bs


class SlowTimeout:
    def __init__(self):
        self.hardware = bs.Options().hardware

    def GetDuration(self):
        return 500

env = {}
if (os.path.exists("/usr/local/bin/chmodtty9.sh")):
    env["DISPLAY"] = ":9"

o = bs.Options()
modules = ["gles2", "gles3"]

version = bs.PiglitTester().mesa_version()
if "11.0" not in version and "11.1" not in version and "11.2" not in version:
    if "skl" in o.hardware or "bdw" in o.hardware or "bsw" in o.hardware:
        modules += ["gles31"]
bs.build(bs.DeqpBuilder(modules, env=env), time_limit=SlowTimeout())
        
