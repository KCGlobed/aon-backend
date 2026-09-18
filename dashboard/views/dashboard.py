"""The admin's home screen: where the platform stands right now.

Everything here is read-only and counted on the way out, so a screen that polls costs nothing but
the queries it runs. The heavy numbers - students, sessions, attempts - are aggregated in the
database rather than walked in Python, which is what keeps the summary a fixed cost as the data
grows.
"""

from datetime import timedelta

from django.db.models import Avg, Count, DurationField, Exists, ExpressionWrapper, F, Max, Min, OuterRef, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from assessment.models import Assessment, AssessmentQuestion
from candidate.models import TestAnswer, TestAttempt
from content.models import Question, QuestionHistory, QuestionOption, Sections
from dashboard.serializers import *
from session.models import Session, SessionStudent
from session.serializers.session_serializers import student_queryset
from users.renderers import UserRenderer
from aon_backend.utils import *
from aon_backend.permissions import RoleOrPermissionCheck

# How far back the trend looks when the request does not say, and the most it will ever look.
DEFAULT_TREND_DAYS = 30
MAX_TREND_DAYS = 365

DEFAULT_ROW_LIMIT = 10
MAX_ROW_LIMIT = 50


def dashboard_permission(permission_name):
    return [IsAuthenticated,
            RoleOrPermissionCheck.for_permission_or_roles(permission_name, [SuperAdmin])]


def read_days(request):
    """How far back the caller asked to look, held between one day and MAX_TREND_DAYS."""
    days = request.query_params.get('days')
    if not days:
        return DEFAULT_TREND_DAYS

    try:
        days = int(days)
    except ValueError:
        raise ValidationError("Invalid days value. Use a whole number.")

    if days < 1:
        raise ValidationError("Days must be at least 1.")

    return min(days, MAX_TREND_DAYS)


def read_limit(request):
    """How many rows the caller asked for, held between one and MAX_ROW_LIMIT."""
    limit = request.query_params.get('limit')
    if not limit:
        return DEFAULT_ROW_LIMIT

    try:
        limit = int(limit)
    except ValueError:
        raise ValidationError("Invalid limit value. Use a whole number.")

    if limit < 1:
        raise ValidationError("Limit must be at least 1.")

    return min(limit, MAX_ROW_LIMIT)


def student_count_data():
    """Students by where they stand, and how many have ever sat a test."""
    students = student_queryset()
    counts = students.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
    )
    attempted = students.filter(test_attempts__isnull=False).distinct().count()

    return {
        'total': counts['total'],
        'active': counts['active'],
        'inactive': counts['total'] - counts['active'],
        'attempted': attempted,
        'never_attempted': counts['total'] - attempted,
    }


def session_count_data(now):
    """Sessions by the switch the admin set, and by where they stand against the clock."""
    counts = Session.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status=True)),
        upcoming=Count('id', filter=Q(start_datetime__gt=now)),
        ongoing=Count('id', filter=Q(start_datetime__lte=now, end_datetime__gte=now)),
        completed=Count('id', filter=Q(end_datetime__lt=now)),
    )
    counts['inactive'] = counts['total'] - counts['active']

    return counts


def attempt_count_data(now):
    """The papers themselves: how many, how they stand, and what they average.

    The average is taken over submitted papers alone - one still being sat has only scored the
    sections handed in so far, and counting it would drag the figure down for no reason.
    """
    counts = TestAttempt.objects.aggregate(
        total=Count('id'),
        in_progress=Count('id', filter=Q(status=TestAttempt.Status.IN_PROGRESS)),
        submitted=Count('id', filter=Q(status=TestAttempt.Status.SUBMITTED)),
        today=Count('id', filter=Q(started_at__date=timezone.localdate(now))),
    )

    average = TestAttempt.objects.filter(
        status=TestAttempt.Status.SUBMITTED, max_marks__gt=0
    ).annotate(score_percentage=SCORE_PERCENTAGE).aggregate(average=Avg('score_percentage'))

    counts['average_percentage'] = rounded(average['average'])

    return counts


def window_start(days):
    """The instant a window of so many days back begins.

    The window is worked out in local dates and turned back into an instant, so a paper opened late
    in the evening counts towards the day the admin saw it happen.
    """
    first_day = timezone.localdate() - timedelta(days=days - 1)

    return first_day, timezone.make_aware(
        datetime.combine(first_day, datetime.min.time()), timezone.get_current_timezone()
    )


def attempt_trend_data(days):
    """Papers opened and handed in on each of the last so many days.

    Days nobody sat anything are filled in as zero rather than left out, so the series can be drawn
    straight onto a chart without the front end working out which dates are missing.
    """
    today = timezone.localdate()
    first_day, start = window_start(days)

    started = TestAttempt.objects.filter(started_at__gte=start).annotate(
        day=TruncDate('started_at')).values('day').annotate(count=Count('id'))
    submitted = TestAttempt.objects.filter(submitted_at__gte=start).annotate(
        day=TruncDate('submitted_at')).values('day').annotate(count=Count('id'))

    started_by_day = {row['day']: row['count'] for row in started}
    submitted_by_day = {row['day']: row['count'] for row in submitted}

    trend = []
    for offset in range(days):
        day = first_day + timedelta(days=offset)
        trend.append({
            'date': day.strftime("%Y-%m-%d"),
            'started': started_by_day.get(day, 0),
            'submitted': submitted_by_day.get(day, 0),
        })

    return {
        'days': days,
        'start_date': first_day.strftime("%Y-%m-%d"),
        'end_date': today.strftime("%Y-%m-%d"),
        'total_started': sum(row['started'] for row in trend),
        'total_submitted': sum(row['submitted'] for row in trend),
        'trend': trend,
    }


def averages_by_session(sessions):
    """What the papers handed in for each of these sessions averaged, read in one query.

    Kept apart from the counts the sessions are annotated with: averaging down a second join would
    let the roster multiply the attempts and quietly skew the figure.
    """
    rows = TestAttempt.objects.filter(
        session__in=sessions, status=TestAttempt.Status.SUBMITTED, max_marks__gt=0
    ).annotate(score_percentage=SCORE_PERCENTAGE).values('session_id').annotate(
        average=Avg('score_percentage'))

    return {row['session_id']: row['average'] for row in rows}


def session_overview_queryset():
    """Sessions carrying the counts the dashboard reads them by."""
    return Session.objects.select_related('assessment').annotate(
        total_students=Count('students', distinct=True),
        attempted=Count('attempts', distinct=True),
        submitted=Count('attempts', filter=Q(attempts__status=TestAttempt.Status.SUBMITTED), distinct=True),
    )


def session_overview_data(sessions, averages=None):
    """The sessions as the dashboard writes them out. Several lists drawn in one response share one
    set of averages rather than each reading its own."""
    if averages is None:
        averages = averages_by_session(sessions)

    return DashboardSessionSerializer(
        sessions, many=True, context={'session_averages': averages}).data


def invite_count_data():
    """Where the session invites stand across every session, counted in one pass."""
    counts = SessionStudent.objects.aggregate(
        total=Count('id'),
        **{
            status_value.lower(): Count('id', filter=Q(email_status=status_value))
            for status_value in SessionStudent.EmailStatus.values
        }
    )

    return counts


class GetDashboardSummaryView(APIView):
    """The headline counts: students, sessions, assessments, the question bank and the papers sat."""

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_summary")
    def get(self, request, format=None):
        now = timezone.now()

        assessments = Assessment.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status=True)),
        )
        sections = Sections.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status=True)),
        )
        questions = Question.objects.aggregate(
            total=Count('id'),
            active=Count('id', filter=Q(status=True)),
            easy=Count('id', filter=Q(difficulty_level=Question.DifficultyLevel.EASY)),
            medium=Count('id', filter=Q(difficulty_level=Question.DifficultyLevel.MEDIUM)),
            hard=Count('id', filter=Q(difficulty_level=Question.DifficultyLevel.HARD)),
        )

        return success_response(
            message="Success",
            data={
                'students': student_count_data(),
                'sessions': session_count_data(now),
                'assessments': {**assessments, 'inactive': assessments['total'] - assessments['active']},
                'sections': {**sections, 'inactive': sections['total'] - sections['active']},
                'questions': {**questions, 'inactive': questions['total'] - questions['active']},
                'attempts': attempt_count_data(now),
                'invites': invite_count_data(),
                'as_of': timezone.localtime(now).strftime("%Y-%m-%d %H:%M:%S"),
            },
            status_code=status.HTTP_200_OK
        )


class GetSessionOverviewView(APIView):
    """The sessions worth looking at, with how far their students have got.

    Without a 'state' the ongoing sessions come first and the upcoming ones after, which is the
    order the screen actually wants them in. Pass 'state' to read one group on its own.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_session_overview")
    def get(self, request, format=None):
        now = timezone.now()
        limit = read_limit(request)

        sessions_list = session_overview_queryset()

        session_status = request.query_params.get('status')
        if session_status:
            if session_status.lower() in ['true', '1', 't', 'yes']:
                sessions_list = sessions_list.filter(status=True)
            elif session_status.lower() in ['false', '0', 'f', 'no']:
                sessions_list = sessions_list.filter(status=False)
            else:
                raise ValidationError("Invalid status value. Use true or false.")

        state = request.query_params.get('state')
        if state:
            if state == Session.State.UPCOMING:
                sessions_list = sessions_list.filter(start_datetime__gt=now).order_by('start_datetime')
            elif state == Session.State.ONGOING:
                sessions_list = sessions_list.filter(start_datetime__lte=now, end_datetime__gte=now).order_by('end_datetime')
            elif state == Session.State.COMPLETED:
                sessions_list = sessions_list.filter(end_datetime__lt=now).order_by('-end_datetime')
            else:
                raise ValidationError("Invalid state value. Use Upcoming, Ongoing or Completed.")

            sessions = list(sessions_list[:limit])
        else:
            ongoing = list(sessions_list.filter(start_datetime__lte=now, end_datetime__gte=now).order_by('end_datetime')[:limit])
            upcoming = list(sessions_list.filter(start_datetime__gt=now).order_by('start_datetime')[:limit - len(ongoing)])
            sessions = ongoing + upcoming

        return success_response(
            message="Success",
            data=session_overview_data(sessions),
            status_code=status.HTTP_200_OK
        )


class GetRecentAttemptsView(APIView):
    """The papers most recently opened, whether or not they have been handed in yet."""

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_recent_attempts")
    def get(self, request, format=None):
        limit = read_limit(request)

        attempts = TestAttempt.objects.select_related('session__assessment', 'student')

        session_id = request.query_params.get('session')
        if session_id:
            attempts = attempts.filter(session_id=session_id)

        attempt_status = request.query_params.get('status')
        if attempt_status:
            if attempt_status not in TestAttempt.Status.values:
                raise ValidationError("Invalid status value. Use In Progress or Submitted.")
            attempts = attempts.filter(status=attempt_status)

        attempts = attempts.order_by('-started_at')[:limit]

        return success_response(
            message="Success",
            data=DashboardAttemptSerializer(attempts, many=True).data,
            status_code=status.HTTP_200_OK
        )


class GetAttemptTrendView(APIView):
    """How many papers were opened and handed in on each of the last so many days.

    Days nobody sat anything are filled in as zero rather than left out, so the series can be drawn
    straight onto a chart without the front end working out which dates are missing.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_attempt_trend")
    def get(self, request, format=None):
        return success_response(
            message="Success",
            data=attempt_trend_data(read_days(request)),
            status_code=status.HTTP_200_OK
        )


class GetTopStudentsView(APIView):
    """The best papers handed in, highest percentage first.

    Only submitted papers are ranked, and only those carrying marks at all: a session whose
    assessment was worth nothing has no percentage to place.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_top_students")
    def get(self, request, format=None):
        limit = read_limit(request)

        attempts = TestAttempt.objects.select_related('session__assessment', 'student').filter(
            status=TestAttempt.Status.SUBMITTED, max_marks__gt=0)

        session_id = request.query_params.get('session')
        if session_id:
            attempts = attempts.filter(session_id=session_id)

        assessment_id = request.query_params.get('assessment')
        if assessment_id:
            attempts = attempts.filter(session__assessment_id=assessment_id)

        attempts = attempts.annotate(score_percentage=SCORE_PERCENTAGE).order_by(
            '-score_percentage', 'submitted_at')[:limit]

        data = DashboardAttemptSerializer(attempts, many=True).data
        for rank, row in enumerate(data, start=1):
            row['rank'] = rank

        return success_response(message="Success", data=data, status_code=status.HTTP_200_OK)


def assessment_state_queryset(now):
    """Assessments carrying where each one stands against the clock.

    An assessment has no schedule of its own - it is a paper, not a sitting - so its state is read
    off the sessions holding it. The three flags are Exists subqueries rather than counts so an
    assessment booked into a hundred sessions costs the same to place as one booked into a single
    session.
    """
    sessions = Session.objects.filter(assessment=OuterRef('pk'))

    return Assessment.objects.annotate(
        has_sessions=Exists(sessions),
        has_ongoing=Exists(sessions.filter(start_datetime__lte=now, end_datetime__gte=now)),
        has_upcoming=Exists(sessions.filter(start_datetime__gt=now)),
    )


def assessment_status_data(now):
    """How many assessments stand in each state, counted in one pass.

    Archived is read off the switch the admin set: an assessment turned off is out of use whatever
    its sessions once did, so it is counted there and nowhere else. The rest are placed by what is
    booked - a sitting running now makes it active, one still to come makes it upcoming, and an
    assessment whose sessions have all ended is completed. Anything never scheduled at all is a
    draft, which is what keeps the five states adding back up to the total.
    """
    counts = assessment_state_queryset(now).aggregate(
        total=Count('id'),
        archived=Count('id', filter=Q(status=False)),
        active=Count('id', filter=Q(status=True, has_ongoing=True)),
        upcoming=Count('id', filter=Q(status=True, has_ongoing=False, has_upcoming=True)),
        completed=Count('id', filter=Q(status=True, has_ongoing=False, has_upcoming=False,
                                       has_sessions=True)),
        draft=Count('id', filter=Q(status=True, has_sessions=False)),
    )

    return counts


class GetAssessmentStatusView(APIView):
    """The assessments by state: total, active, completed, upcoming, archived - and the drafts.

    The five counts are of everything on record and never overlap, so they add back up to the
    total. Nothing is stored: each is read against the clock as the screen is opened, which is why
    an assessment moves from upcoming to active to completed on its own as its sessions run.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_assessment_status")
    def get(self, request, format=None):
        now = timezone.now()

        return success_response(
            message="Success",
            data={
                **assessment_status_data(now),
                'as_of': timezone.localtime(now).strftime("%Y-%m-%d %H:%M:%S"),
            },
            status_code=status.HTTP_200_OK
        )


# How long a paper took: read off the two stamps rather than the session's duration, so a student
# who handed in early is counted for the time actually spent.
TIME_TAKEN = ExpressionWrapper(F('submitted_at') - F('started_at'), output_field=DurationField())


def formatted_duration(delta):
    """A span of time written HH:MM:SS. Null when there is nothing to measure yet."""
    if delta is None:
        return None

    seconds = int(delta.total_seconds())

    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def duration_data(delta):
    """One span of time written three ways: the seconds to compute with, the minutes a test is
    talked about in, and the clock reading a screen shows."""
    return {
        'seconds': int(delta.total_seconds()) if delta is not None else None,
        'minutes': f"{delta.total_seconds() / 60:.2f}" if delta is not None else None,
        'display': formatted_duration(delta),
    }


def performance_attempts(request):
    """The papers this report covers, narrowed to one session or one assessment when asked.

    Both filters read the session the paper was sat for, so 'assessment' gathers every sitting of
    that test rather than only the one the caller happened to have open.
    """
    attempts = TestAttempt.objects.all()

    session_id = request.query_params.get('session')
    if session_id:
        attempts = attempts.filter(session_id=session_id)

    assessment_id = request.query_params.get('assessment')
    if assessment_id:
        attempts = attempts.filter(session__assessment_id=assessment_id)

    return attempts


def performance_data(attempts):
    """What the papers came to: how many were sat, what they scored, how long they took and how
    many passed.

    Everything but the headline count is read off submitted papers alone. One still being sat has
    scored the sections handed in so far and nothing for the rest, so letting it into the average
    would drag the figure down for no reason, and it has no finish time to measure at all.
    """
    counts = attempts.aggregate(
        total_attempts=Count('id'),
        in_progress=Count('id', filter=Q(status=TestAttempt.Status.IN_PROGRESS)),
        submitted=Count('id', filter=Q(status=TestAttempt.Status.SUBMITTED)),
        passed=Count('id', filter=Q(result=TestAttempt.Result.PASS)),
        failed=Count('id', filter=Q(result=TestAttempt.Result.FAIL)),
        pending=Count('id', filter=Q(result=TestAttempt.Result.PENDING)),
    )

    submitted = attempts.filter(status=TestAttempt.Status.SUBMITTED)

    # Only papers carrying marks at all are scored: a session whose assessment was worth nothing
    # has no share to average, and counting it as zero would report a failure nobody had.
    scores = submitted.filter(max_marks__gt=0).aggregate(
        average_score=Avg('total_marks'),
        average_percentage=Avg(SCORE_PERCENTAGE),
        highest_score=Max('total_marks'),
        lowest_score=Min('total_marks'),
        highest_percentage=Max(SCORE_PERCENTAGE),
        lowest_percentage=Min(SCORE_PERCENTAGE),
        average_max_marks=Avg('max_marks'),
    )

    timing = submitted.filter(submitted_at__isnull=False).aggregate(
        average=Avg(TIME_TAKEN), fastest=Min(TIME_TAKEN), slowest=Max(TIME_TAKEN))

    return {
        'total_attempts': counts['total_attempts'],
        'in_progress': counts['in_progress'],
        'submitted': counts['submitted'],
        'average_score': rounded(scores['average_score']),
        'average_percentage': rounded(scores['average_percentage']),
        'highest_score': rounded(scores['highest_score']),
        'highest_percentage': rounded(scores['highest_percentage']),
        'lowest_score': rounded(scores['lowest_score']),
        'lowest_percentage': rounded(scores['lowest_percentage']),
        'average_max_marks': rounded(scores['average_max_marks']),
        'average_completion_time': duration_data(timing['average']),
        'fastest_completion_time': duration_data(timing['fastest']),
        'slowest_completion_time': duration_data(timing['slowest']),
        'pass_fail': {
            'passed': counts['passed'],
            'failed': counts['failed'],
            # A paper still being sat is neither: it is judged only once it is handed in.
            'pending': counts['pending'],
            # Shares of the papers judged, not of every paper sat, so an ongoing session does not
            # read as a drop in the pass rate.
            'pass_percentage': percentage_of(counts['passed'], counts['passed'] + counts['failed']),
            'fail_percentage': percentage_of(counts['failed'], counts['passed'] + counts['failed']),
        },
    }


class GetAttemptPerformanceView(APIView):
    """How the papers sat are actually going: the count, the scores, the time taken and the split
    between passes and failures.

    Pass 'session' or 'assessment' to read one sitting or one test on its own; without either the
    figures cover every paper on record. Nothing is stored - each number is counted off the
    attempts as the screen is opened.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_attempt_performance")
    def get(self, request, format=None):
        now = timezone.now()

        return success_response(
            message="Success",
            data={
                **performance_data(performance_attempts(request)),
                'as_of': timezone.localtime(now).strftime("%Y-%m-%d %H:%M:%S"),
            },
            status_code=status.HTTP_200_OK
        )


def question_bank_queryset():
    """The bank carrying what each question has been through.

    Every flag is an Exists subquery rather than a join, so a question sat by a thousand students
    costs the same to place as one nobody has seen: the database stops at the first row it finds
    and never multiplies the bank out.
    """
    return Question.objects.annotate(
        is_placed=Exists(AssessmentQuestion.objects.filter(question=OuterRef('pk'))),
        is_served=Exists(TestAnswer.objects.filter(assessment_question__question=OuterRef('pk'))),
        has_correct_option=Exists(QuestionOption.objects.filter(question=OuterRef('pk'), right_option=True)),
        is_imported=Exists(QuestionHistory.objects.filter(
            question=OuterRef('pk'), action=QuestionHistory.Action.IMPORTED)),
    )


def question_stock_data():
    """What the bank holds and how much of it is still there to draw on.

    The bank has no review workflow of its own, so 'pending_review' is read off what would happen
    if the question went out: one carrying no right answer would mark every student wrong, which is
    the one fault worth stopping a paper for. Those and the switched-off ones are set aside first,
    and what is left - the questions actually fit to be drawn - is split three ways: served to a
    student already, committed to an assessment but not yet sat, or free. The five add back up to
    the total, so nothing in the bank is counted twice or goes missing.
    """
    fit = Q(status=True, has_correct_option=True)

    counts = question_bank_queryset().aggregate(
        total=Count('id'),
        imported=Count('id', filter=Q(is_imported=True)),
        used=Count('id', filter=Q(is_placed=True)),
        exhausted=Count('id', filter=fit & Q(is_served=True)),
        reserved=Count('id', filter=fit & Q(is_placed=True, is_served=False)),
        available=Count('id', filter=fit & Q(is_placed=False)),
        pending_review=Count('id', filter=Q(status=True, has_correct_option=False)),
        inactive=Count('id', filter=Q(status=False)),
    )

    counts['created'] = counts['total'] - counts['imported']
    # What is left to draw on before somebody has to write more, which is the number a bank runs
    # out on: a question already sat cannot go back out, and one already booked is spoken for.
    counts['usable_share'] = percentage_of(counts['available'], counts['total'])

    return counts


class GetQuestionStockView(APIView):
    """What the question bank holds: uploaded, used, exhausted, available and pending review.

    Every figure is counted off the bank as the screen is opened, so a question moves from
    available to exhausted on its own as soon as a student sits it.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_question_stock")
    def get(self, request, format=None):
        now = timezone.now()

        return success_response(
            message="Success",
            data={
                **question_stock_data(),
                'as_of': timezone.localtime(now).strftime("%Y-%m-%d %H:%M:%S"),
            },
            status_code=status.HTTP_200_OK
        )


def session_stock_queryset():
    """The sessions carrying whether anybody was booked in and whether anybody turned up.

    Both flags are Exists subqueries rather than joins: a session with two hundred students on its
    roster costs the same to place as an empty one, and neither count can multiply the other the
    way two joins down the same query would.
    """
    return Session.objects.annotate(
        has_students=Exists(SessionStudent.objects.filter(session=OuterRef('pk'))),
        has_attempts=Exists(TestAttempt.objects.filter(session=OuterRef('pk'))),
    )


def session_stock_data(now):
    """How many sessions there are and how far each has got.

    Two different things are being counted here, which is why the numbers do not add up in one
    line. 'allocated' and 'used' say what was done with a session - booked, then actually sat -
    while 'active', 'upcoming' and 'completed' say where it stands against the clock. A session
    can be completed and never used: the window closed and nobody turned up.
    """
    counts = session_stock_queryset().aggregate(
        total_available=Count('id'),
        allocated=Count('id', filter=Q(has_students=True)),
        used=Count('id', filter=Q(has_attempts=True)),
        active=Count('id', filter=Q(start_datetime__lte=now, end_datetime__gte=now)),
        upcoming=Count('id', filter=Q(start_datetime__gt=now)),
        completed=Count('id', filter=Q(end_datetime__lt=now)),
        disabled=Count('id', filter=Q(status=False)),
    )

    total = counts['total_available']
    counts['unallocated'] = total - counts['allocated']
    # Still to be sat: nobody has opened a paper for these, whether they are yet to run or ran
    # with nobody turning up.
    counts['remaining'] = total - counts['used']
    counts['used_share'] = percentage_of(counts['used'], total)
    counts['allocated_share'] = percentage_of(counts['allocated'], total)

    return counts


class GetSessionStockView(APIView):
    """The sessions by what has become of them: available, allocated, used, active, completed and
    remaining.

    Counted off the session table as the screen is opened, so a session moves from upcoming to
    active to completed on its own as its window passes.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("dashboard_session_stock")
    def get(self, request, format=None):
        now = timezone.now()

        return success_response(
            message="Success",
            data={
                **session_stock_data(now),
                'as_of': timezone.localtime(now).strftime("%Y-%m-%d %H:%M:%S"),
            },
            status_code=status.HTTP_200_OK
        )
