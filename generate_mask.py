#!/usr/bin/env python

import cv2
import kinectcore
import math
import numpy as np
from motion import frame_to_depth, depth_to_img

kinect = kinectcore.KinectStreamer()
kinect.start()

clicks = []

fx = 594.21
fy = 591.04
a = -0.0030711
b = 3.3309495
cx = 339.5
cy = 242.7
kinect_to_world = np.matrix([
	[1/fx,       0,  0, 0],
	[0,      -1/fy,  0, 0],
	[0,          0,  0, a],
	[-cx/fx, cy/fy,  1, b]
])

def k2w(point):
	# Convert Kinect coordinates to world coordinates
	x, y, z = point
	x, y, z, w = ((x,y,z,1.0) * kinect_to_world).tolist()[0]
	return np.array((x/w, y/w, z/w))

def plane_render(plane, ray):
	# Calculate the intersection of a plane and a line, and return the z
	# coordinate. The line is defined as intersecting ray and 0,0,0
	# See http://en.wikipedia.org/wiki/Line-plane_intersection
	(x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = plane
	(x, y, z) = ray
	mat = np.matrix([
		[-x, x1-x0, x2-x0],
		[-y, y1-y0, y2-y0],
		[-z, z1-z0, z2-z0],
	]).getI().getT()
	vec = np.matrix([-x0, -y0, -z0])
	res = vec * mat
	return res[0,0] * z

try:
	cv2.namedWindow("Depth")
	cv2.namedWindow("Depth Filter")

	def mouse(event, x, y, flags, arg):
		if event == 4:
			clicks.append((x,y,frame[y][x]))

	cv2.setMouseCallback("Depth", mouse)

	depth_filter = None

	for frame in kinect.depth_stream(2):
		depth, mask = frame_to_depth(frame)
		masked_depth = np.ma.array(depth, mask=mask)
		if depth_filter is not None:
			filtered_depth = np.ma.array(depth, mask=(np.logical_or(mask, depth > depth_filter)))
		else:
			filtered_depth = masked_depth
		img_gb = depth_to_img(masked_depth)
		img_r = depth_to_img(filtered_depth)
		img = cv2.merge((img_gb, img_gb, img_r))
		cv2.imshow("Depth", img)
		if depth_filter is not None:
			cv2.imshow("Depth Filter", depth_to_img(depth_filter))
		if cv2.waitKey(10) == 27:
			break

		if len(clicks) >= 3:
			# map plane to real world coordinates
			plane = map(k2w, clicks[:3])
			print plane
			# caclulate unit normal
			normal = np.cross(plane[1] - plane[0], plane[2] - plane[0])
			normal /= math.sqrt(sum(normal * normal))
			# calculate 20cm offset
			offset = 0.2 * normal
			# add it to the plane
			new_plane = [p + offset for p in plane]
			# make sure it points towards us
			d_orig = math.sqrt(sum(plane[0] * plane[0]))
			d_new = math.sqrt(sum(new_plane[0] * new_plane[0]))
			if d_new > d_orig:
				offset = -offset
				new_plane = [p + offset for p in plane]

			depth_filter = np.zeros_like(depth)
			h, w = depth_filter.shape
			for y in xrange(h):
				# calculate depth at the left and right of the scanline
				ray0 = k2w((0, y, 500.0))
				ray1 = k2w((w, y, 500.0))
				z0 = 1.0/plane_render(new_plane, ray0)
				z1 = 1.0/plane_render(new_plane, ray1)
				for x in xrange(w):
					t = x / float(w)
					z = 1.0/((1-t)*z0 + t*z1)
					if not 0 < z < 100:
						z = 100
					depth_filter[y][x] = z

			np.save("depth_filter.npy", depth_filter)
			print "Saved depth_filter.npy"
			clicks = []

finally:
	kinect.stop()
