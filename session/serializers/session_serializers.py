from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from assessment.models import Assessment
from session.models import *
from aon_backend.utils import *


class SessionAssessmentRefSerializer(serializers.ModelSerializer):

    class Meta:
        model = Assessment
        fields = ['id', 'name', 'duration', 'number_of_questions', 'total_marks', 'status']


class SessionStudentRefSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'uid', 'first_name', 'last_name', 'full_name', 'email', 'phone',
                  'application_id', 'is_active']

    def get_full_name(self, obj):
        return " ".join(filter(None, [obj.first_name, obj.last_name])).strip()


class SessionStudentSerializer(serializers.ModelSerializer):
    student = SessionStudentRefSerializer(read_only=True)
    email_sent_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S", read_only=True)

    class Meta:
        model = SessionStudent
        fields = ['id', 'student', 'email_status', 'email_sent', 'email_sent_at', 'email_error',
                  'created_at']


class SessionListingSerializer(serializers.ModelSerializer):
    assessment = SessionAssessmentRefSerializer(read_only=True)
    state = serializers.CharField(read_only=True)
    total_students = serializers.IntegerField(source='students.count', read_only=True)
    created_by_email = serializers.CharField(source='created_by.email', read_only=True, default='')
    start_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    end_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    created_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    updated_at = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Session
        fields = ['id', 'name', 'description', 'assessment', 'start_datetime', 'end_datetime',
                  'duration', 'instructions', 'status', 'state', 'total_students',
                  'created_by_email', 'created_at', 'updated_at']


class InviteCountsMixin(serializers.Serializer):
    invite_counts = serializers.SerializerMethodField()

    def get_invite_counts(self, obj):
        """Where the invites for this session stand right now. Counted off the rows already loaded,
        so a prefetched session costs no extra queries."""
        students = list(obj.students.all())
        counts = {status_value.lower(): 0 for status_value in SessionStudent.EmailStatus.values}
        for session_student in students:
            counts[session_student.email_status.lower()] = counts.get(session_student.email_status.lower(), 0) + 1

        return {'total': len(students), **counts}


class SessionDetailSerializer(InviteCountsMixin, SessionListingSerializer):
    students = SessionStudentSerializer(many=True, read_only=True)

    class Meta(SessionListingSerializer.Meta):
        fields = SessionListingSerializer.Meta.fields + ['invite_counts', 'students']


def student_queryset():
    """Everyone who can sit a test: a student account that has not been removed."""
    return User.objects.filter(role=User.Student, is_deleted=False)


def validate_students_are_bookable(students):
    """The students must be distinct, live accounts that still hold the Student role."""
    student_ids = [student.id for student in students]
    if len(student_ids) != len(set(student_ids)):
        raise serializers.ValidationError("The same student cannot be added to a session more than once!")

    inactive = [student.email for student in students if not student.is_active or student.is_deleted]
    if inactive:
        raise serializers.ValidationError(f"Student(s) {', '.join(inactive)} are inactive and cannot be added to a session!")

    not_students = [student.email for student in students if student.role != User.Student]
    if not_students:
        raise serializers.ValidationError(f"User(s) {', '.join(not_students)} are not students and cannot be added to a session!")

    return students


def validate_students_are_free(students, start_datetime, end_datetime, exclude_session=None):
    """A student can only sit one test at a time, so an overlap with another live session is refused."""
    clashes = SessionStudent.objects.filter(
        student__in=students,
        session__status=True,
        session__start_datetime__lt=end_datetime,
        session__end_datetime__gt=start_datetime,
    ).select_related('student', 'session')

    if exclude_session is not None:
        clashes = clashes.exclude(session_id=exclude_session.pk)

    clash = clashes.first()
    if clash is not None:
        raise serializers.ValidationError(
            f"Student {clash.student.email} is already booked into the session "
            f"'{clash.session.name}' over the same time!"
        )

    return students


class SessionScheduleMixin:
    """The scheduling half of the create and update APIs. The admin gives the test and the start
    time; when the session ends is worked out from the assessment's own duration."""

    def validate_name(self, value):
        name = " ".join(value.split())
        if not name:
            raise serializers.ValidationError("Name cannot be blank!")

        sessions = Session.objects.filter(name__iexact=name)
        if self.instance is not None:
            sessions = sessions.exclude(pk=self.instance.pk)

        if sessions.exists():
            raise serializers.ValidationError("Session with this name already exists!")

        return name

    def validate_assessment(self, value):
        if not value.status:
            raise serializers.ValidationError(f"Assessment '{value.name}' is inactive and cannot be scheduled!")

        if not value.number_of_questions:
            raise serializers.ValidationError(f"Assessment '{value.name}' has no questions and cannot be scheduled!")

        return value

    def validate_students(self, value):
        return validate_students_are_bookable(value)

    def apply_schedule(self, attrs):
        """Fills in the derived end time and duration, and hands both back for the checks that follow."""
        assessment = attrs.get('assessment') or getattr(self.instance, 'assessment', None)
        start_datetime = attrs.get('start_datetime') or getattr(self.instance, 'start_datetime', None)

        attrs['duration'] = assessment.duration
        attrs['end_datetime'] = start_datetime + timedelta(minutes=assessment.duration)

        return start_datetime, attrs['end_datetime']

    def validate_start_is_ahead(self, start_datetime):
        if start_datetime <= timezone.now():
            raise serializers.ValidationError({'start_datetime': "Start time must be in the future!"})

    def save_students(self, session, students):
        """Adds the students that are not on the session yet and hands back only those rows, so
        nobody who has already been told is mailed a second time."""
        existing_ids = set(session.students.values_list('student_id', flat=True))
        added = [student for student in students if student.id not in existing_ids]

        SessionStudent.objects.bulk_create([
            SessionStudent(session=session, student=student) for student in added
        ])

        return list(session.students.select_related('student').filter(student__in=added))


class SessionCreateSerializer(SessionScheduleMixin, serializers.ModelSerializer):
    """The session and the students expected at it in one call. The end time is never taken from the
    request; it follows the assessment's duration."""

    name = serializers.CharField(max_length=255, required=True)
    assessment = serializers.PrimaryKeyRelatedField(queryset=Assessment.objects.all(), required=True)
    start_datetime = serializers.DateTimeField(required=True)
    students = serializers.PrimaryKeyRelatedField(queryset=student_queryset(), many=True, required=False)

    class Meta:
        model = Session
        fields = ['name', 'description', 'assessment', 'start_datetime', 'instructions',
                  'status', 'students']

    def validate(self, attrs):
        start_datetime, end_datetime = self.apply_schedule(attrs)
        self.validate_start_is_ahead(start_datetime)

        students = attrs.get('students') or []
        if students:
            validate_students_are_free(students, start_datetime, end_datetime)

        return attrs

    def create(self, validated_data):
        students = validated_data.pop('students', [])

        with transaction.atomic():
            session = Session.objects.create(**validated_data)
            self.invited_students = self.save_students(session, students)

        return session


class SessionUpdateSerializer(SessionScheduleMixin, serializers.ModelSerializer):
    """The session and, when given, the students expected at it. Leaving 'students' out keeps the
    saved list untouched; sending it replaces the list."""

    name = serializers.CharField(max_length=255, required=True)
    assessment = serializers.PrimaryKeyRelatedField(queryset=Assessment.objects.all(), required=True)
    start_datetime = serializers.DateTimeField(required=True)
    students = serializers.PrimaryKeyRelatedField(queryset=student_queryset(), many=True, required=False)

    class Meta:
        model = Session
        fields = ['name', 'description', 'assessment', 'start_datetime', 'instructions',
                  'status', 'students']

    def validate(self, attrs):
        if self.instance.has_started:
            raise serializers.ValidationError("This session has already started and can no longer be changed!")

        start_datetime, end_datetime = self.apply_schedule(attrs)
        self.validate_start_is_ahead(start_datetime)

        students = attrs.get('students')
        if students:
            validate_students_are_free(students, start_datetime, end_datetime, exclude_session=self.instance)

        return attrs

    def update(self, instance, validated_data):
        students = validated_data.pop('students', None)

        schedule_changed = (
            validated_data['start_datetime'] != instance.start_datetime
            or validated_data['end_datetime'] != instance.end_datetime
        )

        with transaction.atomic():
            for attr, value in validated_data.items():
                setattr(instance, attr, value)
            instance.save()

            if students is not None:
                keep_ids = [student.id for student in students]
                instance.students.exclude(student_id__in=keep_ids).delete()
                self.invited_students = self.save_students(instance, students)
            else:
                self.invited_students = []

            if schedule_changed:
                # The time they were told about no longer holds, so everybody is told again. The
                # rows are put back to Pending by whoever queues the mails.
                self.invited_students = list(instance.students.select_related('student').all())

        return instance


class SessionStudentAddSerializer(serializers.Serializer):
    """Adds students to a session that already exists."""

    students = serializers.PrimaryKeyRelatedField(queryset=student_queryset(), many=True,
                                                  required=True, allow_empty=False)

    def validate_students(self, value):
        return validate_students_are_bookable(value)

    def validate(self, attrs):
        session = self.context['session']
        students = attrs['students']

        if session.state == Session.State.COMPLETED:
            raise serializers.ValidationError("This session is over and students can no longer be added to it!")

        already_added = session.students.filter(student__in=students).select_related('student')
        if already_added.exists():
            emails = ", ".join(row.student.email for row in already_added)
            raise serializers.ValidationError({'students': f"Student(s) {emails} have already been added to this session!"})

        validate_students_are_free(students, session.start_datetime, session.end_datetime,
                                   exclude_session=session)

        return attrs


class SessionInviteResendSerializer(serializers.Serializer):
    """Sends the invite mail again.

    Without 'students' everybody on the session is mailed; 'email_status' narrows that to the ones
    whose invite stands in a given state, which is how a batch of failures gets retried.
    """

    students = serializers.PrimaryKeyRelatedField(queryset=student_queryset(), many=True, required=False)
    email_status = serializers.ChoiceField(choices=SessionStudent.EmailStatus.choices, required=False)

    def validate(self, attrs):
        session = self.context['session']
        students = attrs.get('students')
        email_status = attrs.get('email_status')

        session_students = session.students.select_related('student', 'session__assessment')

        if students:
            # Membership is checked before any status filter, so a student who is on the session but
            # simply does not match the filter is never reported as missing from it.
            on_session = {row.student.email for row in session_students}
            missing = {student.email for student in students} - on_session
            if missing:
                raise serializers.ValidationError({'students': f"Student(s) {', '.join(sorted(missing))} are not on this session!"})

            session_students = session_students.filter(student__in=students)

        if email_status:
            session_students = session_students.filter(email_status=email_status)

        session_students = list(session_students)
        if not session_students:
            if email_status:
                raise serializers.ValidationError(f"This session has no students with a {email_status} invite to notify!")

            raise serializers.ValidationError("This session has no students to notify!")

        attrs['session_students'] = session_students

        return attrs


class SessionStatusSerializer(serializers.ModelSerializer):
    status = serializers.BooleanField(required=True)

    class Meta:
        model = Session
        fields = ['status']


class SessionDropdownSerializer(serializers.ModelSerializer):
    assessment_name = serializers.CharField(source='assessment.name', read_only=True)
    state = serializers.CharField(read_only=True)
    start_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")
    end_datetime = serializers.DateTimeField(format="%Y-%m-%d %H:%M:%S")

    class Meta:
        model = Session
        fields = ['id', 'name', 'assessment_name', 'start_datetime', 'end_datetime',
                  'duration', 'state']
