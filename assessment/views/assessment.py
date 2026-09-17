from rest_framework import status, filters
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from assessment.serializers import *
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck
from aon_backend.pagination import CustomPageNumberPagination


class GetAssessmentListingView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "assessment_listing",
                            [SuperAdmin]
                        )]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'duration', 'number_of_questions', 'total_marks',
                       'status', 'created_at', 'updated_at']
    def get(self, request, format=None):

        assessments_list = Assessment.objects.select_related('created_by').prefetch_related('sections').all()

        name = request.query_params.get('name')
        if name:
            assessments_list = assessments_list.filter(name__icontains=name)

        section = request.query_params.get('section')
        if section:
            assessments_list = assessments_list.filter(sections__section_id=section).distinct()

        assessment_status = request.query_params.get('status')
        if assessment_status:
            if assessment_status.lower() in ['true', '1', 't', 'yes']:
                assessments_list = assessments_list.filter(status=True)
            elif assessment_status.lower() in ['false', '0', 'f', 'no']:
                assessments_list = assessments_list.filter(status=False)
            else:
                raise ValidationError("Invalid status value. Use true or false.")

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                start_datetime_aware = timezone.make_aware(start_datetime, timezone.get_current_timezone())
                assessments_list = assessments_list.filter(created_at__gte=start_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                end_datetime_aware = timezone.make_aware(end_datetime, timezone.get_current_timezone())
                assessments_list = assessments_list.filter(created_at__lte=end_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid end_date format. Use YYYY-MM-DD.")

        search_filter = filters.SearchFilter()
        assessments_list = search_filter.filter_queryset(request, assessments_list, self)

        ordering_filter = filters.OrderingFilter()
        assessments_list = ordering_filter.filter_queryset(request, assessments_list, self)

        if not assessments_list.ordered:
            assessments_list = assessments_list.order_by('-id')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(assessments_list, request, view=self)
        serializer = AssessmentListingSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class GetAssessmentDetailView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "assessment_detail",
                            [SuperAdmin]
                        )]
    def get(self, request, pk, format=None):
        assessment = Assessment.objects.select_related('created_by').prefetch_related('sections__section', 'sections__questions__question').filter(pk=pk).first()
        if assessment is None:
            return error_response(message="Assessment not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        return success_response(message="Success", data=AssessmentDetailSerializer(assessment).data, status_code=status.HTTP_200_OK)


class CreateAssessmentView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "create_assessment",
                            [SuperAdmin]
                        )]
    def post(self, request, format=None):
        serializer = AssessmentCreateSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            assessment = serializer.save(created_by=request.user)
            return success_response(message="Assessment created successfully!", data=AssessmentDetailSerializer(assessment).data, status_code=status.HTTP_201_CREATED)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class UpdateAssessmentView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "update_assessment",
                            [SuperAdmin]
                        )]
    def put(self, request, pk, format=None):
        assessment = Assessment.objects.filter(pk=pk).first()
        if assessment is None:
            return error_response(message="Assessment not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = AssessmentUpdateSerializer(assessment, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            assessment = serializer.save()
            return success_response(message="Assessment updated successfully!", data=AssessmentDetailSerializer(assessment).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class GetAssessmentPatternView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "assessment_pattern",
                            [SuperAdmin]
                        )]
    def get(self, request, pk, format=None):
        assessment = Assessment.objects.filter(pk=pk).first()
        if assessment is None:
            return error_response(message="Assessment not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        sections = assessment.sections.select_related('section').prefetch_related('questions__question')
        serializer = AssessmentSectionSerializer(sections, many=True)
        return success_response(message="Success", data=serializer.data, status_code=status.HTTP_200_OK)


class GetSectionQuestionDropdownView(APIView):
    """Every active question of one section, for picking questions by hand while building a pattern."""

    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "section_question_dropdown",
                            [SuperAdmin]
                        )]
    def get(self, request, section_id, format=None):

        if not Sections.objects.filter(pk=section_id).exists():
            return error_response(message="Section not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        questions_list = Question.objects.filter(section_id=section_id, status=True)

        difficulty_level = request.query_params.get('difficulty_level')
        if difficulty_level:
            if difficulty_level not in [str(choice[0]) for choice in Question.DifficultyLevel.choices]:
                raise ValidationError("Invalid difficulty_level. Use 1 (Easy), 2 (Medium) or 3 (Hard).")
            questions_list = questions_list.filter(difficulty_level=difficulty_level)

        questions_list = questions_list.order_by('question_code')

        serializer = AssessmentQuestionRefSerializer(questions_list, many=True)
        return success_response(message="Success", data=serializer.data, status_code=status.HTTP_200_OK)


class ChangeAssessmentStatusView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "change_assessment_status",
                            [SuperAdmin]
                        )]
    def patch(self, request, pk, format=None):
        assessment = Assessment.objects.filter(pk=pk).first()
        if assessment is None:
            return error_response(message="Assessment not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = AssessmentStatusSerializer(assessment, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            assessment = serializer.save()
            return success_response(message="Assessment status updated successfully!", data=AssessmentDetailSerializer(assessment).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class DeleteAssessmentView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "delete_assessment",
                            [SuperAdmin]
                        )]
    def delete(self, request, pk, format=None):
        assessment = Assessment.objects.filter(pk=pk).first()
        if assessment is None:
            return error_response(message="Assessment not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        assessment.delete()
        return success_response(message="Assessment deleted successfully!", data=[], status_code=status.HTTP_200_OK)


class GetAssessmentDropdownView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "assessment_dropdown",
                            [SuperAdmin]
                        )]
    def get(self, request, format=None):

        assessments_list = Assessment.objects.filter(status=True).order_by('name')

        serializer = AssessmentDropdownSerializer(assessments_list, many=True)
        return success_response(message="Success", data=serializer.data, status_code=status.HTTP_200_OK)
