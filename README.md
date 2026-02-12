# IBKR Wheel Strategy - Django Application

A Django web application for automated Wheel Strategy options trading with Interactive Brokers integration.

## Features

- 📊 Real-time stock and options data from Interactive Brokers
- 🎯 Automated Wheel Strategy signal generation
- 📱 Responsive design (Desktop + Mobile)
- 🔔 Email notifications via Resend
- 🛠 Django Admin for easy management
- 🐳 Docker-ready for easy deployment

## Quick Start

### Prerequisites

- Python 3.11+
- Interactive Brokers account (paper or live)
- TWS (Trader Workstation) or IB Gateway installed
- Resend API key (for emails)

### Installation

1. **Clone the repository**
```bash
cd "c:\Nassif\AI\Wheel Strategy\Wheel Strategy\ibkr-wheel-django"
```

2. **Activate virtual environment**
```bash
# Windows
venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
copy .env.example .env
# Edit .env with your settings
```

5. **Run migrations**
```bash
python manage.py migrate
```

6. **Create superuser**
```bash
python manage.py createsuperuser
```

7. **Start development server**
```bash
python manage.py runserver
```

Visit: http://localhost:8000

## IBKR Setup

1. **Install TWS or IB Gateway**
   - Download from Interactive Brokers website
   - Install and launch the application

2. **Enable API Access**
   - Open TWS
   - File → Global Configuration → API → Settings
   - Check "Enable ActiveX and Socket Clients"
   - Set "Socket port" to 7497 (live) or 7496 (paper)
   - Check "Read-Only API" for safety (optional)
   - Click OK and restart TWS

3. **Configure Connection**
   - Update `.env` file with correct port and settings
   - Default: `IBKR_PORT=7497` (TWS Live) or `7496` (Paper)

## Project Structure

```
ibkr-wheel-django/
├── apps/
│   ├── core/          # Homepage and base functionality
│   ├── ibkr/          # IBKR integration and trading logic
│   └── accounts/      # User authentication (future)
├── config/            # Django settings
├── static/            # CSS, JS, images
├── templates/         # Global templates
└── manage.py          # Django management
```

## Management Commands

```bash
# Sync data from IBKR
python manage.py sync_ibkr

# Run Tailwind watch mode
python manage.py tailwind start

# Collect static files
python manage.py collectstatic
```

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

## Tech Stack

- **Backend:** Django 5.0, Python 3.11
- **Frontend:** Django Templates, Tailwind CSS
- **Database:** SQLite (Django ORM)
- **IBKR API:** ib-insync
- **Email:** Resend API
- **Deployment:** Docker, Coolify

## Development Status

See [PLAN.md](PLAN.md) for detailed development checklist.

## License

MIT License

## Support

For issues or questions, please create an issue on GitHub.
