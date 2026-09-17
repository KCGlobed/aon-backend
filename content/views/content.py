from rest_framework import status, filters
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from content.serializers import *
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck
from aon_backend.pagination import CustomPageNumberPagination


class GetSectionListingView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "section_listing",
                            [SuperAdmin]
                        )]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'section_id']
    ordering_fields = ['name', 'section_id', 'status', 'created_at', 'updated_at']
    def get(self, request, format=None):

        sections_list = Sections.objects.all()

        name = request.query_params.get('name')
        if name:
            sections_list = sections_list.filter(name__icontains=name)

        section_id = request.query_params.get('section_id')
        if section_id:
            sections_list = sections_list.filter(section_id__icontains=section_id)

        section_status = request.query_params.get('status')
        if section_status:
            if section_status.lower() in ['true', '1', 't', 'yes']:
                sections_list = sections_list.filter(status=True)
            elif section_status.lower() in ['false', '0', 'f', 'no']:
                sections_list = sections_list.filter(status=False)
            else:
                raise ValidationError("Invalid status value. Use true or false.")

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                start_datetime_aware = timezone.make_aware(start_datetime, timezone.get_current_timezone())
                sections_list = sections_list.filter(created_at__gte=start_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                end_datetime_aware = timezone.make_aware(end_datetime, timezone.get_current_timezone())
                sections_list = sections_list.filter(created_at__lte=end_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid end_date format. Use YYYY-MM-DD.")

        search_filter = filters.SearchFilter()
        sections_list = search_filter.filter_queryset(request, sections_list, self)

        ordering_filter = filters.OrderingFilter()
        sections_list = ordering_filter.filter_queryset(request, sections_list, self)

        if not sections_list.ordered:
            sections_list = sections_list.order_by('-id')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(sections_list, request, view=self)
        serializer = SectionListingSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CreateSectionView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "create_section",
                            [SuperAdmin]
                        )]
    def post(self, request, format=None):
        serializer = SectionCreateSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            section = serializer.save()
            return success_response(message="Section created successfully!", data=SectionListingSerializer(section).data, status_code=status.HTTP_201_CREATED)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class UpdateSectionView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "update_section",
                            [SuperAdmin]
                        )]
    def put(self, request, pk, format=None):
        section = Sections.objects.filter(pk=pk).first()
        if section is None:
            return error_response(message="Section not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = SectionUpdateSerializer(section, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            section = serializer.save()
            return success_response(message="Section updated successfully!", data=SectionListingSerializer(section).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class ChangeSectionStatusView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "change_section_status",
                            [SuperAdmin]
                        )]
    def patch(self, request, pk, format=None):
        section = Sections.objects.filter(pk=pk).first()
        if section is None:
            return error_response(message="Section not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        serializer = SectionStatusSerializer(section, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            section = serializer.save()
            return success_response(message="Section status updated successfully!", data=SectionListingSerializer(section).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class DeleteSectionView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "delete_section",
                            [SuperAdmin]
                        )]
    def delete(self, request, pk, format=None):
        section = Sections.objects.filter(pk=pk).first()
        if section is None:
            return error_response(message="Section not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if section.questions.exists():
            return error_response(message="Section cannot be deleted because questions are linked to it!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        if section.assessment_sections.exists():
            return error_response(message="Section cannot be deleted because it is used in an assessment!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        section.delete()
        return success_response(message="Section deleted successfully!", data=[], status_code=status.HTTP_200_OK)


class GetSectionDropdownView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "section_dropdown",
                            [SuperAdmin]
                        )]
    def get(self, request, format=None):

        sections_list = Sections.objects.filter(status=True).order_by('name')

        serializer = SectionDropdownSerializer(sections_list, many=True)
        return success_response(message="Success", data=serializer.data, status_code=status.HTTP_200_OK)
