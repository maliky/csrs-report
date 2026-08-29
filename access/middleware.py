"""Apply and audit a superuser's session-scoped simulated identity."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse, JsonResponse

from access.impersonation import ROLE_SIMULATION_SESSION_KEY, end_role_simulation
from access.models import RoleSimulation, RoleSimulationAction


class RoleSimulationMiddleware:
    """Expose a selected user to downstream authorization and audit writes."""

    safe_methods = frozenset({"GET", "HEAD", "OPTIONS"})
    lifecycle_path = "/api/v1/session/impersonation/"
    logout_paths = frozenset({"/api/v1/session/logout/", "/deconnexion/"})
    protected_mutation_paths = frozenset(
        {"/api/v1/me/profile/", "/api/v1/session/password/"}
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        administrator = request.user
        request.real_user = administrator  # type: ignore[attr-defined]
        simulation_id = request.session.get(ROLE_SIMULATION_SESSION_KEY)
        if not simulation_id or not administrator.is_authenticated:
            return self.get_response(request)

        simulation = (
            RoleSimulation.objects.select_related("administrator", "target")
            .filter(pk=simulation_id, ended_at__isnull=True)
            .first()
        )
        valid = bool(
            simulation
            and administrator.is_active
            and administrator.is_superuser
            and simulation.administrator_id == administrator.pk
            and simulation.target is not None
            and simulation.target.is_active
            and not simulation.target.is_superuser
            and not simulation.target.is_it_admin
        )
        if not valid:
            if simulation is not None:
                end_role_simulation(simulation, reason="target_unavailable")
            request.session.pop(ROLE_SIMULATION_SESSION_KEY, None)
            return self.get_response(request)

        if request.path in self.logout_paths:
            end_role_simulation(simulation, reason="logout")
            request.session.pop(ROLE_SIMULATION_SESSION_KEY, None)
            return self.get_response(request)

        request.role_simulation = simulation  # type: ignore[attr-defined]
        request.user = simulation.target
        if request.method in self.safe_methods or request.path == self.lifecycle_path:
            return self.get_response(request)

        action = RoleSimulationAction.objects.create(
            simulation=simulation,
            method=request.method,
            path=request.path[:512],
        )
        if request.path in self.protected_mutation_paths:
            response = JsonResponse(
                {
                    "error": {
                        "code": "impersonation_protected_operation",
                        "message": (
                            "Revenez en mode administrateur pour modifier un compte."
                        ),
                        "fields": {},
                    }
                },
                status=403,
            )
        else:
            response = self.get_response(request)
        action.status_code = response.status_code
        action.save(update_fields=["status_code"])
        return response
