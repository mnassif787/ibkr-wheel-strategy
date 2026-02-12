"""
Management command to run health checks from command line
"""
from django.core.management.base import BaseCommand
from apps.ibkr.services.health_check import HealthCheckService


class Command(BaseCommand):
    help = 'Run comprehensive health check on all platform components'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('🏥 Running Platform Health Checks...'))
        self.stdout.write('')
        
        health_service = HealthCheckService()
        results = health_service.run_all_checks()
        
        self.stdout.write('')
        self.stdout.write('=' * 70)
        
        if results['overall_status'] == 'healthy':
            self.stdout.write(self.style.SUCCESS(f"✅ ALL SYSTEMS OPERATIONAL"))
        elif results['overall_status'] == 'warning':
            self.stdout.write(self.style.WARNING(f"⚠️  SOME ISSUES DETECTED"))
        else:
            self.stdout.write(self.style.ERROR(f"❌ CRITICAL ISSUES DETECTED"))
        
        self.stdout.write('=' * 70)
        self.stdout.write('')
        
        for check in results['checks']:
            if check['status'] == 'passed':
                status_msg = self.style.SUCCESS('✅ PASSED')
            elif check['status'] == 'warning':
                status_msg = self.style.WARNING('⚠️  WARNING')
            else:
                status_msg = self.style.ERROR('❌ FAILED')
            
            self.stdout.write(f"{check['icon']} {check['name']}: {status_msg}")
            self.stdout.write(f"   {check['message']}")
            
            if check['solution']:
                self.stdout.write(self.style.WARNING(f"   💡 Solution: {check['solution']}"))
            
            self.stdout.write('')
        
        passed = len([c for c in results['checks'] if c['status'] == 'passed'])
        warnings = len([c for c in results['checks'] if c['status'] == 'warning'])
        failed = len([c for c in results['checks'] if c['status'] == 'failed'])
        total = len(results['checks'])
        
        self.stdout.write('=' * 70)
        self.stdout.write(f"Summary: {passed} passed, {warnings} warnings, {failed} failed out of {total} checks")
        self.stdout.write('=' * 70)
