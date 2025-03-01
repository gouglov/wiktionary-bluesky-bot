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

    def get_random_word(self):
        """Get a random word from Wiktionary that hasn't been posted before"""
        found=False
        while not(found):#Iteration while nothing is posted
            try:
                # Query for a random word
                params = {
                    "action": "query",
                    "list": "random",
                    "rnnamespace": 0,  # Main namespace
                    "rnlimit": 1,
                    "format": "json"
                }                
                

                response = requests.get(self.api_url, params=params)
                data = response.json()  
                               

                if "query" in data and "random" in data["query"]:
                    word = data["query"]["random"][0]["title"]
                    # Check if we've already posted this word
                    if word in self.posted_words:
                        logger.info(f"Word '{word}' already posted, trying another")
                        continue
                    
                    # Get the definition
                    if (self.filter_data(word)) :
                        definition = self.get_word_definition(word)
                        if definition:
                            found=True
                            return {
                                "word": word,
                                "definition": definition,
                                "url": f"https://{self.language}.wiktionary.org/wiki/{word.replace(' ', '_')}"
                            }
            except Exception as e:
                logger.error(f"Error fetching random word: {e}")
                time.sleep(2)  # Wait before retrying
                
        logger.error("Failed to get a suitable random word after multiple attempts")
        return None

    def filter_data(self, word):
        try:
            params = {
                "action": "query",
                "prop": "extracts",
                "explaintext" : True,
                "exsectionformat": "wiki",
                "titles": word,
                "format": "json"
            }
            
            response = requests.get(self.api_url, params=params)
            data = response.json()

            page_id = next(iter(data["query"]["pages"]))
            if page_id != "-1" and "extract" in data["query"]["pages"][page_id]:
                extract = data["query"]["pages"][page_id]["extract"]
                
                extract = extract.strip()
                #Use Parser From Hell to filtering data from API
                wikicode = mwparserfromhell.parse(extract)
                headings = wikicode.filter_headings()
                
                if("Français" in headings[0] and len(headings) >= 3) :
                    cur_type=headings[2][4:-4]
                    logger.info("C'est un mot français de type "+cur_type) 
                    if(cur_type in self.valid_type) :
                        return True
            
            return False
        except Exception as e:
            logger.error(f"Error fetching definition for word '{word}': {e}")
            return False
    def cleaningDef(self, definition) :
        """Cleaning extra content in the definition"""
        try:
            # cleaning session 
            for p in self.parasites :
                if p in definition :
                    logger.info("on supprime "+p)
                    definition = definition.replace(p,'')

            if len(definition) > 180:
                    definition = definition[:177] + "..."
            
            countEqual = 0
            indexSection = 0
            for letter in definition :
                if letter == "=":
                    countEqual+=1
                indexSection+=1
                if countEqual == 7:
                    logger.info("On supprime ce qui suit : \n"+definition[indexSection:]) 
                    break

            definition = definition[0:indexSection]

            return definition
            
        except Exception as e:
            logger.error(f"Error cleaning definition '{definition}': {e}")
            return None 


    def get_word_definition(self, word):
        """Get the definition of a specific word"""
        try:
            params = {
                "action": "query",
                "prop": "extracts",
                "explaintext" : True,
                "exsectionformat": "wiki",
                "titles": word,
                "format": "json"
            }
            
            response = requests.get(self.api_url, params=params)
            data = response.json()

            page_id = next(iter(data["query"]["pages"]))
            if page_id != "-1" and "extract" in data["query"]["pages"][page_id]:
                extract = data["query"]["pages"][page_id]["extract"]

                wikicode = mwparserfromhell.parse(extract)                
                sections=wikicode.get_sections(include_headings=True)
                
                # Truncate the extract then clean it
                definition=sections[3].strip()
                definition = self.cleaningDef(definition)
                
                return definition

            return None
        except Exception as e:
            logger.error(f"Error fetching definition for word '{word}': {e}")
            return None   

    def post_to_bluesky(self, word_data):
        """Post the word of the day to Bluesky"""
        if not self.client:
            if not self.connect_to_bluesky():
                return False
        
        try:
            #Use text builder to can add clickable links
            text_builder = client_utils.TextBuilder()
            text_builder.text(f"📚 Wiktionnaire - Le mot du jour est \n{word_data['word'].capitalize()}\n")
            text_builder.text(f"{word_data['definition']}\n\n")
            text_builder.text(f"Plus d'info: ")
            text_builder.link(f"{word_data['word']}", f"{word_data['url']}")     

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
            word_data = self.get_random_word()
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
