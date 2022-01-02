import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText  # Added
from email.mime.image import MIMEImage
import os

class Mail:
	#def __init__(self, logging):
		#self.logging = logging
		
	def sendMail(title, content, to, user = None):
		if user != None:
			to = user.email

		uid = os.getenv("sendmail")
		if uid == None:
			return 
		pwd = os.getenv("sendmail-password")
		mail_server = 'smtp.gmail.com'
		message = "From : " + uid + "To : " + to + "Subject: Trading\r\n" + content
		MESSAGE_FORMAT = "From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n%s"
		message = MESSAGE_FORMAT % ('', to, title, content)
		Mail.sendMailIntern(uid, pwd, to, message, mail_server)

	def sendMailIntern(uid, pwd, to, message, mail_server):
		server = smtplib.SMTP(mail_server, 587)
		server.ehlo()
		server.starttls()
		server.ehlo()
		server.login(uid, pwd)
		server.sendmail(uid, to, message)
		server.close()