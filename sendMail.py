import glob
import mimetypes
import os
import smtplib
import sys
import time
import traceback
from email import encoders
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate

BODY_START = r'<body style="font-family:Arial; font-size:10.5pt;">'
BODY_END = r'</body>'


class Email:
    def __init__(self, mailList=None, attDir=None):
        self.emailInit(mailList)
        self.mFolder = os.environ.get("WORKSPACE", r"C:\test") if attDir is None else attDir

    def emailInit(self, mailList):
        self.smtpServer = ("smtp1.hexagonmetrology.com", "smtp2.hexagonmetrology.com", "10.60.226.37", "10.60.226.38")
        self.mailTo = mailList if mailList is not None else os.environ.get("MAIL_LIST", ["Xiang.Ge@hexagon.com",
                                                                                         "Chongjin.Xu@hexagon.com",
                                                                                         "qun.chen@hexagon.com"])
        if not isinstance(self.mailTo, list):
            self.mailTo = self.mailTo.split(' ')

    def addAttachments(self, fp, emailObj):
        if not os.path.isfile(fp):
            return
        filename = os.path.basename(fp)
        ctype, encoding = mimetypes.guess_type(fp)
        if ctype is None or encoding is not None:
            # No guess could be made, or the file is encoded (compressed), so
            # use a generic bag-of-bits type.
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)

        if maintype == 'text':
            fp = open(fp)
            # Note: we should handle calculating the charset
            f_attachment = MIMEText(fp.read(), _subtype=subtype)
            fp.close()
        elif maintype == 'image':
            fp = open(fp, 'rb')
            f_attachment = MIMEImage(fp.read(), _subtype=subtype)
            fp.close()
        elif maintype == 'audio':
            fp = open(fp, 'rb')
            f_attachment = MIMEAudio(fp.read(), _subtype=subtype)
            fp.close()
        else:
            fp = open(fp, 'rb')
            f_attachment = MIMEBase(maintype, subtype)
            f_attachment.set_payload(fp.read())
            fp.close()
            encoders.encode_base64(f_attachment)
        f_attachment.add_header('Content-Disposition', 'attachment', filename=filename)
        emailObj.attach(f_attachment)

    def insertPngs(self, pngFiles, emailObj):
        index = 0
        for file in pngFiles:
            fp = open(file, 'rb')
            msgImage = MIMEImage(fp.read())
            fp.close()
            msgImage.add_header('Content-ID', '<' + str(index) + '>')
            index += 1
            emailObj.attach(msgImage)

    def send(self, content="", subject="", attach=True, location=True):
        email_obj = MIMEMultipart()
        email_obj['From'] = "MI-MSC-Apex.autotest@hexagon.com"
        email_obj['Subject'] = ("[Jenkins]" if location else "") + subject
        email_obj['To'] = ",".join(self.mailTo)
        email_obj['Date'] = formatdate(localtime=True)
        pngFiles = list()
        if os.path.isdir(self.mFolder):
            pngFiles = glob.glob(os.path.join(self.mFolder, "*.png"))
        if os.path.isfile(self.mFolder) and os.path.basename(self.mFolder).split('.')[-1] == "png":
            pngFiles = [self.mFolder]
        for index in range(len(pngFiles)):
            if index % 2 == 0:
                content += '<br><img src="cid:' + str(index) + '"><br>'
            else:
                content += '<img src="cid:' + str(index) + '">'
        content = BODY_START + content + BODY_END
        content = MIMEText(content, 'html', 'utf-8')
        email_obj.attach(content)
        self.insertPngs(pngFiles, email_obj)
        if attach:
            if os.path.isdir(self.mFolder):
                for fp in os.listdir(self.mFolder):
                    self.addAttachments(os.path.join(self.mFolder, fp), email_obj)
            if os.path.isfile(self.mFolder):
                self.addAttachments(self.mFolder, email_obj)
        sent = False
        for _smtp in self.smtpServer:
            sys.stdout.flush()
            print('=' * 100)
            print(f"Using SMTP server {_smtp}\n")
            try:
                with smtplib.SMTP() as server:
                    server.connect(_smtp, 25)
                    server.sendmail("", self.mailTo, email_obj.as_string())
                    sent = True
                    print("Email has been sent successfully!!!")
                    break
            except:
                traceback.print_exc()
                sys.stdout.flush()
                print(f"\n{_smtp} does not work.\n")
                time.sleep(2)
        if not sent:
            raise Exception("Email was failed to send!!!")


def parse_arguments():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('-a', '--address', help='Address of sending email to the people.')
    parser.add_argument('-c', '--content', help='Content in email')
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    args, subargs = parser.parse_known_args()
    return vars(args)


if __name__ == '__main__':
    em = Email()
    em.send('', '', False)
