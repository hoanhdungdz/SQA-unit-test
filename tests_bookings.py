from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from bookings.constants.booking_status import BookingStatus
from bookings.constants.service_type import ServiceType
from bookings.models import Booking, GuestInfo, RefundPolicy
from bookings.serializers import BookingSerializer
from bookings.views import BookingViewSet
from cities.models import City
from countries.models import Country
from hotels.models import Hotel
from payments.constants.payment_method import PaymentMethod
from payments.constants.payment_status import PaymentStatus
from payments.models import Payment
from rooms.models import Room, RoomBookingDetail
from rooms.serializers import RoomBookingDetailCreateSerializer


@override_settings(ROOT_URLCONF="agoda_be.test_urls")
class BookingModuleUnitTests(APITestCase):
    """
    Unit tests for the Booking Module.
    Rollback: Inheriting from APITestCase ensures that every test is wrapped in a DB transaction. 
    At the end of each test method, Django automatically rolls back the transaction, 
    restoring the database to its pre-test state.
    """

    def setUp(self):
        # Arrange: Initialize standard API Client and Models
        self.api_client = APIClient()
        self.user_model = get_user_model()
        
        # Arrange: Create test users
        self.customer_user = self.user_model.objects.create_user(
            username="booking-user",
            email="booking@example.com",
            password="secret123",
            first_name="Book",
            last_name="Tester",
            phone_number="0900000000",
            gender="male",
            role="customer",
        )
        self.hotel_owner_user = self.user_model.objects.create_user(
            username="hotel-owner",
            email="owner@example.com",
            password="secret123",
            first_name="Owner",
            last_name="Hotel",
            phone_number="0911111111",
            gender="female",
            role="owner",
        )
        
        # Authenticate requests using the customer user
        self.api_client.force_authenticate(user=self.customer_user)

        # Arrange: Setup geographical and hotel dependencies
        self.vietnam_country = Country.objects.create(name="Vietnam")
        self.hcm_city = City.objects.create(name="Ho Chi Minh City", country=self.vietnam_country)
        self.test_hotel = Hotel.objects.create(
            city=self.hcm_city,
            owner=self.hotel_owner_user,
            name="Agoda Test Hotel",
        )
        self.deluxe_room = Room.objects.create(
            hotel=self.test_hotel,
            room_type="Deluxe",
            price_per_night=100.0,
            adults_capacity=2,
            children_capacity=1,
            total_rooms=5,
            available_rooms=5,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
        )
        self.booking_api_endpoint = "/api/bookings/"

    def _generate_hotel_booking_payload(self):
        """Helper method to generate a standard hotel booking payload for POST requests."""
        planned_check_in_date = timezone.now() + timedelta(days=2)
        planned_check_out_date = planned_check_in_date + timedelta(days=2)
        return {
            "service_type": ServiceType.HOTEL,
            "guest_info": {
                "full_name": "Nguyen Van A",
                "email": "guest@example.com",
                "phone": "0988888888",
                "country": "Vietnam",
                "special_request": "High floor",
            },
            "room_details": {
                "room": self.deluxe_room.id,
                "check_in": planned_check_in_date.isoformat(),
                "check_out": planned_check_out_date.isoformat(),
                "num_guests": 2,
                "room_count": 1,
            },
        }

    def _execute_hotel_booking_creation(self):
        """Helper method to trigger the booking creation API and return the created DB instance."""
        payload = self._generate_hotel_booking_payload()
        response = self.api_client.post(self.booking_api_endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return Booking.objects.get(pk=response.data["booking_id"])

    # Test Case ID: TC_BKG_BE_01
    def test_booking_model_generates_correct_booking_code(self):
        """
        CheckDB: Verify that upon creation, a Booking instance automatically generates a correct 9-char code starting with 'AGD'.
        """
        # Act
        new_booking = Booking.objects.create(service_type=ServiceType.HOTEL, user=self.customer_user)

        # Assert & CheckDB
        self.assertTrue(new_booking.booking_code.startswith("AGD"))
        self.assertEqual(len(new_booking.booking_code), 9)

    # Test Case ID: TC_BKG_BE_02
    def test_booking_serializer_assigns_authenticated_user_and_creates_guest_info(self):
        """
        CheckDB: Verify the serializer successfully maps the authenticated user and creates the related GuestInfo record.
        """
        # Arrange
        mock_request = type("MockRequest", (), {"user": self.customer_user})()
        booking_data = {
            "service_type": ServiceType.HOTEL,
            "guest_info": {
                "full_name": "Guest Test",
                "email": "guest@test.com",
                "phone": "0901234567",
            },
        }
        booking_serializer = BookingSerializer(data=booking_data, context={"request": mock_request})

        # Act
        self.assertTrue(booking_serializer.is_valid(), booking_serializer.errors)
        created_booking = booking_serializer.save()

        # Assert & CheckDB
        self.assertEqual(created_booking.user, self.customer_user)
        is_guest_info_created = GuestInfo.objects.filter(booking=created_booking, email="guest@test.com").exists()
        self.assertTrue(is_guest_info_created, "GuestInfo record should exist in the database.")

    # Test Case ID: TC_BKG_BE_03
    def test_room_booking_detail_serializer_rejects_invalid_date_range(self):
        """
        CheckDB: Ensure no DB records are created when the check-out date precedes check-in.
        """
        # Arrange: Setup reversed check-out and check-in dates
        invalid_dates_payload = {
            "room": self.deluxe_room.id,
            "check_in": (timezone.now() + timedelta(days=3)).isoformat(),
            "check_out": (timezone.now() + timedelta(days=2)).isoformat(),
            "num_guests": 2,
            "room_count": 1,
        }
        serializer = RoomBookingDetailCreateSerializer(data=invalid_dates_payload)

        # Act & Assert
        self.assertFalse(serializer.is_valid())
        self.assertIn("Check-out must be after check-in", str(serializer.errors))

    # Test Case ID: TC_BKG_BE_04
    def test_room_booking_detail_serializer_rejects_guest_count_over_capacity(self):
        """
        CheckDB: Ensure no DB records are created when the requested guests exceed the room capacity.
        """
        # Arrange: Setup guests exceeding self.deluxe_room capacity
        over_capacity_payload = {
            "room": self.deluxe_room.id,
            "check_in": (timezone.now() + timedelta(days=2)).isoformat(),
            "check_out": (timezone.now() + timedelta(days=3)).isoformat(),
            "num_guests": 5, # Exceeds capacity of 2 adults + 1 child
            "room_count": 1,
        }
        serializer = RoomBookingDetailCreateSerializer(data=over_capacity_payload)

        # Act & Assert
        self.assertFalse(serializer.is_valid())
        self.assertIn("exceeds room capacity", str(serializer.errors))

    # Test Case ID: TC_BKG_BE_05
    def test_create_hotel_booking_updates_room_inventory_and_booking_totals(self):
        """
        CheckDB: Verify that successful booking correctly deducts available room inventory and calculates prices in DB.
        """
        # Arrange
        booking_payload = self._generate_hotel_booking_payload()

        # Act
        api_response = self.api_client.post(self.booking_api_endpoint, booking_payload, format="json")

        # Assert API Response
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        
        # CheckDB: Query DB to verify updates
        created_booking = Booking.objects.get(pk=api_response.data["booking_id"])
        booking_detail = RoomBookingDetail.objects.get(booking=created_booking)
        self.deluxe_room.refresh_from_db() # Refresh to get updated inventory

        # Assert DB States
        self.assertEqual(created_booking.service_ref_ids, [booking_detail.id])
        self.assertEqual(created_booking.total_price, 200.0) # 2 nights * $100
        self.assertEqual(created_booking.final_price, 200.0)
        self.assertEqual(self.deluxe_room.available_rooms, 4) # Decreased from 5

    # Test Case ID: TC_BKG_BE_06
    def test_calculate_refund_amount_without_policy_returns_final_price(self):
        """
        Verify that if no active refund policy exists, a cancellation defaults to refunding the full final price.
        """
        # Arrange
        test_booking = Booking.objects.create(
            service_type=ServiceType.HOTEL,
            user=self.customer_user,
            final_price=350.0,
        )
        booking_viewset = BookingViewSet()

        # Act
        calculated_refund_amount = booking_viewset.calculate_refund_amount(test_booking)

        # Assert
        self.assertEqual(calculated_refund_amount, 350.0)

    # Test Case ID: TC_BKG_BE_07
    def test_calculate_refund_amount_partial_refund_percentage_returns_expected_value(self):
        """
        CheckDB: Verify that when a refund policy is configured in the DB, the refund calculation respects the percentage.
        """
        # Arrange: Setup Booking and Policy
        test_booking = Booking.objects.create(
            service_type=ServiceType.HOTEL,
            user=self.customer_user,
            final_price=400.0,
        )
        RefundPolicy.objects.create(
            service_type=ServiceType.HOTEL,
            name="Partial 25",
            policy_type=RefundPolicy.PolicyType.PARTIAL_REFUND,
            refund_percentage=25,
            hours_before_start=1,
            is_active=True,
        )
        booking_viewset = BookingViewSet()

        # Act
        with patch.object(booking_viewset, "get_start_time_for_booking", return_value=timezone.now() + timedelta(hours=6)):
            calculated_refund_amount = booking_viewset.calculate_refund_amount(test_booking)

        # Assert
        self.assertEqual(calculated_refund_amount, 100.0) # 25% of 400.0

    # Test Case ID: TC_BKG_BE_08
    @patch("bookings.views.BookingViewSet.process_payment_refund", return_value={"id": "refund_1"})
    def test_cancel_booking_paid_hotel_booking_marks_refunded_and_updates_payments(self, mock_payment_refund):
        """
        CheckDB: Verify that cancelling a PAID booking correctly changes statuses to CANCELLED and REFUNDED in DB.
        """
        # Arrange: Setup a confirmed, paid booking
        active_booking = self._execute_hotel_booking_creation()
        active_booking.status = BookingStatus.CONFIRMED
        active_booking.payment_status = PaymentStatus.PAID
        active_booking.final_price = 200.0
        active_booking.total_price = 200.0
        active_booking.save(update_fields=["status", "payment_status", "final_price", "total_price"])
        
        linked_payment = Payment.objects.create(
            booking=active_booking,
            method=PaymentMethod.ONLINE,
            amount=200.0,
            status=PaymentStatus.PAID,
            transaction_id="pi_test",
        )
        cancel_endpoint = f"{self.booking_api_endpoint}{active_booking.id}/cancel/"

        # Act
        api_response = self.api_client.post(cancel_endpoint)

        # Assert API and CheckDB
        self.assertEqual(api_response.status_code, status.HTTP_200_OK)
        active_booking.refresh_from_db()
        linked_payment.refresh_from_db()
        
        self.assertEqual(active_booking.status, BookingStatus.CANCELLED)
        self.assertEqual(active_booking.payment_status, PaymentStatus.REFUNDED)
        self.assertEqual(active_booking.refund_amount, 200.0)
        self.assertEqual(int(linked_payment.status), PaymentStatus.REFUNDED)

    # Test Case ID: TC_BKG_BE_09
    def test_cancel_booking_rejects_completed_booking(self):
        """
        CheckDB: Verify that the DB state remains unchanged (COMPLETED) when trying to cancel an already completed booking.
        """
        # Arrange: Setup completed booking
        completed_booking = Booking.objects.create(
            service_type=ServiceType.HOTEL,
            user=self.customer_user,
            status=BookingStatus.COMPLETED,
            payment_status=PaymentStatus.PAID,
            final_price=100.0,
        )
        cancel_endpoint = f"{self.booking_api_endpoint}{completed_booking.id}/cancel/"

        # Act
        api_response = self.api_client.post(cancel_endpoint)

        # Assert
        self.assertEqual(api_response.status_code, status.HTTP_400_BAD_REQUEST)
        # Ensure error message reflects rule blocking cancellation
        self.assertIn("Kh", api_response.data["message"]) 

    # Test Case ID: TC_BKG_BE_10
    def test_rebook_cancelled_hotel_booking_creates_new_booking_and_marks_old_rebooked(self):
        """
        CheckDB: Ensure rebook action creates a new DB record and correctly updates statuses on the original booking.
        """
        # Arrange: Setup a cancelled booking
        original_cancelled_booking = self._execute_hotel_booking_creation()
        original_cancelled_booking.status = BookingStatus.CANCELLED
        original_cancelled_booking.payment_status = PaymentStatus.CANCELLED
        original_cancelled_booking.save(update_fields=["status", "payment_status"])
        
        Payment.objects.create(
            booking=original_cancelled_booking,
            method=PaymentMethod.CASH,
            amount=200.0,
            status=PaymentStatus.CANCELLED,
        )
        rebook_endpoint = f"{self.booking_api_endpoint}{original_cancelled_booking.id}/rebook/"

        # Act
        api_response = self.api_client.post(
            rebook_endpoint,
            {"num_rooms": 1},
            format="json",
        )

        # Assert & CheckDB
        self.assertEqual(api_response.status_code, status.HTTP_201_CREATED)
        
        # Verify original booking state
        original_cancelled_booking.refresh_from_db()
        self.assertEqual(original_cancelled_booking.status, BookingStatus.REBOOKED)
        self.assertEqual(original_cancelled_booking.payment_status, PaymentStatus.REBOOKED)

        # Verify new booking state is correctly populated in DB
        newly_created_booking = Booking.objects.get(pk=api_response.data["new_booking_id"])
        self.assertEqual(newly_created_booking.status, BookingStatus.PENDING)
        self.assertEqual(newly_created_booking.payment_status, PaymentStatus.PENDING)
        
        is_room_detail_created = RoomBookingDetail.objects.filter(booking=newly_created_booking).exists()
        self.assertTrue(is_room_detail_created, "A new RoomBookingDetail should be created for the rebook.")
