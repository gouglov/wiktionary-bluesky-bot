import requests
import random
import os
from datetime import datetime
import logging
from atproto import Client
import json
import time
from dotenv import load_dotenv
import mwparserfromhell
from atproto import client_utils
from bs4 import BeautifulSoup
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("wiktionary_bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class WiktionaryBlueskyBot:
    def __init__(self):

        # List of data used for filtering and cleaning result
        self.valid_type=["Nom commun","Adverbe", "Verbe", "Adjectif", "Locution nominale", "Locution verbale"]
        self.parasites=["(pluriel à préciser)", "\\Prononciation ?\\"]

        # Bluesky credentials
        self.bluesky_handle = os.getenv("BLUESKY_HANDLE")
        self.bluesky_password = os.getenv("BLUESKY_PASSWORD")
        self.client = None
        
        # Wiktionary API settings
        self.language = os.getenv("WIKTIONARY_LANGUAGE", os.getenv("WIKTIONARY_LANGUAGE"))
        self.api_url = f"https://{self.language}.wiktionary.org/w/api.php"
        
        # Cache for previously posted words
        self.cache_file = "posted_words.json"
        self.posted_words = self._load_posted_words()

    def _load_posted_words(self):
        """Load previously posted words from cache file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            return []
        except Exception as e:
            logger.error(f"Error loading posted words: {e}")
            return []

    def _save_posted_words(self):
        """Save posted words to cache file"""
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.posted_words, f)
        except Exception as e:
            logger.error(f"Error saving posted words: {e}")

    def connect_to_bluesky(self):
        """Connect to Bluesky using API credentials"""
        try:
            self.client = Client()
            self.client.login(self.bluesky_handle, self.bluesky_password)
            logger.info(f"Connected to Bluesky as {self.bluesky_handle}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Bluesky: {e}")
            return False
    
    def get_word_data(self, word):
        """Get the definition of a specific word"""
        try:
            params = {
                "action": "query",
                "prop": "extracts",
                "exsectionformat": "plain",
                "titles": word,
                "format": "json"
            }
            
            response = requests.get(self.api_url, params=params)
            data = response.json()

            page_id = next(iter(data["query"]["pages"]))
            if page_id != "-1" and "extract" in data["query"]["pages"][page_id]:
                extract = data["query"]["pages"][page_id]["extract"]
                
                word_data = {}

                soup = BeautifulSoup(extract, features="lxml")
                
                title = soup.find('p').find('span').text
                word_data["word"] = title
                word_data["url"] = f"https://{self.language}.wiktionary.org/wiki/{title.replace(' ', '_')}"     
                logger.info(f"{title}")

                first_line = soup.find('p').text.strip()
                word_data["first_line"] = first_line 
                logger.info(f"{first_line}")
                
                definition_list = soup.find('ol')
                definitions = definition_list.find_all('li')
                def_num = 1
                length=len(first_line)
                overflow = False
                word_data["def_lines"]=[]
                for definition in definitions :
                    if definition.parent.name == "ol" :
                        def_text_tab = definition.text.strip().split('\n')
                        def_line = f"{def_num} - {def_text_tab[0]}"
                        # Case when the definition is too long for bluesky
                        length += len(def_line)
                        if length >= 229 :
                            overflow = True
                            def_line = def_line[:-3]
                            def_line += "[…]"
                        word_data["def_lines"].append(def_line)
                        logger.info(f"{def_line}")
                        def_num += 1
                        if overflow :
                            break
                        
                            
                logger.info(f"{word_data}")

            return word_data

        except Exception as e:
            logger.error(f"Error fetching definition for word '{word}': {e}")
            return None   

    def get_today_word(self):
            
        current_day = datetime.now().day
        current_month = datetime.now().month
        current_year = datetime.now().year

        page_name = f"Modèle:Entrée du jour/{current_year}/{current_month:02d}/{current_day:02d}"
        logger.info(f"{page_name}")
        try:
            params = {
                "action": "query",
                "prop": "extracts",
                "exsectionformat": "plain",
                "titles": page_name,
                "format": "json"
            }

            response = requests.get(self.api_url, params=params)
            data = response.json()
            

            page_id = next(iter(data["query"]["pages"]))

            if page_id == "-1" or "extract" in data["query"]["pages"][page_id]:
                # fallback
                logger.info(f"Fail to found a page, look at 2021")
                page_name = f"Modèle:Entrée du jour/2021/{current_month:02d}/{current_day:02d}"
                params = {
                    "action": "query",
                    "prop": "extracts",
                    "exsectionformat": "plain",
                    "titles": page_name,
                    "format": "json"
                }

                response = requests.get(self.api_url, params=params)
                data = response.json()

                page_id = next(iter(data["query"]["pages"]))
                
            if page_id != "-1" and "extract" in data["query"]["pages"][page_id]:
                extract = data["query"]["pages"][page_id]["extract"]

                logger.info(f"Page of the day is <{page_name}>")
                return page_name

        except Exception as e:
            logger.error(f"Error fetching random word: {e}")
            time.sleep(2)  # Wait before retrying
                
        logger.error("Failed to get a suitable random word after multiple attempts")
        return None

    def post_to_bluesky(self, word_data):
        """Post the word of the day to Bluesky"""
        if not self.client:
            if not self.connect_to_bluesky():
                return False
        
        try:
            #Use text builder to can add clickable links
            text_builder = client_utils.TextBuilder()
            text_builder.text(f"📚 Wiktionnaire - Le mot du jour est : \n\n{word_data['first_line'].capitalize()}\n")
            for d in word_data['def_lines'] :
                text_builder.text(f"{d}\n")
            text_builder.text(f"\nPlus d'info sur ")
            text_builder.link(f"l'article lié", f"{word_data['url']}")
            text_builder.text(f".")

            self.client.send_post(text_builder)
            logger.info(f"\nPosted word of the day: {word_data['word']}")
            
            # Add to posted words
            self.posted_words.append(word_data['word'])
            self._save_posted_words()
            
            return True
        except Exception as e:
            logger.error(f"Error posting to Bluesky: {e}")
            return False

    def run(self):
        """Main method to run the bot"""
        logger.info("Starting Wiktionary Bluesky Bot")
        
        try:
            # Connect to Bluesky
            if not self.connect_to_bluesky():
                return False
            
            # Get random word and definition
            word_data = self.get_word_data(self.get_today_word())
            if not word_data:
                logger.error("Failed to get word data")
                return False
            
            # Post to Bluesky
            success = self.post_to_bluesky(word_data)
            
            return success
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            return False

if __name__ == "__main__":
    bot = WiktionaryBlueskyBot()
    bot.run()
