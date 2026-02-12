# IBKR Wheel Strategy - Development Plan

## Project Overview
Django web application for Wheel Strategy trading with Interactive Brokers integration.

**Tech Stack:**
- Django 5.0
- Django Templates + Tailwind CSS
- SQLite + Django ORM
- ib_insync (IBKR API wrapper)
- Resend API (emails)
- Docker + Coolify deployment

---

## Development Checklist

### Phase 1: Project Setup
- [x] Create project folder structure
- [ ] Initialize Django project
- [ ] Set up virtual environment
- [ ] Install dependencies (Django, ib_insync, resend, tailwindcss)
- [ ] Configure settings.py (SQLite, apps, static files)
- [ ] Create .env.example and .gitignore
- [ ] Set up Tailwind CSS with Django
- [ ] Create base templates (desktop + mobile)
- [ ] Test Django development server

### Phase 2: Database Models
- [ ] Design database schema
- [ ] Create Stock model (ticker, name, price, beta, roe, etc.)
- [ ] Create Option model (strike, expiry, bid, ask, greeks)
- [ ] Create Signal model (wheel strategy signals)
- [ ] Create UserConfig model (trading preferences)
- [ ] Create Watchlist model
- [ ] Run migrations
- [ ] Configure Django Admin for all models

### Phase 3: IBKR Integration
- [ ] Install ib_insync library
- [ ] Create ibkr_client.py (connection handler)
- [ ] Implement connect/disconnect to TWS/Gateway
- [ ] Test connection with IBKR paper trading account
- [ ] Create market_data.py service
- [ ] Implement fetch_stock_data()
- [ ] Implement fetch_option_chain()
- [ ] Implement real-time price streaming
- [ ] Create Django management command: sync_ibkr
- [ ] Test data retrieval from IBKR

### Phase 4: Core App (Homepage)
- [ ] Create core app
- [ ] Design homepage with Tailwind CSS
- [ ] Create desktop view layout
- [ ] Create mobile-responsive layout
- [ ] Add navigation menu
- [ ] Add footer
- [ ] Test responsive design

### Phase 5: IBKR Dashboard Views
- [ ] Create ibkr app
- [ ] Design dashboard page (overview)
- [ ] Display connected stocks
- [ ] Display account balance (from IBKR)
- [ ] Display portfolio positions
- [ ] Add real-time updates (AJAX/fetch)
- [ ] Create stocks list page
- [ ] Create options chain page
- [ ] Create signals page

### Phase 6: Watchlist Management
- [ ] Create watchlist CRUD views
- [ ] Add ticker form (add to watchlist)
- [ ] Display watchlist table
- [ ] Add remove ticker functionality
- [ ] Integrate with IBKR sync
- [ ] Test watchlist operations

### Phase 7: Signal Generation
- [ ] Design signal generation algorithm
- [ ] Implement fundamental filters (ROE, FCF, Beta)
- [ ] Implement options filters (DTE, Delta, IV)
- [ ] Calculate APY%
- [ ] Store signals in database
- [ ] Display signals in table
- [ ] Add filters/sorting
- [ ] Color-code by quality

### Phase 8: Email Notifications
- [ ] Install Resend library
- [ ] Configure Resend API key
- [ ] Set up Django email backend
- [ ] Create email templates
- [ ] Implement signal notification emails
- [ ] Test with console email backend (development)
- [ ] Test with Resend (production)

### Phase 9: Order Management (Optional)
- [ ] Create order_manager.py service
- [ ] Implement place_order() for IBKR
- [ ] Add order confirmation page
- [ ] Display order status
- [ ] Add order history
- [ ] Test paper trading orders

### Phase 10: Testing & Polish
- [ ] Test all CRUD operations
- [ ] Test IBKR connection handling (reconnect logic)
- [ ] Test mobile responsiveness
- [ ] Add loading states/spinners
- [ ] Add error handling
- [ ] Add user feedback messages
- [ ] Security audit (CSRF, SQL injection, XSS)
- [ ] Performance optimization

### Phase 11: Docker & Deployment
- [ ] Create Dockerfile
- [ ] Create docker-compose.yml
- [ ] Test Docker build locally
- [ ] Set up environment variables
- [ ] Configure static files for production
- [ ] Create deployment documentation
- [ ] Deploy to Coolify
- [ ] Test production deployment
- [ ] Set up monitoring/logging

---

## Current Status
**Phase:** 1 - Project Setup  
**Progress:** 1/9 tasks completed  
**Next Step:** Initialize Django project

---

## IBKR Setup Requirements
- Interactive Brokers account (paper or live)
- TWS (Trader Workstation) or IB Gateway running locally
- API access enabled in TWS settings (File → Global Configuration → API → Settings)
- Default connection: localhost:7497 (TWS Live), localhost:7496 (TWS Paper), localhost:4001 (Gateway Live), localhost:4002 (Gateway Paper)

---

**Last Updated:** January 21, 2026  
**Version:** 1.0.0
