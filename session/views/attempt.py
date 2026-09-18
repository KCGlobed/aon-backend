from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from candidate.models import TestAttempt
from session.serializers import *
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck


class GetStudentAttemptDetailView(APIView):
    """One student's paper, opened from the session screen.

    The images taken as the test started, what was answered question by question, and what it
    scored. Unlike the candidate's own view of the result, this one carries the answer key, since
    whoever is reading it is checking the marking rather than sitting the test.
    """

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "student_attempt_detail",
                            [SuperAdmin]
                        )]
    def get(self, request, pk, format=None):
        attempt = TestAttempt.objects.select_related(
            'session__assessment', 'student'
        ).prefetch_related(
            'sections__assessment_section__section',
            'sections__answers__selected_option',
            'sections__answers__assessment_question__question__options',
        ).filter(pk=pk).first()

        if attempt is None:
            return error_response(message="Test attempt not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        return success_response(message="Success", data=AttemptDetailSerializer(attempt).data, status_code=status.HTTP_200_OK)
