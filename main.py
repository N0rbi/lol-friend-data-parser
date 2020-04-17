from riotwatcher import LolWatcher, ApiError
import pandas as pd
import argparse
from tqdm import tqdm
import collections
import urllib
import json
import os
import datetime

latest_ddragon = json.loads(urllib.request.urlopen("https://ddragon.leagueoflegends.com/api/versions.json").read())[0]


def flatten(d, parent_key='', sep='_'):
    items = []
    for k, v in d.items():
        new_key = parent_key + sep + k if parent_key else k
        if isinstance(v, collections.MutableMapping):
            items.extend(flatten(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

parser = argparse.ArgumentParser("""Riot games data parser for you and your friends""")
parser.add_argument('--api-key', type=str, required=True)
parser.add_argument('--region', type=str,
                    choices=['br1', 'eun1', 'euw1', 'jp1', 'kr', 'la1', 'la2', 'na1', 'oc1', 'tr1', 'ru'],
                    required=True)
parser.add_argument('--my-summoner-name', type=str, required=True)
parser.add_argument('--my-friends', type=str, nargs="+", required=True)
parser.add_argument('--max-match-count', type=int, default=50)

args = parser.parse_args()

api_key = args.api_key
watcher = LolWatcher(api_key)
my_region = args.region
me = args.my_summoner_name
my_friends = args.my_friends
max_match = args.max_match_count

ddragon_kwargs = {"version": latest_ddragon, "locale": "en_US"}
champs = watcher.data_dragon.champions(**ddragon_kwargs)
items = watcher.data_dragon.items(**ddragon_kwargs)
summoner_spells = watcher.data_dragon.summoner_spells(**ddragon_kwargs)


my_data = watcher.summoner.by_name(my_region, me)
my_matches = watcher.match.matchlist_by_account(my_region, my_data['accountId'])

user_data = []
match_data = []

for match, _ in tqdm(list(zip(my_matches['matches'], range(max_match)))):
    match_detail = watcher.match.by_id(my_region, match['gameId'])
    match_timeline = watcher.match.timeline_by_match(my_region, match['gameId'])
    id2sum = {partId['participantId']: partId['player']['summonerName']
              for partId in match_detail['participantIdentities'] if partId['player']['summonerName'] in my_friends + [me]}

    if len(id2sum) == 1:
        # this is a game where non of my friends played
        continue
    teamid2win = {team['teamId']: team['win'] == "Win" for team in match_detail['teams']}
    for player in match_detail['participants']:
        if player['participantId'] in id2sum.keys():
            player['summonerName'] = id2sum[player['participantId']]
            player['match_id'] = match['gameId']
            player['win'] = teamid2win[player['teamId']]
            for k, v in player['stats'].items():
                player[k] = v
            del player['stats']
            for k, v in flatten(player, parent_key='timeline', sep='.').items():
                player[k] = v
            del player['timeline']
            user_data.append(player)

    my_team_id = user_data[-1]['teamId']
    current_match_data = {}
    for team in match_detail['teams']:
        prefix='ally_' if team['teamId'] == my_team_id else 'enemy_'
        for key, value in team.items():
            current_match_data[prefix + key] = value

        match_data.append(current_match_data)

user_df = pd.DataFrame.from_dict(user_data)
match_df = pd.DataFrame.from_dict(match_data)


id2champ = {data['key']: data['id'] for data in champs['data'].values()}
id2item = {k: v['name'] for k,v in items['data'].items()}
id2spell = {data['key']: data['name'] for data in summoner_spells['data'].values()}


user_df['ChampName'] = user_df['championId'].apply(lambda champId: id2champ[str(champId)])
spell_cols = [col for col in user_data[0].keys() if "spell" in col]

for spell_col in spell_cols:
    new_col = spell_col.replace("Id", "Name")
    user_df[new_col] = user_df[spell_col].apply(lambda spellId: id2spell[str(spellId)])

item_cols = [col for col in user_data[0].keys() if "item" in col]

for item_col in item_cols:
    new_col = item_col + "Name"
    user_df[new_col] = user_df[item_col].apply(lambda itemId: id2item[str(itemId)] if itemId != 0 else "Empty Item Slot")

if not os.path.exists("output"):
    os.mkdir("output")

output_dir = os.path.join("output", str(datetime.datetime.now())).replace(":", "..")

os.mkdir(output_dir)

with open(os.path.join(output_dir, "args.json"), "w") as args_file:

    json.dump(vars(args), args_file)

user_df.to_csv(os.path.join(output_dir, "user_data.csv"), sep=";")
match_df.to_csv(os.path.join(output_dir, "match_data.csv"), sep=";")