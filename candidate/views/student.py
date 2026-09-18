"""Managing the students themselves, as opposed to the test one of them is sitting.

The roster import is the same one the session screen uses, re-exposed here so the student module
has its own import without a second copy of the logic behind it.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status, filters
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from candidate.models import TestAttempt
from candidate.serializers import *
from session.models import Session, SessionStudent
from session.serializers.attempt_serializers import AttemptDetailSerializer
from session.views.student_import import GetStudentImportSampleView, ImportStudentView  # noqa: F401
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck
from aon_backend.pagination import CustomPageNumberPagination


def admin_permission(permission_name):
    return [IsAuthenticated,
            RoleOrPermissionCheck.for_permission_or_roles(permission_name, [SuperAdmin])]


def get_student(pk):
    """One student off the listing queryset, so the session counts travel with them. A deleted
    student is not found here, which is what the delete API leaves behind."""
    return student_listing_queryset().filter(pk=pk).first()


def attempts_by_session(student):
    """Each of this student's attempts, keyed by the session it belongs to.

    Read in one query and handed to the serializer through its context, so listing the sessions a
    student is booked into does not cost a query per row.
    """
    return {attempt.session_id: attempt for attempt in TestAttempt.objects.filter(student=student)}


def student_detail_data(student):
    return StudentDetailSerializer(student, context={'attempts': attempts_by_session(student)}).data


class GetStudentListingView(APIView):
    """Every student on record, with how many sessions each has been booked into and sat.

    'sessions_attempted' is the count of papers the student actually opened; sort on it to find the
    students who have never turned up.
    """

    renderer_classes = [UserRenderer]
    permission_classes = admin_permission("student_listing")
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['first_name', 'last_name', 'email', 'phone', 'application_id']
    ordering_fields = ['first_name', 'last_name', 'email', 'application_id', 'is_active',
                       'created_at', 'updated_at', 'total_sessions', 'sessions_attempted',
                       'sessions_submitted']
    def get(self, request, format=None):

        students_list = student_listing_queryset()

        name = request.query_params.get('name')
        if name:
            students_list = students_list.filter(
                Q(first_name__icontains=name) | Q(last_name__icontains=name)
            )

        email = request.query_params.get('email')
        if email:
            students_list = students_list.filter(email__icontains=email)

        application_id = request.query_params.get('application_id')
        if application_id:
            students_list = students_list.filter(application_id__icontains=application_id)

        student_status = request.query_params.get('status')
        if student_status:
            if student_status.lower() in ['true', '1', 't', 'yes']:
                students_list = students_list.filter(is_active=True)
            elif student_status.lower() in ['false', '0', 'f', 'no']:
                students_list = students_list.filter(is_active=False)
            else:
                raise ValidationError("Invalid status value. Use true or false.")

        session_id = request.query_params.get('session')
        if session_id:
            students_list = students_list.filter(assessment_sessions__session_id=session_id)

        attempted = request.query_params.get('attempted')
        if attempted:
            if attempted.lower() in ['true', '1', 't', 'yes']:
                students_list = students_list.filter(sessions_attempted__gt=0)
            elif attempted.lower() in ['false', '0', 'f', 'no']:
                students_list = students_list.filter(sessions_attempted=0)
            else:
                raise ValidationError("Invalid attempted value. Use true or false.")

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                start_datetime_aware = timezone.make_aware(start_datetime, timezone.get_current_timezone())
                students_list = students_list.filter(created_at__gte=start_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                end_datetime_aware = timezone.make_aware(end_datetime, timezone.get_current_timezone())
                students_list = students_list.filter(created_at__lte=end_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid end_date format. Use YYYY-MM-DD.")

        search_filter = filters.SearchFilter()
        students_list = search_filter.filter_queryset(request, students_list, self)

        ordering_filter = filters.OrderingFilter()
        students_list = ordering_filter.filter_queryset(request, students_list, self)

        if not students_list.ordered:
            students_list = students_list.order_by('-id')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(students_list, request, view=self)
        serializer = StudentListingSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class GetStudentDetailView(APIView):
    """One student: their details, how many sessions they have sat, and every session they are on.

    Each session carries its own 'session_id'; the result API is called with that to read the paper
    the student sat for it.
    """

    renderer_classes = [UserRenderer]
    permission_classes = admin_permission("student_detail")
    def get(self, request, pk, format=None):
        student = student_listing_queryset().prefetch_related(
            'assessment_sessions__session__assessment').filter(pk=pk).first()
        if student is None:
            return error_response(message="Student not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        return success_response(message="Success", data=student_detail_data(student), status_code=status.HTTP_200_OK)


class CreateStudentView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = admin_permission("create_student")
    def post(self, request, format=None):
        serializer = StudentCreateSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            student = serializer.save()
            return success_response(message="Student created successfully!", data=StudentListingSerializer(student).data, status_code=status.HTTP_201_CREATED)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class UpdateStudentView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = admin_permission("update_student")
    def put(self, request, pk, format=None):
        student = get_student(pk)
        if student is None:
            return error_response(message="Student not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = StudentUpdateSerializer(student, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            student = serializer.save()
            return success_response(message="Student updated successfully!", data=StudentListingSerializer(student).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class ChangeStudentStatusView(APIView):
    """Activates or deactivates a student.

    A student in the middle of a test is left alone: switching them off under a paper they are
    sitting would end it where it stands.
    """

    renderer_classes = [UserRenderer]
    permission_classes = admin_permission("change_student_status")
    def patch(self, request, pk, format=None):
        student = get_student(pk)
        if student is None:
            return error_response(message="Student not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = StudentStatusSerializer(student, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            if not serializer.validated_data.get('is_active', True) and is_sitting_a_test(student):
                return error_response(message="This student is sitting a test right now and cannot be deactivated!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

            student = serializer.save()
            return success_response(message="Student status updated successfully!", data=StudentListingSerializer(student).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class DeleteStudentView(APIView):
    """Removes a student from the system.

    The account itself is kept and marked deleted rather than dropped, because the papers they have
    already sat hang off it and a session's results have to stay readable afterwards. They are
    taken off the sessions that have not started yet, so those rosters do not carry somebody who
    will never turn up.
    """

    renderer_classes = [UserRenderer]
    permission_classes = admin_permission("delete_student")
    def delete(self, request, pk, format=None):
        student = get_student(pk)
        if student is None:
            return error_response(message="Student not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if is_sitting_a_test(student):
            return error_response(message="This student is sitting a test right now and cannot be deleted!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            student.assessment_sessions.filter(session__start_datetime__gt=timezone.now()).delete()

            student.is_deleted = True
            student.is_active = False
            student.save(update_fields=['is_deleted', 'is_active', 'updated_at'])

        return success_response(message="Student deleted successfully!", data=[], status_code=status.HTTP_200_OK)


class GetStudentSessionResultView(APIView):
    """The paper one student sat for one session, opened from their detail screen.

    This is the admin's view of the result, so the answer key and the images taken as the test
    started travel with it, which the candidate's own view of the same paper leaves out.
    """

    renderer_classes = [UserRenderer]
    permission_classes = admin_permission("student_session_result")
    def get(self, request, pk, session_id, format=None):
        student = student_queryset().filter(pk=pk).first()
        if student is None:
            return error_response(message="Student not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        session = Session.objects.filter(pk=session_id).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if not SessionStudent.objects.filter(session=session, student=student).exists():
            return error_response(message="This student is not on this session!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        attempt = TestAttempt.objects.select_related(
            'session__assessment', 'student'
        ).prefetch_related(
            'sections__assessment_section__section',
            'sections__answers__selected_option',
            'sections__answers__assessment_question__question__options',
        ).filter(session=session, student=student).first()

        if attempt is None:
            return error_response(message="This student has not attempted this session!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(message="Success", data=AttemptDetailSerializer(attempt).data, status_code=status.HTTP_200_OK)


def is_sitting_a_test(student):
    """Whether the student has a paper open on a session that is running right now."""
    now = timezone.now()

    return TestAttempt.objects.filter(
        student=student,
        status=TestAttempt.Status.IN_PROGRESS,
        session__start_datetime__lte=now,
        session__end_datetime__gte=now,
    ).exists()
