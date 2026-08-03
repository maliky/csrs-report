from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api import views
from processes import api as process_api

app_name = "api"

urlpatterns = [
    path("openapi/", SpectacularAPIView.as_view(), name="openapi"),
    path(
        "documentation/",
        SpectacularSwaggerView.as_view(url_name="api:openapi"),
        name="documentation",
    ),
    path("session/", views.SessionView.as_view(), name="session"),
    path("session/logout/", views.LogoutView.as_view(), name="logout"),
    path("processes/", process_api.ProcessListView.as_view(), name="process-list"),
    path(
        "processes/mission-orders/",
        process_api.MissionCreateView.as_view(),
        name="mission-create",
    ),
    path(
        "processes/mission-orders/options/",
        process_api.MissionOptionsView.as_view(),
        name="mission-options",
    ),
    path(
        "processes/<int:pk>/",
        process_api.ProcessDetailView.as_view(),
        name="process-detail",
    ),
    path(
        "processes/<int:pk>/actions/",
        process_api.ProcessActionView.as_view(),
        name="process-action",
    ),
    path(
        "processes/<int:pk>/documents/",
        process_api.ProcessDocumentUploadView.as_view(),
        name="process-document-upload",
    ),
    path(
        "processes/<int:pk>/documents/<int:document_pk>/content/",
        process_api.ProcessDocumentContentView.as_view(),
        name="process-document-content",
    ),
    path(
        "processes/<int:pk>/export/",
        process_api.ProcessExportView.as_view(),
        name="process-export",
    ),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "planning/options/", views.PlanningOptionsView.as_view(), name="planning-options"
    ),
    path(
        "planning/preview/", views.PlanningPreviewView.as_view(), name="planning-preview"
    ),
    path("tasks/", views.TaskCreateView.as_view(), name="task-create"),
    path("tasks/<int:pk>/", views.TaskDetailView.as_view(), name="task-detail"),
    path(
        "tasks/<int:pk>/progress/", views.TaskProgressView.as_view(), name="task-progress"
    ),
    path(
        "tasks/<int:pk>/observations/",
        views.TaskObservationView.as_view(),
        name="task-observation",
    ),
    path(
        "tasks/<int:pk>/transition/",
        views.TaskTransitionView.as_view(),
        name="task-transition",
    ),
    path("proposals/", views.ProposalListCreateView.as_view(), name="proposal-list"),
    path(
        "proposals/<int:pk>/",
        views.ProposalDetailView.as_view(),
        name="proposal-detail",
    ),
    path(
        "proposals/<int:pk>/resubmit/",
        views.ProposalResubmitView.as_view(),
        name="proposal-resubmit",
    ),
    path(
        "proposals/<int:pk>/decision/",
        views.ProposalDecisionView.as_view(),
        name="proposal-decision",
    ),
    path("team/", views.TeamView.as_view(), name="team"),
    path("team/<int:pk>/", views.TeamEmployeeView.as_view(), name="team-employee"),
]
