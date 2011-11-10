#!/usr/bin/env python

import freenect
import logging
import numpy as np
import threading

import debug
from config import *

class StreamerDied(Exception):
	pass

class OneQueue(object):
	def __init__(self):
		self.val = None
		self.event = threading.Event()
		self.lock = threading.Lock()

	def get(self):
		self.event.wait()
		with self.lock:
			self.event.clear()
			if isinstance(self.val, Exception):
				raise self.val
			else:
				return self.val

	def put(self, val):
		with self.lock:
			self.event.set()
			self.val = val

class KinectConsumer(object):
	def __init__(self, remove):
		self.remove = remove
		self.queue = OneQueue()
		self.active = True

	def __iter__(self):
		return self
	def next(self):
		return self.queue.get()

	def stop(self):
		if self.active:
			self.remove(self.queue)
			self.active = False
	def __del__(self):
		self.stop()

class KinectStreamer(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self, name="KinectStreamer")
		self.video_consumers = {}
		self.depth_consumers = {}
		self.video_frame = 0
		self.depth_frame = 0
		self.lock = threading.RLock()
		self.update_cond = threading.Condition(self.lock)
		self.update = threading.Event()
		self.led_update = None
		self.keep_running = True

	def _video_cb(self, dev, data, timestamp):
		if INVERT_KINECT:
			data = data[::-1, ::-1] # Flip upside down
		with self.lock:
			for k,v in self.video_consumers.items():
				if self.video_frame % v == 0:
					k.put(np.copy(data))
		self.video_frame += 1

	def _depth_cb(self, dev, data, timestamp):
		if INVERT_KINECT:
			data = data[::-1, ::-1] # Flip upside down
		with self.lock:
			for k,v in self.depth_consumers.items():
				if self.depth_frame % v == 0:
					k.put(data)
		self.depth_frame += 1

	def depth_stream(self, decimate=1):
		consumer = KinectConsumer(self._remove_depth_stream)
		with self.lock:
			if not self.depth_consumers:
				self.update.set()
				self.update_cond.notify()
			self.depth_consumers[consumer.queue] = decimate
		return consumer

	def _remove_depth_stream(self, queue):
		with self.lock:
			try:
				del self.depth_consumers[queue]
			except KeyError:
				pass
			if not self.depth_consumers:
				self.update.set()
				self.update_cond.notify()

	def video_stream(self, decimate=1):
		consumer = KinectConsumer(self._remove_video_stream)
		with self.lock:
			if not self.video_consumers:
				self.update.set()
				self.update_cond.notify()
			self.video_consumers[consumer.queue] = decimate
		return consumer
	
	def _remove_video_stream(self, queue):
		with self.lock:
			try:
				del self.video_consumers[queue]
			except KeyError:
				pass
			if not self.video_consumers:
				self.update.set()
				self.update_cond.notify()

	def set_led(self, ledstate):
		with self.lock:
			self.led_update = ledstate
			self.update_cond.notify()

	def update_streams(self):
		if self.depth_started and not self.depth_consumers:
			logging.info("Stopping depth")
			freenect.stop_depth(self.dev)
			self.depth_started = False
		elif not self.depth_started and self.depth_consumers:
			logging.info("Starting depth")
			freenect.start_depth(self.dev)
			self.depth_started = True

		if self.video_started and not self.video_consumers:
			logging.info("Stopping video")
			freenect.stop_video(self.dev)
			self.video_started = False
		elif not self.video_started and self.video_consumers:
			logging.info("Starting video")
			freenect.start_video(self.dev)
			self.video_started = True

	def _body(self, ctx):
		with self.lock:
			if self.update.isSet():
				self.update_streams()
				if not self.video_started and not self.depth_started:
					raise freenect.Kill()
				self.update.clear()
				if not self.keep_running:
					raise freenect.Kill()
			if self.led_update is not None:
				freenect.set_led(self.dev, self.led_update)
				self.led_update = None

	def run(self):
		try:
			self.ctx = freenect.init()
			self.dev = freenect.open_device(self.ctx, 0)

			freenect.set_depth_mode(self.dev, freenect.RESOLUTION_MEDIUM, freenect.DEPTH_11BIT)
			freenect.set_depth_callback(self.dev, self._depth_cb)
			freenect.set_video_mode(self.dev, freenect.RESOLUTION_MEDIUM, freenect.VIDEO_RGB)
			freenect.set_video_callback(self.dev, self._video_cb)

			self.video_started = False
			self.depth_started = False

			while self.keep_running:
				with self.lock:
					if self.led_update is not None:
						freenect.set_led(self.dev, self.led_update)
						self.led_update = None
					self.update_streams()
					if not self.video_started and not self.depth_started:
						self.update_cond.wait()
						continue
					self.update.clear()
					if not self.keep_running:
						break
				freenect.base_runloop(self.ctx, self._body)
		finally:
			with self.lock:
				for k in self.depth_consumers.keys() + self.video_consumers.keys():
					k.put(StreamerDied("The Kinect streamer died"))
				self.depth_consumers = {}
				self.video_consumers = {}
				self.update_streams()
			freenect.close_device(self.dev)
			freenect.shutdown(self.ctx)


	def start(self):
		if self.is_alive():
			return
		logging.info("Kinect streamer started")
		self.keep_running = True
		threading.Thread.start(self)

	def stop(self):
		if not self.is_alive():
			return
		with self.lock:
			self.keep_running = False
			self.update.set()
			self.update_cond.notify()
		self.join()
		logging.info("Kinect streamer stopped")
