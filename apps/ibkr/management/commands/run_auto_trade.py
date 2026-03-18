"""
Management command: run_auto_trade

Usage:
    python manage.py run_auto_trade           # Live mode (places real orders)
    python manage.py run_auto_trade --dry-run # Dry-run (logs picks, no orders)
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run one auto-trade wheel strategy cycle.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Log what would be traded without placing any orders.',
        )

    def handle(self, *args, **options):
        from apps.ibkr.services.auto_trade_engine import run_auto_trade_cycle, get_month_progress

        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('🔵 DRY RUN — no orders will be placed'))

        progress = get_month_progress()
        self.stdout.write(
            f'📅 Month progress: ${progress["earned"]:.2f} earned of '
            f'${progress["goal"]:.2f} goal ({progress["pct"]}%)'
        )

        self.stdout.write('🤖 Starting auto-trade cycle...')
        summary = run_auto_trade_cycle(dry_run=dry_run)

        self.stdout.write('')
        self.stdout.write('─' * 50)
        self.stdout.write(f'  Trades placed : {summary["trades"]}')
        self.stdout.write(f'  Skipped       : {summary["skipped"]}')
        self.stdout.write(f'  Premium earned: ${summary["earned"]:.2f}')
        self.stdout.write(f'  Goal met      : {"✅ Yes" if summary["goal_met"] else "❌ Not yet"}')
        if summary['errors']:
            self.stdout.write(self.style.ERROR('  Errors:'))
            for err in summary['errors']:
                self.stdout.write(self.style.ERROR(f'    • {err}'))
        self.stdout.write('─' * 50)

        if summary['goal_met']:
            self.stdout.write(self.style.SUCCESS('✅ Monthly goal met!'))
        else:
            self.stdout.write(self.style.WARNING('⏳ Monthly goal not yet met.'))
