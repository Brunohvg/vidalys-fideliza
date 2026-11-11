from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def health(request):
    """Liveness: não consulta banco nem expõe dados internos."""
    return JsonResponse({"status": "ok", "service": "vidalys-fideliza"})

@require_GET
def ready(request):
    """Readiness: conectividade com PostgreSQL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})
