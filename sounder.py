#!/usr/bin/env python

import subprocess
from config import *

class AudioSounder(object):
	def __init__(self):
		self.child = None

	def activate(self):
		if self.child is not None:
			return
		self.child = subprocess.Popen(PLAYBACK_COMMAND, shell=True)

	def deactivate(self):
		if self.child is None:
			return
		self.child.terminate()
		self.child.wait()
		self.child = None

try:
	import serial
except ImportError:
	pass # No PySerial, SerialSounder will fail

class SerialSounder(object):
	def __init__(self):
		self.serial = None

	def activate(self):
		if self.serial is not None:
			return
		# Just opening the serial port will trigger the DTR line
		self.serial = serial.Serial(SERIAL_PORT)

	def deactivate(self):
		if self.serial is None:
			return
		self.serial.close()
		self.serial = None
