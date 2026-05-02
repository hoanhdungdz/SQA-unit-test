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
    """
    Hotel unit tests mapped to TC_HTL_BE_B_01 -> TC_HTL_BE_B_15.
    Rollback: Django's TestCase wraps tests in transactions and rolls them back after completion.
    The database state is always pristine between test runs.
    """

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
        "TC_HTL_BE_B_01", "TC_HTL_BE_B_02", "TC_HTL_BE_B_03", "TC_HTL_BE_B_04", 
        "TC_HTL_BE_B_05", "TC_HTL_BE_B_06", "TC_HTL_BE_B_07", "TC_HTL_BE_B_08", 
        "TC_HTL_BE_B_09", "TC_HTL_BE_B_10", "TC_HTL_BE_B_11", "TC_HTL_BE_B_12", 
        "TC_HTL_BE_B_13", "TC_HTL_BE_B_14", "TC_HTL_BE_B_15",
    ]
    
    _status_by_tc = {}

    def setUp(self):
        # Arrange: Basic Test Tools
        self.api_client = APIClient()
        self.api_request_factory = APIRequestFactory()
        
        # Arrange: Setup geography
        self.vietnam_country = Country.objects.create(name="Vietnam")
        self.danang_city = City.objects.create(name="Da Nang", country=self.vietnam_country)
        
        # Arrange: Setup users
        self.owner_user = CustomUser.objects.create_user(
            username="owner_user",
            password="password123",
            email="owner@example.com",
            role="owner",
        )
        self.customer_user = CustomUser.objects.create_user(
            username="customer_user",
            password="password123",
            email="customer@example.com",
            role="customer",
        )
        
        # Arrange: Setup core hotel entity
        self.test_hotel = Hotel.objects.create(
            city=self.danang_city,
            owner=self.owner_user,
            name="Sunrise Hotel",
            description="Hotel used for unit tests.",
        )

    def _create_test_room(
        self,
        *,
        room_type,
        price_per_night,
        available_rooms=1,
        total_rooms=1,
        start_date=None,
        end_date=None,
    ):
        """Helper method to construct Room entities attached to self.test_hotel."""
        return Room.objects.create(
            hotel=self.test_hotel,
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
        # Report handling hook executed post-test.
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
        print("TC ID            | Status   | Description")
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
        """Verify the magical __str__ method of Hotel model outputs the hotel name."""
        self.assertEqual(str(self.test_hotel), "Sunrise Hotel")

    # Test Case ID: TC_HTL_BE_B_02
    def test_TC_HTL_BE_B_02_update_min_price_uses_available_rooms_only(self):
        """
        CheckDB: Verify that hotel.min_price correctly updates based on the lowest price 
        among rooms that actually have available inventory.
        """
        # Arrange
        self._create_test_room(room_type="Standard", price_per_night=100, available_rooms=2)
        self._create_test_room(room_type="Deluxe", price_per_night=150, available_rooms=1)
        self._create_test_room(room_type="Sold Out", price_per_night=80, available_rooms=0)

        # Act
        self.test_hotel.update_min_price()
        self.test_hotel.refresh_from_db() # Fetch updated attributes

        # Assert & CheckDB
        # Expected is 100, not 80, because the 80 priced room has 0 available rooms
        self.assertEqual(self.test_hotel.min_price, 100) 

    # Test Case ID: TC_HTL_BE_B_03
    def test_TC_HTL_BE_B_03_update_min_price_defaults_to_zero_without_available_room(self):
        """
        CheckDB: Ensure that min_price evaluates to 0 if all room stock is completely exhausted.
        """
        # Arrange
        self._create_test_room(room_type="Sold Out A", price_per_night=100, available_rooms=0)
        self._create_test_room(room_type="Sold Out B", price_per_night=150, available_rooms=0)

        # Act
        self.test_hotel.update_min_price()
        self.test_hotel.refresh_from_db()

        # Assert & CheckDB
        self.assertEqual(self.test_hotel.min_price, 0)

    # Test Case ID: TC_HTL_BE_B_04
    def test_TC_HTL_BE_B_04_sentiment_score_positive_case(self):
        """Verify proper mathematical calculation of the sentiment score property."""
        # Arrange
        self.test_hotel.total_positive = 8
        self.test_hotel.total_negative = 2
        self.test_hotel.total_neutral = 0

        # Act & Assert
        expected_score = (8 - 2) / (10 + 1) # Formula implementation verification
        self.assertAlmostEqual(self.test_hotel.sentiment_score, expected_score)

    # Test Case ID: TC_HTL_BE_B_05
    def test_TC_HTL_BE_B_05_sentiment_score_zero_total(self):
        """Verify division-by-zero protection in sentiment logic."""
        # Arrange
        self.test_hotel.total_positive = 0
        self.test_hotel.total_negative = 0
        self.test_hotel.total_neutral = 0

        # Act & Assert
        self.assertEqual(self.test_hotel.sentiment_score, 0)

    # Test Case ID: TC_HTL_BE_B_06
    def test_TC_HTL_BE_B_06_click_score_uses_log_formula(self):
        """Verify click scoring applies log formula logic correctly."""
        # Arrange
        self.test_hotel.total_click = 99

        # Act & Assert
        self.assertAlmostEqual(self.test_hotel.click_score, math.log(100))

    # Test Case ID: TC_HTL_BE_B_07
    def test_TC_HTL_BE_B_07_calc_total_weighted_score_combines_metrics(self):
        """Verify the global weighted score algorithm accurately integrates star ratings, clicks, and sentiments."""
        # Arrange
        self.test_hotel.avg_star = 4.5
        self.test_hotel.total_click = 9
        self.test_hotel.total_positive = 3
        self.test_hotel.total_negative = 1
        self.test_hotel.total_neutral = 0

        # Expected formula breakdown
        expected_combined_score = (
            0.6 * self.test_hotel.avg_star
            + 0.3 * math.log(10) # 9 + 1
            + 0.1 * ((3 - 1) / (4 + 1))
        )

        # Act & Assert
        self.assertAlmostEqual(self.test_hotel.calc_total_weighted_score, expected_combined_score)

    # Test Case ID: TC_HTL_BE_B_08
    def test_TC_HTL_BE_B_08_update_total_weighted_score_persists_value(self):
        """
        CheckDB: Verify the calculated aggregate score actually persists to the respective DB column upon update.
        """
        # Arrange
        self.test_hotel.avg_star = 4.5
        self.test_hotel.total_click = 9
        self.test_hotel.total_positive = 3
        self.test_hotel.total_negative = 1
        self.test_hotel.total_neutral = 0
        self.test_hotel.save()

        # Act
        self.test_hotel.update_total_weighted_score()
        self.test_hotel.refresh_from_db()

        # Assert & CheckDB
        self.assertAlmostEqual(
            self.test_hotel.total_weighted_score,
            self.test_hotel.calc_total_weighted_score,
        )

    # Test Case ID: TC_HTL_BE_B_09
    def test_TC_HTL_BE_B_09_save_falls_back_to_zero_when_weighted_score_errors(self):
        """
        CheckDB: Prevent application crash on calculation errors and fallback score gracefully to 0.0 in DB.
        """
        # Arrange: Mock the property to explicitly raise an error
        with patch.object(
            Hotel,
            "calc_total_weighted_score",
            new_callable=PropertyMock,
        ) as mock_calc_weighted_score_property:
            mock_calc_weighted_score_property.side_effect = RuntimeError("calculation failed")
            
            # Act
            fallback_hotel = Hotel.objects.create(
                city=self.danang_city,
                owner=self.owner_user,
                name="Fallback Hotel",
            )

        # Assert & CheckDB
        self.assertEqual(fallback_hotel.total_weighted_score, 0.0)
        fallback_hotel.refresh_from_db()
        self.assertEqual(fallback_hotel.total_weighted_score, 0.0)

    # Test Case ID: TC_HTL_BE_B_10
    def test_TC_HTL_BE_B_10_get_thumbnail_returns_first_image(self):
        """Verify serializer accurately picks the first available image as the UI thumbnail."""
        # Arrange
        HotelImage.objects.create(hotel=self.test_hotel, image="/media/hotel_images/a.jpg")
        HotelImage.objects.create(hotel=self.test_hotel, image="/media/hotel_images/b.jpg")
        hotel_simple_serializer = HotelSimpleSerializer()

        # Act
        hotel_thumbnail = hotel_simple_serializer.get_thumbnail(self.test_hotel)

        # Assert
        self.assertEqual(hotel_thumbnail, "/media/hotel_images/a.jpg")

    # Test Case ID: TC_HTL_BE_B_11
    def test_TC_HTL_BE_B_11_get_thumbnail_returns_none_without_images(self):
        """Verify handling missing thumbnail images returns None cleanly."""
        # Arrange
        hotel_simple_serializer = HotelSimpleSerializer()

        # Act
        hotel_thumbnail = hotel_simple_serializer.get_thumbnail(self.test_hotel)

        # Assert
        self.assertIsNone(hotel_thumbnail)

    # Test Case ID: TC_HTL_BE_B_12
    def test_TC_HTL_BE_B_12_get_owner_returns_nested_payload_when_owner_exists(self):
        """Verify serializer successfully encapsulates owner dictionary payload data."""
        # Arrange
        hotel_serializer = HotelSerializer()
        expected_owner_payload = {"id": self.owner_user.id, "username": self.owner_user.username}

        # Act: Mock the nested serializer to isolate the test scope
        with patch("accounts.serializers.UserSerializer") as mock_user_serializer_class:
            mock_user_serializer_class.return_value.data = expected_owner_payload
            generated_owner_payload = hotel_serializer.get_owner(self.test_hotel)

        # Assert
        self.assertEqual(generated_owner_payload, expected_owner_payload)

    # Test Case ID: TC_HTL_BE_B_13
    def test_TC_HTL_BE_B_13_get_owner_returns_none_without_owner(self):
        """Verify clean fallback when the hotel entity lacks an assigned owner."""
        # Arrange
        hotel_without_owner = Hotel.objects.create(
            city=self.danang_city,
            owner=None,
            name="Ownerless Hotel",
        )
        hotel_serializer = HotelSerializer()

        # Act
        generated_owner_payload = hotel_serializer.get_owner(hotel_without_owner)

        # Assert
        self.assertIsNone(generated_owner_payload)

    # Test Case ID: TC_HTL_BE_B_14
    def test_TC_HTL_BE_B_14_upsert_rejects_missing_hotel_id(self):
        """
        CheckDB: Verify no interaction record is inserted into the DB when a payload is missing required IDs.
        """
        # Arrange
        initial_interaction_db_count = UserHotelInteraction.objects.count()
        self.api_client.force_authenticate(user=self.customer_user)

        # Act
        api_response = self.api_client.post(
            "/api/hotels/user-hotel-interaction/upsert/",
            {},
            format="json",
        )

        # Assert & CheckDB
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(api_response.data["message"], "Missing hotel_id")
        self.assertEqual(UserHotelInteraction.objects.count(), initial_interaction_db_count)

    # Test Case ID: TC_HTL_BE_B_15
    def test_TC_HTL_BE_B_15_upsert_updates_interaction_and_hotel_totals(self):
        """
        CheckDB: Upon submitting interactions (views, ratings), verify a new UserHotelInteraction db record is made 
        and the parent hotel's aggregated statistic counters are correctly refreshed.
        """
        # Arrange
        initial_interaction_db_count = UserHotelInteraction.objects.count()
        upsert_payload = {
            "hotel_id": self.test_hotel.id,
            "click_count": 5,
            "positive_count": 2,
            "negative_count": 1,
            "neutral_count": 0,
        }
        api_request = self.api_request_factory.post(
            "/api/hotels/user-hotel-interaction/upsert/",
            upsert_payload,
            format="json",
        )
        force_authenticate(api_request, user=self.customer_user)
        upsert_view_handler = UserHotelInteractionUpsertView.as_view()

        # Act
        api_response = upsert_view_handler(api_request)

        # Assert Response State
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        self.assertTrue(api_response.data["isSuccess"])
        self.assertEqual(api_response.data["message"], "Interaction created successfully!")
        
        # CheckDB: Verify exact interaction counts and score states exist correctly in database.
        self.assertEqual(UserHotelInteraction.objects.count(), initial_interaction_db_count + 1)
        created_interaction_record = UserHotelInteraction.objects.get(user=self.customer_user, hotel=self.test_hotel)
        self.test_hotel.refresh_from_db()

        # Calculate logical expectations
        expected_user_weighted_score = 0.7 * ((2 - 1) / (3 + 1)) + 0.3 * math.log(6)
        expected_hotel_total_weighted_score = (
            0.6 * self.test_hotel.avg_star
            + 0.3 * math.log(1 + self.test_hotel.total_click)
            + 0.1 * ((self.test_hotel.total_positive - self.test_hotel.total_negative) / (3 + 1))
        )

        # Final Assertions on fetched db entities
        self.assertEqual(created_interaction_record.click_count, 5)
        self.assertEqual(created_interaction_record.positive_count, 2)
        self.assertEqual(created_interaction_record.negative_count, 1)
        self.assertEqual(created_interaction_record.neutral_count, 0)
        self.assertAlmostEqual(created_interaction_record.weighted_score, expected_user_weighted_score)

        self.assertEqual(self.test_hotel.total_click, 5)
        self.assertEqual(self.test_hotel.total_positive, 2)
        self.assertEqual(self.test_hotel.total_negative, 1)
        self.assertEqual(self.test_hotel.total_neutral, 0)
        self.assertAlmostEqual(
            self.test_hotel.total_weighted_score,
            expected_hotel_total_weighted_score,
        )
