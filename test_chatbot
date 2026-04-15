"""
=============================================================
 WHITE-BOX UNIT TEST – Module: Chatbot & Chats 
 File target : chatbots/views.py  |  chats/views.py
 Method      : White-Box Testing (Branch / Path / Condition)
 Run command : pytest chatbots/tests.py chats/tests.py -v
               pytest chatbots/tests.py chats/tests.py --cov=chatbots --cov=chats --cov-report=term-missing --cov-branch -v
=============================================================
"""
import pytest
import uuid
from django.test import RequestFactory
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from chats.models import Conversation, Message

# ── Meaningful model references ────────────────────────────────────────────────
User = get_user_model()


# ==============================================================================
# CHATBOTS MODULE – chatbots/views.py
# ==============================================================================

@pytest.mark.django_db(transaction=True)
# REQUIREMENT "Rollback": transaction=True rollbacks all DB changes after each test.
class TestChatbotsViewsWhiteBox:
    """
    WHITE-BOX UNIT TEST SUITE – Module: chatbots (Mạnh)
    Target: chatbots/views.py
      - ask_chatbot()
      - create_new_chat()
      - get_messages()
    """

    def setup_method(self):
        """Khởi tạo APIClient và URL trước mỗi test."""
        self.api_client        = APIClient()
        self.ask_url           = '/api/chatbot/ask/'
        self.create_chat_url   = '/api/chatbot/new/'
        self.get_messages_url  = '/api/chatbot/messages/'

    # ---------------------------------------------------------------
    # TC_BOT_BE_01 — ask_chatbot() | Condition 1: not question → 400
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_01_ask_chatbot_missing_question_returns_400(self):
        """
        [Test Case ID: TC_BOT_BE_01]
        WHITE-BOX TARGET: ask_chatbot() — Condition Coverage
          Code path: if not question or not chatid: ← (not question = True) → return 400
        Technique  : Condition Coverage
        Input      : POST body chỉ có chatid, thiếu question
        Expected   : HTTP 400 | error = "question and chatid are required"
        """
        # Payload thiếu "question" — triggers condition `not question`
        payload_missing_question = {
            "chatid": "valid-chat-id-123"
            # "question" key bị bỏ qua cố ý
        }

        response = self.api_client.post(
            self.ask_url,
            data=payload_missing_question,
            format='json',
            content_type='application/json'
        )

        assert response.status_code == 400
        assert "question and chatid are required" in str(response.content)

    # ---------------------------------------------------------------
    # TC_BOT_BE_02 — ask_chatbot() | Condition 2: not chatid → 400
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_02_ask_chatbot_missing_chatid_returns_400(self):
        """
        [Test Case ID: TC_BOT_BE_02]
        WHITE-BOX TARGET: ask_chatbot() — Condition Coverage
          Code path: if not question or not chatid: ← (not chatid = True) → return 400
        Technique  : Condition Coverage
        Input      : POST body chỉ có question, thiếu chatid
        Expected   : HTTP 400 | error = "question and chatid are required"
        """
        payload_missing_chatid = {
            "question": "Khách sạn nào tốt tại Đà Nẵng?"
            # "chatid" key bị bỏ qua cố ý
        }

        response = self.api_client.post(
            self.ask_url,
            data=payload_missing_chatid,
            format='json',
            content_type='application/json'
        )

        assert response.status_code == 400
        assert "question and chatid are required" in str(response.content)

    # ---------------------------------------------------------------
    # TC_BOT_BE_03 — create_new_chat() | Branch 2: not user_id → 400
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_03_create_new_chat_missing_user_id_returns_400(self):
        """
        [Test Case ID: TC_BOT_BE_03]
        WHITE-BOX TARGET: create_new_chat() — Branch 2
          Code path: if not user_id: ← True → return JsonResponse(400)
        Technique  : Condition Coverage
        Input      : POST body rỗng {}
        Expected   : HTTP 400 | error = "user_id is required"
        """
        # Body rỗng → trigger guard clause `not user_id`
        empty_payload = {}

        response = self.api_client.post(
            self.create_chat_url,
            data=empty_payload,
            format='json',
            content_type='application/json'
        )

        assert response.status_code == 400
        assert "user_id is required" in str(response.content)

    # ---------------------------------------------------------------
    # TC_BOT_BE_04 — create_new_chat() | Branch 3: DoesNotExist → 404
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_04_create_new_chat_user_not_found_returns_404(self):
        """
        [Test Case ID: TC_BOT_BE_04]
        WHITE-BOX TARGET: create_new_chat() — Branch 3
          Code path: except CustomUser.DoesNotExist: ← fired → return JsonResponse(404)
        Technique  : Branch Coverage
        Pre-cond   : Không có User nào với id=99999 trong DB.
        Input      : POST body: {"user_id": 99999}
        Expected   : HTTP 404 | error = "User not found"
        CheckDB    : Không có User nào với id=99999 (xác nhận pre-condition).
        """
        nonexistent_user_id = 99999

        # REQUIREMENT "CheckDB": xác nhận user không tồn tại trước test
        assert User.objects.filter(id=nonexistent_user_id).exists() is False

        payload_invalid_user = {"user_id": nonexistent_user_id}

        response = self.api_client.post(
            self.create_chat_url,
            data=payload_invalid_user,
            format='json',
            content_type='application/json'
        )

        assert response.status_code == 404
        assert "User not found" in str(response.content)

    # ---------------------------------------------------------------
    # TC_BOT_BE_05 — create_new_chat() | Branch 4: user đã có chat_id
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_05_create_new_chat_user_already_has_chat_id_returns_existing(self):
        """
        [Test Case ID: TC_BOT_BE_05]
        WHITE-BOX TARGET: create_new_chat() — Branch 4
          Code path: if user.chat_id: ← True → return JsonResponse(200, "Chat already exists")
        Technique  : Branch Coverage
        Pre-cond   : User tồn tại và có chat_id = "existing-chat-123".
        Input      : POST body: {"user_id": <user_id>}
        Expected   : HTTP 200 | message = "Chat already exists" | chatid = "existing-chat-123"
        CheckDB    : chat_id trong DB KHÔNG bị ghi đè (giá trị giữ nguyên).
        """
        # Pre-condition: Tạo user đã có chat_id sẵn
        existing_chat_id_value = "existing-chat-abc123"
        user_with_chat = User.objects.create_user(
            username="chatbot_user_existing",
            password="Pass123!"
        )
        user_with_chat.chat_id = existing_chat_id_value
        user_with_chat.save()

        payload = {"user_id": user_with_chat.id}

        response = self.api_client.post(
            self.create_chat_url,
            data=payload,
            format='json',
            content_type='application/json'
        )

        assert response.status_code == 200
        assert "Chat already exists" in str(response.content)
        assert existing_chat_id_value in str(response.content)

        # REQUIREMENT "CheckDB": chat_id phải giữ nguyên, không bị overwrite
        user_with_chat.refresh_from_db()
        assert user_with_chat.chat_id == existing_chat_id_value, \
            "chat_id phải giữ nguyên giá trị cũ, không bị ghi đè"

    # ---------------------------------------------------------------
    # TC_BOT_BE_06 — get_messages() | Branch 1: not chatid → 400
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_06_get_messages_missing_chatid_returns_400(self):
        """
        [Test Case ID: TC_BOT_BE_06]
        WHITE-BOX TARGET: get_messages() — Branch 1
          Code path: if not chatid: ← True → return JsonResponse(400)
        Technique  : Condition Coverage
        Input      : GET request không truyền query param "chatid"
        Expected   : HTTP 400 | error = "chatid is required"
        """
        # GET không có ?chatid= → trigger guard clause
        response = self.api_client.get(self.get_messages_url)

        assert response.status_code == 400
        assert "chatid is required" in str(response.content)


# ==============================================================================
# CHATS MODULE – chats/views.py
# ==============================================================================

@pytest.mark.django_db(transaction=True)
# REQUIREMENT "Rollback": transaction=True rollbacks all DB changes after each test.
class TestChatsViewsWhiteBox:
    """
    WHITE-BOX UNIT TEST SUITE – Module: chats (Mạnh)
    Target: chats/views.py
      - SendMessageView.create()
      - GetOrCreateConversationView.post()
    """

    def setup_method(self):
        """Khởi tạo client, tạo 2 user test và 1 conversation trước mỗi test."""
        self.api_client = APIClient()
        self.send_msg_url     = '/api/chats/messages/send/'
        self.get_or_create_url = '/api/chats/conversations/get_or_create/'

        # Tạo 2 user dùng chung cho nhiều test
        self.user_a = User.objects.create_user(
            username="chat_user_a", password="PassA123!"
        )
        self.user_b = User.objects.create_user(
            username="chat_user_b", password="PassB123!"
        )

    # ---------------------------------------------------------------
    # TC_BOT_BE_07 — SendMessageView.create() | Branch 1: DoesNotExist → 404
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_07_send_message_conversation_not_found_returns_404(self):
        """
        [Test Case ID: TC_BOT_BE_07]
        WHITE-BOX TARGET: SendMessageView.create() — Branch 1
          Code path: except Conversation.DoesNotExist: ← fired → return Response(404)
        Technique  : Branch Coverage
        Pre-cond   : Không có Conversation nào với id = 99999.
        Input      : POST body: {"conversation_id": 99999, "text": "Hello"}
        Expected   : HTTP 404 | isSuccess=False | message="Conversation not found"
        CheckDB    : Message.objects.count() giữ nguyên — không insert tin nhắn rác.
        """
        self.api_client.force_authenticate(user=self.user_a)

        initial_message_count = Message.objects.count()

        payload_invalid_conversation = {
            "conversation_id": 99999,   # ← không tồn tại
            "text": "Hello bot"
        }

        response = self.api_client.post(
            self.send_msg_url,
            data=payload_invalid_conversation,
            format='json'
        )

        assert response.status_code == 404
        assert response.data.get("isSuccess") is False
        assert "Conversation not found" in response.data.get("message", "")

        # REQUIREMENT "CheckDB": không insert Message rác
        assert Message.objects.count() == initial_message_count

    # ---------------------------------------------------------------
    # TC_BOT_BE_08 — SendMessageView.create() | Branch 2: gửi thành công
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_08_send_message_success_saves_to_db(self):
        """
        [Test Case ID: TC_BOT_BE_08]
        WHITE-BOX TARGET: SendMessageView.create() — Branch 2 (success path)
          Code path:
            conversation = Conversation.objects.get(...)  ← found
            message = Message.objects.create(...)         ← tạo message
            conversation.last_message = text             ← cập nhật
            conversation.seen = False                    ← đánh dấu chưa xem
        Technique  : Branch Coverage + Statement Coverage
        Pre-cond   : Conversation giữa user_a và user_b tồn tại.
        Input      : POST body: {"conversation_id": <id>, "text": "Xin chào"}
        Expected   : HTTP 200 | isSuccess=True | data.text == "Xin chào"
        CheckDB    :
          1. Message.objects.count() tăng 1.
          2. conversation.last_message == "Xin chào".
          3. conversation.seen == False.
        """
        # Pre-condition: tạo conversation hợp lệ giữa A và B
        test_conversation = Conversation.objects.create(
            user1=self.user_a,
            user2=self.user_b
        )

        initial_message_count = Message.objects.count()
        self.api_client.force_authenticate(user=self.user_a)

        message_text = "Xin chào từ TC_BOT_BE_08"

        send_payload = {
            "conversation_id": test_conversation.id,
            "text": message_text
        }

        response = self.api_client.post(
            self.send_msg_url,
            data=send_payload,
            format='json'
        )

        assert response.status_code == 200
        assert response.data.get("isSuccess") is True

        # REQUIREMENT "CheckDB" — kiểm chứng 3 điểm:
        # 1. Message được tạo trong DB
        assert Message.objects.count() == initial_message_count + 1

        # 2. last_message được cập nhật trong conversation
        test_conversation.refresh_from_db()
        assert test_conversation.last_message == message_text

        # 3. seen = False sau khi gửi tin mới
        assert test_conversation.seen is False

    # ---------------------------------------------------------------
    # TC_BOT_BE_09 — GetOrCreateConversationView.post() | Branch 1: missing user_id
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_09_get_or_create_conversation_missing_user_id_returns_400(self):
        """
        [Test Case ID: TC_BOT_BE_09]
        WHITE-BOX TARGET: GetOrCreateConversationView.post() — Branch 1
          Code path: if not other_id: ← True → return Response(400)
        Technique  : Condition Coverage
        Input      : POST body: {} (không gửi user_id)
        Expected   : HTTP 400 | isSuccess=False | message="user_id is required"
        """
        self.api_client.force_authenticate(user=self.user_a)

        empty_payload = {}  # Thiếu user_id cố ý

        response = self.api_client.post(
            self.get_or_create_url,
            data=empty_payload,
            format='json'
        )

        assert response.status_code == 400
        assert response.data.get("isSuccess") is False
        assert "user_id is required" in response.data.get("message", "")

    # ---------------------------------------------------------------
    # TC_BOT_BE_10 — GetOrCreateConversationView.post() | Branch 5: tạo mới
    # ---------------------------------------------------------------
    def test_TC_BOT_BE_10_get_or_create_conversation_creates_new_when_not_exist(self):
        """
        [Test Case ID: TC_BOT_BE_10]
        WHITE-BOX TARGET: GetOrCreateConversationView.post() — Branch 5
          Code path:
            conversation = Conversation.objects.filter(...).first()  ← None (chưa có)
            # không có client_conv_id
            conversation = Conversation.objects.create(...)          ← TẠO MỚI
        Technique  : Branch Coverage
        Pre-cond   : Chưa có Conversation giữa user_a và user_b.
        Input      : POST body: {"user_id": <user_b_id>} (không gửi conversation_id)
        Expected   : HTTP 200 | isSuccess=True | message="Conversation created"
        CheckDB    :
          1. Conversation.objects.count() tăng 1.
          2. Conversation mới có user1=user_a, user2=user_b (hoặc ngược lại).
        """
        self.api_client.force_authenticate(user=self.user_a)

        initial_conversation_count = Conversation.objects.count()

        create_payload = {
            "user_id": self.user_b.id
            # Không gửi "conversation_id" → trigger Branch 5 (UUID tự sinh server)
        }

        response = self.api_client.post(
            self.get_or_create_url,
            data=create_payload,
            format='json'
        )

        assert response.status_code == 200
        assert response.data.get("isSuccess") is True
        assert "Conversation created" in response.data.get("message", "")

        # REQUIREMENT "CheckDB" — Conversation mới được tạo trong DB
        assert Conversation.objects.count() == initial_conversation_count + 1

        # Xác minh đúng 2 user trong conversation
        new_conversation_exists = Conversation.objects.filter(
            user1=self.user_a, user2=self.user_b
        ).exists() or Conversation.objects.filter(
            user1=self.user_b, user2=self.user_a
        ).exists()
        assert new_conversation_exists is True, \
            "Conversation phải được tạo với đúng user1 và user2"
