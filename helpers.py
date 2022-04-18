import datetime
import os
import time
from typing import List

import psycopg2
import requests


table = os.getenv("TABLE", "steam")
api_key = os.getenv("API_KEY")


class Database:
    def __init__(self, database=table):
        self.connection = psycopg2.connect("dbname=postgres user=postgres host=localhost port=5432 password=hui1205")
        self.connection.autocommit = True
        self.cursor = self.connection.cursor()

    def insert_listing(self, lst):
        avatar = parse_hash_from_link(lst.owner_avatar)
        self.cursor.execute(
            "INSERT INTO listings(game, item_name, time, price, owner_name, owner_avatar) "
            f"VALUES ({lst.game}, %s, now(), {lst.price}, %s, '{avatar}')"
            " ON CONFLICT DO NOTHING", (lst.item_name, lst.owner_name)
        )
        if self.cursor.rowcount:
            print(f"{datetime.datetime.now()} {lst.game: <5} {lst.item_name: <60} ${lst.price: <4} {lst.owner_name}")

    def get_profiles(self, avatar: str):
        self.cursor.execute(f"SELECT * FROM users WHERE avatar = '{avatar}' LIMIT 5001")  # 1 more than 5000. see app.py
        return [row[0] for row in self.cursor.fetchall()]

    def get_listings(self, games, minprice=0, maxprice=-1, limit=500):
        game_conditions = [f"game = {game}" for game in games]
        conditions = [
            f"({' OR '.join(game_conditions)})",
            f" price > {minprice} ",
            f" price < {maxprice} " if maxprice != -1 else "true",
        ]
        self.cursor.execute(f"SELECT * FROM listings WHERE {' AND '.join(conditions)} ORDER BY id DESC LIMIT {limit}")

        out = []
        for row in self.cursor.fetchall():
            listing = Listing(
                game=row[1],
                item_name=row[2],
                time=row[3],
                price=row[4],
                owner_name=row[5],
                owner_avatar=row[6]
            )
            out.append(listing)
        return out

    def insert_profiles(self, summaries: List):
        if len(summaries) == 0:
            return

        values = [f"({summary['steamid']}, '{parse_hash_from_link(summary['avatar'])}')" for summary in summaries]
        query = f"INSERT INTO users(steam64id, avatar) VALUES {','.join(values)}" \
                " ON CONFLICT(steam64id) DO UPDATE SET avatar = excluded.avatar"
        self.cursor.execute(query)


# @dataclass  # not supported in 3.6, no fucking way i'm messing with python on ubuntu
class Listing:
    game: int
    item_name: str
    time: str
    price: int
    owner_name: str
    owner_avatar: str

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def __str__(self):
        return f"{self.item_name} {self.price} {self.owner_name}"


ALL_ITEMS_API_URL = "https://steamcommunity.com/market/search/render/" \
      "?query=&appid={game}&start={start}&count=100&sort_column=price&sort_dir=desc&search_descriptions=0&norender=1"

ITEM_URL = "https://steamcommunity.com/market/listings/{game}/{name}"

PLAYER_SUMMARIES_URL = "http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/"\
                       "?key={api_key}&steamids={steamids}"

HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/84.0.4147.135 Safari/537.36"
}


def parse_hash_from_link(link):
    return link.split('/avatars/')[1].split('.')[0]


def get_all_market_items(game, start):
    return requests.get(ALL_ITEMS_API_URL.format(game=game, start=start)).json()


def parse_price(string):
    return int(string[1:].replace(",", "").split('.')[0])


def collect_item_urls(game, start=0, price_threshold=0):
    total_count = get_all_market_items(game, 0)["total_count"]

    for start in range(start, total_count, 100):
        print(start)
        resp = get_all_market_items(game, start)
        if resp is None:
            time.sleep(10)
            continue

        for obj in resp["results"]:
            if parse_price(obj["sell_price_text"]) >= price_threshold:
                yield ITEM_URL.format(game=game, name=obj["name"])
        time.sleep(5)


def parse_id(listing_url, **kwargs):
    resp = requests.get(listing_url, headers=HEADERS, **kwargs).content.decode()
    return resp.split('Market_LoadOrderSpread( ')[1].split(' )')[0]


def get_player_summaries(steamids, timeout=3):
    steamids = [str(i) for i in steamids]
    players = []
    for index in range(0, len(steamids), 100):
        url = PLAYER_SUMMARIES_URL.format(api_key=api_key, steamids=','.join(steamids[index:index+100]))
        players += requests.get(url, timeout=timeout).json()["response"]["players"]
    return players
