"""Пересобрать интерактивную карту после изменения content.py: python build_map.py."""
import json
from pathlib import Path
from content import PLACES, ROUTES, map_url

def build():
    data = {k:{**p, 'map_url':map_url(p)} for k,p in PLACES.items()}
    template = (Path(__file__).parent/'map_template.html').read_text(encoding='utf-8')
    # Данные в script не должны содержать закрывающий HTML тег.
    text = template.replace('__PLACES__',json.dumps(data,ensure_ascii=False).replace('<','\\u003c'))
    text = text.replace('__ROUTES__',json.dumps(ROUTES,ensure_ascii=False).replace('<','\\u003c'))
    (Path(__file__).parent/'map.html').write_text(text,encoding='utf-8')

if __name__=='__main__': build()
