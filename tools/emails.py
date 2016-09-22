import smtplib
import json
import os
from email.mime.text import MIMEText


def send_email(regression, jobs, date, message, change=None, admin=False, results=False):
    json_data = open(os.path.join(os.path.abspath(os.path.realpath(os.path.dirname(__file__))),
                                  "seta.cfg"), "r").read()
    data = json.loads(json_data)
    server = smtplib.SMTP(data['hostname'])
    server.starttls()
    server.login(data['username'], data['password'])

    message = "We analyzed %s regressions and found %s jobs to enable: " \
              % (regression, jobs) + message
    if change:
        message += "\nThe jobs added to the current day compared to previous " \
                   "day are:\n\n %s" % change
    message += "\nhttp://alertmanager.allizom.org/seta.html?date=%s\n\n" % date.strftime("%Y-%m-%d")

    msg = MIMEText(message)
    msg['Subject'] = "SETA Results - Date %s" % date.strftime("%Y-%m-%d")
    msg['From'] = data['username']

    if admin:
        server.sendmail(msg['From'], data['admins'], msg.as_string())
    if results:
        server.sendmail(msg['From'], data['results'], msg.as_string())
