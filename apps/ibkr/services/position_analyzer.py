"""
Position Analyzer - Enhanced recommendations and risk analysis for option positions
"""
from decimal import Decimal
from datetime import timedelta
from django.utils import timezone


class PositionAnalyzer:
    """Analyze option positions and provide actionable recommendations"""
    
    @staticmethod
    def analyze_position(position):
        """
        Comprehensive position analysis with actionable recommendations
        
        Args:
            position: OptionPosition instance
        
        Returns:
            dict with analysis, recommendations, and alerts
        """
        stock = position.stock
        current_price = float(stock.last_price) if stock.last_price else 0
        strike = float(position.strike)
        dte = position.dte
        
        analysis = {
            'alerts': [],
            'recommendations': [],
            'metrics': {},
            'scenarios': {},
            'action_plan': {},
        }
        
        # === URGENCY ALERTS ===
        if dte <= 0:
            analysis['alerts'].append({
                'level': 'CRITICAL',
                'icon': '🚨',
                'message': 'EXPIRED - Position needs immediate action',
                'color': 'red'
            })
        elif dte <= 2:
            analysis['alerts'].append({
                'level': 'URGENT',
                'icon': '⚠️',
                'message': f'EXPIRING IN {dte} DAY{"S" if dte > 1 else ""} - Decision needed TODAY',
                'color': 'orange'
            })
        elif dte <= 5:
            analysis['alerts'].append({
                'level': 'WARNING',
                'icon': '⏰',
                'message': f'{dte} days until expiration - Plan your exit strategy',
                'color': 'yellow'
            })
        
        # === ASSIGNMENT PROBABILITY ===
        if position.option_type == 'PUT':
            distance_from_strike = ((current_price - strike) / strike) * 100
            
            if current_price < strike * 0.95:  # Stock 5%+ below strike
                assignment_prob = 'VERY HIGH (>80%)'
                prob_color = 'red'
                prob_icon = '🔴'
                analysis['alerts'].append({
                    'level': 'HIGH',
                    'icon': '📌',
                    'message': f'High assignment risk - Stock ${current_price:.2f} is {abs(distance_from_strike):.1f}% below strike ${strike}',
                    'color': 'red'
                })
            elif current_price < strike:
                assignment_prob = 'HIGH (50-80%)'
                prob_color = 'orange'
                prob_icon = '🟠'
            elif current_price < strike * 1.05:
                assignment_prob = 'MODERATE (20-50%)'
                prob_color = 'yellow'
                prob_icon = '🟡'
            else:
                assignment_prob = 'LOW (<20%)'
                prob_color = 'green'
                prob_icon = '🟢'
            
            analysis['metrics']['assignment_probability'] = {
                'level': assignment_prob,
                'color': prob_color,
                'icon': prob_icon,
                'distance': f'{distance_from_strike:+.1f}%'
            }
        
        # === PROFIT/LOSS SCENARIOS ===
        premium = float(position.total_premium)
        break_even = float(position.break_even)
        
        # Current P/L
        if position.unrealized_pl is not None:
            current_pl = float(position.unrealized_pl)
            current_pl_pct = (current_pl / premium) * 100 if premium > 0 else 0
        else:
            current_pl = 0
            current_pl_pct = 0
        
        analysis['metrics']['current_profit'] = {
            'amount': f'${current_pl:,.2f}',
            'percentage': f'{current_pl_pct:+.1f}%',
            'color': 'green' if current_pl > 0 else 'red' if current_pl < 0 else 'gray'
        }
        
        # === ACTION RECOMMENDATIONS ===
        recommendations = []
        
        # 1. Take Profit Recommendation (50% rule)
        if current_pl_pct >= 50:
            recommendations.append({
                'action': '🎯 TAKE PROFIT',
                'priority': 'HIGH',
                'reason': f'Achieved {current_pl_pct:.0f}% profit (50% rule met)',
                'details': f'Close position now to lock in ${current_pl:.2f} profit',
                'color': 'green'
            })
        elif current_pl_pct >= 30:
            recommendations.append({
                'action': '💰 CONSIDER CLOSING',
                'priority': 'MEDIUM',
                'reason': f'{current_pl_pct:.0f}% profit achieved',
                'details': 'Good profit level - consider taking it or wait for 50%',
                'color': 'green'
            })
        
        # 2. Roll Strategy (if approaching expiration)
        if dte <= 7 and dte > 0:
            if current_price > strike * 0.95:  # Safe distance
                recommendations.append({
                    'action': '🔄 CONSIDER ROLLING',
                    'priority': 'MEDIUM',
                    'reason': f'Expiring in {dte} days with good position',
                    'details': 'Roll out to next expiration to collect more premium',
                    'color': 'blue'
                })
            elif current_price < strike:  # In danger
                recommendations.append({
                    'action': '🔄 ROLL DOWN/OUT',
                    'priority': 'HIGH',
                    'reason': 'At-risk position near expiration',
                    'details': 'Roll to lower strike and/or future date to avoid assignment',
                    'color': 'orange'
                })
        
        # 3. Let Expire Strategy
        if dte <= 3 and current_pl_pct > 80:
            recommendations.append({
                'action': '⏳ LET EXPIRE',
                'priority': 'LOW',
                'reason': f'Only ${premium * (1 - current_pl_pct/100):.2f} remaining value',
                'details': 'Not worth closing costs - let it expire worthless',
                'color': 'green'
            })
        
        # 4. Assignment Preparation
        if position.option_type == 'PUT' and current_price < strike * 0.98:
            shares_value = strike * 100  # For 1 contract
            recommendations.append({
                'action': '💵 PREPARE FOR ASSIGNMENT',
                'priority': 'HIGH',
                'reason': 'Stock near or below strike price',
                'details': f'Ensure ${shares_value:,.0f} cash available to buy 100 shares at ${strike}',
                'color': 'red'
            })
        
        # === WHAT-IF SCENARIOS ===
        if position.option_type == 'PUT':
            # Scenario 1: If Assigned
            cost_basis_if_assigned = strike - (premium / 100)
            current_loss_if_assigned = (current_price - cost_basis_if_assigned) * 100
            
            analysis['scenarios']['if_assigned'] = {
                'title': '📊 If Assigned (you buy 100 shares)',
                'cost_basis': f'${cost_basis_if_assigned:.2f}/share',
                'total_cost': f'${strike * 100:,.0f}',
                'current_value': f'${current_price * 100:,.0f}',
                'unrealized_pl': f'${current_loss_if_assigned:+,.0f}',
                'notes': f'Your real cost: ${cost_basis_if_assigned:.2f} (strike minus premium collected)'
            }
            
            # Scenario 2: If Stock Recovers
            target_prices = [strike * 1.05, strike * 1.10, strike * 1.15]
            recovery_scenarios = []
            for target in target_prices:
                gain_pct = ((target - cost_basis_if_assigned) / cost_basis_if_assigned) * 100
                gain_amt = (target - cost_basis_if_assigned) * 100
                recovery_scenarios.append({
                    'price': f'${target:.2f}',
                    'gain': f'${gain_amt:+,.0f} ({gain_pct:+.1f}%)'
                })
            
            analysis['scenarios']['recovery'] = {
                'title': '📈 Recovery Scenarios (if assigned and price goes up)',
                'scenarios': recovery_scenarios
            }
        
        # === EXIT STRATEGY / ACTION PLAN ===
        action_plan = {
            'immediate': [],
            'before_expiration': [],
            'at_expiration': []
        }
        
        # IMMEDIATE ACTIONS (based on current state)
        if current_pl_pct >= 50:
            action_plan['immediate'].append(f'🎯 Consider closing - Already at {current_pl_pct:.0f}% profit (50% rule achieved)')
        elif current_pl_pct >= 30:
            action_plan['immediate'].append(f'📊 Monitor closely - At {current_pl_pct:.0f}% profit, approaching 50% target')
        
        if dte <= 2:
            action_plan['immediate'].append('🚨 Monitor stock price every hour - expiration imminent')
            if current_price < strike:
                action_plan['immediate'].append(f'💵 Ensure ${strike * 100:,.0f} cash available for potential assignment')
        elif dte <= 7:
            action_plan['immediate'].append(f'⏰ Review position daily - {dte} days until expiration ({position.expiry_date.strftime("%b %d")})')
        
        if current_price < strike * 0.95:
            action_plan['immediate'].append('⚠️ Stock significantly below strike - assignment risk HIGH')
        
        # BEFORE EXPIRATION (planning actions)
        days_until_decision = max(0, dte - 1)
        action_plan['before_expiration'].append(f'📅 Make decision by {(position.expiry_date - timezone.timedelta(days=1)).strftime("%b %d")} (day before expiration)')
        
        if current_pl_pct < 50:
            action_plan['before_expiration'].append('🎯 Set alert for 50% profit - consider closing if reached')
        
        if dte > 3:
            action_plan['before_expiration'].append('🔄 Option: Roll to next month for more premium (if needed)')
        
        if position.option_type == 'PUT':
            action_plan['before_expiration'].append(f'💡 If stock drops to ${strike * 0.95:.2f}, decide: accept assignment or roll out')
        
        # AT EXPIRATION (outcome scenarios)
        if position.option_type == 'PUT':
            if current_price > strike * 1.02:
                action_plan['at_expiration'].append(f'✅ If {position.stock.ticker} stays above ${strike:.2f}: Option expires worthless, keep full ${premium:.2f} premium')
            else:
                action_plan['at_expiration'].append(f'📊 If {position.stock.ticker} > ${strike:.2f}: Expires worthless - best outcome')
                action_plan['at_expiration'].append(f'📌 If {position.stock.ticker} < ${strike:.2f}: Assigned 100 shares at ${strike:.2f}/share (need ${strike * 100:,.0f} cash)')
                cost_basis = strike - (premium / 100)
                action_plan['at_expiration'].append(f'💰 Your real cost if assigned: ${cost_basis:.2f}/share (strike - premium)')
        
        analysis['action_plan'] = action_plan
        analysis['recommendations'] = recommendations
        
        return analysis
