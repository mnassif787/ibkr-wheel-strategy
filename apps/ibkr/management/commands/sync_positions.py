"""
Management command to sync trading positions from IBKR
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.ibkr.services.ibkr_client import IBKRClient
from apps.ibkr.models import Stock, Option, OptionPosition
from decimal import Decimal
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Sync trading positions from IBKR Gateway/TWS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be synced without saving to database',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('🔍 DRY RUN MODE - No changes will be saved'))
        
        self.stdout.write(self.style.SUCCESS('📊 Syncing positions from IBKR...'))
        
        # Connect to IBKR with unique client ID for this command
        import random
        client_id = random.randint(10, 999)
        client = IBKRClient(client_id=client_id)
        if not client.connect():
            self.stdout.write(self.style.ERROR('❌ Failed to connect to IBKR Gateway/TWS'))
            self.stdout.write('Make sure the gateway is running and configured correctly')
            return
        
        try:
            # Fetch positions
            positions_data = client.get_portfolio_positions()
            stock_positions = positions_data['stocks']
            option_positions = positions_data['options']
            
            self.stdout.write(f'\n📦 Found {len(stock_positions)} stock positions')
            self.stdout.write(f'📋 Found {len(option_positions)} option positions\n')
            
            # Sync stock positions
            stocks_synced = 0
            if stock_positions:
                self.stdout.write(self.style.SUCCESS('\n=== Stock Positions ==='))
                for pos in stock_positions:
                    self.stdout.write(f"\n{pos['symbol']}: {pos['position']} shares")
                    self.stdout.write(f"  Avg Cost: ${pos['avg_cost']:.2f}")
                    self.stdout.write(f"  Market Value: ${pos['market_value']:.2f}")
                    self.stdout.write(f"  Unrealized P/L: ${pos['unrealized_pnl']:.2f}")
                    
                    if not dry_run:
                        # Get or create stock
                        stock, _ = Stock.objects.get_or_create(ticker=pos['symbol'])
                        stocks_synced += 1
            
            # Sync option positions
            options_synced = 0
            if option_positions:
                self.stdout.write(self.style.SUCCESS('\n=== Option Positions ==='))
                for pos in option_positions:
                    right = 'PUT' if pos['right'] == 'P' else 'CALL'
                    expiry_str = pos['expiry']
                    
                    # Parse expiry date (format: YYYYMMDD)
                    try:
                        expiry_date = datetime.strptime(expiry_str, '%Y%m%d').date()
                    except:
                        self.stdout.write(self.style.ERROR(f"  ⚠️ Could not parse expiry: {expiry_str}"))
                        continue
                    
                    dte = (expiry_date - timezone.now().date()).days
                    position_qty = pos['position']
                    
                    self.stdout.write(f"\n{pos['symbol']} ${pos['strike']} {right} {expiry_date}")
                    self.stdout.write(f"  Contracts: {abs(position_qty)} {'(SHORT)' if position_qty < 0 else '(LONG)'}")
                    self.stdout.write(f"  DTE: {dte} days")
                    self.stdout.write(f"  Avg Cost: ${pos['avg_cost']:.2f}")
                    self.stdout.write(f"  Market Value: ${pos['market_value']:.2f}")
                    self.stdout.write(f"  Unrealized P/L: ${pos['unrealized_pnl']:.2f}")
                    
                    if not dry_run and position_qty < 0:  # Only track short options (sold)
                        # Get or create stock
                        stock, _ = Stock.objects.get_or_create(ticker=pos['symbol'])
                        
                        # Check if position already exists
                        existing = OptionPosition.objects.filter(
                            stock=stock,
                            option_type=right,
                            strike=Decimal(str(pos['strike'])),
                            expiry_date=expiry_date,
                            status='OPEN'
                        ).first()
                        
                        # Calculate current premium from market value
                        # Market value is negative for sold options (liability)
                        # Current premium = abs(market_value) / (contracts * 100)
                        contracts = abs(int(position_qty))
                        current_premium = abs(Decimal(str(pos['market_value']))) / (contracts * 100) if pos['market_value'] else Decimal('0')
                        
                        if not existing:
                            # Create new position
                            # Premium = avg_cost / (contracts * 100)
                            total_premium = abs(Decimal(str(pos['avg_cost'])))
                            entry_premium = total_premium / (contracts * 100)
                            
                            OptionPosition.objects.create(
                                stock=stock,
                                option_type=right,
                                strike=Decimal(str(pos['strike'])),
                                expiry_date=expiry_date,
                                contracts=contracts,
                                entry_premium=entry_premium,
                                total_premium=total_premium,
                                current_premium=current_premium,
                                entry_stock_price=stock.last_price or 0,
                                status='OPEN',
                                notes='Auto-synced from IBKR'
                            )
                            options_synced += 1
                            self.stdout.write(self.style.SUCCESS(f"  ✅ Created new position"))
                        else:
                            # Update current premium for existing position
                            existing.current_premium = current_premium
                            existing.save(update_fields=['current_premium'])
                            self.stdout.write(f"  ℹ️  Position already tracked - updated current premium: ${current_premium:.2f}")
            
            # Fetch and display open orders
            open_orders = client.get_open_orders()
            if open_orders:
                self.stdout.write(self.style.SUCCESS(f'\n=== Open Orders ({len(open_orders)}) ==='))
                for order in open_orders:
                    order_type = order.get('type', 'STOCK')
                    symbol = order['symbol']
                    action = order['action']
                    qty = order['quantity']
                    status = order['status']
                    
                    if order_type == 'OPTION':
                        right = 'PUT' if order['right'] == 'P' else 'CALL'
                        self.stdout.write(f"\n{symbol} ${order['strike']} {right} {order['expiry']}")
                    else:
                        self.stdout.write(f"\n{symbol} (STOCK)")
                    
                    self.stdout.write(f"  {action} {qty} @ ${order['limit_price']} - {status}")
            
            # Summary
            self.stdout.write(self.style.SUCCESS(f'\n\n{"="*50}'))
            self.stdout.write(self.style.SUCCESS('✅ Sync completed!'))
            if not dry_run:
                self.stdout.write(f'  📦 Stock positions found: {len(stock_positions)}')
                self.stdout.write(f'  📋 Option positions synced: {options_synced}')
                self.stdout.write(f'  📝 Open orders: {len(open_orders)}')
            else:
                self.stdout.write(self.style.WARNING('  (No changes saved - dry run mode)'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'\n❌ Error syncing positions: {e}'))
            logger.exception("Error in sync_positions command")
        
        finally:
            client.disconnect()
            self.stdout.write('\n✅ Disconnected from IBKR\n')
