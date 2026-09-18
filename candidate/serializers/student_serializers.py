"""Student records, as the admin manages them.

The rest of this app answers the student sitting the test; this half is the other side of it - who
the students are, how many sessions they have actually sat, and what each of those papers came to.
The counts are annotated onto the queryset rather than worked out row by row, so a page of students
costs the same handful of queries however long the roster gets.
"""

from django.db import transaction
from django.db.models import Count, Q
from rest_framework import serializers
from rolepermissions.roles import assign_role

from candidate.models import TestAttempt
from session.models import SessionStudent
from session.serializers.session_serializers import NOT_STARTED, local_datetime, student_queryset
from aon_backend.utils import *


# What the admin may fill in beyond the name and email the account itself is built from.
STUDENT_PROFILE_FIELDS = ['application_id', 'address', 'city', 'state', 'country', 'pincode', 'dob']


def student_listing_queryset():
    """Every student on record, with how many sessions each is booked into and has sat.

    'sessions_attempted' counts the papers the student actually opened, submitted or not, which is
    the number both the listing and the detail screen report.
    """
    return student_queryset().annotate(
        total_sessions=Count('assessment_sessions', distinct=True),
        sessions_attempted=Count('test_attempts', distinct=True),
        sessions_submitted=Count(
            'test_attempts',
            filter=Q(test_attempts__status=TestAttempt.Status.SUBMITTED),
            distinct=True,
        ),
    )


class StudentCountsMixin(serializers.Serializer):
    """The session counts the listing queryset annotates on.

    A student just created carries none of those annotations, so each count falls back to zero
    rather than breaking the response the create and update APIs send back.
    """

    total_sessions = serializers.SerializerMethodField()
    sessions_attempted = serializers.SerializerMethodField()
    sessions_submitted = serializers.SerializerMethodField()
    sessions_in_progress = serializers.SerializerMethodField()

    def get_total_sessions(self, obj):
        return getattr(obj, 'total_sessions', 0) or 0

    def get_sessions_attempted(self, obj):
        return getattr(obj, 'sessions_attempted', 0) or 0

    def get_sessions_submitted(self, obj):
        return getattr(obj, 'sessions_submitted', 0) or 0

    def get_sessions_in_progress(self, obj):
        """Papers opened but never handed in - the difference between the two counts above."""
        return self.get_sessions_attempted(obj) - self.get_sessions_submitted(obj)


class StudentListingSerializer(StudentCountsMixin, serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = User
        fields = ['id', 'uid', 'first_name', 'last_name', 'full_name', 'email', 'phone',
                  'application_id', 'address', 'city', 'state', 'country', 'pincode', 'dob',
                  'is_active', 'created_at', 'updated_at', 'total_sessions', 'sessions_attempted',
                  'sessions_submitted', 'sessions_in_progress']

    def get_full_name(self, obj):
        return " ".join(filter(None, [obj.first_name, obj.last_name])).strip()


class StudentSessionSerializer(serializers.ModelSerializer):
    """One session the student is booked into, and where their paper for it stands.

    'session_id' is what the result API is called with once the admin opens the row. A session the
    student never started carries no attempt at all, so it reads Not Started and scores nothing.
    """

    session_id = serializers.IntegerField(read_only=True)
    session_name = serializers.CharField(source='session.name', read_only=True)
    assessment_name = serializers.CharField(source='session.assessment.name', read_only=True)
    duration = serializers.IntegerField(source='session.duration', read_only=True)
    start_datetime = serializers.DateTimeField(source='session.start_datetime', format="%Y-%m-%d %H:%M:%S", read_only=True)
    end_datetime = serializers.DateTimeField(source='session.end_datetime', format="%Y-%m-%d %H:%M:%S", read_only=True)
    state = serializers.CharField(source='session.state', read_only=True)
    attempt_id = serializers.SerializerMethodField()
    attempt_status = serializers.SerializerMethodField()
    started_at = serializers.SerializerMethodField()
    submitted_at = serializers.SerializerMethodField()
    total_questions = serializers.SerializerMethodField()
    correct_answers = serializers.SerializerMethodField()
    wrong_answers = serializers.SerializerMethodField()
    unanswered = serializers.SerializerMethodField()
    total_marks = serializers.SerializerMethodField()
    max_marks = serializers.SerializerMethodField()
    passing_marks = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()
    result = serializers.SerializerMethodField()

    class Meta:
        model = SessionStudent
        fields = ['id', 'session_id', 'session_name', 'assessment_name', 'duration',
                  'start_datetime', 'end_datetime', 'state', 'email_status', 'attempt_id',
                  'attempt_status', 'started_at', 'submitted_at', 'total_questions',
                  'correct_answers', 'wrong_answers', 'unanswered', 'total_marks', 'max_marks',
                  'passing_marks', 'percentage', 'result']

    def attempt_for(self, obj):
        """The student's attempt at this session, out of the 'attempts' context the view hands in."""
        return self.context.get('attempts', {}).get(obj.session_id)

    def get_attempt_id(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.pk if attempt else None

    def get_attempt_status(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.status if attempt else NOT_STARTED

    def get_started_at(self, obj):
        attempt = self.attempt_for(obj)
        return local_datetime(attempt.started_at) if attempt else None

    def get_submitted_at(self, obj):
        attempt = self.attempt_for(obj)
        return local_datetime(attempt.submitted_at) if attempt else None

    def get_total_questions(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.total_questions if attempt else None

    def get_correct_answers(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.correct_answers if attempt else None

    def get_wrong_answers(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.wrong_answers if attempt else None

    def get_unanswered(self, obj):
        attempt = self.attempt_for(obj)
        return attempt.unanswered if attempt else None

    def get_total_marks(self, obj):
        """Only final once the paper is in; a test still running has scored the sections submitted
        so far and nothing for the rest."""
        attempt = self.attempt_for(obj)
        return str(attempt.total_marks) if attempt else None

    def get_max_marks(self, obj):
        attempt = self.attempt_for(obj)
        return str(attempt.max_marks) if attempt else None

    def get_passing_marks(self, obj):
        attempt = self.attempt_for(obj)
        return str(attempt.passing_marks) if attempt else None

    def get_percentage(self, obj):
        attempt = self.attempt_for(obj)
        return str(attempt.percentage) if attempt else None

    def get_result(self, obj):
        """Pending while the paper is still open, then the Pass or Fail saved with it."""
        attempt = self.attempt_for(obj)
        return attempt.result if attempt else None


class StudentDetailSerializer(StudentListingSerializer):
    """The student, how many sessions they have sat, and every session they are booked into."""

    sessions = StudentSessionSerializer(source='assessment_sessions', many=True, read_only=True)

    class Meta(StudentListingSerializer.Meta):
        fields = StudentListingSerializer.Meta.fields + ['sessions']


class StudentFieldsMixin:
    """The checks the create and update APIs share.

    Email and application id are what a student signs in with, so each has to answer for exactly
    one person. Both are matched without regard to case, since neither is typed the same way twice.
    """

    def validate_first_name(self, value):
        first_name = " ".join(value.split())
        if not first_name:
            raise serializers.ValidationError("First name cannot be blank!")

        return first_name

    def validate_email(self, value):
        email = value.strip().lower()

        users = User.objects.filter(email__iexact=email)
        if self.instance is not None:
            users = users.exclude(pk=self.instance.pk)

        if users.exists():
            raise serializers.ValidationError("A user with this email already exists!")

        return email

    def validate_application_id(self, value):
        application_id = " ".join(value.split())
        if not application_id:
            raise serializers.ValidationError("Application Id cannot be blank!")

        users = User.objects.filter(application_id__iexact=application_id)
        if self.instance is not None:
            users = users.exclude(pk=self.instance.pk)

        clash = users.first()
        if clash is not None:
            raise serializers.ValidationError(f"Application Id is already in use by {clash.email}!")

        return application_id


class StudentCreateSerializer(StudentFieldsMixin, serializers.ModelSerializer):
    """A student the admin adds by hand rather than through the roster import.

    The account comes out ready to sit a test: students sign in with their email, application id
    and name, so the password is never used and the email is taken as verified.
    """

    first_name = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(max_length=255, required=True)
    application_id = serializers.CharField(max_length=100, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'application_id', 'address', 'city',
                  'state', 'country', 'pincode', 'dob', 'is_active']

    def create(self, validated_data):
        with transaction.atomic():
            user = User.objects.create_user(
                email=validated_data['email'],
                first_name=validated_data['first_name'],
                last_name=validated_data.get('last_name') or '',
                password=generate_random_password(),
                phone=validated_data.get('phone'),
            )

            user.role = User.Student
            user.email_verified = 1
            user.is_active = validated_data.get('is_active', True)
            for field in STUDENT_PROFILE_FIELDS:
                if field in validated_data:
                    setattr(user, field, validated_data[field])
            user.save()

            assign_role(user, 'Student')

        return user


class StudentUpdateSerializer(StudentFieldsMixin, serializers.ModelSerializer):
    """The same details, changed on a student already on record.

    The role is written back on every save: an account reached through this API is a student, and
    it staying one is what keeps their sessions and their login working.
    """

    first_name = serializers.CharField(max_length=100, required=True)
    email = serializers.EmailField(max_length=255, required=True)
    application_id = serializers.CharField(max_length=100, required=True)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'application_id', 'address', 'city',
                  'state', 'country', 'pincode', 'dob', 'is_active']

    def update(self, instance, validated_data):
        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            instance.role = User.Student
            instance.save()

            assign_role(instance, 'Student')

        return instance


class StudentStatusSerializer(serializers.ModelSerializer):
    """Turns a student on or off. An inactive student cannot sign in and cannot be put on a new
    session, but everything they have already sat is left as it stands."""

    is_active = serializers.BooleanField(required=True)

    class Meta:
        model = User
        fields = ['is_active']
