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


def disable_request_logging():
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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

    def _sent_winrm_command(self, template_name, template_args=None):
        if template_args is None:
            template_args = {}

        message_id = uuid.uuid4()
        template = SOAP_ENV.get_template(template_name)
        url = self.url_template.format(hostname=self.hostname, port=self.port)
        template_data = {
            'uri': url,
            'message_id': message_id,
            'idle_timeout': 300,
        }
        template_data.update(template_args)

        data = template.render(template_data)

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

        return xmltodict.parse(response.text)

    def setup_connection(self):
        self.session = requests.Session()

    def connect(self):
        """
        https://msdn.microsoft.com/en-us/library/cc251739.aspx

        :return: ShellId UUID from WinRM
        """
        if not self.session:
            self.setup_connection()

        response_xml = self._sent_winrm_command('openshell.xml', {
            'work_dir': '%USERPROFILE%\AppData\Local\Temp'
        })
        self.shell_id = response_xml['s:Envelope']['s:Body']['rsp:Shell']['rsp:ShellId']
        return self.shell_id

    def execute_command(self, command, command_args=None, shell_id=None):
        """
        Execute command example: https://msdn.microsoft.com/en-us/library/cc251740.aspx

        :param command: Command to run(e.g. dir)
        :param command_args: Arguments for the command(e.g. c:\)
        :return: Command UUID from WinRM
        """
        if shell_id is None:
            shell_id = self.shell_id

        if shell_id is None:
            shell_id = self.connect()

        response_xml = self._sent_winrm_command('execute_command.xml', {
            'command': command,
            'command_args': command_args,
            'shell_id': shell_id,
        })
        self.last_command = response_xml['s:Envelope']['s:Body']['rsp:CommandResponse']['rsp:CommandId']
        return self.last_command

    def command_output(self, command_id=None, shell_id=None):
        """
        Command Output: https://msdn.microsoft.com/en-us/library/cc251741.aspx

        :param command_id: Command ID returned. Uses the last command ID if None provided.
        :return: exit_code(int), stdout_result(str), stderr_result(str)
        """
        if command_id is None:
            command_id = self.last_command
        if shell_id is None:
            shell_id = self.shell_id

        response_xml = self._sent_winrm_command('response.xml', {
            'shell_id': shell_id,
            'command_id': command_id,
        })

        stdout_result = ''
        stderr_result = ''
        exit_code = int(response_xml['s:Envelope']['s:Body']['rsp:ReceiveResponse']['rsp:CommandState']['rsp:ExitCode'])
        for line_output in response_xml['s:Envelope']['s:Body']['rsp:ReceiveResponse']['rsp:Stream']:
            if line_output.get('@End', False):
                continue
            if line_output['@Name'] == 'stdout':
                stdout_result += base64.b64decode(line_output['#text'])
            if line_output['@Name'] == 'stderr':
                stderr_result += base64.b64decode(line_output['#text'])
        return exit_code, stdout_result, stderr_result

    def close(self, shell_id=None):
        """
        https://msdn.microsoft.com/en-us/library/cc251746.aspx

        :return: ShellId UUID from WinRM
        """
        successfully_close = False
        if shell_id is None:
            shell_id = self.shell_id
        if self.shell_id is None:
            return

        if self.session is None:
            self.setup_connection()

        try:
            self._sent_winrm_command('close_shell.xml', {
                'shell_id': shell_id
            })
            successfully_close = True
        except raxwinrm_exceptions.WinRMResponseException as exc:
            if exc.code == 'w:InvalidSelectors':
                # Shell ID is invalid. No need to raise an exception.
                pass
            else:
                raise
        finally:
            self.session.close()
            self.session = None
        return successfully_close


class WinRMConnectionHTTPS(WinRMConnection):

    def __init__(self, hostname, port=5896, **kwargs):
        super(WinRMConnectionHTTPS, self).__init__(hostname=hostname, port=5986, **kwargs)

