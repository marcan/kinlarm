#!/usr/bin/env python

import base64
import BaseHTTPServer, SocketServer
import cv
import logging
import mimetypes
import numpy as np
from PIL import Image, ImageEnhance, ImageOps
import select
import StringIO
import threading
import urllib2
import urlparse

import debug
import kinectcore

from config import *

color_palette=[]
for i in range(255):
	v = int(i* 6 * 1.0)
	h = v >> 8
	h = h%6
	l = v & 0xff
	if h == 0:
		color_palette += (255,0,255-l)
	elif h == 1:
		color_palette += (255,l,0)
	elif h == 2:
		color_palette += (255-l,255,0)
	elif h == 3:
		color_palette += (0,255,l)
	elif h == 4:
		color_palette += (0,255-l,255)
	elif h == 5:
		color_palette += (l,0,255)
color_palette += (0,0,0)

class ThreadedHTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):
	pass

class RequestHandler(BaseHTTPServer.BaseHTTPRequestHandler):
	MIMETAG = "SW4gU292aWV0IFJ1c3NpYSwgQkFTRTY0IGRlY29kZXMgWU9VIQo="

	STATIC = set([
		"/jquery.js"
	])

	def request_auth(self):
		self.send_response(401, "You Shouldn't Be Here")
		self.send_header("Connection", "Close")
		self.send_header("Content-Type", "text/html")
		self.send_header("WWW-Authenticate", "Basic realm=\"Go Away\"")
		self.end_headers()
		self.wfile.write("401 You Shouldn't Be Here")

	def check_auth(self):
		if "Authorization" not in self.headers:
			self.request_auth()
			return False
		auth = self.headers["Authorization"]
		try:
			method, rest = auth.split(" ",1)
			if method != "Basic":
				self.request_auth()
				return False
			data = base64.b64decode(rest)
			if data != "%s:%s"%(USERNAME,PASSWORD):
				self.request_auth()
				return False
		except:
			self.request_auth()
			return False
		return True

	def do_GET(self):
		if not self.check_auth():
			return
		if self.path in ("/video", "/depth"):
			self.send_response(200)
			self.send_header("Connection", "Close")
			self.send_header("Pragma", "no-cache")
			self.send_header("Expires", "0")
			self.send_header("Content-Type", "multipart/x-mixed-replace;boundary=" + self.MIMETAG)
			self.end_headers()

			if self.path == "/video":
				stream = self.server.kinect.video_stream(15)
			else:
				stream = self.server.kinect.depth_stream(15)

			for frame in stream:
				if self.path == "/video":
					im = self.video_to_image(frame)
				else:
					im = self.depth_to_image(frame)
				fd = StringIO.StringIO()
				im.save(fd, "JPEG", quality=75)
				data = fd.getvalue()
				self.wfile.write("--" + self.MIMETAG + "\r\n")
				self.send_header("Content-Type", "image/jpeg")
				self.send_header("Content-Length", str(len(data)))
				self.end_headers()
				self.wfile.write(data)
				self.wfile.flush()
				if not self.server.keep_running:
					break
		elif self.path == "/":
			self.send_html(self.template("index.html"))
		elif self.path == "/state":
			self.send_text(self.server.controller.state.__name__.title())
		elif self.path.startswith("/setstate?"):
			parsed_path = urlparse.urlparse(self.path)
			if parsed_path.query in self.server.controller.states:
				self.server.controller.switch_state(parsed_path.query)
		elif self.path in self.STATIC:
			data = self.template(self.path[1:])
			self.send_data(data, mimetypes.guess_type(self.path))
		else:
			self.send_error(404)

	def send_redirect(self, to):
		uri = "http://" + self.headers["Host"] + to
		self.send_response(302)
		self.send_header("Connection", "Close")
		self.send_header("Pragma", "no-cache")
		self.send_header("Location", uri)
		self.send_header("Content-Type", "text/plain")
		self.end_headers()

	def send_data(self, data, content_type):
		self.send_response(200)
		self.send_header("Connection", "Close")
		self.send_header("Pragma", "no-cache")
		self.send_header("Expires", "0")
		self.send_header("Content-Type", content_type)
		self.end_headers()
		self.wfile.write(data)
		self.wfile.flush()

	def send_html(self, html):
		self.send_data(html, "text/html; charset=utf-8")

	def send_text(self, text):
		self.send_data(text, "text/plain; charset=utf-8")

	def template(self, name):
		with open("templates/" + name, "rb") as fd:
			return fd.read()

	def depth_to_image(self, frame):
		frame = frame.astype(np.float)
		np.clip(frame, 0, 1046.31, frame)
		frame = 45 / (frame * -0.0030711016 + 3.3309495161) - 45
		np.clip(frame, 0, 255, frame)
		frame = frame.astype(np.uint8)
		im = Image.fromstring("L", (frame.shape[1], frame.shape[0]), frame.tostring())
		im = im.resize((480, 360), Image.BILINEAR)
		im.putpalette(color_palette)
		im = im.convert("RGB")
		#im = ImageEnhance.Brightness(im).enhance(0.2)
		#im = ImageEnhance.Contrast(im).enhance(7.0)
		im = ImageEnhance.Sharpness(im).enhance(1)
		return im

	def video_to_image(self, frame):
		im = Image.fromstring("RGB", (frame.shape[1], frame.shape[0]), frame.tostring())
		im = ImageOps.equalize(im)
		return im.resize((480, 360), Image.BILINEAR)

class WebServer(threading.Thread):
	def __init__(self, controller, kinect):
		threading.Thread.__init__(self, name="WebServer")
		self.controller = controller
		server_address = ('', WEB_PORT)
		self.httpd = ThreadedHTTPServer(server_address, RequestHandler)
		self.httpd.kinect = kinect
		self.httpd.controller = controller
		self.httpd.keep_running = True

	def run(self):
		while self.httpd.keep_running:
			try:
				self.httpd.handle_request()
			except select.error, e:
				if e.args[0] == 4:
					continue
				else:
					raise

	def start(self):
		if self.is_alive():
			return
		logging.info("Web server started")
		self.httpd.keep_running = True
		threading.Thread.start(self)

	def stop(self):
		if not self.is_alive():
			return
		logging.info("Web server stopped")
		self.httpd.keep_running = False
		# Make a fake request to trigger thread exit
		try:
			fd = urllib2.urlopen("http://localhost:%d/" % WEB_PORT)
			fd.read()
			fd.close()
		except urllib2.HTTPError:
			pass
		self.join()

if __name__ == "__main__":
	logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
	kinect = kinectcore.KinectStreamer()
	kinect.start()
	try:
		server = WebServer(None, kinect)
		server.run()
	finally:
		kinect.stop()
