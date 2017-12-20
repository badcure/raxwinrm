from __future__ import absolute_import
import requests
import requests.auth as request_auth
from requests_ntlm import HttpNtlmAuth
from jinja2 import Environment, PackageLoader, select_autoescape
import uuid
import xmltodict
from raxwinrm import exceptions as raxwinrm_exceptions
import base64

SOAP_ENV = Environment(
    loader=PackageLoader('raxwinrm', 'winrm_commands'),
    autoescape=select_autoescape(['html', 'xml'])
)


class WinRMConnection(object):

    url_template = 'https://{hostname}:{port}/wsman'
    prepared_statement = None
    shell_id = None
    last_command = None

    def __init__(self, hostname, port=None, username=None, password=None, **kwargs):
        self.hostname = hostname
        self.port = port
        self.session = None
        self.username = username
        self.password = password
        self.verify = kwargs.get('verify', False)
        if not username or not password:
            raise ValueError("Need username and password defined")

    def setup_connection(self):
        self.session = requests.Session()

    def create_shell(self):
        """
        https://msdn.microsoft.com/en-us/library/cc251546.aspx

        :return: None
        """
        if not self.session:
            self.setup_connection()
        template = SOAP_ENV.get_template('openshell.xml')
        message_id = uuid.uuid4()
        url = self.url_template.format(hostname=self.hostname, port=self.port)

        data = template.render({
            'uri': url,
            'message_id': message_id,
            'idle_timeout': 300,
            'work_dir': '%USERPROFILE%\AppData\Local\Temp'
        })
        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'User-Agent': 'RaxWinRM',
        }
        self.prepared_statement = requests.Request(
            'POST', url=url, headers=headers, data=data, auth=HttpNtlmAuth(username=self.username, password=self.password)).prepare()

        response = self.session.send(self.prepared_statement, verify=self.verify, timeout=10)
        try:
            response.raise_for_status()
        except requests.HTTPError as http_exc:
            raise raxwinrm_exceptions.WinRMResponseException(http_exc)

        response_xml = xmltodict.parse(response.text)
        self.shell_id = response_xml['s:Envelope']['s:Body']['rsp:Shell']['rsp:ShellId']
        return self.shell_id

    def execute_command(self, command, command_args=None):
        if self.shell_id is None:
            self.create_shell()

        template = SOAP_ENV.get_template('execute_command.xml')
        message_id = uuid.uuid4()
        url = self.url_template.format(hostname=self.hostname, port=self.port)

        data = template.render({
            'uri': url,
            'message_id': message_id,
            'shell_id': self.shell_id,
            'command': command,
            'command_args': command_args,
            'timeout': 60
        })

        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'User-Agent': 'RaxWinRM',
        }
        self.prepared_statement = requests.Request(
            'POST', url=url, headers=headers, data=data, auth=HttpNtlmAuth(username=self.username, password=self.password)).prepare()

        response = self.session.send(self.prepared_statement, verify=self.verify, timeout=10)
        try:
            response.raise_for_status()
        except requests.HTTPError as http_exc:
            raise raxwinrm_exceptions.WinRMResponseException(http_exc)

        response_xml = xmltodict.parse(response.text)
        self.last_command = response_xml['s:Envelope']['s:Body']['rsp:CommandResponse']['rsp:CommandId']
        return self.last_command

    def command_output(self, command_id=None):
        if command_id is None:
            command_id = self.last_command

        template = SOAP_ENV.get_template('response.xml')
        message_id = uuid.uuid4()
        url = self.url_template.format(hostname=self.hostname, port=self.port)

        data = template.render({
            'uri': url,
            'message_id': message_id,
            'shell_id': self.shell_id,
            'command_id': command_id,
            'timeout': 60
        })

        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'User-Agent': 'RaxWinRM',
        }
        self.prepared_statement = requests.Request(
            'POST', url=url, headers=headers, data=data, auth=HttpNtlmAuth(username=self.username, password=self.password)).prepare()

        response = self.session.send(self.prepared_statement, verify=self.verify, timeout=10)
        try:
            response.raise_for_status()
        except requests.HTTPError as http_exc:
            raise raxwinrm_exceptions.WinRMResponseException(http_exc)

        response_xml = xmltodict.parse(response.text)
        stdout_result = ''
        stderr_result = ''
        exit_code = int(response_xml['s:Envelope']['s:Body']['rsp:ReceiveResponse']['rsp:CommandState']['rsp:ExitCode'])
        for line_output in response_xml['s:Envelope']['s:Body']['rsp:ReceiveResponse']['rsp:Stream']:
            if line_output['@Name'] == 'stdout':
                stdout_result += base64.b64decode(line_output['#text'])
            if line_output['@Name'] == 'stderr':
                stderr_result += base64.b64decode(line_output['#text'])
        return exit_code, stdout_result, stderr_result


    def close(self):
        self.session.close()
        self.session = None


class WinRMConnectionHTTPS(WinRMConnection):

    def __init__(self, hostname, port=5896, **kwargs):
        super(WinRMConnectionHTTPS, self).__init__(hostname=hostname, port=5986, **kwargs)

