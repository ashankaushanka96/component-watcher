import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import socket
import os
from dotenv import load_dotenv

fromaddr="watcher@gtnmarketdataservices.com"
#toaddr="feed.alerts@gtngroup.com"
toaddr="p.ashan@gtngroup.com"

def mail_send(processname):
    load_dotenv()
    username=os.getenv('USERNAME')
    passswrd=os.getenv('PASSWORD')
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    msg = MIMEMultipart()
    msg['From'] = fromaddr
    msg['To'] = toaddr
    msg['Subject'] = " %s COMPONENT IS DOWN" % processname

    body = """%s - %s COMPONENT IS DOWN""" % (ip_address, processname)
    msg.attach(MIMEText(body, 'plain'))

    server = smtplib.SMTP('email-smtp.us-east-1.amazonaws.com',587)
    server.starttls()
    server.login(username,passswrd)
    text = msg.as_string()
    server.sendmail(fromaddr, toaddr, text)
    server.quit()

