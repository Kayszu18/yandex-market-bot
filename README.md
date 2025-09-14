Pro Yandex Orders Telegram Bot


Requirements
- Python 3.8+
- See requirements.txt


Setup
1. Copy `.env.example` to `.env` and fill values (BOT_TOKEN, ADMIN_IDS, etc.)
2. Install requirements: pip install -r requirements.txt
3. Run: python app.py


Structure
- app.py: entrypoint
- config.py: loads .env
- database.py: sqlite helpers (aiosqlite)
- handlers/: user/admin/payment/referrals/support handlers
- keyboards/: user/admin keyboards
- utils/: excel export and helpers


Features
- /start shows promo video (admin uploads) + promo text
- Tutorial steps with images, video, navigation, and "zakaz" flow
- Zakaz: user posts Yandex Market URL + screenshot → saved to orders
- Admin: view pending orders, approve/reject with inline buttons
- Excel export of orders
- Broadcast / single-message to users
- Block / unblock users
- Withdrawals: request/approve/pay with proof posting to a channel
- Referral reward system
- Support contact button
# yandex-market-bot
