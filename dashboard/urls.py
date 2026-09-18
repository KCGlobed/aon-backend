from django.urls import path
from dashboard.views import *

urlpatterns = [
    path('get-central-dashboard/', GetCentralDashboardView.as_view(), name="get-central-dashboard"),

    path('get-dashboard-summary/', GetDashboardSummaryView.as_view(), name="get-dashboard-summary"),
    path('get-assessment-status/', GetAssessmentStatusView.as_view(), name="get-assessment-status"),
    path('get-session-overview/', GetSessionOverviewView.as_view(), name="get-session-overview"),
    path('get-recent-attempts/', GetRecentAttemptsView.as_view(), name="get-recent-attempts"),
    path('get-attempt-performance/', GetAttemptPerformanceView.as_view(), name="get-attempt-performance"),
    path('get-question-stock/', GetQuestionStockView.as_view(), name="get-question-stock"),
    path('get-session-stock/', GetSessionStockView.as_view(), name="get-session-stock"),
    path('get-attempt-trend/', GetAttemptTrendView.as_view(), name="get-attempt-trend"),
    path('get-top-students/', GetTopStudentsView.as_view(), name="get-top-students"),
]
