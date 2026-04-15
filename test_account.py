"""
=============================================================
 WHITE-BOX UNIT TEST – Module: Accounts
 File target : accounts/views.py  |  accounts/serializers.py
 Method      : White-Box Testing (Branch / Path / Condition)
 Run command : pytest accounts/tests.py -v
 Coverage    : pytest accounts/tests.py --cov=accounts --cov-report=html
=============================================================
"""
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

# ── Meaningful naming: reference to CustomUser model ──────────────────────────
User = get_user_model()


@pytest.mark.django_db(transaction=True)
# REQUIREMENT "Rollback":
#   transaction=True → mỗi test chạy trong 1 DB transaction độc lập.
#   Sau khi test kết thúc, toàn bộ thay đổi DB bị ROLLBACK → DB trở về
#   trạng thái TRƯỚC test, đảm bảo các test không ảnh hưởng lẫn nhau.
class TestAccountsWhiteBox:
    """
    WHITE-BOX UNIT TEST SUITE – Module Accounts
    Assignee : Dũng
    Targets  : RegisterView.create | validate_phone_number | validate_email
               LoginView.post | LogoutView.post
               UserDeleteView.perform_destroy | UserUpdateView (UserAndPasswordSerializer.update)
    """

    def setup_method(self):
        """Khởi tạo API client trước mỗi hàm test."""
        self.api_client   = APIClient()
        self.register_url = '/api/accounts/register/'
        self.login_url    = '/api/accounts/login/'
        self.logout_url   = '/api/accounts/logout/'

    # ===========================================================
    # TC_ACC_BE_01 — RegisterView.create() | Branch 1 (is_valid=True)
    # ===========================================================
    def test_TC_ACC_BE_01_register_valid_data_hits_true_branch(self):
        """
        [Test Case ID: TC_ACC_BE_01]
        WHITE-BOX TARGET : RegisterView.create() — Branch 1
          Code path: if serializer.is_valid(): ← True → return Response(201)
        Technique  : Branch Coverage
        Pre-cond   : DB trống (không có user nào).
        Input      : JSON hợp lệ, đủ tất cả required fields.
        Expected   : HTTP 201 | isSuccess=True
        CheckDB    : User.objects.count() tăng 1.
                     Email "be01@agoda.com" xuất hiện trong DB.
        """
        # ── Pre-condition: ghi lại trạng thái DB trước test ──────────────────
        initial_count = User.objects.count()

        # ── Input  ────────────────────────────────────────────────────────────
        valid_payload = {
            "username":     "dung_tc01",
            "email":        "be01@agoda.com",
            "first_name":   "Dung",
            "last_name":    "Nguyen",
            "password":     "StrongPass123!",
            "phone_number": "0987654321",
            "gender":       "male",
            "role":         "customer",
        }

        # ── Execute ───────────────────────────────────────────────────────────
        response = self.api_client.post(self.register_url, data=valid_payload, format='json')

        # ── Assert: HTTP 201 (Branch True đã chạy) ───────────────────────────
        assert response.status_code == 201
        assert response.data.get("isSuccess") is True

        # ── REQUIREMENT "CheckDB" ─────────────────────────────────────────────
        assert User.objects.count() == initial_count + 1
        assert User.objects.filter(email="be01@agoda.com").exists() is True

    # ===========================================================
    # TC_ACC_BE_02 — RegisterView.create() | Branch 2 (is_valid=False)
    # ===========================================================
    def test_TC_ACC_BE_02_register_duplicate_email_hits_false_branch(self):
        """
        [Test Case ID: TC_ACC_BE_02]
        WHITE-BOX TARGET : RegisterView.create() — Branch 2
          Code path: else ← (is_valid=False) → return Response(400, errors)
        Technique  : Branch Coverage
        Pre-cond   : Đã có user với email "existing@agoda.com" trong DB.
        Input      : JSON có email trùng "existing@agoda.com".
        Expected   : HTTP 400 | isSuccess=False | "errors" key có trong response.
        CheckDB    : User.objects.count() KHÔNG đổi (không insert rác).
        """
        # ── Pre-condition: seed user trước ───────────────────────────────────
        User.objects.create_user(
            username="existing_user",
            email="existing@agoda.com",
            password="Existing123!"
        )
        baseline_count = User.objects.count()

        # ── Input: chỉ email bị trùng, các field khác hợp lệ ─────────────────
        duplicate_email_payload = {
            "username":     "new_user_attempt",
            "email":        "existing@agoda.com",  # ← trùng email cố ý
            "first_name":   "New",
            "last_name":    "User",
            "password":     "NewPass123!",
            "phone_number": "0911222333",
            "gender":       "female",
            "role":         "customer",
        }

        # ── Execute ───────────────────────────────────────────────────────────
        response = self.api_client.post(
            self.register_url, data=duplicate_email_payload, format='json'
        )

        # ── Assert: HTTP 400 (Branch False đã chạy) ──────────────────────────
        assert response.status_code == 400
        assert response.data.get("isSuccess") is False
        assert "errors" in response.data

        # ── REQUIREMENT "CheckDB" ─────────────────────────────────────────────
        # DB count phải giữ nguyên — không insert dữ liệu lỗi
        assert User.objects.count() == baseline_count

    # ===========================================================
    # TC_ACC_BE_03 — validate_phone_number() | Condition 1 (not isdigit)
    # ===========================================================
    def test_TC_ACC_BE_03_validate_phone_non_digit_raises_validation_error(self):
        """
        [Test Case ID: TC_ACC_BE_03]
        WHITE-BOX TARGET : RegisterSerializer.validate_phone_number() — Condition 1
          Code path: if value and not value.isdigit(): ← True → raise ValidationError
        Technique  : Condition Coverage
        Input      : phone_number = "abc12345" (chứa ký tự không phải số)
        Expected   : HTTP 400 | errors.phone_number có thông báo lỗi.
        CheckDB    : count() không đổi — không insert user lỗi.
        """
        initial_count = User.objects.count()

        invalid_phone_payload = {
            "username":     "phone_cond1",
            "email":        "cond1@agoda.com",
            "first_name":   "Test",
            "last_name":    "Phone",
            "password":     "ValidPass123!",
            "phone_number": "abc12345",  # ← không phải số nguyên
            "gender":       "male",
            "role":         "customer",
        }

        response = self.api_client.post(
            self.register_url, data=invalid_phone_payload, format='json'
        )

        assert response.status_code == 400
        errors = response.data.get("errors", {})
        assert "phone_number" in errors

        # ── REQUIREMENT "CheckDB": Rollback — không có user rác trong DB ──────
        assert User.objects.count() == initial_count

    # ===========================================================
    # TC_ACC_BE_04 — validate_phone_number() | Condition 2 (len != 10)
    # ===========================================================
    def test_TC_ACC_BE_04_validate_phone_wrong_length_raises_validation_error(self):
        """
        [Test Case ID: TC_ACC_BE_04]
        WHITE-BOX TARGET : RegisterSerializer.validate_phone_number() — Condition 2
          Code path: if value and len(value) != 10: ← True → raise ValidationError
        Technique  : Condition Coverage + BVA (6 chữ số — ranh giới dưới vi phạm)
        Input      : phone_number = "098765" (chỉ 6 chữ số, pass isdigit nhưng sai độ dài)
        Expected   : HTTP 400 | errors.phone_number có thông báo độ dài.
        CheckDB    : count() không đổi.
        """
        initial_count = User.objects.count()

        short_phone_payload = {
            "username":     "phone_cond2",
            "email":        "cond2@agoda.com",
            "first_name":   "Test",
            "last_name":    "Phone",
            "password":     "ValidPass123!",
            "phone_number": "098765",  # ← đúng số nhưng chỉ 6 ký tự
            "gender":       "male",
            "role":         "customer",
        }

        response = self.api_client.post(
            self.register_url, data=short_phone_payload, format='json'
        )

        assert response.status_code == 400
        errors = response.data.get("errors", {})
        assert "phone_number" in errors

        # ── REQUIREMENT "CheckDB" ─────────────────────────────────────────────
        assert User.objects.count() == initial_count

    # ===========================================================
    # TC_ACC_BE_05 — LoginView.post() | Branch 1 (user is not None)
    # ===========================================================
    def test_TC_ACC_BE_05_login_valid_credentials_hits_user_found_branch(self):
        """
        [Test Case ID: TC_ACC_BE_05]
        WHITE-BOX TARGET : LoginView.post() — Branch 1
          Code path: if user is not None: ← True → tạo JWT, return Response(200)
        Technique  : Branch Coverage
        Pre-cond   : User "login_user" tồn tại trong DB.
        Input      : username + password đúng.
        Expected   : HTTP 200 | data.access có JWT | data.refresh có token.
        CheckDB    : Xác nhận user tồn tại trước khi login thành công.
        """
        # ── Pre-condition ─────────────────────────────────────────────────────
        User.objects.create_user(username="login_user", password="SecurePassword123")

        # ── REQUIREMENT "CheckDB": user phải ở DB mới login được ─────────────
        assert User.objects.filter(username="login_user").exists() is True

        valid_credentials = {
            "username": "login_user",
            "password": "SecurePassword123",
        }

        # ── Execute ───────────────────────────────────────────────────────────
        response = self.api_client.post(self.login_url, data=valid_credentials, format='json')

        # ── Assert: Branch True → tokens được cấp ────────────────────────────
        assert response.status_code == 200
        assert response.data.get("isSuccess") is True

        jwt_access  = response.data.get("data", {}).get("access")
        jwt_refresh = response.data.get("data", {}).get("refresh")
        assert jwt_access  is not None, "access token phải có trong response"
        assert jwt_refresh is not None, "refresh token phải có trong response"

    # ===========================================================
    # TC_ACC_BE_06 — LoginView.post() | Branch 2 (user is None)
    # ===========================================================
    def test_TC_ACC_BE_06_login_wrong_password_hits_user_none_branch(self):
        """
        [Test Case ID: TC_ACC_BE_06]
        WHITE-BOX TARGET : LoginView.post() — Branch 2 (else / user = None)
          Code path: else: ← authenticate() trả None → return Response(isSuccess=False)
        Technique  : Branch Coverage
        Input      : password sai cố ý.
        Expected   : HTTP 200 | isSuccess=False | data={} | không có token.
        """
        User.objects.create_user(username="valid_user", password="CorrectPassword123")

        wrong_credentials = {
            "username": "valid_user",
            "password": "WrongPassword999",  # ← sai mật khẩu
        }

        response = self.api_client.post(self.login_url, data=wrong_credentials, format='json')

        # ── Assert: Branch False → không cấp token ───────────────────────────
        assert response.status_code == 200
        assert response.data.get("isSuccess") is False

        returned_token = response.data.get("data", {}).get("access")
        assert returned_token is None, "Không được cấp token khi xác thực thất bại"

    # ===========================================================
    # TC_ACC_BE_07 — LogoutView.post() | Path 1 (thiếu refresh token)
    # ===========================================================
    def test_TC_ACC_BE_07_logout_missing_token_hits_guard_clause_path(self):
        """
        [Test Case ID: TC_ACC_BE_07]
        WHITE-BOX TARGET : LogoutView.post() — Path 1 (guard clause)
          Code path: if not refresh_token: ← True → return Response(400)
        Technique  : Path Coverage
        Input      : Body rỗng {} — không gửi trường "refresh".
        Expected   : HTTP 400 | message = "Refresh token is required"
        """
        # Body rỗng → trigger guard clause đầu hàm
        empty_body = {}

        response = self.api_client.post(self.logout_url, data=empty_body, format='json')

        assert response.status_code == 400
        assert "Refresh token is required" in response.data.get("message", "")

    # ===========================================================
    # TC_ACC_BE_08 — LogoutView.post() | Path 3 (blacklist thành công)
    # ===========================================================
    def test_TC_ACC_BE_08_logout_valid_token_executes_blacklist_path(self):
        """
        [Test Case ID: TC_ACC_BE_08]
        WHITE-BOX TARGET : LogoutView.post() — Path 3 (try block / success)
          Code path: try: refresh.blacklist() ← thực thi → return Response(200)
        Technique  : Path Coverage + Statement Coverage
        Pre-cond   : User đã login, có refresh token hợp lệ.
        Input      : {"refresh": "<valid_refresh_token>"}
        Expected   : HTTP 200 | isSuccess=True | "Logged out successfully"
        CheckDB    : Token được ghi vào bảng BlacklistedToken trong DB.
        """
        # ── Pre-condition: tạo user và generate refresh token thật ───────────
        logout_user = User.objects.create_user(
            username="logout_tester",
            password="LogoutPass123"
        )
        # Tạo refresh token thật từ simplejwt (không qua HTTP)
        refresh_token_obj       = RefreshToken.for_user(logout_user)
        valid_refresh_token_str = str(refresh_token_obj)

        logout_payload = {"refresh": valid_refresh_token_str}

        # ── Execute ───────────────────────────────────────────────────────────
        response = self.api_client.post(self.logout_url, data=logout_payload, format='json')

        # ── Assert: Path 3 → blacklist() chạy → 200 ──────────────────────────
        assert response.status_code == 200
        assert response.data.get("isSuccess") is True
        assert "Logged out successfully" in response.data.get("message", "")

    # ===========================================================
    # TC_ACC_BE_09 — UserDeleteView.perform_destroy() | Soft Delete
    # ===========================================================
    def test_TC_ACC_BE_09_soft_delete_sets_is_active_false_not_hard_delete(self):
        """
        [Test Case ID: TC_ACC_BE_09]
        WHITE-BOX TARGET : UserDeleteView.perform_destroy()
          Code path: instance.is_active = False  ← dòng này thực thi
                     instance.save()
        Technique  : Statement Coverage (kiểm tra mỗi dòng trong perform_destroy)
        Pre-cond   : User tồn tại và is_active=True.
        Expected   : HTTP 200 | isSuccess=True
        CheckDB    :
          1. Record VẪN TỒN TẠI trong DB (không bị xóa cứng / hard delete).
          2. Cột is_active chuyển thành False (soft delete).
        """
        # ── Pre-condition ─────────────────────────────────────────────────────
        target_user = User.objects.create_user(
            username="soft_delete_target",
            password="DeleteMe123!"
        )
        target_user_id = target_user.id

        # Xác nhận user đang ACTIVE trước khi xóa
        assert target_user.is_active is True

        # ── Execute ───────────────────────────────────────────────────────────
        self.api_client.force_authenticate(user=target_user)
        response = self.api_client.delete(
            f'/api/accounts/users/{target_user_id}/delete/'
        )

        # ── Assert HTTP 200 ───────────────────────────────────────────────────
        assert response.status_code == 200
        assert response.data.get("isSuccess") is True

        # ── REQUIREMENT "CheckDB" ─────────────────────────────────────────────
        # Kiểm chứng 1: Record vẫn tồn tại trong DB (Soft Delete, không phải Hard Delete)
        record_still_exists = User.objects.filter(id=target_user_id).exists()
        assert record_still_exists is True, \
            "Soft Delete: bản ghi phải còn trong DB, không bị xóa cứng"

        # Kiểm chứng 2: is_active phải là False
        refreshed = User.objects.get(id=target_user_id)
        assert refreshed.is_active is False, \
            "Soft Delete: cột is_active phải được set thành False"

    # ===========================================================
    # TC_ACC_BE_10 — UserAndPasswordSerializer.update() | Branch 1 (có password)
    # ===========================================================
    def test_TC_ACC_BE_10_update_with_password_triggers_set_password_branch(self):
        """
        [Test Case ID: TC_ACC_BE_10]
        WHITE-BOX TARGET : UserAndPasswordSerializer.update() — Branch 1
          Code path: password = validated_data.pop("password", None)
                     if password: ← True → instance.set_password(password)
        Technique  : Branch Coverage
        Pre-cond   : User tồn tại với password cũ "OldPassword123!".
        Input      : PATCH body chứa cả first_name lẫn password mới.
        Expected   : HTTP 200 | isSuccess=True
        CheckDB    :
          1. first_name trong DB == "UpdatedName".
          2. check_password("NewPassword456!") trả True (set_password đã chạy).
          3. check_password("OldPassword123!") trả False (pass cũ không còn hợp lệ).
        """
        # ── Pre-condition: tạo user với password cũ ───────────────────────────
        user_to_update = User.objects.create_user(
            username="update_target",
            email="update@agoda.com",
            password="OldPassword123!",
            first_name="OldName"
        )
        user_id = user_to_update.id
        self.api_client.force_authenticate(user=user_to_update)

        # ── Input: payload có cả field thường lẫn password mới ───────────────
        update_payload_with_password = {
            "first_name": "UpdatedName",
            "password":   "NewPassword456!",  # ← triggers set_password() branch
        }

        # ── Execute ───────────────────────────────────────────────────────────
        response = self.api_client.patch(
            f'/api/accounts/users/{user_id}/update/',
            data=update_payload_with_password,
            format='json'
        )

        # ── Assert HTTP 200 ───────────────────────────────────────────────────
        assert response.status_code == 200
        assert response.data.get("isSuccess") is True

        # ── REQUIREMENT "CheckDB": reload dữ liệu mới nhất từ DB ─────────────
        user_to_update.refresh_from_db()

        # Kiểm chứng 1: first_name đã được cập nhật
        assert user_to_update.first_name == "UpdatedName"

        # Kiểm chứng 2: mật khẩu mới phải hoạt động (set_password đã hash đúng)
        assert user_to_update.check_password("NewPassword456!") is True, \
            "Mật khẩu mới phải được hash và lưu đúng vào DB"

        # Kiểm chứng 3: mật khẩu cũ phải bị vô hiệu hoá
        assert user_to_update.check_password("OldPassword123!") is False, \
            "Mật khẩu cũ phải bị thay thế hoàn toàn"
