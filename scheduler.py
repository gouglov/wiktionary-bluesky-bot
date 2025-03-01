import schedule
import time
import logging
from wiktionary_bluesky_bot import WiktionaryBlueskyBot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scheduler.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def run_bot():
    """Run the Wiktionary Bluesky Bot"""
    logger.info("Scheduled job: Running Wiktionary Bluesky Bot")
    bot = WiktionaryBlueskyBot()
    success = bot.run()
    if success:
        logger.info("Bot ran successfully")
    else:
        logger.error("Bot failed to run properly")

# Schedule the bot to run daily at a specific time (e.g., 10:00 AM)
schedule.every().day.at("10:00").do(run_bot)

logger.info("Scheduler started. Bot will run daily at 10:00 AM")

# Run the bot immediately on first execution
run_bot()

# Keep the script running
while True:
    schedule.run_pending()
    time.sleep(60)  # Check every minute
