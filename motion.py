#!/usr/bin/env python

import cv2
import logging
import numpy as np
import threading

import kinectcore

from config import *

def frame_to_depth(frame):
	mask = frame > 1070
	frame = frame.astype(np.float)
	# Calculate depth in meters as a function of depth value
	depth = 1.0 / (frame * -0.0030711016 + 3.3309495161)
	# Fill the masked (invalid) areas with "5 meters" for computational purposes
	depth = np.ma.filled(np.ma.array(depth, mask=mask), 5)

	return depth, mask

def bool_to_img(frame):
	return 255 * frame.astype(np.uint8)

def depth_to_img(frame):
	return 255-((30 * frame).astype(np.uint8))

def delta_to_img(frame):
	return np.clip((60 * frame), 0, 255).astype(np.uint8)

class MotionSensor(threading.Thread):

	def __init__(self, kinect):
		threading.Thread.__init__(self, name="MotionSensor")
		self.kinect = kinect
		self.debug = False
		self.detected = threading.Event()
		self.keep_running = True

	def run(self):
		self.detected.clear()
		stream = self.kinect.depth_stream(5)

		# Load depth filter
		try:
			depth_filter = np.load("depth_filter.npy")
		except:
			depth_filter = None

		# Drop initial frames that are less than 50% valid
		while np.count_nonzero(stream.next() != 2047) < VALID_THRESHOLD:
			if not self.keep_running:
				return

		# Drop a few more frames to ensure a stable image
		for i in range(30):
			stream.next()
			if not self.keep_running:
				return

		# Obtain reference image
		ref, mask = frame_to_depth(stream.next())
		# Apply depth filter
		if depth_filter is not None:
			ref = np.minimum(ref, depth_filter)
		# Blur it
		ref = cv2.GaussianBlur(ref, (0, 0), 2)
		# Create reference mask buffer
		ref_mask_buf = mask.astype(np.float)


		# Create dilation kernel
		dilate_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))

		for frame in stream:
			# Get current frame
			depth, mask = frame_to_depth(frame)

			# Apply depth filter
			if depth_filter is not None:
				depth = np.minimum(depth, depth_filter)

			# Blur the depth
			depth = cv2.GaussianBlur(depth, (0, 0), 2)

			# Booleanize the current reference mask buffer
			ref_mask = ref_mask_buf > 0.5
			# Mask out invalid pixels in either image
			invalid = np.logical_or(mask, ref_mask)
			# Dilate the mask
			invalid = cv2.dilate(invalid.astype(np.uint8), dilate_kernel).astype(bool)

			# Count pixels lost vs. the reference image
			lost = np.logical_and(mask, np.logical_not(ref_mask))
			lost_count = np.count_nonzero(lost)

			# Mask both arrays
			masked_ref = np.ma.array(ref, mask=ref_mask)
			masked_depth = np.ma.array(depth, mask=invalid)

			# Compare, blur the difference
			delta = np.ma.filled(np.abs(masked_ref - masked_depth), 0)
			delta = cv2.GaussianBlur(delta, (0, 0), 1)
			# Mask out pixels under the threshold
			delta = np.ma.array(ref, mask=(delta < Z_THRESHOLD))
			# Compute the sum of deltas as a motion value
			motion = sum(sum(np.ma.filled(delta, 0)))

			# Accumulate into the reference buffer
			ref = ref * (1 - DECAY_K) + np.where(mask, ref, depth) * DECAY_K
			ref_mask_buf = ref_mask_buf * (1 - DECAY_K) + mask * DECAY_K

			# Trigger the alarm if motion or excessive lost pixels are detected
			if motion > MOTION_THRESHOLD or lost_count > LOST_THRESHOLD:
				if not self.detected.is_set():
					logging.info("Motion detected (%d,%d)", motion, lost_count)
				self.detected.set()

			if self.debug:
				print motion > MOTION_THRESHOLD, lost_count > LOST_THRESHOLD
				cv2.imshow("Ref", depth_to_img(masked_ref))
				cv2.imshow("Depth", depth_to_img(masked_depth))
				cv2.imshow("Delta", delta_to_img(np.ma.filled(delta, 0)))
				if cv2.waitKey(10) == 27:
					return

			if not self.keep_running:
				return

	def start(self):
		if self.is_alive():
			return
		logging.info("Motion detection started")
		self.keep_running = True
		threading.Thread.start(self)

	def stop(self):
		if not self.is_alive():
			return
		self.keep_running = False
		self.join()
		logging.info("Motion detection stopped")

if __name__ == "__main__":
	kinect = kinectcore.KinectStreamer()
	kinect.start()
	try:
		motion = MotionSensor(kinect)
		motion.debug = True
		motion.run()
	finally:
		kinect.stop()
