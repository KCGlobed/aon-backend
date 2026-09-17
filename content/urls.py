from django.urls import path
from content.views import *

urlpatterns = [
    path('get-section-listing/', GetSectionListingView.as_view(), name="get-section-listing"),
    path('create-section/', CreateSectionView.as_view(), name="create-section"),
    path('update-section/<int:pk>/', UpdateSectionView.as_view(), name="update-section"),
    path('change-section-status/<int:pk>/', ChangeSectionStatusView.as_view(), name="change-section-status"),
    path('delete-section/<int:pk>/', DeleteSectionView.as_view(), name="delete-section"),
    path('get-section-dropdown/', GetSectionDropdownView.as_view(), name="get-section-dropdown"),

    path('get-question-listing/', GetQuestionListingView.as_view(), name="get-question-listing"),
    path('get-question-detail/<int:pk>/', GetQuestionDetailView.as_view(), name="get-question-detail"),
    path('create-question/', CreateQuestionView.as_view(), name="create-question"),
    path('update-question/<int:pk>/', UpdateQuestionView.as_view(), name="update-question"),
    path('change-question-status/<int:pk>/', ChangeQuestionStatusView.as_view(), name="change-question-status"),
    path('delete-question/<int:pk>/', DeleteQuestionView.as_view(), name="delete-question"),
    path('import-question/', ImportQuestionView.as_view(), name="import-question"),
    path('get-question-history/<int:pk>/', GetQuestionHistoryView.as_view(), name="get-question-history"),
]
