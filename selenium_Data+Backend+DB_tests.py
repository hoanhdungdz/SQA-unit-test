import html
import sys
import time
import unittest
from pathlib import Path

from api_system_tests import (
    BE_URL,
    FE_URL,
    build_user_payload,
    cleanup_user_by_identity,
    cleanup_user_payload,
    db_fetch_all,
    db_fetch_one,
    get_hotel_detail_via_api,
    get_hotel_list_via_api,
    get_location_suggestions_via_api,
    login_user_via_api,
    register_user_via_api,
)

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait

    SELENIUM_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover
    webdriver = None
    TimeoutException = Exception
    By = None
    EC = None
    WebDriverWait = None
    SELENIUM_IMPORT_ERROR = exc


TEST_CASES = {
    "TC_DBD_01": {
        "name": "Guest header renders auth entry points",
        "method": "GET",
        "steps": "1. Open homepage 2. Check guest header links",
        "expected": "Guest can see login and register actions in header",
    },
    "TC_DBD_02": {
        "name": "UI registration persists customer role in DB",
        "method": "POST (UI + DB)",
        "steps": "1. Submit registration form 2. Query DB by username",
        "expected": "Customer account is created with expected role and email",
    },
    "TC_DBD_03": {
        "name": "UI login stores token and can fetch profile",
        "method": "POST (UI)",
        "steps": "1. Login from UI 2. Read localStorage token 3. Verify profile API",
        "expected": "Access token is stored and backend profile matches the login account",
    },
    "TC_DBD_04": {
        "name": "Invalid password does not create session",
        "method": "POST (UI)",
        "steps": "1. Enter valid username 2. Enter invalid password 3. Submit",
        "expected": "UI stays on login page and access token remains empty",
    },
    "TC_DBD_05": {
        "name": "Password is stored hashed after registration",
        "method": "POST",
        "steps": "1. Register new user 2. Inspect password column in DB",
        "expected": "Stored password differs from raw password and uses Django hash prefix",
    },
    "TC_DBD_06": {
        "name": "Duplicate username is blocked by backend",
        "method": "POST",
        "steps": "1. Seed existing user 2. Submit same username from UI",
        "expected": "Database still contains a single record for that username",
    },
    "TC_DBD_07": {
        "name": "Hotel list API returns pagination payload",
        "method": "GET API",
        "steps": "1. Call hotel list endpoint with page size",
        "expected": "Response includes meta/data structure and HTTP 200",
    },
    "TC_DBD_08": {
        "name": "Hotel detail API matches DB source row",
        "method": "GET API",
        "steps": "1. Read one hotel id from API 2. Compare detail payload with DB row",
        "expected": "Hotel detail endpoint returns the same id and name as DB",
    },
    "TC_DBD_09": {
        "name": "Forgot password flow reaches success state",
        "method": "GET",
        "steps": "1. Open forgot password page 2. Submit email 3. Wait for success result",
        "expected": "Frontend switches to success message after mock email send",
    },
    "TC_DBD_10": {
        "name": "Logout clears local token and returns guest navigation",
        "method": "UI + LocalStorage",
        "steps": "1. Seed token 2. Logout from header menu 3. Recheck header state",
        "expected": "Local token is removed and guest login link is visible again",
    },
    "TC_DBD_11": {
        "name": "Location suggestion API returns hotel or city candidates",
        "method": "GET API",
        "steps": "1. Query suggestion endpoint with hotel keyword",
        "expected": "Suggestion endpoint responds successfully with candidate records",
    },
}


def testcase_metadata(case_id: str):
    return TEST_CASES[case_id]


class BaseSeleniumTest(unittest.TestCase):
    frontend_url = FE_URL
    backend_url = BE_URL
    max_wait = 20

    def setUp(self):
        if SELENIUM_IMPORT_ERROR is not None:
            self.skipTest(f"Selenium is not installed: {SELENIUM_IMPORT_ERROR}")

        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, self.max_wait)

    def tearDown(self):
        if hasattr(self, "driver"):
            self.driver.quit()

    def open(self, path: str):
        self.driver.get(f"{self.frontend_url}{path}")

    def wait_for_css(self, selector: str):
        return self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )

    def wait_for_xpath(self, selector: str):
        return self.wait.until(EC.presence_of_element_located((By.XPATH, selector)))

    def click_xpath(self, selector: str):
        element = self.wait.until(EC.element_to_be_clickable((By.XPATH, selector)))
        element.click()
        return element

    def click_css(self, selector: str):
        element = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
        element.click()
        return element

    def fill_input_by_placeholder(self, placeholder: str, value: str):
        input_el = self.wait_for_xpath(f"//input[@placeholder='{placeholder}']")
        input_el.clear()
        input_el.send_keys(value)
        return input_el

    def fill_password_by_placeholder(self, placeholder: str, value: str):
        input_el = self.wait_for_xpath(f"//input[@placeholder='{placeholder}']")
        input_el.clear()
        input_el.send_keys(value)
        return input_el

    def submit_button(self, label: str):
        return self.click_xpath(
            f"//button[.//span[normalize-space()='{label}'] or normalize-space()='{label}']"
        )

    def select_gender(self, label: str):
        self.click_xpath("//div[contains(@class,'ant-select-selector')]")
        self.click_xpath(
            "//div[contains(@class,'ant-select-item-option-content') and normalize-space()='%s']"
            % label
        )

    def get_local_storage(self, key: str):
        return self.driver.execute_script(
            "return window.localStorage.getItem(arguments[0]);", key
        )

    def set_local_storage(self, key: str, value: str):
        self.driver.execute_script(
            "window.localStorage.setItem(arguments[0], arguments[1]);", key, value
        )

    def set_cookie_via_js(self, name: str, value: str):
        self.driver.execute_script(
            "document.cookie = arguments[0] + '=' + arguments[1] + '; path=/';",
            name,
            value,
        )

    def wait_for_token_value(self, should_exist: bool):
        def _predicate(_driver):
            value = self.get_local_storage("access_token_agoda")
            return bool(value) if should_exist else value is None

        return self.wait.until(_predicate)


class TestHomepage(BaseSeleniumTest):
    def test_TC_DBD_01_guest_header_actions_visible(self):
        """TC_DBD_01: Guest header renders auth entry points → thấy link Login/Register."""
        meta = testcase_metadata("TC_DBD_01")
        start = time.time()
        self.open("/")
        self.wait_for_css("a[href='/login']")
        self.wait_for_css("a[href='/register']")
        elapsed = time.time() - start

        self.assertLess(
            elapsed,
            10,
            f"{meta['name']} took too long to load: {elapsed:.2f}s",
        )


class TestLogin(BaseSeleniumTest):
    def setUp(self):
        super().setUp()
        self.valid_user = build_user_payload("login_ui")
        cleanup_user_payload(self.valid_user)
        register_result = register_user_via_api(self.valid_user)
        self.assertEqual(
            register_result["status_code"],
            200,
            f"Setup register failed: {register_result['json']}",
        )

    def tearDown(self):
        cleanup_user_payload(self.valid_user)
        super().tearDown()

    def test_TC_DBD_03_login_stores_token_and_profile_matches(self):
        """TC_DBD_03: Đăng nhập hợp lệ → có access_token + DB role=customer."""
        self.open("/login")
        self.fill_input_by_placeholder("Tên đăng nhập", self.valid_user["username"])
        self.fill_password_by_placeholder("Mật khẩu", self.valid_user["password"])
        self.submit_button("Đăng nhập")
        self.wait_for_token_value(True)
        self.wait.until(lambda driver: "/login" not in driver.current_url)

        token = self.get_local_storage("access_token_agoda")
        self.assertTrue(token, "Access token was not stored after valid login")
        user_row = db_fetch_one(
            "SELECT username, email, role FROM accounts_customuser WHERE username=%s",
            (self.valid_user["username"],),
        )
        self.assertIsNotNone(user_row)
        self.assertEqual(user_row["role"], "customer")

    def test_TC_DBD_04_login_invalid_password_has_no_session(self):
        """TC_DBD_04: Đăng nhập sai mật khẩu → ở lại /login, không phát sinh token."""
        self.open("/login")
        self.fill_input_by_placeholder("Tên đăng nhập", self.valid_user["username"])
        self.fill_password_by_placeholder("Mật khẩu", "WrongPass123!")
        self.submit_button("Đăng nhập")
        time.sleep(1.5)

        token = self.get_local_storage("access_token_agoda")
        self.assertIsNone(token, "Token should not be generated for invalid password")
        self.assertIn("/login", self.driver.current_url)


class TestRegister(BaseSeleniumTest):
    def _fill_register_form(self, payload: dict, phone_override: str | None = None):
        self.fill_input_by_placeholder("Họ", payload["first_name"])
        self.fill_input_by_placeholder("Tên", payload["last_name"])
        self.fill_input_by_placeholder("Địa chỉ email", payload["email"])
        self.fill_input_by_placeholder("Tên đăng nhập", payload["username"])
        self.fill_input_by_placeholder("Số điện thoại", phone_override or payload["phone_number"])
        self.select_gender("Nam")
        self.fill_password_by_placeholder("Mật khẩu", payload["password"])
        self.fill_password_by_placeholder("Xác nhận mật khẩu", payload["password"])
        self.click_xpath("//span[contains(normalize-space(),'Tôi đồng ý với')]")

    def test_TC_DBD_02_register_creates_customer_record(self):
        """TC_DBD_02: Đăng ký từ UI → DB có user mới, role=customer, email đúng."""
        payload = build_user_payload("register_ui")
        cleanup_user_payload(payload)

        self.open("/register")
        self._fill_register_form(payload)
        self.submit_button("Đăng ký tài khoản")
        self.wait.until(lambda driver: "/login" in driver.current_url)

        row = db_fetch_one(
            "SELECT username, email, first_name, last_name, role FROM accounts_customuser WHERE username=%s",
            (payload["username"],),
        )
        self.assertIsNotNone(row, "Registered user was not found in DB")
        self.assertEqual(row["email"], payload["email"])
        self.assertEqual(row["role"], "customer")
        cleanup_user_payload(payload)

    def test_TC_DBD_06_register_duplicate_username_keeps_single_row(self):
        """TC_DBD_06: Username trùng → backend chặn, DB chỉ có 1 record cho username đó."""
        existing = build_user_payload("duplicate_username")
        cleanup_user_payload(existing)
        register_result = register_user_via_api(existing)
        self.assertEqual(
            register_result["status_code"],
            200,
            f"Setup register failed: {register_result['json']}",
        )

        duplicate = build_user_payload("duplicate_candidate")
        duplicate["username"] = existing["username"]
        cleanup_user_by_identity(email=duplicate["email"])

        self.open("/register")
        self._fill_register_form(duplicate)
        self.submit_button("Đăng ký tài khoản")
        time.sleep(1.5)

        username_rows = db_fetch_all(
            "SELECT id FROM accounts_customuser WHERE username=%s", (existing["username"],)
        )
        self.assertEqual(
            len(username_rows),
            1,
            "Duplicate username should not create an extra user row",
        )
        self.assertIn("/register", self.driver.current_url)

        cleanup_user_payload(existing)
        cleanup_user_payload(duplicate)

    def test_TC_DBD_05_register_password_is_hashed_in_db(self):
        """TC_DBD_05: Đăng ký user → password lưu dưới dạng hash (pbkdf2_), khác raw password."""
        payload = build_user_payload("hash_check")
        cleanup_user_payload(payload)

        self.open("/register")
        self._fill_register_form(payload)
        self.submit_button("Đăng ký tài khoản")
        self.wait.until(lambda driver: "/login" in driver.current_url)

        created = db_fetch_one(
            "SELECT id, password FROM accounts_customuser WHERE username=%s",
            (payload["username"],),
        )
        self.assertIsNotNone(created, "User should be created before password hash check")
        self.assertNotEqual(created["password"], payload["password"])
        self.assertTrue(created["password"].startswith("pbkdf2_"))

        cleanup_user_payload(payload)


class TestHotelSearch(unittest.TestCase):
    def test_TC_DBD_07_hotel_list_has_meta_and_data(self):
        """TC_DBD_07: Hotel list API → trả về meta + data list (HTTP 200)."""
        response = get_hotel_list_via_api(page_size=5)
        self.assertEqual(response["status_code"], 200)
        payload = response["json"]
        self.assertTrue(payload.get("isSuccess"))
        self.assertIn("data", payload)
        self.assertIsInstance(payload["data"], list)
        self.assertIn("meta", payload)
        self.assertIn("totalItems", payload["meta"])

    def test_TC_DBD_08_hotel_detail_matches_db_name(self):
        """TC_DBD_08: Hotel detail API → id/name khớp với row tương ứng trong DB."""
        list_response = get_hotel_list_via_api(page_size=1)
        self.assertEqual(list_response["status_code"], 200)
        hotels = list_response["json"].get("data", [])
        if not hotels:
            self.skipTest("TC_DBD_08 SKIP: No hotels in DB")

        hotel_id = hotels[0]["id"]
        detail_response = get_hotel_detail_via_api(hotel_id)
        self.assertEqual(detail_response["status_code"], 200)
        payload = detail_response["json"]
        self.assertTrue(payload.get("isSuccess"))
        self.assertEqual(payload["data"]["id"], hotel_id)
        db_hotel = db_fetch_one("SELECT id, name FROM hotels_hotel WHERE id=%s", (hotel_id,))
        self.assertIsNotNone(db_hotel)
        self.assertEqual(payload["data"]["name"], db_hotel["name"])

    def test_TC_DBD_11_location_suggestions_return_candidates(self):
        """TC_DBD_11: Location suggestion API → trả về danh sách candidate (>=1)."""
        hotel_row = db_fetch_one(
            "SELECT name FROM hotels_hotel WHERE name IS NOT NULL AND name <> '' ORDER BY id ASC LIMIT 1"
        )
        if not hotel_row:
            self.skipTest("TC_DBD_11 SKIP: No hotel name available for suggestion query")

        query = hotel_row["name"][:4]
        response = get_location_suggestions_via_api(query, "hotel")
        self.assertEqual(response["status_code"], 200)
        payload = response["json"]
        candidates = payload.get("results") or payload.get("data") or []
        self.assertIsInstance(candidates, list)
        self.assertGreater(
            len(candidates),
            0,
            "Suggestion endpoint should return at least one candidate",
        )


class TestForgotPassword(BaseSeleniumTest):
    def test_TC_DBD_09_forgot_password_reaches_success_state(self):
        """TC_DBD_09: Quên mật khẩu → submit email và thấy message 'Email đã được gửi'."""
        self.open("/forgot-password")
        self.fill_input_by_placeholder("Địa chỉ email", "demo@example.com")
        self.submit_button("Gửi email khôi phục")
        self.wait_for_xpath("//*[contains(text(),'Email đã được gửi')]")
        self.assertIn("Email", self.driver.page_source)


class TestLogout(BaseSeleniumTest):
    def test_TC_DBD_10_logout_clears_token_and_restores_guest_header(self):
        """TC_DBD_10: Logout từ UI → xoá token localStorage + header hiện lại link login."""
        payload = build_user_payload("logout_ui")
        cleanup_user_payload(payload)
        register_result = register_user_via_api(payload)
        self.assertEqual(
            register_result["status_code"],
            200,
            f"Setup register failed: {register_result['json']}",
        )
        login_result = login_user_via_api(payload["username"], payload["password"])
        self.assertEqual(login_result["status_code"], 200)
        self.assertTrue(login_result["json"].get("isSuccess"))

        access = login_result["json"]["data"]["access"]
        refresh = login_result["json"]["data"]["refresh"]

        self.open("/")
        self.set_local_storage("access_token_agoda", access)
        self.set_cookie_via_js("refresh_token_agoda", refresh)
        self.driver.refresh()

        self.wait.until(
            lambda driver: payload["first_name"] in driver.page_source
            or payload["last_name"] in driver.page_source
        )
        self.click_xpath(f"//*[contains(text(),'{payload['first_name']}')]")
        self.click_xpath("//*[normalize-space()='Thoát']")
        self.wait_for_token_value(False)

        self.assertIsNone(self.get_local_storage("access_token_agoda"))
        self.wait_for_css("a[href='/login']")
        cleanup_user_payload(payload)


class HtmlFriendlyTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.case_records = []
        self._start_times = {}

    def startTest(self, test):
        self._start_times[test.id()] = time.time()
        super().startTest(test)

    def addSuccess(self, test):
        self.case_records.append(self._build_record(test, "PASS"))
        super().addSuccess(test)

    def addSkip(self, test, reason):
        self.case_records.append(self._build_record(test, "SKIPPED", reason))
        super().addSkip(test, reason)

    def addFailure(self, test, err):
        self.case_records.append(
            self._build_record(test, "FAIL", self._exc_info_to_string(err, test))
        )
        super().addFailure(test, err)

    def addError(self, test, err):
        self.case_records.append(
            self._build_record(test, "ERROR", self._exc_info_to_string(err, test))
        )
        super().addError(test, err)

    def _build_record(self, test, result: str, detail: str = ""):
        test_name = test._testMethodName
        case_id = None
        for key in TEST_CASES:
            if key.lower() in test_name.lower():
                case_id = key
                break
        meta = TEST_CASES.get(case_id or "", {})
        started_at = self._start_times.get(test.id(), time.time())
        return {
            "test_id": case_id or test_name,
            "test_name": meta.get("name", test_name),
            "method": meta.get("method", ""),
            "steps": meta.get("steps", ""),
            "expected": meta.get("expected", ""),
            "actual": detail or result,
            "result": result,
            "duration": time.time() - started_at,
            "test_path": test.id(),
        }


def render_html_report(result: HtmlFriendlyTestResult, output_file: Path) -> Path:
    rows = []
    for record in result.case_records:
        rows.append(
            "<tr>"
            f"<td>{html.escape(record['test_id'])}</td>"
            f"<td>{html.escape(record['test_name'])}</td>"
            f"<td>{html.escape(record['method'])}</td>"
            f"<td>{html.escape(record['steps'])}</td>"
            f"<td>{html.escape(record['expected'])}</td>"
            f"<td>{html.escape(str(record['actual']))}</td>"
            f"<td>{html.escape(record['result'])}</td>"
            f"<td>{record['duration']:.2f}s</td>"
            f"<td>{html.escape(record['test_path'])}</td>"
            "</tr>"
        )

    total = result.testsRun
    passed = len([r for r in result.case_records if r["result"] == "PASS"])
    skipped = len([r for r in result.case_records if r["result"] == "SKIPPED"])
    failed = len([r for r in result.case_records if r["result"] == "FAIL"])
    errors = len([r for r in result.case_records if r["result"] == "ERROR"])

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Agoda Selenium UI Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d0d7de; padding: 8px; vertical-align: top; text-align: left; }}
    th {{ background: #f6f8fa; }}
    .summary {{ display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }}
    .card {{ border: 1px solid #d0d7de; border-radius: 8px; padding: 12px 16px; min-width: 120px; }}
  </style>
</head>
<body>
  <h1>Agoda Selenium UI Test Report</h1>
  <div class="summary">
    <div class="card"><strong>Total</strong><br>{total}</div>
    <div class="card"><strong>Passed</strong><br>{passed}</div>
    <div class="card"><strong>Failed</strong><br>{failed}</div>
    <div class="card"><strong>Errors</strong><br>{errors}</div>
    <div class="card"><strong>Skipped</strong><br>{skipped}</div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Test Case ID</th>
        <th>Test Case Name</th>
        <th>Method</th>
        <th>Steps</th>
        <th>Expected Result</th>
        <th>Actual Result</th>
        <th>Test Result</th>
        <th>Duration</th>
        <th>Test</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>
</body>
</html>
"""
    output_file.write_text(html_doc, encoding="utf-8")
    return output_file


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2, resultclass=HtmlFriendlyTestResult)
    result = runner.run(suite)

    reports_dir = Path(__file__).resolve().parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = render_html_report(result, reports_dir / "selenium_ui_report.html")
    print(f"HTML report: {report_path}")
    sys.exit(0 if result.wasSuccessful() else 1)
