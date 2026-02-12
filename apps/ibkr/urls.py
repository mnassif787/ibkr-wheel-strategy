from django.urls import path
from . import views

app_name = 'ibkr'

urlpatterns = [
    # Main Hub (new unified interface)
    path('', views.hub, name='hub'),
    
    # Legacy routes (keep for backwards compatibility)
    path('dashboard/', views.dashboard, name='dashboard'),
    path('health/', views.health_check, name='health_check'),
    path('stocks/', views.stocks_list, name='stocks'),
    path('stocks/export/', views.export_wheel_scores, name='export_wheel_scores'),
    path('options/', views.options_list, name='options'),
    path('options/<str:ticker>/', views.options_list, name='options_ticker'),
    path('signals/', views.signals_list, name='signals'),
    path('discovery/', views.discovery, name='discovery'),
    path('stock/<str:ticker>/', views.stock_detail, name='stock_detail'),
    path('watchlist/add/', views.watchlist_add, name='watchlist_add'),
    path('watchlist/remove/<str:ticker>/', views.watchlist_remove, name='watchlist_remove'),
    path('watchlist/refresh/', views.refresh_watchlist_data, name='watchlist_refresh'),
    path('options/sync/yfinance/', views.sync_yfinance_options_view, name='sync_yfinance_options'),
    path('positions/', views.positions_list, name='positions'),
    path('positions/open/', views.open_position, name='open_position'),
    path('positions/close/<int:position_id>/', views.close_position, name='close_position'),
    
    # IB Gateway Control
    path('gateway/', views.gateway_control, name='gateway_control'),
    path('gateway/api/status/', views.gateway_status_api, name='gateway_status_api'),
    path('gateway/api/connect/', views.gateway_connect_api, name='gateway_connect_api'),
    path('gateway/api/disconnect/', views.gateway_disconnect_api, name='gateway_disconnect_api'),
    
    # Data Refresh API
    path('api/refresh/', views.refresh_all_data_api, name='refresh_all_data_api'),
    path('api/refresh/status/', views.refresh_status_api, name='refresh_status_api'),
    
    # Position Sync API
    path('api/positions/sync/', views.sync_positions_api, name='sync_positions_api'),
    path('api/positions/sync/status/', views.sync_positions_status_api, name='sync_positions_status_api'),
    
    # Alert Management API
    path('api/alerts/create/', views.create_alert_api, name='create_alert_api'),
    path('api/alerts/', views.list_alerts_api, name='list_alerts_api'),
    path('api/alerts/<int:alert_id>/dismiss/', views.dismiss_alert_api, name='dismiss_alert_api'),
    path('api/telegram/save-chat-id/', views.save_telegram_chat_id, name='save_telegram_chat_id'),
    
    # Order Placement
    path('orders/', views.orders_page, name='orders'),
    path('api/orders/place/', views.place_order_api, name='place_order_api'),
    path('api/orders/cancel/', views.cancel_order_api, name='cancel_order_api'),
    path('api/orders/open/', views.open_orders_api, name='open_orders_api'),
    path('api/orders/quote/', views.option_quote_api, name='option_quote_api'),
]
