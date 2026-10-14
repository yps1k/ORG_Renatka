"""Изображения Wikipedia/Wikimedia с автором, лицензией и страницей файла.

Локальные фото имеют приоритет: photos/<place_id>.jpg + photo_credits.json.
Ошибки внешнего сервиса не блокируют текстовую карточку.
"""
import asyncio
import json
import logging
import re
import time
from html import unescape
from urllib.parse import quote

import aiohttp

def plain(value):
    return unescape(re.sub('<[^>]+>', '', value or '')).strip()

class Photos:
    def __init__(self, root, session):
        self.root, self.session = root, session
        self.cache = {}
        self.locks = {}
        path = root / 'photo_credits.json'
        self.credits = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}

    async def get(self, key, title):
        local = self.root / 'photos' / f'{key}.jpg'
        if local.exists() and key in self.credits:
            return local.read_bytes(), self.credits[key]
        async with self.locks.setdefault(key, asyncio.Lock()):
            cached = self.cache.get(key)
            if cached and time.monotonic()-cached[0] < (3600 if cached[1] else 60):
                return cached[1]
            result = None
            try:
                result = await self.fetch(title)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError, StopIteration):
                logging.warning('Фото временно недоступно для %s', key)
            self.cache[key] = time.monotonic(), result
            return result

    async def query(self, **params):
        async with self.session.get('https://ru.wikipedia.org/w/api.php',
                                    params={'action':'query','format':'json', **params}) as response:
            response.raise_for_status()
            return await response.json()

    async def fetch(self, title):
        result = await self.query(titles=title, prop='pageimages', piprop='thumbnail|name',
                                  pithumbsize='1000', redirects='1')
        page = next(iter(result.get('query', {}).get('pages', {}).values()), {})
        if not page.get('thumbnail') or not page.get('pageimage'):
            return None
        info = await self.query(titles='File:'+page['pageimage'], prop='imageinfo',
                                iiprop='url|extmetadata')
        file_page = next(iter(info.get('query', {}).get('pages', {}).values()), {})
        image_info = file_page.get('imageinfo', [{}])[0]
        meta = image_info.get('extmetadata', {})
        credit = {'author':plain(meta.get('Artist',{}).get('value','')),
                  'license':plain(meta.get('LicenseShortName',{}).get('value','')),
                  'url':image_info.get('descriptionurl','https://commons.wikimedia.org/wiki/File:'+quote(page['pageimage']))}
        # Не публикуем изображение без метаданных лицензии и авторства.
        if not credit['license'] or not credit['author']:
            return None
        async with self.session.get(page['thumbnail']['source']) as response:
            response.raise_for_status()
            if not response.headers.get('Content-Type','').startswith('image/'):
                return None
            data = await response.content.read(8*1024*1024+1)
            if len(data) > 8*1024*1024:
                return None
        return data, credit
