import logging
import threading
import time

from django.conf import settings
from django.core.mail import send_mail
from django.db import connections, transaction
from django.template import loader
from django.utils import timezone

from aon_backend.utils import getSMTPConfiguration, get_smtp_default_from_email

logger = logging.getLogger()

INVITE_SUBJECT = "You have been scheduled for {assessment_name}"
DATETIME_FORMAT = "%d %b %Y, %I:%M %p"

# A status write that loses a race with another connection is retried rather than
# reported, since the mail it describes has already gone out.
STATUS_WRITE_ATTEMPTS = 4
STATUS_WRITE_RETRY_SECONDS = 0.2


def format_datetime(value):
    local_value = timezone.localtime(value)
    return f"{local_value.strftime(DATETIME_FORMAT)} ({local_value.tzname()})"


def build_invite_context(session_student):
    session = session_student.session
    student = session_student.student
    full_name = " ".join(filter(None, [student.first_name, student.last_name])).strip()

    return {
        'name': full_name or student.email,
        'session_name': session.name,
        'assessment_name': session.assessment.name,
        'start_datetime': format_datetime(session.start_datetime),
        'end_datetime': format_datetime(session.end_datetime),
        'duration': session.duration,
        'number_of_questions': session.assessment.number_of_questions,
        'total_marks': session.assessment.total_marks,
        'application_id': student.application_id or '',
        'instructions': session.instructions or session.assessment.instructions,
        'login_link': f"{settings.ADMIN_BASE_URL}/student/login/",
    }


def record_invite_status(session_student, mark, *args):
    """Writes an invite's outcome back to its row, retrying a few times.

    The database can refuse a write for a moment while another connection holds the row, and the
    mails are sent from a thread of their own, so a single refusal is not worth turning into a
    reported failure. A row that still cannot be written is left alone and logged.
    """
    for attempt in range(1, STATUS_WRITE_ATTEMPTS + 1):
        try:
            mark(*args)
            return True
        except Exception as error:
            if attempt == STATUS_WRITE_ATTEMPTS:
                logger.error(
                    f"The invite status for session student {session_student.pk} could not be "
                    f"recorded after {STATUS_WRITE_ATTEMPTS} attempts: {error}"
                )
                return False

            time.sleep(STATUS_WRITE_RETRY_SECONDS * attempt)


def send_session_invites(session_students):
    """Mails every student their session details.

    One bad address is recorded against that student alone and does not hold up the rest, and a
    missing SMTP configuration leaves the session itself intact - the invites can be sent again
    once the configuration is in place.
    """
    session_students = list(session_students)
    summary = {'total': len(session_students), 'sent': 0, 'failed': 0}
    if not session_students:
        return summary

    connection = None
    connection_error = ''
    try:
        connection = getSMTPConfiguration()
        from_email = get_smtp_default_from_email()
    except Exception as error:
        connection_error = str(error)
        logger.error(f"Session invite mail could not reach the mail server: {connection_error}")

    for session_student in session_students:
        if connection_error:
            record_invite_status(session_student, session_student.mark_email_failed, connection_error)
            summary['failed'] += 1
            continue

        try:
            context = build_invite_context(session_student)
            html_message = loader.render_to_string('session_invite_email.html', context)
            message = (
                f"Hi {context['name']}, you have been scheduled for {context['assessment_name']}. "
                f"It starts on {context['start_datetime']} and ends on {context['end_datetime']}."
            )
            send_mail(
                INVITE_SUBJECT.format(assessment_name=context['assessment_name']),
                message,
                from_email,
                [session_student.student.email],
                html_message=html_message,
                connection=connection,
            )
        except Exception as error:
            logger.error(f"Session invite mail to {session_student.student.email} failed: {error}")
            record_invite_status(session_student, session_student.mark_email_failed, error)
            summary['failed'] += 1
            continue

        # The mail has left. Anything that goes wrong from here is bookkeeping, and is deliberately
        # kept out of the try above: recording a delivered invite as Failed would have the admin
        # send it a second time.
        record_invite_status(session_student, session_student.mark_email_sent)
        summary['sent'] += 1

    if connection is not None:
        try:
            connection.close()
        except Exception:
            pass

    return summary


def deliver_invites(session_student_ids):
    """The body of the background thread: re-reads the rows on this thread's own connection, mails
    them, and hands the connection back so it is not left open for the life of the thread."""
    from session.models import SessionStudent

    try:
        session_students = list(
            SessionStudent.objects.select_related('student', 'session__assessment')
            .filter(id__in=session_student_ids)
        )
        summary = send_session_invites(session_students)
        logger.info(f"Session invites delivered in the background: {summary}")
    except Exception as error:
        logger.error(f"Background session invite delivery failed: {error}")
    finally:
        connections.close_all()


def queue_session_invites(session_students):
    """Hands the invites to a background thread so the caller's request returns without waiting on
    the mail server.

    The rows are marked Pending before the request returns, so the session's student listing shows
    where each invite stands straight away. Anything still Pending or Failed can be put through
    again with the resend API - worth knowing, because a thread does not survive a restart of the
    process the way a real task queue would.
    """
    from session.models import SessionStudent

    session_students = list(session_students)
    summary = {'total': len(session_students), 'queued': 0}
    if not session_students:
        return summary

    session_student_ids = [session_student.id for session_student in session_students]
    SessionStudent.objects.filter(id__in=session_student_ids).update(
        email_status=SessionStudent.EmailStatus.PENDING,
        email_sent=False,
        email_error='',
        updated_at=timezone.now(),
    )

    if not getattr(settings, 'SEND_SESSION_INVITES_IN_BACKGROUND', True):
        # Turned off so that a caller which needs the outcome in hand - a management command, or a
        # test - can have the mails go out then and there. The summary then carries 'sent' and
        # 'failed' in place of 'queued', which is what tells the two modes apart.
        return send_session_invites(session_students)

    def start_delivery():
        threading.Thread(
            target=deliver_invites,
            args=(session_student_ids,),
            name=f"session-invites-{session_student_ids[0]}",
            daemon=True,
        ).start()

    # Waiting for the commit keeps the thread from reading rows that its own connection cannot see
    # yet. Outside a transaction this runs immediately.
    transaction.on_commit(start_delivery)

    summary['queued'] = len(session_student_ids)

    return summary
