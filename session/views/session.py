from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status, filters
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from session.emails import queue_session_invites
from session.serializers import *
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck
from aon_backend.pagination import CustomPageNumberPagination


def session_response_data(session, invite_summary=None):
    """The saved session, plus how the invite mails went whenever any were sent."""
    data = SessionDetailSerializer(session).data
    if invite_summary is not None:
        data['invite_summary'] = invite_summary

    return data


class GetSessionListingView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "session_listing",
                            [SuperAdmin]
                        )]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description', 'assessment__name']
    ordering_fields = ['name', 'start_datetime', 'end_datetime', 'duration', 'status',
                       'created_at', 'updated_at']
    def get(self, request, format=None):

        sessions_list = Session.objects.select_related('assessment', 'created_by').prefetch_related('students').all()

        name = request.query_params.get('name')
        if name:
            sessions_list = sessions_list.filter(name__icontains=name)

        assessment = request.query_params.get('assessment')
        if assessment:
            sessions_list = sessions_list.filter(assessment_id=assessment)

        student = request.query_params.get('student')
        if student:
            sessions_list = sessions_list.filter(students__student_id=student).distinct()

        session_status = request.query_params.get('status')
        if session_status:
            if session_status.lower() in ['true', '1', 't', 'yes']:
                sessions_list = sessions_list.filter(status=True)
            elif session_status.lower() in ['false', '0', 'f', 'no']:
                sessions_list = sessions_list.filter(status=False)
            else:
                raise ValidationError("Invalid status value. Use true or false.")

        state = request.query_params.get('state')
        if state:
            now = timezone.now()
            if state == Session.State.UPCOMING:
                sessions_list = sessions_list.filter(start_datetime__gt=now)
            elif state == Session.State.ONGOING:
                sessions_list = sessions_list.filter(start_datetime__lte=now, end_datetime__gte=now)
            elif state == Session.State.COMPLETED:
                sessions_list = sessions_list.filter(end_datetime__lt=now)
            else:
                raise ValidationError("Invalid state value. Use Upcoming, Ongoing or Completed.")

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                start_datetime_aware = timezone.make_aware(start_datetime, timezone.get_current_timezone())
                sessions_list = sessions_list.filter(start_datetime__gte=start_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                end_datetime_aware = timezone.make_aware(end_datetime, timezone.get_current_timezone())
                sessions_list = sessions_list.filter(start_datetime__lte=end_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid end_date format. Use YYYY-MM-DD.")

        search_filter = filters.SearchFilter()
        sessions_list = search_filter.filter_queryset(request, sessions_list, self)

        ordering_filter = filters.OrderingFilter()
        sessions_list = ordering_filter.filter_queryset(request, sessions_list, self)

        if not sessions_list.ordered:
            sessions_list = sessions_list.order_by('-id')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(sessions_list, request, view=self)
        serializer = SessionListingSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class GetSessionDetailView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "session_detail",
                            [SuperAdmin]
                        )]
    def get(self, request, pk, format=None):
        session = Session.objects.select_related('assessment', 'created_by').prefetch_related('students__student').filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        return success_response(message="Success", data=SessionDetailSerializer(session).data, status_code=status.HTTP_200_OK)


class CreateSessionView(APIView):
    """The admin picks the assessment and the start time; the end time comes from the assessment's
    duration. Every student added is mailed the schedule."""

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "create_session",
                            [SuperAdmin]
                        )]
    def post(self, request, format=None):
        serializer = SessionCreateSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            session = serializer.save(created_by=request.user)
            invite_summary = queue_session_invites(serializer.invited_students)
            return success_response(message="Session created successfully!", data=session_response_data(session, invite_summary), status_code=status.HTTP_201_CREATED)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class UpdateSessionView(APIView):
    """A session can be changed until it starts. Moving it re-notifies everyone on it, since the
    time they were told about no longer holds."""

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "update_session",
                            [SuperAdmin]
                        )]
    def put(self, request, pk, format=None):
        session = Session.objects.select_related('assessment').filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = SessionUpdateSerializer(session, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            session = serializer.save()
            invite_summary = queue_session_invites(serializer.invited_students)
            return success_response(message="Session updated successfully!", data=session_response_data(session, invite_summary), status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class AddSessionStudentsView(APIView):
    """Adds students to a session that already exists and mails them the schedule."""

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "add_session_student",
                            [SuperAdmin]
                        )]
    def post(self, request, pk, format=None):
        session = Session.objects.select_related('assessment').filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = SessionStudentAddSerializer(data = request.data, context = {'session': session})
        if serializer.is_valid(raise_exception = True):
            added = SessionStudent.objects.bulk_create([
                SessionStudent(session=session, student=student)
                for student in serializer.validated_data['students']
            ])
            invite_summary = queue_session_invites(
                session.students.select_related('student').filter(id__in=[row.id for row in added])
            )
            return success_response(message="Student(s) added to the session successfully!", data=session_response_data(session, invite_summary), status_code=status.HTTP_201_CREATED)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class RemoveSessionStudentView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "remove_session_student",
                            [SuperAdmin]
                        )]
    def delete(self, request, pk, student_id, format=None):
        session = Session.objects.filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        session_student = session.students.filter(student_id=student_id).first()
        if session_student is None:
            return error_response(message="Student is not on this session!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        session_student.delete()
        return success_response(message="Student removed from the session successfully!", data=SessionDetailSerializer(session).data, status_code=status.HTTP_200_OK)


class ResendSessionInviteView(APIView):
    """Mails the session details again, either to the students named in the request or to everybody
    on the session."""

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "resend_session_invite",
                            [SuperAdmin]
                        )]
    def post(self, request, pk, format=None):
        session = Session.objects.select_related('assessment').filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = SessionInviteResendSerializer(data = request.data, context = {'session': session})
        if serializer.is_valid(raise_exception = True):
            invite_summary = queue_session_invites(serializer.validated_data['session_students'])
            return success_response(message="Session notification sent successfully!", data=session_response_data(session, invite_summary), status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class ChangeSessionStatusView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "change_session_status",
                            [SuperAdmin]
                        )]
    def patch(self, request, pk, format=None):
        session = Session.objects.filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = SessionStatusSerializer(session, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            session = serializer.save()
            return success_response(message="Session status updated successfully!", data=SessionDetailSerializer(session).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class DeleteSessionView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "delete_session",
                            [SuperAdmin]
                        )]
    def delete(self, request, pk, format=None):
        session = Session.objects.filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if session.state == Session.State.ONGOING:
            return error_response(message="This session is running right now and cannot be deleted!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        session.delete()
        return success_response(message="Session deleted successfully!", data=[], status_code=status.HTTP_200_OK)


class GetSessionStudentListingView(APIView):
    """The students on one session and where each invite stands: Pending, Sent or Failed.

    Invites go out on a background thread, so a student added a moment ago reads Pending until the
    mail actually leaves. Filter on email_status=Failed to find the ones worth resending.
    """

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "session_student_listing",
                            [SuperAdmin]
                        )]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['student__first_name', 'student__last_name', 'student__email',
                     'student__application_id']
    ordering_fields = ['email_status', 'email_sent_at', 'created_at', 'student__first_name',
                       'student__email']
    def get(self, request, pk, format=None):

        session = Session.objects.filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        students_list = session.students.select_related('student').all()

        email_status = request.query_params.get('email_status')
        if email_status:
            if email_status not in SessionStudent.EmailStatus.values:
                raise ValidationError("Invalid email_status value. Use Pending, Sent or Failed.")
            students_list = students_list.filter(email_status=email_status)

        email_sent = request.query_params.get('email_sent')
        if email_sent:
            if email_sent.lower() in ['true', '1', 't', 'yes']:
                students_list = students_list.filter(email_sent=True)
            elif email_sent.lower() in ['false', '0', 'f', 'no']:
                students_list = students_list.filter(email_sent=False)
            else:
                raise ValidationError("Invalid email_sent value. Use true or false.")

        search_filter = filters.SearchFilter()
        students_list = search_filter.filter_queryset(request, students_list, self)

        ordering_filter = filters.OrderingFilter()
        students_list = ordering_filter.filter_queryset(request, students_list, self)

        if not students_list.ordered:
            students_list = students_list.order_by('id')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(students_list, request, view=self)
        serializer = SessionStudentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class GetSessionInviteStatusView(APIView):
    """How many invites on a session are Pending, Sent or Failed. Cheap enough to poll while a
    batch is still going out."""

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "session_student_listing",
                            [SuperAdmin]
                        )]
    def get(self, request, pk, format=None):
        session = Session.objects.filter(pk=pk).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        counts = {status_value.lower(): 0 for status_value in SessionStudent.EmailStatus.values}
        for row in session.students.values('email_status').annotate(count=Count('id')):
            counts[row['email_status'].lower()] = row['count']

        return success_response(
            message="Success",
            data={'session_id': session.pk, 'total': sum(counts.values()), **counts},
            status_code=status.HTTP_200_OK
        )


class GetSessionStudentDropdownView(APIView):
    """Every student that can be added to a session. Pass 'session' to leave out the ones already
    on that session."""

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "session_student_dropdown",
                            [SuperAdmin]
                        )]
    def get(self, request, format=None):

        students_list = student_queryset().filter(is_active=True)

        session_id = request.query_params.get('session')
        if session_id:
            session = Session.objects.filter(pk=session_id).first()
            if session is None:
                return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

            students_list = students_list.exclude(assessment_sessions__session_id=session.pk)

        search = request.query_params.get('search')
        if search:
            students_list = students_list.filter(
                Q(first_name__icontains=search) | Q(last_name__icontains=search)
                | Q(email__icontains=search) | Q(application_id__icontains=search)
            )

        students_list = students_list.order_by('first_name', 'last_name', 'email')

        serializer = SessionStudentRefSerializer(students_list, many=True)
        return success_response(message="Success", data=serializer.data, status_code=status.HTTP_200_OK)


class GetSessionDropdownView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "session_dropdown",
                            [SuperAdmin]
                        )]
    def get(self, request, format=None):

        sessions_list = Session.objects.select_related('assessment').filter(status=True).order_by('start_datetime')

        serializer = SessionDropdownSerializer(sessions_list, many=True)
        return success_response(message="Success", data=serializer.data, status_code=status.HTTP_200_OK)
