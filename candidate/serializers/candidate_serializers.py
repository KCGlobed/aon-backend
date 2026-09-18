import random
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from assessment.models import AssessmentQuestion, AssessmentSection
from candidate.models import *
from content.models import QuestionOption
from session.models import Session, SessionStudent
from aon_backend.utils import *


ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.webp']
MAX_IMAGE_SIZE_MB = 5

# A section submitted a shade after the session closes is still accepted; the answers were given
# while it was open and the student should not lose them to the time the request took.
SUBMIT_GRACE_SECONDS = 120


def shuffled_options(question, attempt_id):
    """The options of one question in an order of this paper's own.

    Two students sitting the same session see the options in different orders, so a glance at the
    next desk is worth less. The order is drawn from the attempt and the question rather than at
    random each time, which means a student who reloads mid-section gets the same paper back.
    """
    options = list(question.options.all())
    random.Random(f"{attempt_id}:{question.pk}").shuffle(options)

    return options


def validate_upload(value, label):
    if not value.name.lower().endswith(tuple(ALLOWED_IMAGE_EXTENSIONS)):
        raise serializers.ValidationError(
            f"{label} must be an image ({', '.join(ALLOWED_IMAGE_EXTENSIONS)})!"
        )

    if value.size == 0:
        raise serializers.ValidationError(f"{label} is empty!")

    if value.size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise serializers.ValidationError(f"{label} must be {MAX_IMAGE_SIZE_MB}MB or smaller!")

    return value


class CandidateOptionSerializer(serializers.ModelSerializer):
    """The options as the student sees them while sitting the test.

    'right_option' is deliberately not a field here: this serializer is what answers the question
    paper, and the answer key must not travel with it.
    """

    class Meta:
        model = QuestionOption
        fields = ['id', 'option_text']


class CandidateQuestionSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source='question.id', read_only=True)
    assessment_question_id = serializers.IntegerField(source='id', read_only=True)
    question_code = serializers.CharField(source='question.question_code', read_only=True)
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    correct_answer_mark = serializers.DecimalField(source='question.correct_answer_mark', max_digits=5, decimal_places=2, read_only=True)
    negative_mark = serializers.DecimalField(source='question.negative_mark', max_digits=5, decimal_places=2, read_only=True)
    options = serializers.SerializerMethodField()

    class Meta:
        model = AssessmentQuestion
        fields = ['id', 'assessment_question_id', 'question_code', 'question_text',
                  'correct_answer_mark', 'negative_mark', 'order', 'options']

    def get_options(self, obj):
        return CandidateOptionSerializer(shuffled_options(obj.question, self.context.get('attempt_id')),
                                         many=True).data


class CandidateSectionSerializer(serializers.ModelSerializer):
    """One section of the student's paper: where it stands, and what it is worth."""

    id = serializers.IntegerField(read_only=True)
    assessment_section_id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(source='assessment_section.section.name', read_only=True)
    section_id = serializers.CharField(source='assessment_section.section.section_id', read_only=True)
    order = serializers.IntegerField(source='assessment_section.order', read_only=True)
    allow_negative_marking = serializers.BooleanField(source='assessment_section.allow_negative_marking', read_only=True)
    submitted_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = TestSectionAttempt
        fields = ['id', 'assessment_section_id', 'name', 'section_id', 'order', 'status',
                  'allow_negative_marking', 'total_questions', 'max_marks', 'submitted_at']


class CandidateSectionResultSerializer(CandidateSectionSerializer):
    """The same section once it has been submitted, with what it scored."""

    class Meta(CandidateSectionSerializer.Meta):
        fields = CandidateSectionSerializer.Meta.fields + [
            'score', 'correct_answers', 'wrong_answers', 'unanswered']


class CandidateAttemptSerializer(serializers.ModelSerializer):
    session_id = serializers.IntegerField(read_only=True)
    session_name = serializers.CharField(source='session.name', read_only=True)
    assessment_name = serializers.CharField(source='session.assessment.name', read_only=True)
    duration = serializers.IntegerField(source='session.duration', read_only=True)
    instructions = serializers.SerializerMethodField()
    start_datetime = serializers.DateTimeField(source='session.start_datetime', format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_datetime = serializers.DateTimeField(source='session.end_datetime', format="%Y-%m-%d %H:%M:%S", read_only=True)
    seconds_remaining = serializers.SerializerMethodField()
    candidate_image = serializers.SerializerMethodField()
    id_proof_image = serializers.SerializerMethodField()
    sections = CandidateSectionSerializer(many=True, read_only=True)
    started_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    submitted_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = TestAttempt
        fields = ['id', 'session_id', 'session_name', 'assessment_name', 'duration', 'instructions',
                  'start_datetime', 'end_datetime', 'seconds_remaining', 'status',
                  'candidate_image', 'id_proof_image', 'total_questions', 'max_marks',
                  'started_at', 'submitted_at', 'sections']

    def get_instructions(self, obj):
        return obj.session.instructions or obj.session.assessment.instructions

    def get_seconds_remaining(self, obj):
        if obj.is_submitted:
            return 0

        return max(0, int((obj.session.end_datetime - timezone.now()).total_seconds()))

    def get_candidate_image(self, obj):
        return obj.candidate_image.url if obj.candidate_image else None

    def get_id_proof_image(self, obj):
        return obj.id_proof_image.url if obj.id_proof_image else None


class CandidateResultSerializer(CandidateAttemptSerializer):
    sections = CandidateSectionResultSerializer(many=True, read_only=True)
    percentage = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)

    class Meta(CandidateAttemptSerializer.Meta):
        fields = CandidateAttemptSerializer.Meta.fields + [
            'total_marks', 'percentage', 'correct_answers', 'wrong_answers', 'unanswered']


class CandidateSessionSerializer(serializers.ModelSerializer):
    """A session the student is booked into, and where their attempt stands."""

    assessment_name = serializers.CharField(source='assessment.name', read_only=True)
    number_of_questions = serializers.IntegerField(source='assessment.number_of_questions', read_only=True)
    total_marks = serializers.DecimalField(source='assessment.total_marks', max_digits=7, decimal_places=2, read_only=True)
    start_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    state = serializers.CharField(read_only=True)
    attempt_status = serializers.SerializerMethodField()
    attempt_id = serializers.SerializerMethodField()
    can_start = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = ['id', 'name', 'assessment_name', 'duration', 'number_of_questions', 'total_marks',
                  'start_datetime', 'end_datetime', 'state', 'attempt_status', 'attempt_id',
                  'can_start']

    def attempt_for(self, obj):
        return self.context['attempts'].get(obj.pk)

    def get_attempt_status(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.status if attempt else 'Not Started'

    def get_attempt_id(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.pk if attempt else None

    def get_can_start(self, obj):
        attempt = self.attempt_for(obj)
        if attempt is not None and attempt.is_submitted:
            return False

        return obj.status and obj.state == Session.State.ONGOING


class StartTestSerializer(serializers.Serializer):
    """Opens the student's attempt. The photo and the identity document are what let a proctor put
    a face to the paper afterwards, so both are required before any question is handed over."""

    candidate_image = serializers.ImageField(required=True)
    id_proof_image = serializers.ImageField(required=True)

    def validate_candidate_image(self, value):
        return validate_upload(value, 'Candidate image')

    def validate_id_proof_image(self, value):
        return validate_upload(value, 'ID proof image')


class SectionAnswerSerializer(serializers.Serializer):
    assessment_question = serializers.PrimaryKeyRelatedField(queryset=AssessmentQuestion.objects.all(), required=True)
    selected_option = serializers.PrimaryKeyRelatedField(queryset=QuestionOption.objects.all(), required=False, allow_null=True)


class SubmitSectionSerializer(serializers.Serializer):
    """The answers for one section, submitted in one go.

    Questions left out of the request count as unanswered. A section can only be submitted once.
    """

    answers = serializers.ListField(child=SectionAnswerSerializer(), required=True, allow_empty=True)

    def validate(self, attrs):
        section_attempt = self.context['section_attempt']
        answers = attrs['answers']

        if section_attempt.is_submitted:
            raise serializers.ValidationError("This section has already been submitted and cannot be answered again!")

        if section_attempt.attempt.is_submitted:
            raise serializers.ValidationError("This test has already been submitted!")

        session = section_attempt.attempt.session
        if timezone.now() > session.end_datetime + timedelta(seconds=SUBMIT_GRACE_SECONDS):
            raise serializers.ValidationError("This session is over and answers can no longer be submitted!")

        questions = {assessment_question.pk: assessment_question
                     for assessment_question in section_attempt.assessment_section.questions.select_related('question')}

        seen = set()
        cleaned = []
        for answer in answers:
            assessment_question = answer['assessment_question']

            if assessment_question.pk not in questions:
                raise serializers.ValidationError({'answers': f"Question {assessment_question.pk} is not part of this section!"})

            if assessment_question.pk in seen:
                raise serializers.ValidationError({'answers': f"Question {assessment_question.pk} has been answered more than once!"})

            seen.add(assessment_question.pk)

            selected_option = answer.get('selected_option')
            if selected_option is not None and selected_option.question_id != assessment_question.question_id:
                raise serializers.ValidationError({'answers': f"The option chosen for question {assessment_question.pk} does not belong to it!"})

            cleaned.append({'assessment_question': questions[assessment_question.pk],
                            'selected_option': selected_option})

        attrs['answers'] = cleaned
        attrs['questions'] = questions

        return attrs

    def save(self, **kwargs):
        """Writes a row for every question in the section, scores each one, and closes the section."""
        section_attempt = self.context['section_attempt']
        allow_negative_marking = section_attempt.assessment_section.allow_negative_marking
        chosen = {answer['assessment_question'].pk: answer['selected_option']
                  for answer in self.validated_data['answers']}

        rows = []
        for assessment_question in self.validated_data['questions'].values():
            selected_option = chosen.get(assessment_question.pk)
            is_correct, marks = score_answer(assessment_question.question, selected_option,
                                             allow_negative_marking)
            rows.append(TestAnswer(section_attempt=section_attempt,
                                   assessment_question=assessment_question,
                                   selected_option=selected_option,
                                   is_correct=is_correct,
                                   marks_awarded=marks))

        with transaction.atomic():
            TestAnswer.objects.bulk_create(rows)
            section_attempt.sync_totals()
            section_attempt.attempt.sync_totals()

        return section_attempt
