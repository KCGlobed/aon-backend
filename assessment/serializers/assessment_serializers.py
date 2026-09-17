from rest_framework import serializers
from django.db import transaction
from assessment.models import *
from aon_backend.utils import *


class AssessmentSectionRefSerializer(serializers.ModelSerializer):

    class Meta:
        model = Sections
        fields = ['id', 'name', 'section_id']


class AssessmentQuestionRefSerializer(serializers.ModelSerializer):
    difficulty_level_display = serializers.CharField(source='get_difficulty_level_display', read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'question_code', 'question_text', 'difficulty_level', 'difficulty_level_display',
                  'correct_answer_mark', 'negative_mark', 'status']


class AssessmentQuestionSerializer(serializers.ModelSerializer):
    question = AssessmentQuestionRefSerializer(read_only=True)

    class Meta:
        model = AssessmentQuestion
        fields = ['id', 'question', 'order']


class AssessmentSectionSerializer(serializers.ModelSerializer):
    section = AssessmentSectionRefSerializer(read_only=True)
    selection_type_display = serializers.CharField(source='get_selection_type_display', read_only=True)
    total_marks = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    questions = AssessmentQuestionSerializer(many=True, read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = AssessmentSection
        fields = ['id', 'section', 'number_of_questions', 'total_marks',
                  'allow_negative_marking', 'easy_questions', 'medium_questions',
                  'hard_questions', 'selection_type', 'selection_type_display',
                  'order', 'questions', 'created_at', 'updated_at']


class AssessmentListingSerializer(serializers.ModelSerializer):
    total_sections = serializers.IntegerField(source='sections.count', read_only=True)
    created_by_email = serializers.CharField(source='created_by.email', read_only=True, default='')
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Assessment
        fields = ['id', 'name', 'description', 'duration', 'number_of_questions', 'total_marks',
                  'instructions', 'status', 'total_sections', 'created_by_email',
                  'created_at', 'updated_at']


class AssessmentDetailSerializer(AssessmentListingSerializer):
    sections = AssessmentSectionSerializer(many=True, read_only=True)

    class Meta(AssessmentListingSerializer.Meta):
        fields = AssessmentListingSerializer.Meta.fields + ['sections']


class AssessmentSectionWriteSerializer(serializers.ModelSerializer):
    section = serializers.PrimaryKeyRelatedField(queryset=Sections.objects.all(), required=True)
    number_of_questions = serializers.IntegerField(min_value=1, required=True)
    selection_type = serializers.ChoiceField(choices=AssessmentSection.SelectionType.choices, default=AssessmentSection.SelectionType.RANDOM)
    easy_questions = serializers.IntegerField(min_value=0, required=False, default=0)
    medium_questions = serializers.IntegerField(min_value=0, required=False, default=0)
    hard_questions = serializers.IntegerField(min_value=0, required=False, default=0)
    questions = serializers.PrimaryKeyRelatedField(queryset=Question.objects.all(), many=True, required=False)

    class Meta:
        model = AssessmentSection
        fields = ['section', 'number_of_questions', 'allow_negative_marking',
                  'easy_questions', 'medium_questions', 'hard_questions',
                  'selection_type', 'order', 'questions']

    def validate_section(self, value):
        if not value.status:
            raise serializers.ValidationError(f"Section '{value.name}' is inactive and cannot be used in an assessment!")

        return value

    def validate(self, attrs):
        section = attrs.get('section')
        number_of_questions = attrs.get('number_of_questions')
        selection_type = attrs.get('selection_type', AssessmentSection.SelectionType.RANDOM)
        questions = attrs.get('questions') or []

        if not section or not number_of_questions:
            return attrs

        distribution = self.validate_difficulty_distribution(section, number_of_questions, attrs)

        if selection_type == AssessmentSection.SelectionType.MANUAL:
            attrs['questions'] = self.validate_manual_questions(section, number_of_questions, distribution, questions)
        else:
            attrs['questions'] = []
            self.validate_random_availability(section, number_of_questions, distribution)

        return attrs

    def validate_difficulty_distribution(self, section, number_of_questions, attrs):
        """{level: count} asked for by the admin. Empty when no split was given, which leaves the
        whole section open to questions of any difficulty."""
        distribution = {}
        for field, difficulty_level in DIFFICULTY_FIELDS.items():
            count = attrs.get(field) or 0
            if count:
                distribution[difficulty_level] = count

        if not distribution:
            return {}

        split_total = sum(distribution.values())
        if split_total != number_of_questions:
            raise serializers.ValidationError({
                'number_of_questions': f"The difficulty split for section '{section.name}' adds up to {split_total} question(s) but the section is defined with {number_of_questions} question(s)!"
            })

        return distribution

    def validate_manual_questions(self, section, number_of_questions, distribution, questions):
        if not questions:
            raise serializers.ValidationError({'questions': f"Questions must be selected for section '{section.name}' when the selection type is Manual!"})

        question_ids = [question.id for question in questions]
        if len(question_ids) != len(set(question_ids)):
            raise serializers.ValidationError({'questions': f"The same question cannot be selected more than once in section '{section.name}'!"})

        if len(questions) != number_of_questions:
            raise serializers.ValidationError({'questions': f"Section '{section.name}' expects {number_of_questions} question(s) but {len(questions)} were selected!"})

        outside = [question.question_code for question in questions if question.section_id != section.id]
        if outside:
            raise serializers.ValidationError({'questions': f"Question(s) {', '.join(outside)} do not belong to section '{section.name}'!"})

        inactive = [question.question_code for question in questions if not question.status]
        if inactive:
            raise serializers.ValidationError({'questions': f"Question(s) {', '.join(inactive)} are inactive and cannot be used!"})

        for difficulty_level, required in distribution.items():
            picked = len([question for question in questions if question.difficulty_level == difficulty_level])
            if picked != required:
                label = Question.DifficultyLevel(difficulty_level).label
                raise serializers.ValidationError({'questions': f"Section '{section.name}' expects {required} {label} question(s) but {picked} were selected!"})

        return questions

    def validate_random_availability(self, section, number_of_questions, distribution):
        for difficulty_level, required in (distribution or {None: number_of_questions}).items():
            available = self.available_questions(section, difficulty_level).count()
            if available < required:
                label = f"{Question.DifficultyLevel(difficulty_level).label} " if difficulty_level else ""
                raise serializers.ValidationError({
                    'number_of_questions': f"Section '{section.name}' has only {available} active {label}question(s) available but {required} were requested!"
                })

    @staticmethod
    def available_questions(section, difficulty_level=None):
        questions = Question.objects.filter(section=section, status=True)
        if difficulty_level:
            questions = questions.filter(difficulty_level=difficulty_level)

        return questions


class AssessmentPatternWriteMixin:
    """The question pattern side of the create and update APIs: checks the sections add up to the
    test, then writes them along with the questions each section holds."""

    def validate_sections(self, value):
        if not value:
            raise serializers.ValidationError("At least one section is required in the question pattern!")

        section_ids = [row['section'].id for row in value]
        if len(section_ids) != len(set(section_ids)):
            raise serializers.ValidationError("A section can only be added once to an assessment!")

        picked_ids = [question.id for row in value for question in row.get('questions') or []]
        if len(picked_ids) != len(set(picked_ids)):
            raise serializers.ValidationError("The same question cannot be selected more than once in an assessment!")

        return value

    def save_pattern(self, assessment, sections):
        """Replaces the whole pattern. Random sections are drawn here, skipping anything already
        used elsewhere in the same test."""
        assessment.assessment_questions.all().delete()
        assessment.sections.all().delete()

        used_question_ids = set()

        for row in sections:
            row = dict(row)
            questions = row.pop('questions', [])
            assessment_section = AssessmentSection.objects.create(assessment=assessment, **row)

            if assessment_section.selection_type == AssessmentSection.SelectionType.RANDOM:
                questions = self.pick_random_questions(assessment_section, used_question_ids)

            AssessmentQuestion.objects.bulk_create([
                AssessmentQuestion(assessment=assessment, assessment_section=assessment_section,
                                   question=question, order=index)
                for index, question in enumerate(questions, start=1)
            ])

            used_question_ids.update(question.id for question in questions)

    def pick_random_questions(self, assessment_section, used_question_ids):
        """Draws each difficulty bucket separately so the admin's Easy/Medium/Hard split is honoured.
        Without a split the whole section is drawn from questions of any difficulty."""
        distribution = assessment_section.difficulty_distribution or {None: assessment_section.number_of_questions}

        picked = []
        for difficulty_level, required in distribution.items():
            drawn_ids = used_question_ids | {question.id for question in picked}
            picked += self.draw_questions(assessment_section, difficulty_level, required, drawn_ids)

        return picked

    def draw_questions(self, assessment_section, difficulty_level, required, exclude_question_ids):
        questions = AssessmentSectionWriteSerializer.available_questions(
            assessment_section.section, difficulty_level
        ).exclude(id__in=exclude_question_ids)

        drawn = list(questions.order_by('?')[:required])

        if len(drawn) < required:
            label = f"{Question.DifficultyLevel(difficulty_level).label} " if difficulty_level else ""
            raise serializers.ValidationError({
                'sections': f"Section '{assessment_section.section.name}' has only {len(drawn)} unused active {label}question(s) available but {required} were requested!"
            })

        return drawn


class AssessmentCreateSerializer(AssessmentPatternWriteMixin, serializers.ModelSerializer):
    """The test and its question pattern in one call."""

    name = serializers.CharField(max_length=255, required=True)
    duration = serializers.IntegerField(min_value=1, required=True)
    sections = AssessmentSectionWriteSerializer(many=True, required=True)

    class Meta:
        model = Assessment
        fields = ['name', 'description', 'duration', 'instructions', 'status', 'sections']

    def validate_name(self, value):
        name = " ".join(value.split())
        if not name:
            raise serializers.ValidationError("Name cannot be blank!")

        if Assessment.objects.filter(name__iexact=name).exists():
            raise serializers.ValidationError("Assessment with this name already exists!")

        return name

    def create(self, validated_data):
        sections = validated_data.pop('sections')

        with transaction.atomic():
            assessment = Assessment.objects.create(**validated_data)
            self.save_pattern(assessment, sections)
            assessment.sync_totals()

        return assessment


class AssessmentUpdateSerializer(AssessmentPatternWriteMixin, serializers.ModelSerializer):
    """The test and its question pattern in one call. Leaving 'sections' out keeps the saved
    pattern untouched."""

    name = serializers.CharField(max_length=255, required=True)
    duration = serializers.IntegerField(min_value=1, required=True)
    sections = AssessmentSectionWriteSerializer(many=True, required=False)

    class Meta:
        model = Assessment
        fields = ['name', 'description', 'duration', 'instructions', 'status', 'sections']

    def validate_name(self, value):
        name = " ".join(value.split())
        if not name:
            raise serializers.ValidationError("Name cannot be blank!")

        if Assessment.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError("Assessment with this name already exists!")

        return name

    def update(self, instance, validated_data):
        sections = validated_data.pop('sections', None)

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if sections is not None:
                self.save_pattern(instance, sections)
                instance.sync_totals()

        return instance


class AssessmentStatusSerializer(serializers.ModelSerializer):
    status = serializers.BooleanField(required=True)

    class Meta:
        model = Assessment
        fields = ['status']


class AssessmentDropdownSerializer(serializers.ModelSerializer):

    class Meta:
        model = Assessment
        fields = ['id', 'name', 'duration', 'number_of_questions', 'total_marks']
