"""What an admin sees when they open one student's paper from the session screen.

This is the other side of the candidate serializers: the same attempt, read by somebody marking it
rather than sitting it, so the answer key travels with it and the proctoring images are included.
"""

from rest_framework import serializers

from candidate.models import TestAnswer, TestAttempt, TestSectionAttempt
from content.models import QuestionOption
from session.serializers.session_serializers import SessionStudentRefSerializer, local_datetime


class AttemptOptionSerializer(serializers.ModelSerializer):
    """The options with 'right_option' on them - this is the marked paper, not the question paper."""

    class Meta:
        model = QuestionOption
        fields = ['id', 'option_text', 'right_option']


class AttemptAnswerSerializer(serializers.ModelSerializer):
    """One question as the student left it, with what it was worth."""

    assessment_question_id = serializers.IntegerField(source='assessment_question.id', read_only=True)
    question_code = serializers.CharField(source='assessment_question.question.question_code', read_only=True)
    question_text = serializers.CharField(source='assessment_question.question.question_text', read_only=True)
    order = serializers.IntegerField(source='assessment_question.order', read_only=True)
    correct_answer_mark = serializers.DecimalField(source='assessment_question.question.correct_answer_mark', max_digits=5, decimal_places=2, read_only=True)
    negative_mark = serializers.DecimalField(source='assessment_question.question.negative_mark', max_digits=5, decimal_places=2, read_only=True)
    options = AttemptOptionSerializer(source='assessment_question.question.options', many=True, read_only=True)
    selected_option_id = serializers.SerializerMethodField()
    selected_option_text = serializers.SerializerMethodField()
    is_answered = serializers.SerializerMethodField()

    class Meta:
        model = TestAnswer
        fields = ['id', 'assessment_question_id', 'question_code', 'question_text', 'order',
                  'correct_answer_mark', 'negative_mark', 'options', 'selected_option_id',
                  'selected_option_text', 'is_answered', 'is_correct', 'marks_awarded']

    def get_selected_option_id(self, obj):
        return obj.selected_option_id

    def get_selected_option_text(self, obj):
        return obj.selected_option.option_text if obj.selected_option_id else None

    def get_is_answered(self, obj):
        """A row with nothing chosen is a question the student left alone, not a wrong answer."""
        return obj.selected_option_id is not None


class AttemptSectionDetailSerializer(serializers.ModelSerializer):
    """One section of the paper and every question in it.

    A section the student never submitted carries no answer rows at all - nothing was ever saved
    for it - so 'answers' comes back empty and 'status' says why.
    """

    name = serializers.CharField(source='assessment_section.section.name', read_only=True)
    section_id = serializers.CharField(source='assessment_section.section.section_id', read_only=True)
    order = serializers.IntegerField(source='assessment_section.order', read_only=True)
    allow_negative_marking = serializers.BooleanField(source='assessment_section.allow_negative_marking', read_only=True)
    submitted_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    answers = AttemptAnswerSerializer(many=True, read_only=True)

    class Meta:
        model = TestSectionAttempt
        fields = ['id', 'assessment_section_id', 'name', 'section_id', 'order', 'status',
                  'allow_negative_marking', 'score', 'max_marks', 'total_questions',
                  'correct_answers', 'wrong_answers', 'unanswered', 'submitted_at', 'answers']


class AttemptDetailSerializer(serializers.ModelSerializer):
    """The whole sitting: who sat it, the images taken as it opened, and what it scored."""

    student = SessionStudentRefSerializer(read_only=True)
    session_id = serializers.IntegerField(read_only=True)
    session_name = serializers.CharField(source='session.name', read_only=True)
    assessment_name = serializers.CharField(source='session.assessment.name', read_only=True)
    duration = serializers.IntegerField(source='session.duration', read_only=True)
    start_datetime = serializers.DateTimeField(source='session.start_datetime', format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_datetime = serializers.DateTimeField(source='session.end_datetime', format="%Y-%m-%d %H:%M:%S", read_only=True)
    started_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    submitted_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    time_taken_minutes = serializers.SerializerMethodField()
    candidate_image = serializers.SerializerMethodField()
    id_proof_image = serializers.SerializerMethodField()
    is_passed = serializers.BooleanField(read_only=True)
    sections = AttemptSectionDetailSerializer(many=True, read_only=True)

    class Meta:
        model = TestAttempt
        fields = ['id', 'student', 'session_id', 'session_name', 'assessment_name', 'duration',
                  'start_datetime', 'end_datetime', 'status', 'started_at', 'submitted_at',
                  'time_taken_minutes', 'candidate_image', 'id_proof_image', 'total_questions',
                  'correct_answers', 'wrong_answers', 'unanswered', 'total_marks', 'max_marks',
                  'passing_marks', 'percentage', 'result', 'is_passed', 'sections']

    def get_time_taken_minutes(self, obj):
        """How long the student was actually at the paper. Null while it is still open."""
        if not obj.submitted_at:
            return None

        return round((obj.submitted_at - obj.started_at).total_seconds() / 60)

    def get_candidate_image(self, obj):
        return obj.candidate_image.url if obj.candidate_image else None

    def get_id_proof_image(self, obj):
        return obj.id_proof_image.url if obj.id_proof_image else None
