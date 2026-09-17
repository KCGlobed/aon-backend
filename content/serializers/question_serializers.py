from rest_framework import serializers
from django.db import transaction
from content.models import *
from aon_backend.utils import *


class QuestionOptionSerializer(serializers.ModelSerializer):
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = QuestionOption
        fields = ['id', 'option_text', 'right_option', 'created_at']


class QuestionOptionWriteSerializer(serializers.ModelSerializer):
    option_text = serializers.CharField(required=True)

    class Meta:
        model = QuestionOption
        fields = ['option_text', 'right_option']


class QuestionSectionSerializer(serializers.ModelSerializer):

    class Meta:
        model = Sections
        fields = ['id', 'name', 'section_id']


class QuestionListingSerializer(serializers.ModelSerializer):
    section = QuestionSectionSerializer(read_only=True)
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Question
        fields = ['id', 'section', 'question_code', 'question_text', 'difficulty_level',
                  'difficulty_level_display', 'correct_answer_mark', 'negative_mark',
                  'status', 'created_at', 'updated_at']


class QuestionDetailSerializer(QuestionListingSerializer):
    options = QuestionOptionSerializer(many=True, read_only=True)

    class Meta(QuestionListingSerializer.Meta):
        fields = QuestionListingSerializer.Meta.fields + ['options']


class QuestionOptionValidationMixin:

    def validate_options(self, value):
        if len(value) < 2:
            raise serializers.ValidationError("At least 2 options are required!")

        right_options = [option for option in value if option.get('right_option')]
        if len(right_options) != 1:
            raise serializers.ValidationError("Exactly one option must be marked as the right option!")

        return value


class QuestionCreateSerializer(QuestionOptionValidationMixin, serializers.ModelSerializer):
    question_code = serializers.CharField(max_length=50, required=True)
    question_text = serializers.CharField(required=True)
    options = QuestionOptionWriteSerializer(many=True, required=True)

    class Meta:
        model = Question
        fields = ['section', 'question_code', 'question_text', 'difficulty_level',
                  'correct_answer_mark', 'negative_mark', 'status', 'options']

    def validate_question_code(self, value):
        question_code = value.strip()
        if not question_code:
            raise serializers.ValidationError("Question code cannot be blank!")

        if Question.objects.filter(question_code__iexact=question_code).exists():
            raise serializers.ValidationError("Question with this code already exists!")

        return question_code

    def create(self, validated_data):
        options = validated_data.pop('options')

        with transaction.atomic():
            question = Question.objects.create(**validated_data)
            QuestionOption.objects.bulk_create([
                QuestionOption(question=question, **option) for option in options
            ])

        return question


class QuestionUpdateSerializer(QuestionOptionValidationMixin, serializers.ModelSerializer):
    question_code = serializers.CharField(max_length=50, required=True)
    question_text = serializers.CharField(required=True)
    options = QuestionOptionWriteSerializer(many=True, required=False)

    class Meta:
        model = Question
        fields = ['section', 'question_code', 'question_text', 'difficulty_level',
                  'correct_answer_mark', 'negative_mark', 'status', 'options']

    def validate_question_code(self, value):
        question_code = value.strip()
        if not question_code:
            raise serializers.ValidationError("Question code cannot be blank!")

        if Question.objects.filter(question_code__iexact=question_code).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Question with this code already exists!")

        return question_code

    def update(self, instance, validated_data):
        options = validated_data.pop('options', None)

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if options is not None:
                instance.options.all().delete()
                QuestionOption.objects.bulk_create([
                    QuestionOption(question=instance, **option) for option in options
                ])

        return instance


class QuestionStatusSerializer(serializers.ModelSerializer):
    status = serializers.BooleanField(required=True)

    class Meta:
        model = Question
        fields = ['status']


class SectionDropdownSerializer(serializers.ModelSerializer):

    class Meta:
        model = Sections
        fields = ['id', 'name', 'section_id']


class QuestionHistoryUserSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'name', 'email']

    def get_name(self, obj):
        return " ".join(filter(None, [obj.first_name, obj.last_name]))


class QuestionHistorySerializer(serializers.ModelSerializer):
    changed_by = QuestionHistoryUserSerializer(read_only=True)
    changed_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = QuestionHistory
        fields = ['id', 'question', 'question_code', 'action', 'changes',
                  'changed_by', 'changed_by_email', 'changed_at']
