"""
Context processors for IBKR app
Makes health check status available to all templates
"""
from apps.ibkr.services.health_check import get_health_check_service


def health_status(request):
    """Add health check status to template context"""
    try:
        health_service = get_health_check_service()
        quick_status = health_service.get_quick_status()
        
        return {
            'health_status': quick_status,
        }
    except Exception as e:
        return {
            'health_status': {
                'status': 'unknown',
                'icon': '❓',
                'message': 'Health check unavailable',
                'failed_count': 0,
                'warning_count': 0,
                'passed_count': 0,
                'total_count': 0,
            }
        }
