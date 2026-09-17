from django.urls import path
from assessment.views import *

urlpatterns = [
    path('get-assessment-listing/', GetAssessmentListingView.as_view(), name="get-assessment-listing"),
    path('get-assessment-detail/<int:pk>/', GetAssessmentDetailView.as_view(), name="get-assessment-detail"),

    path('create-assessment/', CreateAssessmentView.as_view(), name="create-assessment"),
    path('update-assessment/<int:pk>/', UpdateAssessmentView.as_view(), name="update-assessment"),

    path('get-assessment-pattern/<int:pk>/', GetAssessmentPatternView.as_view(), name="get-assessment-pattern"),
    path('get-question-dropdown/<int:section_id>/', GetSectionQuestionDropdownView.as_view(), name="get-question-dropdown"),

    path('change-assessment-status/<int:pk>/', ChangeAssessmentStatusView.as_view(), name="change-assessment-status"),
    path('delete-assessment/<int:pk>/', DeleteAssessmentView.as_view(), name="delete-assessment"),
    path('get-assessment-dropdown/', GetAssessmentDropdownView.as_view(), name="get-assessment-dropdown"),
]
