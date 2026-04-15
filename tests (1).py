import math
import os
from unittest.mock import PropertyMock, patch

from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

# Ensure Django settings are available during test module import/collection.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "agoda_be.settings")

from accounts.models import CustomUser
from cities.models import City
from countries.models import Country
from hotels.models import Hotel, HotelImage, UserHotelInteraction
from hotels.serializers import HotelSerializer, HotelSimpleSerializer
from hotels.views import UserHotelInteractionUpsertView
from rooms.models import Room


class HotelUnitTests(TestCase):
    """Hotel unit tests mapped to TC_HTL_BE_B_01 -> TC_HTL_BE_B_15."""

    TEST_CASE_META = {
        "test_TC_HTL_BE_B_01_hotel_str_returns_name": (
            "TC_HTL_BE_B_01",
            "Return hotel name string representation correctly",
        ),
        "test_TC_HTL_BE_B_02_update_min_price_uses_available_rooms_only": (
            "TC_HTL_BE_B_02",
            "Update min_price from available rooms only",
        ),
        "test_TC_HTL_BE_B_03_update_min_price_defaults_to_zero_without_available_room": (
            "TC_HTL_BE_B_03",
            "Set min_price to 0 when no available room exists",
        ),
        "test_TC_HTL_BE_B_04_sentiment_score_positive_case": (
            "TC_HTL_BE_B_04",
            "Calculate positive sentiment score correctly",
        ),
        "test_TC_HTL_BE_B_05_sentiment_score_zero_total": (
            "TC_HTL_BE_B_05",
            "Avoid division-by-zero in sentiment score when all counters are zero",
        ),
        "test_TC_HTL_BE_B_06_click_score_uses_log_formula": (
            "TC_HTL_BE_B_06",
            "Compute click score using logarithmic formula",
        ),
        "test_TC_HTL_BE_B_07_calc_total_weighted_score_combines_metrics": (
            "TC_HTL_BE_B_07",
            "Compute combined weighted score from avg star, click score, and sentiment score",
        ),
        "test_TC_HTL_BE_B_08_update_total_weighted_score_persists_value": (
            "TC_HTL_BE_B_08",
            "Persist total weighted score to database",
        ),
        "test_TC_HTL_BE_B_09_save_falls_back_to_zero_when_weighted_score_errors": (
            "TC_HTL_BE_B_09",
            "Save hotel with fallback weighted score when score calculation raises exception",
        ),
        "test_TC_HTL_BE_B_10_get_thumbnail_returns_first_image": (
            "TC_HTL_BE_B_10",
            "Return first image as thumbnail when hotel has images",
        ),
        "test_TC_HTL_BE_B_11_get_thumbnail_returns_none_without_images": (
            "TC_HTL_BE_B_11",
            "Return None as thumbnail when hotel has no images",
        ),
        "test_TC_HTL_BE_B_12_get_owner_returns_nested_payload_when_owner_exists": (
            "TC_HTL_BE_B_12",
            "Return serialized owner data when hotel owner exists",
        ),
        "test_TC_HTL_BE_B_13_get_owner_returns_none_without_owner": (
            "TC_HTL_BE_B_13",
            "Return None when hotel owner is missing",
        ),
        "test_TC_HTL_BE_B_14_upsert_rejects_missing_hotel_id": (
            "TC_HTL_BE_B_14",
            "Reject interaction upsert when hotel_id is missing",
        ),
        "test_TC_HTL_BE_B_15_upsert_updates_interaction_and_hotel_totals": (
            "TC_HTL_BE_B_15",
            "Create or update interaction and refresh hotel aggregate counters correctly",
        ),
    }
    TEST_CASE_ORDER = [
        "TC_HTL_BE_B_01",
        "TC_HTL_BE_B_02",
        "TC_HTL_BE_B_03",
        "TC_HTL_BE_B_04",
        "TC_HTL_BE_B_05",
        "TC_HTL_BE_B_06",
        "TC_HTL_BE_B_07",
        "TC_HTL_BE_B_08",
        "TC_HTL_BE_B_09",
        "TC_HTL_BE_B_10",
        "TC_HTL_BE_B_11",
        "TC_HTL_BE_B_12",
        "TC_HTL_BE_B_13",
        "TC_HTL_BE_B_14",
        "TC_HTL_BE_B_15",
    ]
    _status_by_tc = {}

    def setUp(self):
        self.api_client = APIClient()
        self.factory = APIRequestFactory()
        self.country = Country.objects.create(name="Vietnam")
        self.city = City.objects.create(name="Da Nang", country=self.country)
        self.owner = CustomUser.objects.create_user(
            username="owner_user",
            password="password123",
            email="owner@example.com",
            role="owner",
        )
        self.customer = CustomUser.objects.create_user(
            username="customer_user",
            password="password123",
            email="customer@example.com",
            role="customer",
        )
        self.hotel = Hotel.objects.create(
            city=self.city,
            owner=self.owner,
            name="Sunrise Hotel",
            description="Hotel used for unit tests.",
        )

    def _create_room(
        self,
        *,
        room_type,
        price_per_night,
        available_rooms=1,
        total_rooms=1,
        start_date=None,
        end_date=None,
    ):
        return Room.objects.create(
            hotel=self.hotel,
            room_type=room_type,
            price_per_night=price_per_night,
            adults_capacity=2,
            children_capacity=1,
            total_rooms=total_rooms,
            available_rooms=available_rooms,
            stay_type="overnight",
            start_date=start_date,
            end_date=end_date,
        )

    def _is_current_test_failed(self):
        outcome = getattr(self, "_outcome", None)
        if outcome is None:  # pragma: no cover
            return False
        return not bool(getattr(outcome, "success", True))

    def tearDown(self):
        method_name = getattr(self, "_testMethodName", "")
        meta = self.TEST_CASE_META.get(method_name)
        if meta:  # pragma: no cover
            tc_id, description = meta
            status_label = "Failed" if self._is_current_test_failed() else "Passed"
            self.__class__._status_by_tc[tc_id] = status_label
            print(f"[{tc_id}] {status_label} - {description}")
        super().tearDown()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        print("\n===== HOTEL UNIT TEST STATUS SUMMARY =====")
        print("TC ID           | Status   | Description")
        print("----------------+----------+-----------------------------------------------")

        description_by_tc = {
            tc_id: desc for tc_id, desc in (meta for meta in cls.TEST_CASE_META.values())
        }
        for tc_id in cls.TEST_CASE_ORDER:
            status_label = cls._status_by_tc.get(tc_id, "Untested")
            description = description_by_tc.get(tc_id, "")
            print(f"{tc_id:<15} | {status_label:<8} | {description}")

    # Test Case ID: TC_HTL_BE_B_01
    def test_TC_HTL_BE_B_01_hotel_str_returns_name(self):
        self.assertEqual(str(self.hotel), "Sunrise Hotel")

    # Test Case ID: TC_HTL_BE_B_02
    def test_TC_HTL_BE_B_02_update_min_price_uses_available_rooms_only(self):
        self._create_room(room_type="Standard", price_per_night=100, available_rooms=2)
        self._create_room(room_type="Deluxe", price_per_night=150, available_rooms=1)
        self._create_room(room_type="Sold Out", price_per_night=80, available_rooms=0)

        self.hotel.update_min_price()
        self.hotel.refresh_from_db()

        self.assertEqual(self.hotel.min_price, 125)

    # Test Case ID: TC_HTL_BE_B_03
    def test_TC_HTL_BE_B_03_update_min_price_defaults_to_zero_without_available_room(self):
        self._create_room(room_type="Sold Out A", price_per_night=100, available_rooms=0)
        self._create_room(room_type="Sold Out B", price_per_night=150, available_rooms=0)

        self.hotel.update_min_price()
        self.hotel.refresh_from_db()

        self.assertEqual(self.hotel.min_price, 0)

    # Test Case ID: TC_HTL_BE_B_04
    def test_TC_HTL_BE_B_04_sentiment_score_positive_case(self):
        self.hotel.total_positive = 8
        self.hotel.total_negative = 2
        self.hotel.total_neutral = 0

        self.assertAlmostEqual(self.hotel.sentiment_score, 6 / 11)

    # Test Case ID: TC_HTL_BE_B_05
    def test_TC_HTL_BE_B_05_sentiment_score_zero_total(self):
        self.hotel.total_positive = 0
        self.hotel.total_negative = 0
        self.hotel.total_neutral = 0

        self.assertEqual(self.hotel.sentiment_score, 0)

    # Test Case ID: TC_HTL_BE_B_06
    def test_TC_HTL_BE_B_06_click_score_uses_log_formula(self):
        self.hotel.total_click = 99

        self.assertAlmostEqual(self.hotel.click_score, math.log(100))

    # Test Case ID: TC_HTL_BE_B_07
    def test_TC_HTL_BE_B_07_calc_total_weighted_score_combines_metrics(self):
        self.hotel.avg_star = 4.5
        self.hotel.total_click = 9
        self.hotel.total_positive = 3
        self.hotel.total_negative = 1
        self.hotel.total_neutral = 0

        expected = (
            0.6 * self.hotel.avg_star
            + 0.3 * math.log(10)
            + 0.1 * ((3 - 1) / (4 + 1))
        )

        self.assertAlmostEqual(self.hotel.calc_total_weighted_score, expected)

    # Test Case ID: TC_HTL_BE_B_08
    def test_TC_HTL_BE_B_08_update_total_weighted_score_persists_value(self):
        self.hotel.avg_star = 4.5
        self.hotel.total_click = 9
        self.hotel.total_positive = 3
        self.hotel.total_negative = 1
        self.hotel.total_neutral = 0
        self.hotel.save()

        self.hotel.update_total_weighted_score()
        self.hotel.refresh_from_db()

        self.assertAlmostEqual(
            self.hotel.total_weighted_score,
            self.hotel.calc_total_weighted_score,
        )

    # Test Case ID: TC_HTL_BE_B_09
    def test_TC_HTL_BE_B_09_save_falls_back_to_zero_when_weighted_score_errors(self):
        with patch.object(
            Hotel,
            "calc_total_weighted_score",
            new_callable=PropertyMock,
        ) as mocked_weighted_score:
            mocked_weighted_score.side_effect = RuntimeError("calculation failed")
            hotel = Hotel.objects.create(
                city=self.city,
                owner=self.owner,
                name="Fallback Hotel",
            )

        self.assertEqual(hotel.total_weighted_score, 0.0)
        hotel.refresh_from_db()
        self.assertEqual(hotel.total_weighted_score, 0.0)

    # Test Case ID: TC_HTL_BE_B_10
    def test_TC_HTL_BE_B_10_get_thumbnail_returns_first_image(self):
        HotelImage.objects.create(hotel=self.hotel, image="/media/hotel_images/a.jpg")
        HotelImage.objects.create(hotel=self.hotel, image="/media/hotel_images/b.jpg")
        serializer = HotelSimpleSerializer()

        thumbnail = serializer.get_thumbnail(self.hotel)

        self.assertEqual(thumbnail, "/media/hotel_images/a.jpg")

    # Test Case ID: TC_HTL_BE_B_11
    def test_TC_HTL_BE_B_11_get_thumbnail_returns_none_without_images(self):
        serializer = HotelSimpleSerializer()

        thumbnail = serializer.get_thumbnail(self.hotel)

        self.assertIsNone(thumbnail)

    # Test Case ID: TC_HTL_BE_B_12
    def test_TC_HTL_BE_B_12_get_owner_returns_nested_payload_when_owner_exists(self):
        serializer = HotelSerializer()
        expected_payload = {"id": self.owner.id, "username": self.owner.username}

        with patch("accounts.serializers.UserSerializer") as mock_user_serializer:
            mock_user_serializer.return_value.data = expected_payload
            owner_payload = serializer.get_owner(self.hotel)

        self.assertEqual(owner_payload, expected_payload)

    # Test Case ID: TC_HTL_BE_B_13
    def test_TC_HTL_BE_B_13_get_owner_returns_none_without_owner(self):
        hotel_without_owner = Hotel.objects.create(
            city=self.city,
            owner=None,
            name="Ownerless Hotel",
        )
        serializer = HotelSerializer()

        owner_payload = serializer.get_owner(hotel_without_owner)

        self.assertIsNone(owner_payload)

    # Test Case ID: TC_HTL_BE_B_14
    def test_TC_HTL_BE_B_14_upsert_rejects_missing_hotel_id(self):
        before_count = UserHotelInteraction.objects.count()
        self.api_client.force_authenticate(user=self.customer)

        response = self.api_client.post(
            "/api/hotels/user-hotel-interaction/upsert/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["message"], "Missing hotel_id")
        self.assertEqual(UserHotelInteraction.objects.count(), before_count)

    # Test Case ID: TC_HTL_BE_B_15
    def test_TC_HTL_BE_B_15_upsert_updates_interaction_and_hotel_totals(self):
        before_count = UserHotelInteraction.objects.count()
        request = self.factory.post(
            "/api/hotels/user-hotel-interaction/upsert/",
            {
                "hotel_id": self.hotel.id,
                "click_count": 5,
                "positive_count": 2,
                "negative_count": 1,
                "neutral_count": 0,
            },
            format="json",
        )
        force_authenticate(request, user=self.customer)
        view = UserHotelInteractionUpsertView.as_view()

        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["isSuccess"])
        self.assertEqual(response.data["message"], "Interaction created successfully!")
        self.assertEqual(UserHotelInteraction.objects.count(), before_count + 1)

        interaction = UserHotelInteraction.objects.get(user=self.customer, hotel=self.hotel)
        self.hotel.refresh_from_db()

        expected_weighted_score = 0.7 * ((2 - 1) / (3 + 1)) + 0.3 * math.log(6)
        expected_total_weighted_score = (
            0.6 * self.hotel.avg_star
            + 0.3 * math.log(1 + self.hotel.total_click)
            + 0.1 * ((self.hotel.total_positive - self.hotel.total_negative) / (3 + 1))
        )

        self.assertEqual(interaction.click_count, 5)
        self.assertEqual(interaction.positive_count, 2)
        self.assertEqual(interaction.negative_count, 1)
        self.assertEqual(interaction.neutral_count, 0)
        self.assertAlmostEqual(interaction.weighted_score, expected_weighted_score)

        self.assertEqual(self.hotel.total_click, 5)
        self.assertEqual(self.hotel.total_positive, 2)
        self.assertEqual(self.hotel.total_negative, 1)
        self.assertEqual(self.hotel.total_neutral, 0)
        self.assertAlmostEqual(
            self.hotel.total_weighted_score,
            expected_total_weighted_score,
        )
