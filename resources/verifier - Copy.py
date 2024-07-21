import base64
import csv
import io
import json
import re
import time
import urllib.parse

from requests import Timeout

from resources.base import BaseVerifier
import resources.templates as templates
import PyPDF2
from tqdm import tqdm
import warnings
warnings.filterwarnings("ignore")

class MahareraitVerifier(BaseVerifier):
    headers = {
        'authority': 'maharerait.mahaonline.gov.in',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'en-US,en;q=0.9,hi;q=0.8',
        'cache-control': 'max-age=0',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }

    url = "https://maharerait.mahaonline.gov.in/"
    pre_query_url = "https://maharerait.mahaonline.gov.in/searchlist/search?MenuID=1069"
    get_district_url = "https://maharerait.mahaonline.gov.in/SearchList/GetDistrict"
    get_taluka_url = "https://maharerait.mahaonline.gov.in/SearchList/GetTaluka"
    search_query_url = "https://maharerait.mahaonline.gov.in/SearchList/Search"
    show_certificate_url = "https://maharerait.mahaonline.gov.in/SearchList/ShowCertificate"
    maharashtra_state_id = 27
    max_retries = 10
    retry_delay = 5
    current_retries = 0

    def __init__(self, to_verify):
        super().__init__(to_verify)
        self.token = None
        self.user_id = None
        self.count = 0

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
            return None

    def pre_query(self, *args, **kwargs):
        resp = self.smart_request("GET", self.pre_query_url, headers=self.headers, verify=False)

        hidden_payload = self.get_hidden_payload(resp)

        self.token = hidden_payload.get('__RequestVerificationToken')
        return self.search_query()

    def get_districts(self):
        payload = {"DivID": self.maharashtra_state_id}  # State id of maharashtra hardcoded.

        resp = self.smart_request("POST", self.get_district_url, headers=self.headers, data=payload, verify=False)
        districts = resp.json()

        return districts

    def get_talukas(self, dis_id):
        payload = {"DisID": dis_id}

        resp = self.smart_request("POST", self.get_taluka_url, headers=self.headers, data=payload, verify=False)
        talukas = resp.json()

        return talukas

    def show_certificate(self, qstr):
        payload = {"ID": qstr}

        resp = self.smart_request("POST", self.show_certificate_url, headers=self.headers, data=payload, verify=False)
        certificate_data = resp.text

        return certificate_data

    def view_details_query(self, url):
        resp = self.smart_request("GET", url, headers=self.headers, verify=False)
        return self.extract_view_details_data(resp)

    @staticmethod
    def extract_view_details_label(tree, label, heading=None):
        label_re = f"//label[text()[normalize-space() = '{label}']]/../following-sibling::div[1]"
        label_second_re = f"//*[text()[normalize-space() = '{label}']]/following-sibling::div[1]"

        if heading:
            label_re = f"//*[text()[normalize-space() = '{heading}']]/../following-sibling::div//label[text()[normalize-space() = '{label}']]/../following-sibling::div[1]"
            label_second_re = f"//*[text()[normalize-space() = '{heading}']]/../following-sibling::div//*[text()[normalize-space() = '{label}']]/following-sibling::div[1]"

        try:
            label_match = tree.xpath(label_re)

            if not len(label_match):
                label_match = tree.xpath(label_second_re)

            label_data = len(label_match) and label_match[0].text or ""

        except Exception as exc:
            print(f"Could not find {label}", exc)
            return ""

        label_data = label_data.replace("\r\n", "").strip()

        return label_data

    def extract_view_details_data(self, response):
        tree = self.get_etree(response)
        project_data = dict()

        project_data["Do you have any Past Experience ?"] = self.extract_view_details_label(
            tree,
            "Do you have any Past Experience ?",
        )

        project_data["Pin Code"] = self.extract_view_details_label(
            tree,
            "Pin Code",
        )

        project_data["Office Number"] = self.extract_view_details_label(
            tree,
            "Office Number",
        )

        project_data["Website URL"] = self.extract_view_details_label(
            tree,
            "Website URL",
        )

        project_data["Project Status"] = self.extract_view_details_label(
            tree,
            "Project Status",
            "Project"
        )

        project_data["Proposed Date of Completion"] = self.extract_view_details_label(
            tree,
            "Proposed Date of Completion",
            "Project"
        )

        project_data["Revised Proposed Date of Completion"] = self.extract_view_details_label(
            tree,
            "Revised Proposed Date of Completion",
            "Project"
        ) or project_data["Proposed Date of Completion"]

        project_data["Litigations related to the project ?"] = self.extract_view_details_label(
            tree,
            "Litigations related to the project ?",
            "Project"
        )
        project_data["Project Type"] = self.extract_view_details_label(
            tree,
            "Project Type",
            "Project"
        )

        project_data["Are there any Promoter(Land Owner/ Investor)"] = self.extract_view_details_label(
            tree,
            "Are there any Promoter(Land Owner/ Investor) (as defined by MahaRERA Order) in the project ?",
            "Project"
        )

        project_data["Division"] = self.extract_view_details_label(
            tree,
            "Division",
            "Project"
        )

        project_data["District"] = self.extract_view_details_label(
            tree,
            "District",
            "Project"
        )

        project_data["Taluka"] = self.extract_view_details_label(
            tree,
            "Taluka",
            "Project"
        )

        project_data["Village"] = self.extract_view_details_label(
            tree,
            "Village",
            "Project"
        )

        project_data["Street Pin Code"] = self.extract_view_details_label(
            tree,
            "Pin Code",
            "Project"
        )

        project_data["Total Plot/Project area (sqmts)"] = self.extract_view_details_label(
            tree,
            "Total Plot/Project area (sqmts)",
            "Project"
        )

        project_data[
            "Total Number of Proposed Building/Wings (In the Layout/Plot)"] = self.safe_int(
            self.extract_view_details_label(
                tree,
                "Total Number of Proposed Building/Wings (In the Layout/Plot)",
                "Project"
            ))

        project_data["Total Recreational Open Space as Per Sanctioned Plan"] = self.extract_view_details_label(
            tree,
            "Total Recreational Open Space as Per Sanctioned Plan",
            "Project"
        )

        project_data[
            "Sanctioned FSI of the project applied for registration (Sanctioned Built-up Area)"] = \
            self.extract_view_details_label(
                tree,
                "Sanctioned FSI of the project applied for registration (Sanctioned Built-up Area)",
                "FSI Details"
            )

        project_data[
            "Built-up-Area as per Proposed FSI (In sqmts) ( Proposed but not sanctioned) "
            "(As soon as approved, should be immediately updated in Approved FSI)"] = \
            self.extract_view_details_label(
                tree,
                "Built-up-Area as per Proposed FSI (In sqmts) ( Proposed but not sanctioned) "
                "(As soon as approved, should be immediately updated in Approved FSI)",
                "FSI Details"
            )

        project_data["Permissible Total FSI of Plot (Permissible Built-up Area)"] = self.extract_view_details_label(
            tree,
            "Permissible Total FSI of Plot (Permissible Built-up Area)",
            "FSI Details"
        )

        project_data["Bank Name"] = self.extract_view_details_label(tree, "Bank Name", "Bank Details")

        project_data["IFSC Code"] = self.extract_view_details_label(
            tree,
            "IFSC Code",
            "Bank Details"
        )

        try:
            community_buildings_available = tree.xpath(
                "//td[text()[normalize-space() = 'Community Buildings :']]/../td[2]")[0].text.replace("\r\n",
                                                                                                      "").replace(" ",
                                                                                                                  "")

            project_data["Community Buildings Available"] = community_buildings_available

            community_buildings_percent = tree.xpath(
                "//td[text()[normalize-space() = 'Community Buildings :']]/../td[3]")[0].text.replace("\r\n",
                                                                                                      "").replace(" ",
                                                                                                                  "")

            project_data["Community Buildings Percent"] = community_buildings_percent
        except Exception as exc:
            print("Exception while fetching Community data", exc)

        project_data["Number of Sanctioned Floors"] = self.extract_building_details(tree, "Number of Sanctioned Floors")

        project_data["Total no. of open Parking as per Sanctioned Plan (4-wheeler+2-Wheeler)"] = \
            self.extract_building_details(tree,
                                          "Total no. of open Parking as per Sanctioned Plan (4-wheeler+2-Wheeler)")

        project_data["Number of Closed Parking"] = \
            self.extract_building_details(tree, "Number of Closed Parking")

        try:
            carpet_area_range = {
                "carpet_area_apartments_0_30": 0,
                "carpet_area_booked_apartments_0_30": 0,
                "carpet_area_apartments_30_45": 0,
                "carpet_area_booked_apartments_30_45": 0,
                "carpet_area_apartments_45_60": 0,
                "carpet_area_booked_apartments_45_60": 0,
                "carpet_area_apartments_60_90": 0,
                "carpet_area_booked_apartments_60_90": 0,
                "carpet_area_apartments_90_120": 0,
                "carpet_area_booked_apartments_90_120": 0,
                "carpet_area_apartments_120_150": 0,
                "carpet_area_booked_apartments_120_150": 0,
                "carpet_area_apartments_150_200": 0,
                "carpet_area_booked_apartments_150_200": 0,
                "carpet_area_apartments_more_than_200": 0,
                "carpet_area_booked_apartments_more_than_200": 0,
                "apartments_1rk": 0,
                "booked_apartments_1rk": 0,
                "apartments_1bhk": 0,
                "booked_apartments_1bhk": 0,
                "apartments_2bhk": 0,
                "booked_apartments_2bhk": 0,
                "apartments_3bhk": 0,
                "booked_apartments_3bhk": 0,
                "apartments_4bhk": 0,
                "booked_apartments_4bhk": 0,
                "apartments_5bhk": 0,
                "booked_apartments_5bhk": 0,
                "apartments_shops": 0,
                "booked_apartments_shops": 0,
                "apartments_bungalow": 0,
                "booked_apartments_bungalow": 0,
                "apartments_office_space": 0,
                "booked_apartments_office_space": 0,
                "apartments_others": 0,
                "booked_apartments_others": 0,
            }

            carpet_area_th_arr = tree.xpath("//th[text()[normalize-space() = 'Carpet Area (in Sqmts)']]")

            carpet_area_arr = []
            total_no_of_apartment = 0
            total_no_of_booked_apartment = 0

            for carpet_area_th in carpet_area_th_arr:
                carpet_area_th_list = carpet_area_th.findall("../th")
                carpet_area_th_idx = carpet_area_th_list.index(carpet_area_th)

                carpet_area_rows = list(carpet_area_th.getparent().itersiblings("tr"))

                for row in carpet_area_rows:
                    carpet_areas = self.safe_float(row.findall("td")[carpet_area_th_idx].text)
                    apartment_type = str(row.findall("td")[carpet_area_th_idx - 1].text).replace(" ", "").upper()
                    no_of_apartment = self.safe_float(row.findall("td")[carpet_area_th_idx + 1].text)
                    no_of_booked_apartment = self.safe_float(row.findall("td")[carpet_area_th_idx + 2].text)

                    total_no_of_apartment += no_of_apartment
                    total_no_of_booked_apartment += no_of_booked_apartment

                    if self.regex_match(r'(1(RK))|(STUDIO)', apartment_type):
                        carpet_area_range["apartments_1rk"] += no_of_apartment
                        carpet_area_range["booked_apartments_1rk"] += no_of_booked_apartment

                    elif self.regex_match(r'1(BHK|RHK|RLK)', apartment_type):
                        carpet_area_range["apartments_1bhk"] += no_of_apartment
                        carpet_area_range["booked_apartments_1bhk"] += no_of_booked_apartment

                    elif self.regex_match(r'(2|1.5)(BHK|RHK|RLK)', apartment_type):
                        carpet_area_range["apartments_2bhk"] += no_of_apartment
                        carpet_area_range["booked_apartments_2bhk"] += no_of_booked_apartment

                    elif self.regex_match(r'(3|2.5)(BHK|RHK|RLK)', apartment_type):
                        carpet_area_range["apartments_3bhk"] += no_of_apartment
                        carpet_area_range["booked_apartments_3bhk"] += no_of_booked_apartment

                    elif self.regex_match(r'(4|3.5)(BHK|RHK|RLK)', apartment_type):
                        carpet_area_range["apartments_4bhk"] += no_of_apartment
                        carpet_area_range["booked_apartments_4bhk"] += no_of_booked_apartment

                    elif self.regex_match(r'(5|4.5)(BHK|RHK|RLK)', apartment_type):
                        carpet_area_range["apartments_5bhk"] += no_of_apartment
                        carpet_area_range["booked_apartments_5bhk"] += no_of_booked_apartment

                    elif self.regex_match(r'SHOP', apartment_type):
                        carpet_area_range["apartments_shops"] += no_of_apartment
                        carpet_area_range["booked_apartments_shops"] += no_of_booked_apartment

                    elif self.regex_match(r'BUNGALOW', apartment_type):
                        carpet_area_range["apartments_bungalow"] += no_of_apartment
                        carpet_area_range["booked_apartments_bungalow"] += no_of_booked_apartment

                    elif self.regex_match(r'OFFICE', apartment_type):
                        carpet_area_range["apartments_office_space"] += no_of_apartment
                        carpet_area_range["booked_apartments_office_space"] += no_of_booked_apartment

                    else:
                        carpet_area_range["apartments_others"] += no_of_apartment
                        carpet_area_range["booked_apartments_others"] += no_of_booked_apartment

                    if 0 <= carpet_areas <= 30:
                        carpet_area_range["carpet_area_apartments_0_30"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_0_30"] += no_of_booked_apartment
                    elif 30 < carpet_areas <= 45:
                        carpet_area_range["carpet_area_apartments_30_45"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_30_45"] += no_of_booked_apartment
                    elif 45 < carpet_areas <= 60:
                        carpet_area_range["carpet_area_apartments_45_60"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_45_60"] += no_of_booked_apartment
                    elif 60 < carpet_areas <= 90:
                        carpet_area_range["carpet_area_apartments_60_90"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_60_90"] += no_of_booked_apartment
                    elif 90 < carpet_areas <= 120:
                        carpet_area_range["carpet_area_apartments_90_120"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_90_120"] += no_of_booked_apartment
                    elif 120 < carpet_areas <= 150:
                        carpet_area_range["carpet_area_apartments_120_150"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_120_150"] += no_of_booked_apartment
                    elif 150 < carpet_areas <= 200:
                        carpet_area_range["carpet_area_apartments_150_200"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_150_200"] += no_of_booked_apartment
                    else:
                        carpet_area_range["carpet_area_apartments_more_than_200"] += no_of_apartment
                        carpet_area_range["carpet_area_booked_apartments_more_than_200"] += no_of_booked_apartment

                    carpet_area_arr.append(carpet_areas * no_of_apartment)

            project_data.update(carpet_area_range)

            project_data["Carpet Area (in Sqmts)"] = sum(carpet_area_arr)
            project_data["Number of Apartment"] = total_no_of_apartment
            project_data["Number of Booked Apartment"] = total_no_of_booked_apartment

        except IndexError:
            print("Could not find carpet area data")
        except Exception as exc:
            print("Exception while fetching carpet area data", exc)

        project_data["Excavation"] = self.extract_building_tasks(tree, "Excavation") / (
                project_data["Total Number of Proposed Building/Wings (In the Layout/Plot)"] or 1)

        project_data["X number of Slabs of Super Structure"] = self.extract_building_tasks(
            tree, "X number of Slabs of Super Structure"
        ) / (project_data["Total Number of Proposed Building/Wings (In the Layout/Plot)"] or 1)

        project_data[
            "Installation of lifts, water pumps, Fire Fighting Fittings and Equipment"] = \
            self.extract_building_tasks(
                tree,
                "Installation of lifts, water pumps, "
                "Fire Fighting Fittings and Equipment as per CFO NOC, "
                "Electrical fittings to Common Areas, electro, mechanical equipment,"
                " Compliance to conditions of environment /CRZ NOC,"
                " Finishing to entrance lobby/s, plinth protection, "
                "paving of areas appurtenant to Building/Wing, "
                "Compound Wall and all other requirements as may be required to Obtain Occupation /Completion Certificate"
            ) / (project_data["Total Number of Proposed Building/Wings (In the Layout/Plot)"] or 1)

        form_4 = tree.xpath(
            "//td/span[contains(text(), 'Certificates of Architect') or "
            "contains(text(), 'Completion Certificate') or "
            "contains(text(), 'certificate of completion') or "
            "contains(text(), 'Certificate on Completion') or "
            "contains(text(), 'Form 4')"
            "]/../following-sibling::td/button")

        project_data["form_4"] = len(form_4) and "YES" or "NO"

        status_of_conveyance = tree.xpath(
            "//td/span[text()[normalize-space() = '1 Status of Conveyance']]/../following-sibling::td/button")

        project_data["conveyance"] = len(status_of_conveyance) and "YES" or "NO"
        if tree.xpath("//th[text()[normalize-space() = 'Complaint No']]"):
            complaint_details_table = tree.xpath("//th[text()[normalize-space() = 'Complaint No']]")[0]
            project_data["complaint_details"] = len(list(complaint_details_table.getparent().itersiblings("tr")))
        else:
            project_data["complaint_details"] = 0
        if tree.xpath("//th[text()[normalize-space() = 'Preventive/Injunction/Interim Order is Passed?']]"):
            litigation_details_table = tree.xpath("//th[text()[normalize-space() = 'Preventive/Injunction/Interim Order is Passed?']]")[0]
            project_data["litigation_details"] = len(list(litigation_details_table.getparent().itersiblings("tr")))
        else:
            project_data["litigation_details"] = 0

        return project_data

    def extract_building_details(self, tree, key):
        try:
            th_arr = tree.xpath(f"//th[text()[normalize-space() = '{key}']]")

            final_value = 0

            for th in th_arr:
                th_list = th.findall("../th")
                th_idx = th_list.index(th)

                value = list(th.getparent().itersiblings("tr"))[0].findall("td")[th_idx].text

                final_value += self.safe_int(value)

        except Exception as exc:
            print(f"Could not find {key}", exc)
            return 0

        return final_value

    def extract_building_tasks(self, tree, key):
        try:
            td_arr = tree.xpath(f"//td[text()[normalize-space() = '{key}']]/following-sibling::td")
            final_value = 0

            for td in td_arr:
                final_value += self.safe_int(td.text)

        except Exception as exc:
            print(f"Could not find {key}", exc)
            return 0

        return final_value

    @staticmethod
    def clean_number(value):
        if value is None:
            return None

        # Remove all non-digit and non-dot characters
        cleaned_value = re.sub(r'[^\d.]', '', value)

        # Replace consecutive dots with a single dot
        cleaned_value = re.sub(r'\.+', '.', cleaned_value)

        return cleaned_value

    def safe_float(self, value) -> float:
        cleaned_number = self.clean_number(value)

        try:
            result = cleaned_number and float(cleaned_number) or 0.0
            return result
        except ValueError:
            return 0.0

    def safe_int(self, value) -> int:
        cleaned_number = self.clean_number(value)

        try:
            result = cleaned_number and int(cleaned_number) or 0
            return result
        except ValueError:
            return 0

    def search_query(self):
        while self.current_retries < self.max_retries:
            # ['Ahmednagar', 'Akola', 'Amravati', 'Aurangabad', 'beed', 'Bhandara', 'Buldana', 'Chandrapur', 'Dhule', 'Gadchiroli', 'Gondiya', 'Hingoli', 'Jalgaon', 'Jalna', 'Kolhapur', 'Latur', 'Mumbai City', 'Mumbai Suburban', 'Nagpur', 'Nanded', 'Nandurbar', 'Nashik', 'Osmanabad', 'Palghar', 'Parbhani', 'Pune', 'Raigarh', 'Ratnagiri', 'Sangli', 'Satara', 'Sindhudurg', 'Solapur', 'Thane', 'Wardha', 'Washim', 'Yavatmal']

            try:
                districts = self.get_districts()
                print([a['Text'] for a in districts])

                current_state = self.load_state()

                for district in tqdm(districts[:]):
                    district_id = district.get("ID")
                    district_name = district.get("Text")
                    # if district_name in ['Thane', 'Pune', 'Mumbai City', 'Mumbai Suburban']:
                    #     continue

                    if current_state["current_district"] is not None and district_name.upper() \
                            < current_state["current_district"].upper():
                        print(f"Skipping '{district_name}' as it is already processed.")
                        continue

                    payload_data = templates.search_query_template(self.token, self.maharashtra_state_id, district_id)
                    payload = urllib.parse.urlencode(payload_data)

                    header = {**self.headers, "content-type": "application/x-www-form-urlencoded"}

                    if current_state["current_page"] == -1:
                        resp = self.smart_request("POST", self.search_query_url, headers=header, data=payload,
                                                  verify=False)

                        tree = self.get_etree(resp)

                        current_page = 0
                        print(tree.xpath("//label[text()='Total Pages :']/following-sibling::text()"))
                        print(resp.text)
                        total_pages = self.safe_int(
                            tree.xpath("//label[text()='Total Pages :']/following-sibling::text()")[0])
                        print(tree + ' 222')
                        self.append_to_csv(self.extract_projects_list_data(tree))
                        self.save_state(district_name, 0, total_pages)

                    else:
                        current_page = current_state["current_page"]
                        total_pages = current_state["total_pages"]

                    for i in tqdm(range(current_page, total_pages)):  # Saving data for rest of the pages
                        if i <= current_state["current_page"]:
                            print(f"Page {i} already processed")
                            continue

                        payload_data = templates.search_query_template(self.token, self.maharashtra_state_id,
                                                                       district_id, i)
                        payload = urllib.parse.urlencode(payload_data)

                        resp = self.smart_request("POST", self.search_query_url, headers=header, data=payload,
                                                  verify=False)

                        tree = self.get_etree(resp)

                        self.append_to_csv(self.extract_projects_list_data(tree))
                        self.save_state(district_name, i, total_pages)

                        time.sleep(0.75)

                    current_page = -1
                    total_pages = 0
                    self.save_state(district_name, current_page, total_pages)
                break
            except Exception as exc:
                print("Unexpected error occurred", exc)
                print(f"Retrying in  {self.retry_delay}")
                self.current_retries += 1
                time.sleep(self.retry_delay)

    def extract_projects_list_data(self, tree):
        projects_list_xpath = "//table/tbody/tr"
        projects_list = tree.xpath(projects_list_xpath)

        result_list = []

        for project in projects_list:
            td_arr = project.getchildren()
            project_data = templates.projects_data_template()

            project_data["Project Name"] = td_arr[1].text
            project_data["Promoter Name"] = td_arr[2].text
            project_data["Last Modified Date"] = td_arr[3].text

            # Extracting view details page.
            view_details_url = self.url + td_arr[4].find("b/a").get("href")
            view_details_data = self.view_details_query(view_details_url)
            # break

            project_data = {**project_data, **view_details_data}

            try:
                # Extracting certificate_data
                certificate_id = td_arr[6].find("b/a[2]").get("data-docname")
                project_data["View Certificate"] = certificate_id

                certificate_qstr = td_arr[6].find("b/a[2]").get("data-qstr")

                cert_base64 = self.show_certificate(certificate_qstr)

                decoded_data = base64.b64decode(cert_base64)
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(decoded_data))

                pdf_text = ""
                num_pages = len(pdf_reader.pages)
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    pdf_text += page.extract_text()

                pdf_text = pdf_text.replace("\xa0", " ").replace("\n", "")

                cert_date_match = re.search("commencing from {2}([0-9/]+) {2}and ending", pdf_text)

                project_data["Certificate Date"] = cert_date_match.group(1)
            except Exception as exc:
                print("Could not find certificate data", exc)

            result_list.append(project_data)

        return result_list

    @staticmethod
    def save_state(district, current_page, total_pages):
        state = {"current_district": district, "current_page": current_page, "total_pages": total_pages}
        with open('state.json', 'w') as f:
            json.dump(state, f)

    @staticmethod
    def load_state():
        init_state = {"current_district": "", "current_page": -1, "total_page": 0}
        try:
            with open('state.json', 'r') as f:
                state = json.load(f)
                return state

        except (FileNotFoundError, json.JSONDecodeError):
            with open('state.json', 'w') as f:
                json.dump(init_state, f)
                return init_state

    @staticmethod
    def append_to_csv(data):
        try:
            with open('rera_data.csv', 'a+', newline='', encoding="utf-8") as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=[*data[0].keys()])

                if csvfile.tell() == 0:
                    writer.writeheader()

                writer.writerows(data)
        except Exception as exc:
            print("Exception while saving data to csv", exc)

    @staticmethod
    def regex_match(regex, string):
        if re.search(regex, string, re.IGNORECASE):
            return True

        return False

    @classmethod
    def fetch_data(cls):
        return cls(None).pre_query()


if __name__ == "__main__":
    verifier = MahareraitVerifier.fetch_data()
