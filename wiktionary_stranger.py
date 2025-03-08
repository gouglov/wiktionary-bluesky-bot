import requests
import os
from datetime import datetime
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import time

import re
import typing as t
import httpx
from atproto import Client, models

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("wiktionary_stranger.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class WiktionayStranger :
    def __init__(self):
        # Bluesky credentials
        self.bluesky_handle = os.getenv("BLUESKY_HANDLE")
        self.bluesky_password = os.getenv("BLUESKY_PASSWORD")
        self.client = None

        # OG settings
        self._META_PATTERN = re.compile(r'<meta property="og:.*?>')
        self._CONTENT_PATTERN = re.compile(r'<meta[^>]+content="([^"]+)"')

        # Message settings
        self.messageHead = "📚 Wiktionnaire - Le mot du jour est :\n\n"
        self.blueskyMaxLength = 300

        # Wiktionary API settings
        self.language = os.getenv("WIKTIONARY_LANGUAGE", os.getenv("WIKTIONARY_LANGUAGE"))
        self.api_url = f"https://{self.language}.wiktionary.org/w/api.php"

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

            sizeMessage = len(self.messageHead)

            response = requests.get(self.api_url, params=params)
            data = response.json()

            logger.info(f"data is {data}")

            page_id = next(iter(data["query"]["pages"]))
            logger.info(f"page_id is {page_id}")
            logger.info(f"extract control is {data["query"]["pages"][page_id]}")

            if page_id != "-1" and "extract" in data["query"]["pages"][page_id]:
                extract = data["query"]["pages"][page_id]["extract"]
                logger.info(f"extract is {extract}")

                word_data = {}

                soup = BeautifulSoup(extract, features="lxml")

                title = soup.text
                word_data["word"] = title
                word_data["url"] = f"https://{self.language}.wiktionary.org/wiki/{title.replace(' ', '_')}"
                logger.info(f" Title is : {title}")

                first_line = soup.find('p').text.strip()
                word_data["first_line"] = first_line
                logger.info(f" First line is : {first_line}")
                sizeMessage += len(first_line)
                definition_list = soup.find('ol')
                definitions = definition_list.find_all('li')
                def_num = 1
                overflow = False
                word_data["def_lines"] = []

                for definition in definitions:
                    if definition.parent.name == "ol":
                        logger.info(f"Current message size : {sizeMessage}")
                        def_text_tab = definition.text.strip().split('\n')
                        def_line = f"{def_num} - {def_text_tab[0]}"
                        logger.info(f"Def_line is {def_line}")
                        # Case when the definition is too long for bluesky

                        cur_length = len(def_line)
                        logger.info(f"Size of def_line is {cur_length}")
                        if sizeMessage + cur_length > self.blueskyMaxLength:
                            logger.info(f"Overflow detected")
                            overflow = True

                            buffer = self.blueskyMaxLength - sizeMessage - 7  # Maximal size for the def
                            def_line = def_line[:buffer]
                            def_line += "[…]"
                            logger.info(f"Def_line is now {def_line}")
                        word_data["def_lines"].append(def_line)
                        sizeMessage += cur_length
                        def_num += 1
                        if overflow:
                            break

                logger.info(f"World_data is {word_data}")
                return word_data

            raise ValueError('Definition not found')

        except Exception as e:
            logger.error(f"Error fetching definition for word '{word}': {e}")
            return None

    def post_to_bluesky(self, word_data):
        """Post the word of the day to Bluesky"""
        logger.info("post_to_bluesky started")
        if not self.client:
            logger.error("No connection valid")
            if not self.connect_to_bluesky():
                return False

        try:
            # Use text builder to can add clickable links
            logger.info(f"Connection valid, data is {word_data}")
            url = word_data['url']

            text_builder = f"📚 Wiktionnaire - Le mot du jour est : \n\n{word_data['first_line'].capitalize()}\n"
            for d in word_data['def_lines']:
                text_builder += f"{d}\n"

            logger.info(f"text_builder length is {str(len(text_builder))}")
            logger.info(f"text_builder is {text_builder}")

            description = word_data['first_line'].split("—")[1].capitalize()
            logger.info(f"description is {description}")

            img_url, title = self.get_og_tags(url)
            if title is None:
                raise ValueError('Required Open Graph Protocol (OGP) tags not found')

            thumb_blob = None
            if img_url:
                # Download image from og:image url and upload it as a blob
                img_data = httpx.get(img_url).content
                thumb_blob = self.client.upload_blob(img_data).blob

            # AppBskyEmbedExternal is the same as "link card" in the app
            embed_external = models.AppBskyEmbedExternal.Main(
                external=models.AppBskyEmbedExternal.External(title=title, description=f"{description}", uri=url,
                                                              thumb=thumb_blob)
            )
            self.client.send_post(text=text_builder, embed=embed_external)

            return True
        except Exception as e:
            logger.error(f"Error posting to Bluesky: {e}")
            return False

    # Test link card

    def _find_tag(self, og_tags: t.List[str], search_tag: str) -> t.Optional[str]:
        for tag in og_tags:
            if search_tag in tag:
                return tag

        return None

    def _get_tag_content(self, tag: str) -> t.Optional[str]:
        match = self._CONTENT_PATTERN.match(tag)
        if match:
            return match.group(1)

        return None

    def _get_og_tag_value(self, og_tags: t.List[str], tag_name: str) -> t.Optional[str]:
        tag = self._find_tag(og_tags, tag_name)
        if tag:
            return self._get_tag_content(tag)

        return None

    def get_og_tags(self, url: str) -> t.Tuple[t.Optional[str], t.Optional[str]]:
        response = httpx.get(url)
        response.raise_for_status()

        og_tags = self._META_PATTERN.findall(response.text)

        og_image = self._get_og_tag_value(og_tags, 'og:image')
        og_title = self._get_og_tag_value(og_tags, 'og:title')

        return og_image, og_title

    def get_today_word(self):

        current_day = datetime.now().day
        current_month = datetime.now().month
        current_year = datetime.now().year

        page_name = f"Modèle:Entrée du jour/{current_year}/{current_month:02d}/{current_day:02d}"
        page_name = f"Modèle:Entrée étrangère du jour/{current_year}/{current_month:02d}/{current_day:02d}"
        logger.info(f"Page_name is {page_name}")
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

            logger.info(f"page_id is {page_id}")
            logger.info(f"data[query][pages][page_id] is {data["query"]["pages"][page_id]}")

            if page_id == "-1" or "extract" not in data["query"]["pages"][page_id]:
                # fallback
                logger.info(f"Fail to found a page, look at 2021")

                page_name = f"Modèle:Entrée étrangère du jour/2021/{current_month:02d}/{current_day:02d}"
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

                logger.info(f"page_name is <{page_name}>")
                return page_name

        except Exception as e:
            logger.error(f"Error fetching random word: {e}")
            time.sleep(2)  # Wait before retrying

        logger.error("Failed to get a suitable random word after multiple attempts")
        return None

    def run(self):
        """Main method to run the bot"""
        logger.info("Starting Wiktionary Bluesky Bot")

        try:
            # Connect to Bluesky
            if not self.connect_to_bluesky():
                return False



            word_data = self.get_word_data(self.get_today_word())
            if not word_data:
                logger.error("Failed to get word data")
                return False


            # # Post to Bluesky
            # success = self.post_to_bluesky(word_data)
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            return False

if __name__ == "__main__":
    bot = WiktionayStranger()
    bot.run()