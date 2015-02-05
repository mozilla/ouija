import smtplib
import json
import datetime
import os
from email.mime.text import MIMEText


def send_email(regression, jobs, message, addition=None, deletion=None, admin=False, results=False):
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.starttls()
    server.login("setamozilla", "seta_mozilla")

    message = "We analyzed %s regressions and found %s jobs to disable - " % (regression, jobs) + message
    if addition and deletion:
        message += "\nThe jobs added to the current day compared to previous day are:\n\n %s" % addition
        message += "\n\nThe jobs deleted from the current day compared to previous day are:\n\n %s" % deletion

    msg = MIMEText(message)
    msg['Subject'] = "SETA Results - Date %s" % datetime.datetime.now().strftime("%Y-%m-%d")
    msg['From'] = "setamozilla@gmail.com"

    json_data = open(os.path.join(os.path.abspath(os.path.realpath(os.path.dirname(__file__))), "seta.cfg"), "r").read()
    data = json.loads(json_data)
    if admin:
        server.sendmail(msg['From'], data['admins'], msg.as_string())
    if results:
        server.sendmail(msg['From'], data['results'], msg.as_string())
