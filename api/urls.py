from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from api import views

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
