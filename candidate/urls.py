from django.urls import path
from candidate.views import *

urlpatterns = [
    path('get-student-listing/', GetStudentListingView.as_view(), name="get-student-listing"),
    path('get-student-detail/<int:pk>/', GetStudentDetailView.as_view(), name="get-student-detail"),

    path('create-student/', CreateStudentView.as_view(), name="create-student"),
    path('update-student/<int:pk>/', UpdateStudentView.as_view(), name="update-student"),
    path('change-student-status/<int:pk>/', ChangeStudentStatusView.as_view(), name="change-student-status"),
    path('delete-student/<int:pk>/', DeleteStudentView.as_view(), name="delete-student"),

    path('import-student/', ImportStudentView.as_view(), name="import-student"),
    path('get-student-import-sample/', GetStudentImportSampleView.as_view(), name="get-student-import-sample"),

    path('get-student-session-result/<int:pk>/<int:session_id>/', GetStudentSessionResultView.as_view(), name="get-student-session-result"),

    path('get-my-sessions/', GetMySessionsView.as_view(), name="get-my-sessions"),

    path('start-test/<int:session_id>/', StartTestView.as_view(), name="start-test"),
    path('get-test-detail/<int:pk>/', GetTestDetailView.as_view(), name="get-test-detail"),

    path('get-section-questions/<int:pk>/<int:section_pk>/', GetSectionQuestionsView.as_view(), name="get-section-questions"),
    path('submit-section/<int:pk>/<int:section_pk>/', SubmitSectionView.as_view(), name="submit-section"),

    path('submit-test/<int:pk>/', SubmitTestView.as_view(), name="submit-test"),
    path('get-test-result/<int:pk>/', GetTestResultView.as_view(), name="get-test-result"),
]
