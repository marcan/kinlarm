#!/usr/bin/env python

from email.mime.text import MIMEText
import logging
import smtplib
import sys
import time

from config import *

def send_alert(subject):
	logging.info("Sending mail alert (%s)" % subject)

	body = MAIL_TEMPLATE % subject
	msg = MIMEText(body)
	msg['Subject'] = 'Security alert: %s' % subject
	msg['From'] = MAIL_FROM
	msg['To'] = MAIL_TO

	smtp = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
	if SMTP_TLS:
		smtp.starttls()
	if SMTP_USER is not None and SMTP_PASSWORD is not None:
		smtp.login(SMTP_USER, SMTP_PASSWORD)
	smtp.sendmail(MAIL_FROM, [MAIL_TO], msg.as_string())
	smtp.quit()
