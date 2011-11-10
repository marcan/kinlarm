#!/usr/bin/env python

import logging
import sys
import time
import threading

import kinectcore
import mail
import motion
import sounder
import web

from freenect import LED_GREEN, LED_RED, LED_YELLOW, LED_BLINK_RED_YELLOW, LED_BLINK_GREEN

from config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')

class AlarmSystem(object):
	def __init__(self):
		self.kinect = kinectcore.KinectStreamer()
		self.motion = motion.MotionSensor(self.kinect)
		self.web = web.WebServer(self, self.kinect)
		self.sounder = sounder.AudioSounder()
		self.lock = threading.Lock()

		self.threads = [
			self.kinect,
			self.motion,
			self.web
		]

		self.states = [
			"disarmed", "arming", "armed", "prealarm", "notify", "alarm", "silenced"
		]

	def run(self):
		logging.warning("Alarm controller starting")
		try:
			self.body()
		finally:
			for thread in self.threads[::-1]:
				try:
					if thread.is_alive():
						thread.stop()
				except:
					logging.exception("Exception while stopping thread")

	def body(self):
		self.kinect.start()
		self.web.start()

		self.state = self.disarmed
		self.new_state = None
		while True:
			self.state = self.state()
			with self.lock:
				if self.new_state:
					self.state = self.new_state
					self.new_state = None

	def disarmed(self):
		logging.info("State: DISARMED")
		self.kinect.set_led(LED_GREEN)
		while True:
			time.sleep(1)
			if self.new_state:
				return

	def arming(self):
		logging.info("State: ARMING")
		self.kinect.set_led(LED_BLINK_GREEN)
		for i in range(ARM_TIME):
			time.sleep(1)
			if self.new_state:
				return
		return self.armed

	def armed(self):
		logging.info("State: ARMED")
		self.kinect.set_led(LED_YELLOW)
		self.motion.start()
		try:
			self.motion.detected.clear()

			while True:
				time.sleep(1)
				if self.motion.detected.is_set():
					return self.prealarm
				if self.new_state:
					return
		finally:
			self.motion.stop()

	def prealarm(self):
		logging.info("State: PREALARM")
		self.kinect.set_led(LED_BLINK_RED_YELLOW)
		for i in range(PREALARM_GRACE):
			time.sleep(1)
			if self.new_state:
				return
		return self.notify

	def notify(self):
		logging.warning("State: NOTIFY")
		self.kinect.set_led(LED_RED)
		try:
			mail.send_alert("Motion detected")
		except:
			logging.exception("Alert failed!")
			return self.alarm

		for i in range(NOTIFY_TIMEOUT):
			time.sleep(1)
			if self.new_state:
				return
		return self.alarm

	def alarm(self):
		logging.warning("State: ALARM")
		self.kinect.set_led(LED_RED)
		self.sounder.activate()
		try:
			while True:
				time.sleep(1)
				if self.new_state:
					return
		finally:
			self.sounder.deactivate()

	def silenced(self):
		logging.warning("State: SILENCED")
		self.kinect.set_led(LED_RED)
		while True:
			time.sleep(1)
			if self.new_state:
				return

	def switch_state(self, new_state):
		with self.lock:
			statefunc = getattr(self,new_state)
			if statefunc == self.state:
				return
			else:
				self.new_state = statefunc

	def stop(self):
		self.web.stop()
		self.motion.stop()
		self.kinect.stop()

if __name__ == "__main__":
	system = AlarmSystem()
	system.run()
