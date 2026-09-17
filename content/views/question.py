from rest_framework import status, filters
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.db import transaction
from content.serializers import *
from content.utils import snapshot_question, diff_snapshots, log_question_history
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck
from aon_backend.pagination import CustomPageNumberPagination


class GetQuestionListingView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "question_listing",
                            [SuperAdmin]
                        )]
    pagination_class = CustomPageNumberPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['question_code', 'question_text', 'section__name', 'section__section_id']
    ordering_fields = ['question_code', 'difficulty_level', 'correct_answer_mark',
                       'negative_mark', 'status', 'created_at', 'updated_at']
    def get(self, request, format=None):

        questions_list = Question.objects.select_related('section').all()

        question_code = request.query_params.get('question_code')
        if question_code:
            questions_list = questions_list.filter(question_code__icontains=question_code)

        question_text = request.query_params.get('question_text')
        if question_text:
            questions_list = questions_list.filter(question_text__icontains=question_text)

        section = request.query_params.get('section')
        if section:
            questions_list = questions_list.filter(section_id=section)

        section_code = request.query_params.get('section_code')
        if section_code:
            questions_list = questions_list.filter(section__section_id__icontains=section_code)

        difficulty_level = request.query_params.get('difficulty_level')
        if difficulty_level:
            if difficulty_level not in [str(choice[0]) for choice in Question.DifficultyLevel.choices]:
                raise ValidationError("Invalid difficulty_level. Use 1 (Easy), 2 (Medium) or 3 (Hard).")
            questions_list = questions_list.filter(difficulty_level=difficulty_level)

        question_status = request.query_params.get('status')
        if question_status:
            if question_status.lower() in ['true', '1', 't', 'yes']:
                questions_list = questions_list.filter(status=True)
            elif question_status.lower() in ['false', '0', 'f', 'no']:
                questions_list = questions_list.filter(status=False)
            else:
                raise ValidationError("Invalid status value. Use true or false.")

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_datetime = datetime.fromisoformat(start_date)
                start_datetime_aware = timezone.make_aware(start_datetime, timezone.get_current_timezone())
                questions_list = questions_list.filter(created_at__gte=start_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid start_date format. Use YYYY-MM-DD.")

        if end_date:
            try:
                end_datetime = datetime.fromisoformat(end_date)
                end_datetime_aware = timezone.make_aware(end_datetime, timezone.get_current_timezone())
                questions_list = questions_list.filter(created_at__lte=end_datetime_aware)
            except ValueError:
                raise ValidationError("Invalid end_date format. Use YYYY-MM-DD.")

        search_filter = filters.SearchFilter()
        questions_list = search_filter.filter_queryset(request, questions_list, self)

        ordering_filter = filters.OrderingFilter()
        questions_list = ordering_filter.filter_queryset(request, questions_list, self)

        if not questions_list.ordered:
            questions_list = questions_list.order_by('-id')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(questions_list, request, view=self)
        serializer = QuestionListingSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class GetQuestionDetailView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "question_detail",
                            [SuperAdmin]
                        )]
    def get(self, request, pk, format=None):
        question = Question.objects.select_related('section').prefetch_related('options').filter(pk=pk).first()
        if question is None:
            return error_response(message="Question not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        return success_response(message="Success", data=QuestionDetailSerializer(question).data, status_code=status.HTTP_200_OK)


class CreateQuestionView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "create_question",
                            [SuperAdmin]
                        )]
    def post(self, request, format=None):
        serializer = QuestionCreateSerializer(data = request.data)
        if serializer.is_valid(raise_exception = True):
            question = serializer.save()
            log_question_history(question, QuestionHistory.Action.CREATED, request.user,
                                 changes=snapshot_question(question))
            return success_response(message="Question created successfully!", data=QuestionDetailSerializer(question).data, status_code=status.HTTP_201_CREATED)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class UpdateQuestionView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "update_question",
                            [SuperAdmin]
                        )]
    def put(self, request, pk, format=None):
        question = Question.objects.filter(pk=pk).first()
        if question is None:
            return error_response(message="Question not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        before = snapshot_question(question)

        serializer = QuestionUpdateSerializer(question, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            question = serializer.save()

            changes = diff_snapshots(before, snapshot_question(question))
            if changes:
                log_question_history(question, QuestionHistory.Action.UPDATED, request.user, changes=changes)

            return success_response(message="Question updated successfully!", data=QuestionDetailSerializer(question).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class ChangeQuestionStatusView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "change_question_status",
                            [SuperAdmin]
                        )]
    def patch(self, request, pk, format=None):
        question = Question.objects.filter(pk=pk).first()
        if question is None:
            return error_response(message="Question not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        previous_status = question.status

        serializer = QuestionStatusSerializer(question, data = request.data, partial = True)
        if serializer.is_valid(raise_exception = True):
            question = serializer.save()

            if previous_status != question.status:
                log_question_history(question, QuestionHistory.Action.STATUS_CHANGED, request.user,
                                     changes={'status': {'old': previous_status, 'new': question.status}})

            return success_response(message="Question status updated successfully!", data=QuestionDetailSerializer(question).data, status_code=status.HTTP_200_OK)

        return error_response(message="failed", data = serializer.errors, status_code=status.HTTP_400_BAD_REQUEST)


class DeleteQuestionView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "delete_question",
                            [SuperAdmin]
                        )]
    def delete(self, request, pk, format=None):
        question = Question.objects.filter(pk=pk).first()
        if question is None:
            return error_response(message="Question not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        if question.assessment_questions.exists():
            return error_response(message="Question cannot be deleted because it is used in an assessment!", data={}, status_code=status.HTTP_400_BAD_REQUEST)

        question_code = question.question_code
        final_state = snapshot_question(question)

        question.delete()

        log_question_history(None, QuestionHistory.Action.DELETED, request.user,
                             changes=final_state, question_code=question_code)

        return success_response(message="Question deleted successfully!", data=[], status_code=status.HTTP_200_OK)


class GetQuestionHistoryView(APIView):
    renderer_classes = [UserRenderer]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "question_history",
                            [SuperAdmin]
                        )]
    pagination_class = CustomPageNumberPagination
    def get(self, request, pk, format=None):
        question = Question.objects.filter(pk=pk).first()
        if question is None:
            return error_response(message="Question not found!", data={}, status_code=status.HTTP_404_NOT_FOUND)

        history_list = QuestionHistory.objects.select_related('changed_by').filter(question=question)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(history_list, request, view=self)
        serializer = QuestionHistorySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ImportQuestionView(APIView):
    renderer_classes = [UserRenderer]
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated,
                          RoleOrPermissionCheck.for_permission_or_roles(
                              "import_question",
                            [SuperAdmin]
                        )]
    def post(self, request, format=None):
        serializer = QuestionImportSerializer(data = request.data)
        serializer.is_valid(raise_exception = True)

        rows = serializer.validated_data['rows']
        errors = serializer.validated_data['errors']

        if errors:
            return error_response(
                message="Import failed. No questions were imported. Please correct the errors and upload the file again.",
                data={'total_rows': len(rows) + len(errors), 'error_count': len(errors), 'errors': errors},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                imported = []
                for row in rows:
                    question = Question.objects.create(
                        section=row['section'],
                        question_code=row['question_code'],
                        question_text=row['question_text'],
                        difficulty_level=row['difficulty_level'],
                        correct_answer_mark=row['correct_answer_mark'],
                        negative_mark=row['negative_mark'],
                    )
                    QuestionOption.objects.bulk_create([
                        QuestionOption(question=question, **option) for option in row['options']
                    ])
                    log_question_history(question, QuestionHistory.Action.IMPORTED, request.user,
                                         changes=snapshot_question(question))
                    imported.append(question.question_code)
        except Exception as e:
            logger.error(f"Question import failed: {e}")
            return error_response(
                message="Import failed. No questions were imported. Please try again.",
                data={'total_rows': len(rows)},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        return success_response(
            message=f"{len(imported)} questions imported successfully!",
            data={'total_rows': len(rows), 'imported_count': len(imported), 'question_codes': imported},
            status_code=status.HTTP_201_CREATED
        )
