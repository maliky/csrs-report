from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api import views
from agenda import api as agenda_api

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
    path("visits/", agenda_api.VisitListCreateView.as_view(), name="visit-list"),
    path(
        "visits/<int:pk>/departure/",
        agenda_api.VisitDepartureView.as_view(),
        name="visit-departure",
    ),
    path(
        "availability/",
        agenda_api.AvailabilityListCreateView.as_view(),
        name="availability-list",
    ),
    path(
        "availability/<int:pk>/",
        agenda_api.AvailabilityDetailView.as_view(),
        name="availability-detail",
    ),
    path(
        "availability/<int:pk>/cancel/",
        agenda_api.AvailabilityCancelView.as_view(),
        name="availability-cancel",
    ),
    path(
        "agenda/preview/", agenda_api.AgendaPreviewView.as_view(), name="agenda-preview"
    ),
    path("agenda/draft/", agenda_api.AgendaDraftView.as_view(), name="agenda-draft"),
    path(
        "agenda/versions/",
        agenda_api.AgendaVersionListCreateView.as_view(),
        name="agenda-version-list",
    ),
    path(
        "agenda/versions/<int:pk>/pdf/",
        agenda_api.AgendaVersionPdfView.as_view(),
        name="agenda-version-pdf",
    ),
    path("dashboard/", views.DashboardView.as_view(), name="dashboard"),
    path(
        "planning/options/", views.PlanningOptionsView.as_view(), name="planning-options"
    ),
    path(
        "planning/preview/", views.PlanningPreviewView.as_view(), name="planning-preview"
    ),
    path("tasks/", views.TaskCreateView.as_view(), name="task-create"),
    path(
        "task-management/",
        views.TaskManagementView.as_view(),
        name="task-management",
    ),
    path(
        "tasks/bulk-delete/",
        views.TaskBulkDeleteView.as_view(),
        name="task-bulk-delete",
    ),
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
