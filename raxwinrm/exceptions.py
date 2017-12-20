from requests.exceptions import HTTPError
import xmltodict


class RAXWinRMException(Exception):
    pass


class ConnectionException(RAXWinRMException):
    pass


class WinRMResponseException(RAXWinRMException):
    code = None
    reason = None
    detailed_reason = "No Reason Provided"

    def __init__(self, http_exc):
        if not isinstance(http_exc, HTTPError):
            raise TypeError("requests.exceptions.HTTPError required")

        response_xml = xmltodict.parse(http_exc.response.text)

        fault_info = response_xml['s:Envelope']['s:Body']['s:Fault']
        self.code = fault_info['s:Code']['s:Subcode']['s:Value']
        self.reason = fault_info['s:Reason']['s:Text']['#text']
        if 'f:WSManFault' in fault_info['s:Detail']:
            self.detailed_reason = fault_info['s:Detail']['f:WSManFault']['f:Message']
            self.code_id = long(fault_info['s:Detail']['f:WSManFault']['@Code'])
        elif 'p:MSFT_WmiError' in fault_info['s:Detail']:
            self.detailed_reason = fault_info['s:Detail']['p:MSFT_WmiError']['p:error_WindowsErrorMessage']['#text']
            self.code_id = long(fault_info['s:Detail']['p:MSFT_WmiError']['p:error_Code']['#text'])

    def __str__(self):
        return "WinRMExcetion {code_text}: {code_reason}".format(code_text=self.code, code_reason=self.detailed_reason)