import smtplib
import json
from email.mime.text import MIMEText

def send_email(regression, jobs, message, addition=None, deletion=None, admin=False, results=False):
    server = smtplib.SMTP('smtp.gmail.com:587')
    server.starttls()
    server.login("setamozilla","seta_mozilla")

    message = "We analyzed %s regressions and found %s jobs to disable - " % (regression, jobs) + message
    if addition and deletion:
        message += "\nThe jobs added to the current day compared to previous day are: ", addition
        message += "\nThe jobs deleted from the current day compared to previous day are: ", deletion

    msg = MIMEText(message)
    msg['Subject'] = "SETA Results"
    msg['From'] = "setamozilla@gmail.com"

    json_data = open("seta.cfg", "r").read()
    data = json.loads(json_data)
    if admin:
        server.sendmail(msg['From'], data['admins'], msg.as_string())
    if results:
        server.sendmail(msg['From'], data['results'], msg.as_string())
