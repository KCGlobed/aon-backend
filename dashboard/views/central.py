"""The central dashboard: the whole platform on one screen.

Five blocks, each answering a different question the admin opens the screen with - what the
platform has been doing, whether the candidates are turning up, whether the question bank is in
good order, what the assessments are being used for, and how much of each session was actually
sat.

It is one call rather than five so the blocks agree with each other: read separately they would be
counted at slightly different moments, and an attempt landing in between would have the session
block disagreeing with the candidate block. Everything is aggregated in the database, so the cost
is a fixed handful of queries however much data sits behind it.
"""

from django.db.models import Avg, Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView

from assessment.models import Assessment
from candidate.models import TestAttempt
from content.models import Question, Sections
from dashboard.serializers import *
from dashboard.views.dashboard import (attempt_count_data, attempt_trend_data, averages_by_session,
                                       dashboard_permission, invite_count_data, read_days,
                                       read_limit, session_count_data, session_overview_data,
                                       session_overview_queryset, student_count_data,
                                       window_start)
from session.models import Session, SessionStudent
from session.serializers.session_serializers import student_queryset
from users.renderers import UserRenderer
from aon_backend.utils import *

# The embedded lists are meant to be glanced at rather than paged through; the listing APIs are
# there for anybody who wants the whole of one.
EMBEDDED_ROWS = 5


def platform_activity_data(now, days, students, sessions):
    """What the platform holds, and what has happened on it lately.

    The counts are everything on record; the 'recent' block is the same story over the window the
    caller asked for, which is what tells an admin whether the place is actually being used.
    """
    first_day, start = window_start(days)

    return {
        'students': students,
        'sessions': sessions,
        'assessments': count_with_inactive(Assessment.objects),
        'sections': count_with_inactive(Sections.objects),
        'questions': count_with_inactive(Question.objects),
        'attempts': attempt_count_data(now),
        'invites': invite_count_data(),
        'recent': {
            'days': days,
            'start_date': first_day.strftime("%Y-%m-%d"),
            'end_date': timezone.localdate().strftime("%Y-%m-%d"),
            'students_added': student_queryset().filter(created_at__gte=start).count(),
            'sessions_created': Session.objects.filter(created_at__gte=start).count(),
            'assessments_created': Assessment.objects.filter(created_at__gte=start).count(),
            'questions_added': Question.objects.filter(created_at__gte=start).count(),
            'attempts_started': TestAttempt.objects.filter(started_at__gte=start).count(),
            'attempts_submitted': TestAttempt.objects.filter(submitted_at__gte=start).count(),
        },
        'trend': attempt_trend_data(days)['trend'],
    }


def count_with_inactive(manager):
    """Total, on and off, for one of the switched tables."""
    counts = manager.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status=True)),
    )
    counts['inactive'] = counts['total'] - counts['active']

    return counts


def candidate_activity_data(now, limit, students):
    """Whether the candidates are actually turning up, and how they are doing when they do.

    'sitting_now' is read against the clock rather than off the status alone: a paper left open by
    a student who walked away stays In Progress until something reads it, so counting those would
    report people at desks they left days ago.
    """
    seats = SessionStudent.objects.count()
    attempts = TestAttempt.objects.count()

    sitting_now = TestAttempt.objects.filter(
        status=TestAttempt.Status.IN_PROGRESS,
        session__start_datetime__lte=now,
        session__end_datetime__gte=now,
    ).count()

    submitted = TestAttempt.objects.filter(status=TestAttempt.Status.SUBMITTED)

    scored = submitted.filter(max_marks__gt=0).annotate(score_percentage=SCORE_PERCENTAGE)
    bands = scored.aggregate(
        below_40=Count('id', filter=Q(score_percentage__lt=40)),
        between_40_60=Count('id', filter=Q(score_percentage__gte=40, score_percentage__lt=60)),
        between_60_80=Count('id', filter=Q(score_percentage__gte=60, score_percentage__lt=80)),
        above_80=Count('id', filter=Q(score_percentage__gte=80)),
        average=Avg('score_percentage'),
    )
    average = bands.pop('average')

    return {
        'total_students': students['total'],
        'active_students': students['active'],
        'inactive_students': students['inactive'],
        'attempted': students['attempted'],
        'never_attempted': students['never_attempted'],
        'sitting_now': sitting_now,
        'submitted_today': submitted.filter(submitted_at__date=timezone.localdate(now)).count(),
        'booked_seats': seats,
        'attempts': attempts,
        # A student booked into two sessions counts twice here, once for each seat, which is what
        # makes this a measure of turnout rather than of headcount.
        'turnout': percentage_of(attempts, seats),
        'completion_rate': percentage_of(submitted.count(), attempts),
        'average_percentage': rounded(average),
        'score_bands': bands,
        'recent_attempts': DashboardAttemptSerializer(
            TestAttempt.objects.select_related('session__assessment', 'student').order_by('-started_at')[:limit],
            many=True).data,
        'top_students': top_student_data(limit),
    }


def top_student_data(limit):
    """The best papers handed in, highest first, each carrying its place."""
    attempts = TestAttempt.objects.select_related('session__assessment', 'student').filter(
        status=TestAttempt.Status.SUBMITTED, max_marks__gt=0
    ).annotate(score_percentage=SCORE_PERCENTAGE).order_by('-score_percentage', 'submitted_at')[:limit]

    data = DashboardAttemptSerializer(attempts, many=True).data
    for rank, row in enumerate(data, start=1):
        row['rank'] = rank

    return data


def question_bank_data(limit):
    """What is in the bank and whether it is fit to be drawn on.

    'unused' and 'without_correct_option' are the two worth acting on: the first is bank nobody is
    testing with, the second is a question that would mark every student wrong if it ever went out.
    """
    questions = Question.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(status=True)),
        easy=Count('id', filter=Q(difficulty_level=Question.DifficultyLevel.EASY)),
        medium=Count('id', filter=Q(difficulty_level=Question.DifficultyLevel.MEDIUM)),
        hard=Count('id', filter=Q(difficulty_level=Question.DifficultyLevel.HARD)),
    )
    questions['inactive'] = questions['total'] - questions['active']

    sections = Sections.objects.annotate(
        total_questions=Count('questions', distinct=True),
        active_questions=Count('questions', filter=Q(questions__status=True), distinct=True),
        easy=Count('questions', filter=Q(questions__difficulty_level=Question.DifficultyLevel.EASY), distinct=True),
        medium=Count('questions', filter=Q(questions__difficulty_level=Question.DifficultyLevel.MEDIUM), distinct=True),
        hard=Count('questions', filter=Q(questions__difficulty_level=Question.DifficultyLevel.HARD), distinct=True),
    ).order_by('-total_questions', 'name')[:limit]

    return {
        'questions': questions,
        'sections': count_with_inactive(Sections.objects),
        'unused': Question.objects.filter(assessment_questions__isnull=True).count(),
        'without_correct_option': Question.objects.exclude(options__right_option=True).count(),
        'by_section': [
            {
                'id': section.pk,
                'name': section.name,
                'section_id': section.section_id,
                'status': section.status,
                'total_questions': section.total_questions,
                'active_questions': section.active_questions,
                'easy': section.easy,
                'medium': section.medium,
                'hard': section.hard,
            }
            for section in sections
        ],
    }


def assessment_data(limit):
    """The assessments, and what each has actually been used for.

    The per-assessment figures are read in their own grouped queries and stitched together here:
    counting sessions, seats and attempts down one set of joins would let each multiply the others.
    """
    counts = count_with_inactive(Assessment.objects)
    scheduled = Assessment.objects.filter(sessions__isnull=False).distinct().count()

    sessions_by_assessment = {
        row['assessment_id']: row['sessions']
        for row in Session.objects.values('assessment_id').annotate(sessions=Count('id'))
    }
    seats_by_assessment = {
        row['session__assessment_id']: row['seats']
        for row in SessionStudent.objects.values('session__assessment_id').annotate(seats=Count('id'))
    }
    attempts_by_assessment = {
        row['session__assessment_id']: row
        for row in TestAttempt.objects.annotate(score_percentage=SCORE_PERCENTAGE).values(
            'session__assessment_id').annotate(
            attempted=Count('id'),
            submitted=Count('id', filter=Q(status=TestAttempt.Status.SUBMITTED)),
            average=Avg('score_percentage', filter=Q(status=TestAttempt.Status.SUBMITTED, max_marks__gt=0)),
        )
    }

    ranked = sorted(
        Assessment.objects.all(),
        key=lambda assessment: (sessions_by_assessment.get(assessment.pk, 0),
                                attempts_by_assessment.get(assessment.pk, {}).get('attempted', 0)),
        reverse=True,
    )[:limit]

    utilisation = []
    for assessment in ranked:
        seats = seats_by_assessment.get(assessment.pk, 0)
        attempts = attempts_by_assessment.get(assessment.pk, {})
        attempted = attempts.get('attempted', 0)

        utilisation.append({
            'id': assessment.pk,
            'name': assessment.name,
            'duration': assessment.duration,
            'number_of_questions': assessment.number_of_questions,
            'total_marks': str(assessment.total_marks),
            'status': assessment.status,
            'total_sessions': sessions_by_assessment.get(assessment.pk, 0),
            'booked_seats': seats,
            'attempted': attempted,
            'submitted': attempts.get('submitted', 0),
            'turnout': percentage_of(attempted, seats),
            'average_percentage': rounded(attempts.get('average')),
        })

    return {
        **counts,
        'scheduled': scheduled,
        'never_scheduled': counts['total'] - scheduled,
        'utilisation': utilisation,
    }


def session_utilisation_data(now, limit, sessions_counts):
    """How much of what was booked was actually used.

    A seat is one student on one session. 'turnout' is the share of those seats somebody sat down
    at; 'completion_rate' is the share of the papers opened that were handed in. A session nobody
    turned up to reads zero on both rather than dropping out of the figures.
    """
    seats = SessionStudent.objects.count()

    attempts = TestAttempt.objects.aggregate(
        attempted=Count('id'),
        submitted=Count('id', filter=Q(status=TestAttempt.Status.SUBMITTED)),
    )

    sessions = session_overview_queryset()
    ongoing = list(sessions.filter(start_datetime__lte=now, end_datetime__gte=now).order_by('end_datetime')[:limit])
    upcoming = list(sessions.filter(start_datetime__gt=now).order_by('start_datetime')[:limit])
    completed = list(sessions.filter(end_datetime__lt=now).order_by('-end_datetime')[:limit])

    # All three lists share one reading of the averages rather than each fetching its own.
    averages = averages_by_session(ongoing + upcoming + completed)

    return {
        **sessions_counts,
        'booked_seats': seats,
        'attempted': attempts['attempted'],
        'submitted': attempts['submitted'],
        'not_started': max(0, seats - attempts['attempted']),
        'turnout': percentage_of(attempts['attempted'], seats),
        'completion_rate': percentage_of(attempts['submitted'], attempts['attempted']),
        'ongoing_sessions': session_overview_data(ongoing, averages),
        'upcoming_sessions': session_overview_data(upcoming, averages),
        'completed_sessions': session_overview_data(completed, averages),
    }


class GetCentralDashboardView(APIView):
    """The whole platform on one screen, in five blocks.

    'days' sets the window the activity block and the chart series look back over, and 'limit' how
    many rows each embedded list carries. Neither changes the counts themselves, which are always
    of everything on record.
    """

    renderer_classes = [UserRenderer]
    permission_classes = dashboard_permission("central_dashboard")
    def get(self, request, format=None):
        now = timezone.now()
        days = read_days(request)
        limit = read_limit(request) if request.query_params.get('limit') else EMBEDDED_ROWS

        # Counted once and shared: two blocks report the same students and the same sessions, and
        # reading them twice would both cost more and let the two halves of the screen disagree.
        students = student_count_data()
        sessions = session_count_data(now)

        return success_response(
            message="Success",
            data={
                'platform_activity': platform_activity_data(now, days, students, sessions),
                'candidate_activity': candidate_activity_data(now, limit, students),
                'question_bank': question_bank_data(limit),
                'assessments': assessment_data(limit),
                'session_utilisation': session_utilisation_data(now, limit, sessions),
                'as_of': timezone.localtime(now).strftime("%Y-%m-%d %H:%M:%S"),
            },
            status_code=status.HTTP_200_OK
        )
