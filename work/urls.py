from django.urls import path

from work import views

urlpatterns = [
    path("app/", views.react_app, name="react-app"),
    path("app/<path:route>/", views.react_app, name="react-app-route"),
    path("", views.dashboard, name="dashboard"),
    path("taches/nouvelle/", views.create_assignment, name="assignment-create"),
    path("taches/<int:pk>/", views.assignment_detail, name="assignment-detail"),
    path(
        "taches/<int:pk>/progression.json",
        views.assignment_progress_json,
        name="assignment-progress-json",
    ),
    path("observable/", views.observable_export_page, name="observable-export"),
    path(
        "observable/progression.json",
        views.observable_progress_export,
        name="observable-progress-export",
    ),
    path("taches/<int:pk>/modifier/", views.edit_assignment, name="assignment-edit"),
    path("taches/<int:pk>/progression/", views.update_progress, name="progress-update"),
    path("taches/<int:pk>/commentaires/", views.add_comment, name="comment-add"),
    path("taches/<int:pk>/action/", views.assignment_action, name="assignment-action"),
    path("propositions/nouvelle/", views.create_proposal, name="proposal-create"),
    path("propositions/", views.proposal_list, name="proposal-list"),
    path("propositions/a-traiter/", views.proposal_queue, name="proposal-queue"),
    path(
        "propositions/<int:pk>/decision/", views.decide_proposal, name="proposal-decide"
    ),
    path("equipe/", views.team_summary, name="team-summary"),
    path(
        "equipe/<int:employee_id>/progressions.json",
        views.team_member_progress_json,
        name="team-member-progress-json",
    ),
    path("equipe/<int:employee_id>/", views.employee_detail, name="employee-detail"),
]
