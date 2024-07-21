import time

from lxml import etree
from requests import session, codes
from requests.exceptions import Timeout, ConnectionError

from resources.exceptions import VerifierRequestException


class BaseVerifier(object):
    headers = dict()
    common_params = None
    pre_query_url = None
    query_url = None
    pre = False
    applicant_class = None
    rules = {

    }
    timeout_setting = {
        "timeout": 1000
    }
    number_retries = 20
    proxy_class = 'default'

    def __init__(self, proxy=None):
        self.validity = None
        self.session = self.get_requests_session(proxy=proxy)

    @classmethod
    def get_requests_session(cls, proxy=None):
        requests_session = session()
        if proxy:
            requests_session.proxies = {
                'http': None,
                'https': None
            }
        requests_session.headers.update(cls.headers)

        return requests_session

    def smart_request(self, type_of_request, url, **kwargs):
        count = 0
        number_retries = kwargs.pop('number_retries', None)
        updated_kwargs = {**self.timeout_setting, **kwargs}
        if number_retries is None:
            number_retries = self.number_retries
        while count < number_retries:
            try:
                if type_of_request == 'GET':
                    response = self.session.get(url, **updated_kwargs)
                elif type_of_request == 'POST':
                    response = self.session.post(url, **updated_kwargs)
                else:
                    response = self.session.request(type_of_request, url, **updated_kwargs)
                return response
            except Timeout:
                count += 1
                print('Timeout Happened, Retrying after 60 seconds')
                time.sleep(60)
                continue
            except ConnectionError as e:
                print(e)
                count += 0.1
                print('Timeout Happened, Retrying after 60 seconds')
                time.sleep(60)
                continue
        else:
            raise VerifierRequestException

    # @classmethod
    # def get_html_session(cls):
    #     html_session = HTMLSession()
    #     html_session.headers.update(cls.headers)
    #     return html_session

    @staticmethod
    def get_etree(response):
        if hasattr(response, 'content'):
            tree = etree.HTML(response.content)
        else:
            tree = etree.HTML(response)
        return tree

    @staticmethod
    def get_xml_tree(response):
        if hasattr(response, 'content'):
            tree = etree.XML(response.content)
        else:
            tree = etree.XML(response)
        return tree

    @staticmethod
    def request_ok(status_code):
        return status_code == codes.ok

    def pre_query(self, *args, **kwargs):
        pass

    def query_info(self, **kwargs):
        pass

    def extract_info(self, response):
        pass

    def verify_info(self, **kwargs):
        pass

    @classmethod
    def verify(cls, db_ob, **_kwargs):
        applicant = cls.applicant_class.object_to_applicant(db_ob)
        if cls.pre:
            return cls(applicant).pre_query()
        else:
            return cls(applicant).query_info()

    @classmethod
    def get_hidden_payload(cls, response):
        tree = cls.get_etree(response)
        hidden_inputs = tree.xpath("//form//input[@type='hidden']")
        hidden_payload = {x.attrib.get('name'): x.attrib.get('value') for x in hidden_inputs}
        return hidden_payload
