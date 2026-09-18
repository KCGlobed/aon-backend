from django.urls import path
from candidate.views import *

urlpatterns = [
    path('get-my-sessions/', GetMySessionsView.as_view(), name="get-my-sessions"),

    path('start-test/<int:session_id>/', StartTestView.as_view(), name="start-test"),
    path('get-test-detail/<int:pk>/', GetTestDetailView.as_view(), name="get-test-detail"),

    path('get-section-questions/<int:pk>/<int:section_pk>/', GetSectionQuestionsView.as_view(), name="get-section-questions"),
    path('submit-section/<int:pk>/<int:section_pk>/', SubmitSectionView.as_view(), name="submit-section"),

    path('submit-test/<int:pk>/', SubmitTestView.as_view(), name="submit-test"),
    path('get-test-result/<int:pk>/', GetTestResultView.as_view(), name="get-test-result"),
]
