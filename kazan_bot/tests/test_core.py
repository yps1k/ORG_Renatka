import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from content import PLACES, ROUTES, route_url
from storage import Store

class ContentTests(unittest.TestCase):
    def test_routes_reference_existing_distinct_places(self):
        self.assertGreaterEqual(len(ROUTES['heritage']['stops']),10)
        for route in ROUTES.values():
            keys=[key for _,key in route['stops']]
            self.assertEqual(len(keys),len(set(keys)))
            for key in keys:
                self.assertIn(key,PLACES)
                self.assertLessEqual(len(('reviews:'+key).encode()),64)
            parsed=parse_qs(urlsplit(route_url(route)).query)
            self.assertEqual(len(parsed['rtext'][0].split('~')),len(keys))

    def test_coordinates_and_content(self):
        for p in PLACES.values():
            self.assertTrue(55.7 < p['lat'] < 55.9)
            self.assertTrue(49.0 < p['lon'] < 49.3)
            self.assertTrue(p['description'] and p['tip'] and p['wiki'])
            self.assertTrue(p['source'].startswith('https://'))

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'test.db'
        self.store=Store(self.path)
    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()
    def test_favorites_persist_and_toggle(self):
        self.assertTrue(self.store.toggle(1,'kremlin'))
        self.store.db.close()
        self.store=Store(self.path)
        self.assertEqual(self.store.favorites(1),['kremlin'])
        self.assertEqual(self.store.favorites(2),[])
        self.assertFalse(self.store.toggle(1,'kremlin'))
    def test_moderation_and_replace(self):
        old=self.store.add_review(1,'kremlin',5,'Отлично!')
        self.assertEqual(self.store.rating('kremlin'),(None,0))
        self.store.moderate(old,True)
        self.assertEqual(self.store.rating('kremlin'),(5.0,1))
        new=self.store.add_review(1,'kremlin',3,'Новый отзыв')
        self.assertNotEqual(old,new)
        self.store.moderate(old,True)
        self.assertEqual(self.store.rating('kremlin'),(None,0))
        self.store.moderate(new,True)
        self.assertEqual(self.store.rating('kremlin'),(3.0,1))
    def test_delete_only_own_data(self):
        self.store.toggle(1,'kremlin');self.store.toggle(2,'kremlin')
        self.store.add_review(1,'kremlin',4,'Прекрасно')
        self.store.add_review(2,'kremlin',5,'Очень хорошо')
        self.store.delete_user(1)
        self.assertEqual(self.store.favorites(1),[])
        self.assertEqual(self.store.favorites(2),['kremlin'])
        self.assertEqual(len(self.store.pending()),1)

if __name__=='__main__':unittest.main()
