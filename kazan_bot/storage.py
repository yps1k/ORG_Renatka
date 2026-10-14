"""SQLite: один отзыв на пользователя и место; публикация после модерации."""
import sqlite3
from pathlib import Path

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS favorites(user INTEGER, place TEXT, PRIMARY KEY(user,place));
        CREATE TABLE IF NOT EXISTS reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT, user INTEGER, place TEXT, stars INTEGER CHECK(stars BETWEEN 1 AND 5),
            text TEXT, approved INTEGER DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user,place));
        ''')
        self.db.commit()

    def toggle(self, user, place):
        exists = self.db.execute('SELECT 1 FROM favorites WHERE user=? AND place=?',(user,place)).fetchone()
        if exists:
            self.db.execute('DELETE FROM favorites WHERE user=? AND place=?',(user,place))
        else:
            self.db.execute('INSERT INTO favorites VALUES (?,?)',(user,place))
        self.db.commit()
        return not bool(exists)

    def favorites(self, user):
        return [r[0] for r in self.db.execute('SELECT place FROM favorites WHERE user=? ORDER BY place',(user,))]

    def add_review(self, user, place, stars, text):
        self.db.execute('DELETE FROM reviews WHERE user=? AND place=?',(user,place))
        cursor = self.db.execute('INSERT INTO reviews(user,place,stars,text) VALUES (?,?,?,?)',
                                 (user,place,stars,text))
        self.db.commit()
        return cursor.lastrowid

    def reviews(self, place):
        return self.db.execute('SELECT stars,text,created FROM reviews WHERE place=? AND approved=1 ORDER BY created DESC LIMIT 5',(place,)).fetchall()

    def rating(self, place):
        return self.db.execute('SELECT AVG(stars),COUNT(*) FROM reviews WHERE place=? AND approved=1',(place,)).fetchone()

    def pending(self):
        return self.db.execute('SELECT id,place,stars,text FROM reviews WHERE approved=0 ORDER BY created LIMIT 20').fetchall()

    def moderate(self, review_id, approve):
        if approve:
            self.db.execute('UPDATE reviews SET approved=1 WHERE id=?',(review_id,))
        else:
            self.db.execute('DELETE FROM reviews WHERE id=?',(review_id,))
        self.db.commit()

    def delete_user(self, user):
        for table in ('favorites','reviews'):
            self.db.execute(f'DELETE FROM {table} WHERE user=?',(user,))
        self.db.commit()
