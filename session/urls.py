from django.urls import path
from session.views import *

urlpatterns = [
    path('get-session-listing/', GetSessionListingView.as_view(), name="get-session-listing"),
    path('get-session-detail/<int:pk>/', GetSessionDetailView.as_view(), name="get-session-detail"),

    path('create-session/', CreateSessionView.as_view(), name="create-session"),
    path('update-session/<int:pk>/', UpdateSessionView.as_view(), name="update-session"),

    path('get-session-student-listing/<int:pk>/', GetSessionStudentListingView.as_view(), name="get-session-student-listing"),
    path('get-session-invite-status/<int:pk>/', GetSessionInviteStatusView.as_view(), name="get-session-invite-status"),

    path('get-student-attempt-detail/<int:pk>/', GetStudentAttemptDetailView.as_view(), name="get-student-attempt-detail"),

    path('add-session-students/<int:pk>/', AddSessionStudentsView.as_view(), name="add-session-students"),
    path('remove-session-student/<int:pk>/<int:student_id>/', RemoveSessionStudentView.as_view(), name="remove-session-student"),
    path('resend-session-invite/<int:pk>/', ResendSessionInviteView.as_view(), name="resend-session-invite"),

    path('change-session-status/<int:pk>/', ChangeSessionStatusView.as_view(), name="change-session-status"),
    path('delete-session/<int:pk>/', DeleteSessionView.as_view(), name="delete-session"),

    path('import-student/', ImportStudentView.as_view(), name="import-student"),
    path('get-student-import-sample/', GetStudentImportSampleView.as_view(), name="get-student-import-sample"),

    path('get-student-dropdown/', GetSessionStudentDropdownView.as_view(), name="get-student-dropdown"),
    path('get-session-dropdown/', GetSessionDropdownView.as_view(), name="get-session-dropdown"),
]
