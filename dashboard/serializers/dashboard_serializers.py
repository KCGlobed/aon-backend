"""What the admin's home screen reads.

Nothing here is stored: every number is counted off the session, assessment and attempt tables as
the screen is opened. The counts the rows carry are annotated by the views rather than worked out
per row, so a dashboard full of sessions still costs a fixed handful of queries.
"""

from decimal import Decimal

from django.db.models import F
from rest_framework import serializers

from candidate.models import TestAttempt
from session.models import Session
from session.serializers.session_serializers import SessionStudentRefSerializer


# The overall score to sort and average on. It reads the column sync_totals saves rather than
# working the share out a second way, so the dashboard and the result the student was shown can
# never drift apart.
SCORE_PERCENTAGE = F('percentage')


def rounded(value):
    """A percentage as the two-decimal string every other API writes its marks in."""
    return str(round(value, 2)) if value is not None else None


def percentage_of(part, whole):
    """One count as a share of another.

    Nothing to divide into reads 0.00 rather than failing: a platform with no sessions booked yet
    has a utilisation of zero, which is a fact about it and not an error.
    """
    if not whole:
        return "0.00"

    return str(round(Decimal(part) * 100 / Decimal(whole), 2))


class DashboardSessionSerializer(serializers.ModelSerializer):
    """One session on the dashboard, with how far the students booked into it have got.

    'attempted' counts the students who opened the paper at all; 'not_started' is everybody else on
    the roster, which is the number worth watching while a session is running.
    """

    assessment_name = serializers.CharField(source='assessment.name', read_only=True)
    start_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    state = serializers.CharField(read_only=True)
    total_students = serializers.IntegerField(read_only=True)
    attempted = serializers.IntegerField(read_only=True)
    submitted = serializers.IntegerField(read_only=True)
    in_progress = serializers.SerializerMethodField()
    not_started = serializers.SerializerMethodField()
    utilisation = serializers.SerializerMethodField()
    average_percentage = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = ['id', 'name', 'assessment_name', 'start_datetime', 'end_datetime', 'duration',
                  'status', 'state', 'total_students', 'attempted', 'submitted', 'in_progress',
                  'not_started', 'utilisation', 'average_percentage']

    def get_in_progress(self, obj):
        return obj.attempted - obj.submitted

    def get_not_started(self, obj):
        """Never below zero: a student taken off the roster after sitting the test would otherwise
        leave more attempts than students."""
        return max(0, obj.total_students - obj.attempted)

    def get_utilisation(self, obj):
        """How much of the session was actually used: the share of its roster that turned up."""
        return percentage_of(obj.attempted, obj.total_students)

    def get_average_percentage(self, obj):
        """What the papers handed in for this session averaged, out of the 'session_averages'
        context the views hand in. Null until somebody submits one."""
        return rounded(self.context.get('session_averages', {}).get(obj.pk))


class DashboardAttemptSerializer(serializers.ModelSerializer):
    """One paper, as the dashboard lists it: who sat it, for which session, and what it came to."""

    student = SessionStudentRefSerializer(read_only=True)
    session_id = serializers.IntegerField(read_only=True)
    session_name = serializers.CharField(source='session.name', read_only=True)
    assessment_name = serializers.CharField(source='session.assessment.name', read_only=True)
    started_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    submitted_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    percentage = serializers.SerializerMethodField()

    class Meta:
        model = TestAttempt
        fields = ['id', 'student', 'session_id', 'session_name', 'assessment_name', 'status',
                  'started_at', 'submitted_at', 'total_questions', 'correct_answers',
                  'wrong_answers', 'unanswered', 'total_marks', 'max_marks', 'passing_marks',
                  'percentage', 'result']

    def get_percentage(self, obj):
        return str(obj.percentage)
