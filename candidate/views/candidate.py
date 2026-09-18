from django.db import transaction
from django.utils import timezone
from rest_framework import status, filters
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from candidate.serializers import *
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck
from aon_backend.pagination import CustomPageNumberPagination


def student_permission(permission_name):
    return [IsAuthenticated,
            RoleOrPermissionCheck.for_permission_or_roles(permission_name, [Student])]


def close_if_time_is_up(attempt):
    """A paper left open past the session's end is closed where it stands.

    Nothing schedules this; it happens the next time the attempt is read, which is enough to keep
    a student who simply walked away from sitting In Progress for ever.
    """
    if attempt.is_submitted:
        return attempt

    if timezone.now() <= attempt.session.end_datetime + timedelta(seconds=SUBMIT_GRACE_SECONDS):
        return attempt

    attempt.status = TestAttempt.Status.SUBMITTED
    attempt.submitted_at = attempt.session.end_datetime
    attempt.save(update_fields=['status', 'submitted_at', 'updated_at'])
    attempt.sync_totals()

    return attempt


def get_own_attempt(request, pk):
    """The student's own attempt, or None. Scoping every read to the signed-in student is what keeps
    one candidate out of another's paper."""
    return TestAttempt.objects.select_related('session__assessment', 'student').filter(
        pk=pk, student=request.user).first()


class GetMySessionsView(APIView):
    """Every session this student is booked into, and where their attempt stands."""

    renderer_classes = [UserRenderer]
    permission_classes = student_permission("my_sessions")
    pagination_class = CustomPageNumberPagination
    def get(self, request, format=None):

        sessions_list = Session.objects.select_related('assessment').filter(
            students__student=request.user, status=True).distinct()

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

        sessions_list = sessions_list.order_by('start_datetime')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(sessions_list, request, view=self)
        attempts = {attempt.session_id: attempt for attempt in
                    TestAttempt.objects.filter(student=request.user,
                                               session__in=[session.pk for session in page])}
        serializer = CandidateSessionSerializer(page, many=True, context={'attempts': attempts})
        return paginator.get_paginated_response(serializer.data)


class StartTestView(APIView):
    """Opens the student's paper for a session.

    The photo and the identity document are taken here, before any question is handed over. Coming
    back to a paper already open returns it as it stands rather than starting a second one.
    """

    renderer_classes = [UserRenderer]
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = student_permission("start_test")
    def post(self, request, session_id, format=None):
        session = Session.objects.select_related('assessment').filter(pk=session_id, status=True).first()
        if session is None:
            return error_response(message="Session not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if not SessionStudent.objects.filter(session=session, student=request.user).exists():
            return error_response(message="You are not scheduled for this session!", data={}, status_code=status.HTTP_403_FORBIDDEN)

        attempt = TestAttempt.objects.filter(session=session, student=request.user).first()
        if attempt is not None:
            attempt = close_if_time_is_up(attempt)
            if attempt.is_submitted:
                return error_response(message="You have already submitted this test!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

            return success_response(message="Test resumed successfully!", data=self.attempt_data(attempt), status_code=status.HTTP_200_OK)

        if session.state == Session.State.UPCOMING:
            return error_response(message="This session has not started yet!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        if session.state == Session.State.COMPLETED:
            return error_response(message="This session is over!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        serializer = StartTestSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            attempt = self.open_attempt(request, session, serializer.validated_data)
            return success_response(message="Test started successfully!", data=self.attempt_data(attempt), status_code=status.HTTP_201_CREATED)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)

    def open_attempt(self, request, session, validated_data):
        """Creates the attempt and lays out a row for every section of the paper."""
        assessment_sections = session.assessment.sections.select_related('section').prefetch_related('questions__question')

        with transaction.atomic():
            attempt = TestAttempt.objects.create(
                session=session,
                student=request.user,
                candidate_image=validated_data['candidate_image'],
                id_proof_image=validated_data['id_proof_image'],
            )

            TestSectionAttempt.objects.bulk_create([
                TestSectionAttempt(
                    attempt=attempt,
                    assessment_section=assessment_section,
                    total_questions=len(assessment_section.questions.all()),
                    max_marks=assessment_section.total_marks,
                )
                for assessment_section in assessment_sections
            ])

            attempt.max_marks = sum(section.max_marks for section in attempt.sections.all())
            attempt.save(update_fields=['max_marks', 'updated_at'])
            attempt.sync_totals()

        return attempt

    def attempt_data(self, attempt):
        return CandidateAttemptSerializer(attempt).data


class GetTestDetailView(APIView):
    """The student's paper: the sections, which are done, and how long is left."""

    renderer_classes = [UserRenderer]
    permission_classes = student_permission("test_detail")
    def get(self, request, pk, format=None):
        attempt = get_own_attempt(request, pk)
        if attempt is None:
            return error_response(message="Test not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        attempt = close_if_time_is_up(attempt)
        return success_response(message="Success", data=CandidateAttemptSerializer(attempt).data, status_code=status.HTTP_200_OK)


class GetSectionQuestionsView(APIView):
    """The questions of one section, without the answer key."""

    renderer_classes = [UserRenderer]
    permission_classes = student_permission("section_questions")
    def get(self, request, pk, section_pk, format=None):
        attempt = get_own_attempt(request, pk)
        if attempt is None:
            return error_response(message="Test not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        attempt = close_if_time_is_up(attempt)
        if attempt.is_submitted:
            return error_response(message="This test has already been submitted!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        section_attempt = attempt.sections.select_related('assessment_section__section').filter(pk=section_pk).first()
        if section_attempt is None:
            return error_response(message="Section not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if section_attempt.is_submitted:
            return error_response(message="This section has already been submitted!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        questions = section_attempt.assessment_section.questions.select_related('question').prefetch_related('question__options')

        return success_response(
            message="Success",
            data={
                'section': CandidateSectionSerializer(section_attempt).data,
                'seconds_remaining': max(0, int((attempt.session.end_datetime - timezone.now()).total_seconds())),
                'questions': CandidateQuestionSerializer(
                    questions, many=True, context={'attempt_id': attempt.pk}).data,
            },
            status_code=status.HTTP_200_OK
        )


class SubmitSectionView(APIView):
    """Takes one section's answers, scores them and closes the section.

    Marking follows the assessment: a right answer earns the question's mark, a wrong one costs the
    question's negative mark where the section carries negative marking, and anything left alone is
    worth nothing.
    """

    renderer_classes = [UserRenderer]
    permission_classes = student_permission("submit_section")
    def post(self, request, pk, section_pk, format=None):
        attempt = get_own_attempt(request, pk)
        if attempt is None:
            return error_response(message="Test not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        section_attempt = attempt.sections.select_related(
            'assessment_section__section', 'attempt__session').filter(pk=section_pk).first()
        if section_attempt is None:
            return error_response(message="Section not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = SubmitSectionSerializer(data = request.data, context = {'section_attempt': section_attempt})
        if serializer.is_valid(raise_exception = True):
            section_attempt = serializer.save()
            attempt.refresh_from_db()
            return success_response(
                message="Section submitted successfully!",
                data={
                    'section': CandidateSectionResultSerializer(section_attempt).data,
                    'attempt': CandidateAttemptSerializer(attempt).data,
                },
                status_code=status.HTTP_200_OK
            )

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class SubmitTestView(APIView):
    """Closes the whole paper. Sections never submitted are left as they are and their questions
    count as unanswered."""

    renderer_classes = [UserRenderer]
    permission_classes = student_permission("submit_test")
    def post(self, request, pk, format=None):
        attempt = get_own_attempt(request, pk)
        if attempt is None:
            return error_response(message="Test not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if attempt.is_submitted:
            return error_response(message="You have already submitted this test!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            attempt.status = TestAttempt.Status.SUBMITTED
            attempt.submitted_at = timezone.now()
            attempt.save(update_fields=['status', 'submitted_at', 'updated_at'])
            attempt.sync_totals()

        return success_response(message="Test submitted successfully!", data=CandidateResultSerializer(attempt).data, status_code=status.HTTP_200_OK)


class GetTestResultView(APIView):
    """What the student scored once the paper is closed.

    The per-question answer key is deliberately left out: this is the candidate's own view, and the
    questions are drawn from a bank that later sittings reuse.
    """

    renderer_classes = [UserRenderer]
    permission_classes = student_permission("test_result")
    def get(self, request, pk, format=None):
        attempt = get_own_attempt(request, pk)
        if attempt is None:
            return error_response(message="Test not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        attempt = close_if_time_is_up(attempt)
        if not attempt.is_submitted:
            return error_response(message="This test has not been submitted yet!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        return success_response(message="Success", data=CandidateResultSerializer(attempt).data, status_code=status.HTTP_200_OK)
