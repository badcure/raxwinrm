from __future__ import absolute_import
import requests
from jinja2 import Environment, PackageLoader, select_autoescape

SOAP_ENV = Environment(
    loader=PackageLoader('raxwinrm', 'winrm_commands'),
    autoescape=select_autoescape(['html', 'xml'])
)


class WinRMConnection(object):

    def __init__(self, hostname, port=None, **kwargs):
        self.hostname = hostname
        self.port = port
        self.session = requests.Session()

    def create_shell(self):
        """
        https://msdn.microsoft.com/en-us/library/cc251546.aspx

        :return: None
        """
        pass

    def close(self):
        self.session.close()


class WinRMConnectionHTTPS(WinRMConnection):

    def __init__(self, hostname, port=5896, **kwargs):
        super(WinRMConnectionHTTPS, self).__init__(hostname=hostname, port=5986, **kwargs)

