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
    def setUp(self):
        self.client = APIClient()
        self.User = get_user_model()
        self.user = self.User.objects.create_user(
            username="booking-user",
            email="booking@example.com",
            password="secret123",
            first_name="Book",
            last_name="Tester",
            phone_number="0900000000",
            gender="male",
            role="customer",
        )
        self.owner = self.User.objects.create_user(
            username="hotel-owner",
            email="owner@example.com",
            password="secret123",
            first_name="Owner",
            last_name="Hotel",
            phone_number="0911111111",
            gender="female",
            role="owner",
        )
        self.client.force_authenticate(user=self.user)

        self.country = Country.objects.create(name="Vietnam")
        self.city = City.objects.create(name="Ho Chi Minh City", country=self.country)
        self.hotel = Hotel.objects.create(
            city=self.city,
            owner=self.owner,
            name="Agoda Test Hotel",
        )
        self.room = Room.objects.create(
            hotel=self.hotel,
            room_type="Deluxe",
            price_per_night=100.0,
            adults_capacity=2,
            children_capacity=1,
            total_rooms=5,
            available_rooms=5,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=30),
        )
        self.booking_url = "/api/bookings/"

    def _build_hotel_booking_payload(self):
        check_in = timezone.now() + timedelta(days=2)
        check_out = check_in + timedelta(days=2)
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
                "room": self.room.id,
                "check_in": check_in.isoformat(),
                "check_out": check_out.isoformat(),
                "num_guests": 2,
                "room_count": 1,
            },
        }

    def _create_hotel_booking(self):
        response = self.client.post(self.booking_url, self._build_hotel_booking_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return Booking.objects.get(pk=response.data["booking_id"])

    def test_booking_model_generates_booking_code(self):
        booking = Booking.objects.create(service_type=ServiceType.HOTEL, user=self.user)

        self.assertTrue(booking.booking_code.startswith("AGD"))
        self.assertEqual(len(booking.booking_code), 9)

    def test_booking_serializer_assigns_authenticated_user_and_creates_guest_info(self):
        serializer = BookingSerializer(
            data={
                "service_type": ServiceType.HOTEL,
                "guest_info": {
                    "full_name": "Guest Test",
                    "email": "guest@test.com",
                    "phone": "0901234567",
                },
            },
            context={"request": type("Req", (), {"user": self.user})()},
        )

        self.assertTrue(serializer.is_valid(), serializer.errors)
        booking = serializer.save()

        self.assertEqual(booking.user, self.user)
        self.assertTrue(GuestInfo.objects.filter(booking=booking, email="guest@test.com").exists())

    def test_room_booking_detail_serializer_rejects_invalid_date_range(self):
        serializer = RoomBookingDetailCreateSerializer(
            data={
                "room": self.room.id,
                "check_in": (timezone.now() + timedelta(days=3)).isoformat(),
                "check_out": (timezone.now() + timedelta(days=2)).isoformat(),
                "num_guests": 2,
                "room_count": 1,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("Check-out must be after check-in", str(serializer.errors))

    def test_room_booking_detail_serializer_rejects_guest_count_over_capacity(self):
        serializer = RoomBookingDetailCreateSerializer(
            data={
                "room": self.room.id,
                "check_in": (timezone.now() + timedelta(days=2)).isoformat(),
                "check_out": (timezone.now() + timedelta(days=3)).isoformat(),
                "num_guests": 5,
                "room_count": 1,
            }
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("exceeds room capacity", str(serializer.errors))

    def test_create_hotel_booking_updates_room_inventory_and_booking_totals(self):
        response = self.client.post(self.booking_url, self._build_hotel_booking_payload(), format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        booking = Booking.objects.get(pk=response.data["booking_id"])
        detail = RoomBookingDetail.objects.get(booking=booking)
        self.room.refresh_from_db()

        self.assertEqual(booking.service_ref_ids, [detail.id])
        self.assertEqual(booking.total_price, 200.0)
        self.assertEqual(booking.final_price, 200.0)
        self.assertEqual(self.room.available_rooms, 4)

    def test_calculate_refund_amount_without_policy_returns_final_price(self):
        booking = Booking.objects.create(
            service_type=ServiceType.HOTEL,
            user=self.user,
            final_price=350.0,
        )
        view = BookingViewSet()

        refund_amount = view.calculate_refund_amount(booking)

        self.assertEqual(refund_amount, 350.0)

    def test_calculate_refund_amount_partial_refund_percentage_returns_expected_value(self):
        booking = Booking.objects.create(
            service_type=ServiceType.HOTEL,
            user=self.user,
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
        view = BookingViewSet()

        with patch.object(view, "get_start_time_for_booking", return_value=timezone.now() + timedelta(hours=6)):
            refund_amount = view.calculate_refund_amount(booking)

        self.assertEqual(refund_amount, 100.0)

    @patch("bookings.views.BookingViewSet.process_payment_refund", return_value={"id": "refund_1"})
    def test_cancel_booking_paid_hotel_booking_marks_refunded_and_updates_payments(self, _mock_refund):
        booking = self._create_hotel_booking()
        booking.status = BookingStatus.CONFIRMED
        booking.payment_status = PaymentStatus.PAID
        booking.final_price = 200.0
        booking.total_price = 200.0
        booking.save(update_fields=["status", "payment_status", "final_price", "total_price"])
        payment = Payment.objects.create(
            booking=booking,
            method=PaymentMethod.ONLINE,
            amount=200.0,
            status=PaymentStatus.PAID,
            transaction_id="pi_test",
        )

        response = self.client.post(f"/api/bookings/{booking.id}/cancel/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        booking.refresh_from_db()
        payment.refresh_from_db()
        self.assertEqual(booking.status, BookingStatus.CANCELLED)
        self.assertEqual(booking.payment_status, PaymentStatus.REFUNDED)
        self.assertEqual(booking.refund_amount, 200.0)
        self.assertEqual(int(payment.status), PaymentStatus.REFUNDED)

    def test_cancel_booking_rejects_completed_booking(self):
        booking = Booking.objects.create(
            service_type=ServiceType.HOTEL,
            user=self.user,
            status=BookingStatus.COMPLETED,
            payment_status=PaymentStatus.PAID,
            final_price=100.0,
        )

        response = self.client.post(f"/api/bookings/{booking.id}/cancel/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Kh", response.data["message"])

    def test_rebook_cancelled_hotel_booking_creates_new_booking_and_marks_old_rebooked(self):
        original_booking = self._create_hotel_booking()
        original_booking.status = BookingStatus.CANCELLED
        original_booking.payment_status = PaymentStatus.CANCELLED
        original_booking.save(update_fields=["status", "payment_status"])
        Payment.objects.create(
            booking=original_booking,
            method=PaymentMethod.CASH,
            amount=200.0,
            status=PaymentStatus.CANCELLED,
        )

        response = self.client.post(
            f"/api/bookings/{original_booking.id}/rebook/",
            {"num_rooms": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        original_booking.refresh_from_db()
        new_booking = Booking.objects.get(pk=response.data["new_booking_id"])

        self.assertEqual(original_booking.status, BookingStatus.REBOOKED)
        self.assertEqual(original_booking.payment_status, PaymentStatus.REBOOKED)
        self.assertEqual(new_booking.status, BookingStatus.PENDING)
        self.assertEqual(new_booking.payment_status, PaymentStatus.PENDING)
        self.assertTrue(RoomBookingDetail.objects.filter(booking=new_booking).exists())
